import asyncio
import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    # รองรับการรันแบบโมดูล (python -m src.main) และรันตรงจากรากโปรเจ็กต์
    from adapters.vts.vts_client import VTSClient
except ModuleNotFoundError:
    # หากรันเป็นโมดูลไม่สำเร็จ ลองนำเข้าแบบมี prefix แพ็กเกจ src
    from src.adapters.vts.vts_client import VTSClient
try:
    from core.config import get_settings
except ModuleNotFoundError:
    from src.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def run_vts_demo(duration_sec: float = 25.0):
    # ใช้ค่า settings จาก .env ผ่าน Config เพื่อให้เดโมสะท้อนการตั้งค่าการเคลื่อนไหว
    settings = get_settings()
    host = settings.VTS_HOST
    port = settings.VTS_PORT
    plugin_name = settings.VTS_PLUGIN_NAME or os.getenv("VTS_PLUGIN_NAME", "AI VTuber Demo")

    client = VTSClient(plugin_name=plugin_name, plugin_developer="VIoneyy", host=host, port=port, config=settings)

    try:
        ok = await client.connect()
        if not ok:
            logger.error("❌ เชื่อมต่อกับ VTube Studio ไม่สำเร็จ")
            return

        await client.verify_connection()
        logger.info("🎯 พารามิเตอร์ที่มีอยู่: %d", len(client.available_parameters))
        logger.info("🎯 ฮ็อตคีย์ทั้งหมด: %d", len(client.available_hotkeys))

        # โหลดและใช้ style profile + บันทึกสแน็ปช็อตการตั้งค่า
        try:
            client.apply_style_profile_from_config()
        except Exception:
            pass

        # โหมดสุ่มเหตุการณ์แบบต่อเนื่อง: ไม่มีเวลาจำกัด (จนกว่าจะสั่งหยุด)
        if getattr(settings, "VTS_RANDOM_EVENTS_CONTINUOUS", False):
            logger.info("🎬 ใช้ neuro-random events (continuous, no time limit)")
            await client.start_neuro_random_events()
            # หากกำหนดระยะเวลาเป็น 0 หรือค่าติดลบ ให้รันไปเรื่อย ๆ จนกดหยุด
            run_sec = float(getattr(settings, "VTS_PRESET_DURATION_SEC", 0.0))
            if run_sec <= 0:
                try:
                    # รันไปเรื่อย ๆ จนผู้ใช้หยุดโปรเซสเอง
                    while True:
                        await asyncio.sleep(60)
                except asyncio.CancelledError:
                    pass
            else:
                await asyncio.sleep(run_sec)
            await client.stop_neuro_random_events()
            return

        # โหมดสุ่มเหตุการณ์ระยะเวลาคงที่: เล่นเป็นคลิปสั้น ๆ
        if getattr(settings, "VTS_RANDOM_EVENTS_PRESET", False):
            # ใช้ระยะเวลาจาก settings หากตั้งค่าไว้
            duration_override = float(getattr(settings, "VTS_PRESET_DURATION_SEC", duration_sec)) or duration_sec
            logger.info("🎬 ใช้ neuro-random events preset (fixed duration) ~%.1f วินาที", duration_override)
            await client.play_neuro_random_events(duration_sec=duration_override)
            return

        # โหมดสคริปต์: เล่นพรีเซ็ต Neuro แบบไม่ใช้ motion loop
        if getattr(settings, "VTS_SCRIPTED_PRESET", False):
            logger.info("🎬 ใช้ scripted Neuro preset (no motion loop) ความยาว ~%.1f วินาที", duration_sec)
            await client.play_neuro_clip_preset(duration_sec=duration_sec)
            return

        # ปิดการเริ่ม motion ทั้งหมดตามคำสั่งผู้ใช้ — ไม่เรียก start_random_motion หรือ start_continuous_natural_motion
        logger.info("⏸️ ข้ามการเริ่ม motion ทั้งหมดตามคำสั่งผู้ใช้")
        # แสดงอีโมททันทีเพื่อให้เห็นการตอบสนองชัดเจน (ถ้ามี hotkey)
        try:
            import os as _os
            _hk = _os.getenv("VTS_HOTKEY_ON_CONNECT", "happy")
            if _os.getenv("VTS_ENABLE_AUTOHOTKEY", "0") == "1":
                await client.trigger_hotkey_by_name(_hk)
        except Exception:
            pass
        # ไม่มีการเริ่ม motion จึงไม่ต้องหยุด
        # สร้างการขยับหลายแกนตามการตั้งค่าที่คุณส่ง
        try:
            import math, time as _time, os as _os
            present = set(client.available_parameters or [])
            # หากปิด motion ทั้งหมด ให้ข้ามการฉีดพารามิเตอร์และอยู่เฉย ๆ
            if getattr(settings, "VTS_DISABLE_ALL_MOTION", False):
                logger.info("🔒 ข้ามการฉีดพารามิเตอร์ทั้งหมด (multi-sway/eyes/mouth) — VTS_DISABLE_ALL_MOTION=1")
                await asyncio.Event().wait()
                return
            # helper: เลือกชื่อพารามิเตอร์ตัวแรกที่มีอยู่จริง (Input ก่อน Output)
            def pick(*names):
                for nm in names:
                    if nm in present:
                        return nm
                return None
            # ช่องมุม/องศา และการมองตา/กาย: ใช้ Input เป็นหลักตาม mapping ใน VTS
            channels = []
            _ax = pick("BodyAngleX", "FaceAngleX", "ParamAngleX", "ParamBodyAngleX")
            _ay = pick("BodyAngleY", "FaceAngleY", "ParamAngleY", "ParamBodyAngleY")
            _az = pick("BodyAngleZ", "FaceAngleZ", "ParamAngleZ", "ParamBodyAngleZ")
            if _ax:
                channels.append({"name": _ax, "amp_env": "VTS_SWAY_PARAMANGLEX_AMPLITUDE", "freq_env": "VTS_SWAY_PARAMANGLEX_FREQUENCY", "amp": 30.0, "freq": 0.5, "phase": 0.0, "limit": (-30.0, 30.0)})
            if _ay:
                channels.append({"name": _ay, "amp_env": "VTS_SWAY_PARAMANGLEY_AMPLITUDE", "freq_env": "VTS_SWAY_PARAMANGLEY_FREQUENCY", "amp": 20.0, "freq": 0.4, "phase": math.pi/2, "limit": (-30.0, 30.0)})
            if _az:
                channels.append({"name": _az, "amp_env": "VTS_SWAY_PARAMANGLEZ_AMPLITUDE", "freq_env": "VTS_SWAY_PARAMANGLEZ_FREQUENCY", "amp": 30.0, "freq": 0.6, "phase": math.pi, "limit": (-30.0, 30.0)})
            # เพิ่มการเลื่อนหน้าซ้าย-ขวา/บน-ล่าง ถ้ามี FacePosition*
            _posx = pick("FacePositionX")
            _posy = pick("FacePositionY")
            if _posx:
                channels.append({"name": _posx, "amp_env": "VTS_SWAY_FACEPOSITIONX_AMPLITUDE", "freq_env": "VTS_SWAY_FACEPOSITIONX_FREQUENCY", "amp": 0.4, "freq": 0.12, "phase": 0.0, "limit": (-1.0, 1.0)})
            if _posy:
                channels.append({"name": _posy, "amp_env": "VTS_SWAY_FACEPOSITIONY_AMPLITUDE", "freq_env": "VTS_SWAY_FACEPOSITIONY_FREQUENCY", "amp": 0.3, "freq": 0.10, "phase": math.pi/2, "limit": (-1.0, 1.0)})
            _step = pick("Step", "ParamStep")
            if _step:
                channels.append({"name": _step, "amp_env": "VTS_SWAY_PARAMSTEP_AMPLITUDE", "freq_env": "VTS_SWAY_PARAMSTEP_FREQUENCY", "amp": 10.0, "freq": 0.5, "phase": 0.0, "limit": (-10.0, 10.0)})
            # ลูกตา: ขับซ้าย/ขวาแยกกันถ้ามี
            _eyeLX = pick("EyeLeftX", "ParamEyeBallX")
            _eyeRX = pick("EyeRightX", "ParamEyeBallX")
            _eyeLY = pick("EyeLeftY", "ParamEyeBallY")
            _eyeRY = pick("EyeRightY", "ParamEyeBallY")
            for nm, freq, phase in [( _eyeLX, 0.25, 0.0 ), ( _eyeRX, 0.28, math.pi/4 ), ( _eyeLY, 0.30, math.pi/3 ), ( _eyeRY, 0.32, -math.pi/3 )]:
                if nm:
                    channels.append({"name": nm, "amp_env": "VTS_SWAY_EYEBALL_AMPLITUDE", "freq_env": "VTS_SWAY_EYEBALL_FREQUENCY", "amp": 0.7, "freq": freq, "phase": phase, "limit": (-1.0, 1.0)})
            # กรองเฉพาะช่องที่โมเดลมีจริง และอ่านค่า ENV ถ้ามี
            active = []
            for ch in channels:
                ch["amp"] = float(_os.getenv(ch["amp_env"], str(ch["amp"])) )
                ch["freq"] = float(_os.getenv(ch["freq_env"], str(ch["freq"])) )
                active.append(ch)
            # ถ้า random motion ของ VTSClient ทำงานอยู่ ให้หลีกเลี่ยงการเขียนทับหัว/ตัว/ตำแหน่งหน้า
            # เพื่อกันการชนกันของสองลูปซึ่งเป็นสาเหตุหลักของการสั่น
            try:
                if getattr(client, "motion_enabled", False):
                    conflict_names = {
                        "FaceAngleX", "FaceAngleY", "FaceAngleZ",
                        "BodyAngleX", "BodyAngleY", "BodyAngleZ",
                        "FacePositionX", "FacePositionY",
                    }
                    before = ", ".join(ch["name"] for ch in active)
                    active = [ch for ch in active if ch["name"] not in conflict_names]
                    after = ", ".join(ch["name"] for ch in active)
                    if before != after:
                        logger.info("🛡️ กำลังรัน random motion อยู่ — กรองช่องที่ชนกันออก: %s", after or "(none)")
            except Exception:
                pass
            # หายใจ: ใช้ชื่อ Input ก่อน เช่น Breath
            _breath_name = pick("Breath", "ParamBreath")
            breath_enable = bool(_breath_name)
            breath_freq = float(_os.getenv("VTS_BREATH_FREQUENCY", "0.2"))
            breath_amp = float(_os.getenv("VTS_BREATH_AMPLITUDE", "0.4"))  # 0..1
            # กระพริบตาซ้าย/ขวา: ใช้ EyeOpenLeft/Right ก่อน และรองรับ EyeClose* เป็น fallback
            _eyeL_open = pick("EyeOpenLeft", "ParamEyeLOpen")
            _eyeL_close = pick("EyeCloseLeft", "ParamEyeLClose")
            _eyeR_open = pick("EyeOpenRight", "ParamEyeROpen")
            _eyeR_close = pick("EyeCloseRight", "ParamEyeRClose")
            eyeL_enable = bool(_eyeL_open or _eyeL_close)
            eyeL_freq = float(_os.getenv("VTS_EYE_L_FREQUENCY", "0.25"))
            eyeL_hold_ms = float(_os.getenv("VTS_EYE_L_HOLD_MS", "250"))
            eyeR_enable = bool(_eyeR_open or _eyeR_close)
            eyeR_freq = float(_os.getenv("VTS_EYE_R_FREQUENCY", "0.25"))
            eyeR_hold_ms = float(_os.getenv("VTS_EYE_R_HOLD_MS", "250"))
            eyeL_duty = float(_os.getenv("VTS_EYE_L_DUTY", "0.15"))
            eyeR_duty = float(_os.getenv("VTS_EYE_R_DUTY", "0.15"))
            # ยิ้มตา: ไม่มี default เสมอไป — ใช้ Param* ถ้ามี
            _eyeLS = pick("ParamEyeLSmile")
            _eyeRS = pick("ParamEyeRSmile")
            eyeLS_enable = bool(_eyeLS)
            eyeLS_freq = float(_os.getenv("VTS_EYE_L_SMILE_FREQUENCY", "0.20"))
            eyeLS_amp = float(_os.getenv("VTS_EYE_L_SMILE_AMPLITUDE", "0.6"))
            eyeRS_enable = bool(_eyeRS)
            eyeRS_freq = float(_os.getenv("VTS_EYE_R_SMILE_FREQUENCY", "0.20"))
            eyeRS_amp = float(_os.getenv("VTS_EYE_R_SMILE_AMPLITUDE", "0.6"))
            # คิ้ว: ใช้ BrowLeft*/Right* เป็นหลัก
            _browLY = pick("BrowLeftY", "ParamBrowLY")
            _browRY = pick("BrowRightY", "ParamBrowRY")
            _browLF = pick("BrowLeftForm", "ParamBrowLForm")
            _browRF = pick("BrowRightForm", "ParamBrowRForm")
            browL_enable = bool(_browLY)
            browR_enable = bool(_browRY)
            browLF_enable = bool(_browLF)
            browRF_enable = bool(_browRF)
            brow_freq = float(_os.getenv("VTS_BROW_FREQUENCY", "0.25"))
            brow_amp = float(_os.getenv("VTS_BROW_AMPLITUDE", "0.6"))
            # ปาก: ใช้ Input ก่อน (MouthX, MouthOpen, MouthSmile)
            _mouthX = pick("MouthX", "ParamMouthX")
            _mouthOpen = pick("MouthOpen", "ParamMouthOpenY")
            _mouthForm = pick("MouthSmile", "ParamMouthForm")
            mouthForm_enable = bool(_mouthForm)
            mouthForm_freq = float(_os.getenv("VTS_MOUTH_FORM_FREQUENCY", "0.20"))
            mouthForm_amp = float(_os.getenv("VTS_MOUTH_FORM_AMPLITUDE", "0.8"))
            # ปิดการอ้าปากในโหมด idle โดยค่าเริ่มต้น (เปิดเฉพาะตอนพูด/อีโมท)
            # เปิดได้ด้วย ENV: VTS_ENABLE_IDLE_MOUTH_OPEN=1
            mouthOpen_enable = bool(_mouthOpen) and os.getenv("VTS_ENABLE_IDLE_MOUTH_OPEN", "0") == "1"
            mouthOpen_freq = float(_os.getenv("VTS_MOUTH_OPEN_FREQUENCY", "0.18"))
            mouthOpen_amp = float(_os.getenv("VTS_MOUTH_OPEN_AMPLITUDE", "0.7"))
            mouthX_enable = bool(_mouthX)
            mouthX_freq = float(_os.getenv("VTS_MOUTH_X_FREQUENCY", "0.35"))
            mouthX_amp = float(_os.getenv("VTS_MOUTH_X_AMPLITUDE", "0.8"))
            # เพิ่มสวิตช์ปิดลูป multi-sway ที่ override พารามิเตอร์ (default ปิด)
            # เปิดได้ด้วย ENV: VTS_ENABLE_INPUT_LOOP=1
            enable_input_loop = os.getenv("VTS_ENABLE_INPUT_LOOP", "0") == "1"
            if enable_input_loop and (active or breath_enable or eyeL_enable or eyeR_enable or eyeLS_enable or eyeRS_enable or browL_enable or browR_enable or browLF_enable or browRF_enable or mouthForm_enable or mouthOpen_enable or mouthX_enable):
                # ลดความเร็วอัปเดตเพื่อให้การขยับดูช้าลง
                tick = 1.0/20.0
                start = _time.perf_counter()

                # ทำงานต่อเนื่องจนกว่าจะหยุดโปรเซส
                names = ", ".join(ch["name"] for ch in active)
                if names:
                    logger.info(f"🌊 เริ่ม multi-sway บน (Input-first): {names}")
                if breath_enable:
                    logger.info(f"💨 เปิดการหายใจบน {_breath_name}")
                if eyeL_enable or eyeR_enable:
                    logger.info("👁️ เปิดกระพริบตา EyeOpenLeft/Right หรือ ParamEyeL/R")
                if eyeLS_enable or eyeRS_enable:
                    logger.info("😊 เปิดยิ้มตา ParamEyeLSmile/ParamEyeRSmile")
                if browL_enable or browR_enable or browLF_enable or browRF_enable:
                    logger.info("🪄 เปิดคิ้ว BrowLeft/RightY, BrowLeft/RightForm")
                if mouthForm_enable or mouthOpen_enable or mouthX_enable:
                    logger.info("👄 เปิดปาก MouthSmile/Open/X (Input-first)")
                    if not mouthOpen_enable:
                        logger.info("   ⚠️ ปิด MouthOpen ใน idle (เปิดเฉพาะตอนพูด/อีโมท)")

                while True:
                    t = _time.perf_counter() - start
                    try:
                        # องศา/ลูกตา/ตำแหน่งหน้า
                        for ch in active:
                            val = ch["amp"] * math.sin(2.0 * math.pi * ch["freq"] * t + ch["phase"]) 
                            lo, hi = ch["limit"]
                            if val < lo: val = lo
                            if val > hi: val = hi
                            await client.set_parameter_value(ch["name"], val)
                        # หายใจ
                        if breath_enable:
                            bval = 0.5 + breath_amp * math.sin(2.0 * math.pi * breath_freq * t)
                            bval = min(1.0, max(0.0, bval))
                            await client.set_parameter_value(_breath_name, bval)
                        # กระพริบตาซ้าย/ขวา: hold ปิดตานานขึ้น และรองรับ EyeClose* เป็น fallback
                        if eyeL_enable:
                            periodL = 1.0 / eyeL_freq
                            closed_windowL = min(periodL * 0.9, eyeL_hold_ms / 1000.0)
                            phaseL = t % periodL
                            closedL = phaseL < closed_windowL
                            if _eyeL_open:
                                await client.set_parameter_value(_eyeL_open, 0.0 if closedL else 1.0)
                            elif _eyeL_close:
                                await client.set_parameter_value(_eyeL_close, 1.0 if closedL else 0.0)
                        if eyeR_enable:
                            periodR = 1.0 / eyeR_freq
                            closed_windowR = min(periodR * 0.9, eyeR_hold_ms / 1000.0)
                            phaseR = t % periodR
                            closedR = phaseR < closed_windowR
                            if _eyeR_open:
                                await client.set_parameter_value(_eyeR_open, 0.0 if closedR else 1.0) 
                            elif _eyeR_close:
                                await client.set_parameter_value(_eyeR_close, 1.0 if closedR else 0.0)
                        # ยิ้มตา (soft pulse)
                        if eyeLS_enable:
                            ls = eyeLS_amp * 0.5 + eyeLS_amp * 0.5 * (1.0 + math.sin(2.0 * math.pi * eyeLS_freq * t - math.pi/6))
                            ls = min(1.0, max(0.0, ls))
                            await client.set_parameter_value(_eyeLS, ls)
                        if eyeRS_enable:
                            rs = eyeRS_amp * 0.5 + eyeRS_amp * 0.5 * (1.0 + math.sin(2.0 * math.pi * eyeRS_freq * t + math.pi/6))
                            rs = min(1.0, max(0.0, rs))
                            await client.set_parameter_value(_eyeRS, rs)
                        # คิ้วยก/รูปทรง (ซ้ายขวาสวนเฟสเล็กน้อย)
                        if browL_enable:
                            bly = brow_amp * 0.5 + brow_amp * 0.5 * (1.0 + math.sin(2.0 * math.pi * brow_freq * t))
                            await client.set_parameter_value(_browLY, min(1.0, max(0.0, bly)))
                        if browR_enable:
                            bry = brow_amp * 0.5 + brow_amp * 0.5 * (1.0 + math.sin(2.0 * math.pi * brow_freq * t + math.pi/4))
                            await client.set_parameter_value(_browRY, min(1.0, max(0.0, bry)))
                        if browLF_enable:
                            blf = brow_amp * 0.5 + brow_amp * 0.5 * (1.0 + math.sin(2.0 * math.pi * brow_freq * t + math.pi/3))
                            await client.set_parameter_value(_browLF, min(1.0, max(0.0, blf)))
                        if browRF_enable:
                            brf = brow_amp * 0.5 + brow_amp * 0.5 * (1.0 + math.sin(2.0 * math.pi * brow_freq * t + 2*math.pi/3))
                            await client.set_parameter_value(_browRF, min(1.0, max(0.0, brf)))
                        # ปาก: ยิ้ม/เปิด/แกว่ง X
                        if mouthForm_enable:
                            # ลดความแรงของยิ้มในลูป input เพื่อหลีกเลี่ยงชนกับ VTSClient
                            mf = (mouthForm_amp * 0.25) + (mouthForm_amp * 0.25) * (1.0 + math.sin(2.0 * math.pi * mouthForm_freq * 0.6 * t))
                            await client.set_parameter_value(_mouthForm, min(1.0, max(0.0, mf)))
                        # ปิดการอ้าปากใน idle — เปิดเฉพาะตอนพูดผ่าน VTSClient/lipsync เท่านั้น
                        if mouthOpen_enable:
                            mo = 0.5 + mouthOpen_amp * math.sin(2.0 * math.pi * mouthOpen_freq * t)
                            await client.set_parameter_value(_mouthOpen, min(1.0, max(0.0, mo)))
                        if mouthX_enable:
                            mx = mouthX_amp * math.sin(2.0 * math.pi * mouthX_freq * t)
                            await client.set_parameter_value(_mouthX, min(1.0, max(-1.0, mx)))
                    except Exception as e:
                        logger.debug(f"[motion-loop] ignore error: {e}")
                    finally:
                        await asyncio.sleep(tick)
                 # loop นี้ทำงานต่อเนื่อง ไม่รีเซ็ตค่าเป็นคาบๆ เพื่อหลีกเลี่ยงอาการค้าง

            else:
                 logger.warning("ไม่พบพารามิเตอร์ที่รองรับสำหรับการฉีดแบบ Input-first — โปรดเปิด mapping หรือส่งชื่อพารามิเตอร์ของโมเดลมาให้ผมผูกเพิ่ม")
        except Exception:
            pass
        # รอแบบไม่สิ้นสุดเพื่อให้ random motion ทำงานต่อเนื่องจนกว่าจะถูกหยุด
        await asyncio.Event().wait()
    except Exception as e:
        logger.exception(f"เกิดข้อผิดพลาด: {e}")
    finally:
        try:
            await client.stop_random_motion()
        except Exception:
            pass
        await client.disconnect()
        logger.info("✅ ปิดการเชื่อมต่อและออกจากระบบเรียบร้อย")


if __name__ == "__main__":
    asyncio.run(run_vts_demo())