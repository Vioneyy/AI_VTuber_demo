from __future__ import annotations
import asyncio
from pathlib import Path

from core.config import get_settings
from core.scheduler import PriorityScheduler
from core.policy import PolicyGuard
from core.types import Message, Response

from personality.personality import Personality
from llm.chatgpt_client import ChatGPTClient
from adapters.discord_bot import DiscordAdapter
from adapters.youtube_live import YouTubeLiveAdapter
from adapters.vts.vts_client import VTSClient
from adapters.vts.hotkeys import EmotionHotkeyController
from adapters.tts.tts_stub import StubTTSEngine
from adapters.tts.f5_tts_thai import F5TTSThaiEngine
from audio.rvc_v2 import convert as rvc_convert


async def build_system_prompt() -> str:
    p = Path(__file__).parent / "llm" / "prompts" / "system_prompt.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""

async def main():
    settings = get_settings()
    scheduler = PriorityScheduler()
    policy = PolicyGuard(allow_mild_profanity=True)
    persona = Personality.load()
    llm = ChatGPTClient()
    vts = VTSClient()

    # เลือก TTS engine ตาม .env
    if settings.TTS_ENGINE.lower() == "f5_tts_thai":
        tts_engine = F5TTSThaiEngine()
    else:
        tts_engine = StubTTSEngine()

    async def worker(msg: Message):
        ok, reason = policy.check_message_ok(msg)
        if not ok:
            print(f"ข้ามข้อความ: {reason}")
            return

        # ทริกเกอร์สถานะ "กำลังคิด" สำหรับข้อความที่ยาวหรือเป็นคำถาม
        try:
            if len(msg.text) >= 40 or msg.is_question:
                await vts.trigger_hotkey_by_name(settings.VTS_HK_THINKING)
        except Exception:
            pass

        system_prompt = await build_system_prompt()
        resp: Response = llm.generate_reply(msg.text, system_prompt, persona.data)
        resp.text = policy.sanitize_output(resp.text)
        emo_cfg = persona.get_emotion_config(resp.emotion.value)
        # ส่ง emotion key เพื่อให้ VTSClient แมป hotkey ได้ถูกต้อง
        emo_cfg["_emotion_key"] = resp.emotion.value
        await vts.apply_emotion(emo_cfg)

        audio = tts_engine.speak(
            resp.text,
            voice_id=settings.TTS_VOICE_ID,
            emotion=resp.emotion.value,
            prosody={"rate": float(settings.F5_TTS_SPEED)},
        )
        # ใช้ RVC v2 (สคาฟโฟลด์) แปลงเสียงตามพรีเซ็ต หากเปิดใช้งาน
        if audio and settings.ENABLE_RVC:
            audio = rvc_convert(audio, settings.VOICE_PRESET)

        print(f"[{msg.source.value}] -> {resp.emotion.value}: {resp.text}")
        # เล่นเสียงทันทีจากหน่วยความจำ และลิปซิงก์โดยไม่บันทึกไฟล์
        try:
            if audio:
                # ลิปซิงก์ไปพร้อม ๆ กัน
                asyncio.create_task(vts.lipsync_bytes(audio))
                # เล่นเสียงแบบ async ในหน่วยความจำ (Windows)
                try:
                    import winsound
                    winsound.PlaySound(audio, winsound.SND_MEMORY | winsound.SND_ASYNC)
                except Exception:
                    pass
        except Exception:
            pass
        # หมายเหตุ: ในเดโม่นี้ไม่เล่นเสียงออก แต่สามารถบันทึกไฟล์ชั่วคราวเพื่อตรวจสอบได้
        # ถ้าต้องการบันทึกตัวอย่าง ให้ปลดคอมเมนต์ด้านล่าง
        # if audio:
        #     out = Path("output_demo.wav")
        #     out.write_bytes(audio)

    # เริ่มเชื่อมต่อ VTS และ idle motion
    try:
        await vts.connect()
        if settings.IDLE_MOTION_ENABLED:
            # เริ่ม idle motion
            await vts.start_idle_motion()
            
            # เริ่มกระพริบตาอัตโนมัติ (ถ้าเปิดใช้งาน)
            if getattr(settings, "BLINK_ENABLED", True):
                await vts.start_blinking()
                
            # เริ่มการหายใจอัตโนมัติ (ถ้าเปิดใช้งาน)
            if getattr(settings, "BREATHING_ENABLED", True):
                await vts.start_breathing()
                
            # เริ่มการยิ้มสุ่ม (ถ้าเปิดใช้งาน)
            if getattr(settings, "RANDOM_SMILE_ENABLED", True):
                await vts.start_random_smile()
            
            # มองรอบ ๆ แบบสุ่มตามโมเดล (ถ้าเปิดใช้งานและโมเดลรองรับ)
            if getattr(settings, "AUTO_GAZE_ENABLED", True):
                await vts.start_auto_gaze()
            
            # แสดง micro-expressions แบบสุ่ม (ถ้าเปิดใช้งานและโมเดลรองรับ)
            if getattr(settings, "MICRO_EXPRESSIONS_ENABLED", True):
                await vts.start_micro_expressions()

            # เล่นอนิเมชันตาม hotkeys ของโมเดลแบบสุ่ม (ถ้าเปิดใช้งาน)
            if getattr(settings, "AUTO_ANIMATIONS_ENABLED", True):
                await vts.start_random_animations()
        # Start global emotion hotkeys (F1=Neutral, F2=Happy, F3=Sad)
        try:
            hk = EmotionHotkeyController(vts)
            loop = asyncio.get_running_loop()
            hk.start(loop)
        except Exception:
            pass
    except Exception:
        pass

    # เริ่มตัวจัดคิว
    asyncio.create_task(scheduler.start(worker))

    # เริ่มตัวอ่าน YouTube หากตั้งค่า STREAM ID
    if settings.YOUTUBE_STREAM_ID:
        yt = YouTubeLiveAdapter(scheduler)
        yt.start()
    else:
        try:
            print("ข้าม YouTube: ไม่ได้ตั้งค่า YOUTUBE_STREAM_ID")
        except Exception:
            pass

    # เริ่มบอท Discord หากมีโทเคน
    if settings.DISCORD_BOT_TOKEN:
        discord_adapter = DiscordAdapter(scheduler, llm, tts_engine, vts)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, discord_adapter.run)
    else:
        try:
            print("ข้าม Discord: ไม่ได้ตั้งค่า DISCORD_BOT_TOKEN")
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())