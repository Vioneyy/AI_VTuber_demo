"""
TTS Engine Factory - รองรับ F5-TTS-Thai + Google TTS
"""
import os
import logging

logger = logging.getLogger(__name__)

def create_tts_engine():
    """
    สร้าง TTS Engine ตาม config
    
    TTS_ENGINE ที่รองรับ:
    - gtts หรือ google: Google TTS (เร็ว แนะนำ)
    - f5_tts_thai: F5-TTS-Thai (เสียงดีที่สุด แต่ช้า)
    - stub: Stub TTS (ทดสอบ)
    """
    engine_type = os.getenv("TTS_ENGINE", "gtts").lower()
    
    logger.info(f"🎯 TTS Engine: {engine_type}")
    
    # 1. F5-TTS-Thai (เสียงธรรมชาติที่สุด)
    if engine_type == "f5_tts_thai":
        try:
            from .f5_tts_thai_real import F5TTSThai
            logger.info("✅ ใช้ F5-TTS-Thai")
            return F5TTSThai()
        except ImportError as e:
            logger.error(f"❌ ไม่สามารถโหลด F5-TTS-Thai: {e}")
            logger.error("ติดตั้งด้วย: pip install f5-tts-thai")
            logger.info("ลองใช้ Google TTS แทน...")
            
            # Fallback to Google TTS
            try:
                from .gtts_engine import GoogleTTSEngine
                return GoogleTTSEngine()
            except:
                logger.info("ใช้ StubTTS แทน")
                return StubTTS()
        except Exception as e:
            logger.error(f"❌ F5-TTS-Thai error: {e}", exc_info=True)
            logger.info("ลองใช้ Google TTS แทน...")
            
            try:
                from .gtts_engine import GoogleTTSEngine
                return GoogleTTSEngine()
            except:
                logger.info("ใช้ StubTTS แทน")
                return StubTTS()
    
    # 2. Google TTS (แนะนำ - เร็ว)
    elif engine_type in ["gtts", "google"]:
        try:
            from .gtts_engine import GoogleTTSEngine
            logger.info("✅ ใช้ Google TTS")
            return GoogleTTSEngine()
        except ImportError as e:
            logger.error(f"❌ ไม่สามารถโหลด Google TTS: {e}")
            logger.error("ติดตั้งด้วย: pip install gtts pydub")
            logger.error("และ: winget install ffmpeg")
            logger.info("ใช้ StubTTS แทน")
            return StubTTS()
        except Exception as e:
            logger.error(f"❌ Google TTS error: {e}")
            logger.info("ใช้ StubTTS แทน")
            return StubTTS()
    
    # 3. Stub (ทดสอบ)
    elif engine_type == "stub":
        logger.info("ใช้ StubTTS (test mode)")
        return StubTTS()
    
    # 4. ไม่รู้จัก -> ใช้ Google TTS
    else:
        logger.warning(f"⚠️ ไม่รู้จัก TTS engine '{engine_type}' ใช้ Google TTS แทน")
        try:
            from .gtts_engine import GoogleTTSEngine
            return GoogleTTSEngine()
        except:
            logger.info("ใช้ StubTTS แทน")
            return StubTTS()


class StubTTS:
    """Stub TTS สำหรับทดสอบ"""
    def __init__(self):
        logger.warning("⚠️ StubTTS: สร้างเสียงทดสอบ (sine wave 440Hz)")
    
    def synthesize(self, text: str) -> bytes:
        import numpy as np
        import torch
        import torchaudio
        from io import BytesIO
        
        logger.warning(f"[Stub TTS] {text[:50]}...")
        
        sample_rate = 24000
        duration = 2.0
        frequency = 440.0
        
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        audio = np.sin(frequency * 2 * np.pi * t) * 0.3
        audio = audio.astype(np.float32)
        
        buffer = BytesIO()
        audio_tensor = torch.from_numpy(audio).unsqueeze(0)
        torchaudio.save(buffer, audio_tensor, sample_rate, format="wav")
        buffer.seek(0)
        return buffer.read()
    
    def set_use_reference(self, use_ref: bool):
        pass