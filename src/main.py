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

        # โหมดเริ่มเคลื่อนไหวแบบสุ่มทันที (ไม่มีลูป input-first)
        logger.info("🎬 ใช้ neuro-random events (default) — ไม่มีการฉีดแบบลูป")
        try:
            await client.start_neuro_random_events()
            # หากต้องการกำหนดเวลา ให้ใช้ VTS_PRESET_DURATION_SEC; ถ้าไม่กำหนด จะรันไปเรื่อย ๆ
            run_sec = float(getattr(settings, "VTS_PRESET_DURATION_SEC", 0.0))
            if run_sec > 0:
                await asyncio.sleep(run_sec)
            else:
                await asyncio.Event().wait()
        except Exception:
            pass
    except Exception as e:
        logger.exception(f"เกิดข้อผิดพลาด: {e}")
    finally:
        try:
            await client.stop_neuro_random_events()
        except Exception:
            pass
        await client.disconnect()
        logger.info("✅ ปิดการเชื่อมต่อและออกจากระบบเรียบร้อย")


if __name__ == "__main__":
    asyncio.run(run_vts_demo())