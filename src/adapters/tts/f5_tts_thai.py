"""
TTS Engine Factory - บังคับใช้ F5-TTS-Thai เท่านั้น (ไม่มี fallback)
"""
import os
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

class F5ThaiAdapter:
    """Adapter ให้อินเทอร์เฟซแบบ generate(text) คืนพาธไฟล์ WAV
    ใช้ F5TTSThai.synthesize() ภายใน
    """
    def __init__(self, engine):
        self.engine = engine

    async def generate(self, text: str) -> str:
        wav_bytes = self.engine.synthesize(text)
        # เขียนเป็นไฟล์ชั่วคราว
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp.write(wav_bytes)
        tmp.flush()
        tmp.close()
        return str(Path(tmp.name))


def create_tts_engine(engine_type: str | None = None):
    """
    สร้าง TTS Engine ตาม config (รองรับเฉพาะ F5-TTS-Thai)
    - หากไม่ใช่ f5_tts_thai จะยกเว้นด้วยข้อความแนะนำให้ตั้งค่า .env ให้ถูกต้อง
    """
    et = (engine_type or os.getenv("TTS_ENGINE", "f5_tts_thai")).lower()
    logger.info(f"🎯 TTS Engine: {et}")

    if et != "f5_tts_thai":
        logger.error("❌ ระบบตั้งให้ใช้เฉพาะ F5-TTS-Thai เท่านั้น กรุณาตั้งค่า TTS_ENGINE=f5_tts_thai ใน .env")
        raise RuntimeError("Unsupported TTS_ENGINE. Set TTS_ENGINE=f5_tts_thai")

    try:
        from .f5_tts_thai_real import F5TTSThai
        logger.info("✅ ใช้ F5-TTS-Thai")
        return F5ThaiAdapter(F5TTSThai())
    except ImportError as e:
        logger.error(f"❌ ไม่สามารถโหลด F5-TTS-Thai: {e}")
        logger.error("ติดตั้งด้วย: pip install f5-tts-th")
        raise
    except Exception as e:
        logger.error(f"❌ F5-TTS-Thai error: {e}", exc_info=True)
        raise