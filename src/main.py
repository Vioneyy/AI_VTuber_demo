import asyncio
import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# รองรับการรันแบบโมดูล (python -m src.main) และรันตรงจากรากโปรเจ็กต์
try:
    from adapters.vts.motion_controller import CompatibleMotionController
except ModuleNotFoundError:
    from src.adapters.vts.motion_controller import CompatibleMotionController

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
    plugin_dev = os.getenv("VTS_PLUGIN_DEVELOPER", "VIoneyy")

    # ใช้ Motion Controller รุ่นเข้ากันได้ เพื่อควบคุมการขยับ
    motion = CompatibleMotionController(host=host, port=port, plugin_name=plugin_name, plugin_developer=plugin_dev)

    try:
        ok = await motion.start()
        if not ok:
            logger.error("❌ เชื่อมต่อ/ยืนยันตัวตนกับ VTube Studio ไม่สำเร็จ")
            return

        # หากกำหนดระยะเวลาไว้ ให้รอแล้วหยุดตามเวลาที่ตั้งค่า
        run_sec = float(getattr(settings, "VTS_PRESET_DURATION_SEC", duration_sec)) or duration_sec
        if run_sec > 0:
            logger.info("🎬 เริ่ม motion เป็นเวลา ~%.1f วินาที", run_sec)
            await asyncio.sleep(run_sec)
        else:
            logger.info("🎬 เริ่ม motion ต่อเนื่อง (หยุดด้วย Ctrl+C)")
            await asyncio.Event().wait()
    except Exception as e:
        logger.exception(f"เกิดข้อผิดพลาด: {e}")
    finally:
        await motion.stop()
        logger.info("✅ ปิดการเชื่อมต่อและหยุดระบบเรียบร้อย")


if __name__ == "__main__":
    asyncio.run(run_vts_demo())