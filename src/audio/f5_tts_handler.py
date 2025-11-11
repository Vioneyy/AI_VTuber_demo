"""
F5TTSHandler
- Wrapper ให้ F5-TTS-Thai คืนค่าเป็น (np.ndarray, sample_rate)
- รองรับ reference voice จาก `reference_audio/jeed_voice.wav`
"""
import logging
from typing import Optional, Tuple
import numpy as np
import io

logger = logging.getLogger(__name__)


class F5TTSHandler:
    """TTS Handler สำหรับ F5-TTS-Thai ที่คืนข้อมูลเป็น numpy array"""

    def __init__(self, reference_wav: Optional[str] = None, device: Optional[str] = None):
        try:
            # รองรับทั้งกรณีรันแบบแพ็กเกจ (root on sys.path) และรันจากโฟลเดอร์ src โดยตรง
            try:
                from src.adapters.tts.f5_tts_thai import F5TTSThai
            except ImportError:
                from adapters.tts.f5_tts_thai import F5TTSThai
            # หาก .env มี TTS_REFERENCE_WAV จะอ่านโดย engine ภายในอยู่แล้ว
            self.engine = F5TTSThai(device=device, reference_wav=reference_wav)
            logger.info("✅ F5TTSHandler initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize F5TTSHandler: {e}")
            raise

    async def generate_speech(self, text: str, output_path: Optional[str] = None) -> Tuple[Optional[np.ndarray], Optional[int]]:
        """
        สังเคราะห์เสียงด้วย F5-TTS-Thai และแปลงเป็น numpy array

        Returns:
            (audio_array: np.ndarray(float32, mono), sample_rate: int)
        """
        try:
            wav_bytes: bytes = await self.engine.generate(text)
        except Exception as e:
            logger.error(f"F5-TTS generate failed: {e}")
            return None, None

        try:
            import soundfile as sf
            buf = io.BytesIO(wav_bytes)
            audio, sr = sf.read(buf)
            # Convert stereo -> mono ด้วย mean
            if isinstance(audio, np.ndarray) and audio.ndim > 1:
                audio = audio.mean(axis=1)
            audio = audio.astype(np.float32)

            # Normalize เล็กน้อย
            max_val = float(np.max(np.abs(audio))) if audio.size > 0 else 0.0
            if max_val > 0:
                audio = (audio / max_val * 0.95).astype(np.float32)

            # Guard: silent audio
            if audio.size == 0 or np.max(np.abs(audio)) < 1e-4:
                logger.error("❌ Generated audio is SILENT!")
                return None, None

            # หากระบุ output_path ให้บันทึก wav bytes ลงไฟล์
            try:
                if output_path:
                    with open(output_path, 'wb') as wf:
                        wf.write(wav_bytes)
            except Exception as write_e:
                logger.warning(f"⚠️ ไม่สามารถบันทึกไฟล์ TTS: {write_e}")

            return audio, int(sr)
        except Exception as e:
            logger.error(f"Failed to decode WAV bytes: {e}")
            return None, None