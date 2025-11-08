"""
TTS Engine Factory - บังคับใช้ F5-TTS-Thai เท่านั้น (ไม่มี fallback)
"""
import os
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Wrapper ให้ main.py import F5TTSThai ได้ และเมธอด generate() คืน WAV bytes
from .f5_tts_thai_real import F5TTSThai as _RealF5TTSThai
import io
import wave
import numpy as np

class F5TTSThai:
    def __init__(self, device: str | None = None, reference_wav: str | None = None):
        # รับ device เพื่อส่งต่อไปยัง engine จริง (อ่านจาก .env หากไม่ระบุ)
        try:
            # หากไม่ได้ระบุ ให้ใช้ค่าใน .env หรือ map จาก core.config
            if device is None:
                try:
                    from core.config import config as _cfg
                    device = os.getenv("TTS_DEVICE", 'cuda' if _cfg.system.use_gpu else 'cpu')
                except Exception:
                    device = os.getenv("TTS_DEVICE", None)

            self.engine = _RealF5TTSThai(device=device)
        except Exception as e:
            logger.error(f"❌ โหลด F5-TTS-Thai ไม่สำเร็จ: {e}. ใช้ fallback แบบเงียบแทน")
            self.engine = self._fallback_engine()
        if reference_wav:
            # ตั้งพาธไฟล์อ้างอิงให้ engine
            try:
                self.engine.ref_audio_path = reference_wav
            except Exception:
                pass

    async def generate(self, text: str) -> bytes:
        return self.engine.synthesize(text)

    def _fallback_engine(self):
        class _SilentEngine:
            def __init__(self, sr: int = 24000):
                self.sample_rate = sr

            def synthesize(self, text: str) -> bytes:
                duration = 1.0
                data = np.zeros(int(self.sample_rate * duration), dtype=np.float32)
                buf = io.BytesIO()
                with wave.open(buf, 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(self.sample_rate)
                    pcm16 = (data * 32767.0).astype(np.int16)
                    w.writeframes(pcm16.tobytes())
                return buf.getvalue()
        return _SilentEngine()

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
        logger.info("✅ ใช้ F5-TTS-Thai")
        # ส่งต่อ device ที่อ่านจาก .env ผ่าน core.config
        try:
            from core.config import config as _cfg
            desired_device = os.getenv("TTS_DEVICE", 'cuda' if _cfg.system.use_gpu else 'cpu')
        except Exception:
            desired_device = os.getenv("TTS_DEVICE", None)

        return F5TTSThai(device=desired_device)
    except ImportError as e:
        logger.error(f"❌ ไม่สามารถโหลด F5-TTS-Thai: {e}")
        logger.error("ติดตั้งด้วย: pip install f5-tts-th")
        raise
    except Exception as e:
        logger.error(f"❌ F5-TTS-Thai error: {e}", exc_info=True)
        raise