"""
F5-TTS-Thai Engine (Real Implementation)
✅ รองรับ API จริงของ F5-TTS-Thai
"""
import os
import numpy as np
import torch
import torchaudio
from io import BytesIO
import logging

logger = logging.getLogger(__name__)

class F5TTSThai:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.use_reference = os.getenv("F5_TTS_USE_REFERENCE", "false").lower() == "true"
        self.ref_audio_path = os.getenv("TTS_REFERENCE_WAV", "ref_audio.wav")
        self.ref_text = os.getenv("F5_TTS_REF_TEXT", "")
        self.speed = float(os.getenv("F5_TTS_SPEED", "1.0"))
        self.steps = int(os.getenv("F5_TTS_STEPS", "32"))  # default 32
        self.cfg_strength = float(os.getenv("F5_TTS_CFG_STRENGTH", "2.0"))
        self.sample_rate = int(os.getenv("F5_TTS_SAMPLE_RATE", "24000"))
        
        logger.info(f"F5-TTS-Thai: device={self.device}, speed={self.speed}, steps={self.steps}")
        
        try:
            # ✅ วิธีที่ถูกต้อง: ใช้ TTS class จาก f5_tts_th.tts
            from f5_tts_th.tts import TTS
            
            logger.info("📦 กำลังโหลด F5-TTS-Thai model...")
            
            # โหลด model ด้วย TTS class
            self.tts = TTS(model="v1")  # ใช้ model v1 ตาม Hugging Face
            
            logger.info("✅ F5-TTS-Thai โหลดสำเร็จ!")

            
        except ImportError as e:
            logger.error(f"❌ ไม่สามารถ import F5-TTS-Thai: {e}")
            logger.error("ติดตั้งด้วย: pip install f5-tts-thai")
            raise
        except Exception as e:
            logger.error(f"❌ โหลด F5-TTS-Thai ไม่สำเร็จ: {e}")
            raise

    def set_use_reference(self, use_ref: bool):
        """เปิด/ปิด reference runtime"""
        self.use_reference = use_ref
        logger.info(f"F5-TTS: use_reference = {use_ref}")

    def _sanitize_text(self, text: str) -> str:
        """ทำความสะอาดข้อความ"""
        text = text.strip()
        import re
        # ลบ emoji และ special characters
        text = re.sub(r'[^\w\s\u0E00-\u0E7F.,!?-]', '', text)
        return text

    def synthesize(self, text: str) -> bytes:
        """
        สังเคราะห์เสียงจากข้อความ
        """
        try:
            text = self._sanitize_text(text)
            
            if not text:
                logger.warning("ข้อความว่าง")
                return self._generate_silence(1.0)

            logger.info(f"🎤 F5-TTS-Thai กำลังสังเคราะห์: {text[:50]}...")

            # ตั้งค่า reference
            if self.use_reference and os.path.exists(self.ref_audio_path) and self.ref_text:
                ref_audio = self.ref_audio_path
                ref_text = self.ref_text
                logger.info(f"🎙️ ใช้ reference: {ref_text[:30]}...")
            else:
                # ไม่ใช้ reference - ใช้เสียงเงียบ
                ref_audio = self._get_silent_reference()
                ref_text = ""
                logger.info("🔇 ไม่ใช้ reference")

            # เรียก TTS.infer ตาม API ที่ถูกต้อง
            generated_audio = self.tts.infer(
                ref_audio=ref_audio,
                ref_text=ref_text,
                gen_text=text,
                step=self.steps,
                cfg=self.cfg_strength,
                speed=self.speed
            )

            # Clean audio
            audio_data = self._clean_audio(generated_audio)
            
            # แปลงเป็น WAV bytes
            wav_bytes = self._to_wav_bytes(audio_data, self.sample_rate)
            
            logger.info(f"✅ สังเคราะห์สำเร็จ: {len(wav_bytes)} bytes")
            return wav_bytes

        except Exception as e:
            logger.error(f"❌ F5-TTS synthesis error: {e}", exc_info=True)
            return self._generate_silence(2.0)

    def _clean_audio(self, audio: np.ndarray) -> np.ndarray:
        """ทำความสะอาดเสียง"""
        # ลบ NaN/Inf
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        
        # Clip
        audio = np.clip(audio, -1.0, 1.0)
        
        # RMS Normalize
        rms = np.sqrt(np.mean(audio**2))
        if rms > 1e-6:
            target_rms = 0.1
            audio = audio * (target_rms / rms)
        
        # Fade in/out (10ms)
        fade_samples = int(self.sample_rate * 0.01)
        if len(audio) > fade_samples * 2:
            fade_in = np.linspace(0, 1, fade_samples)
            fade_out = np.linspace(1, 0, fade_samples)
            audio[:fade_samples] *= fade_in
            audio[-fade_samples:] *= fade_out
        
        return audio

    def _to_wav_bytes(self, audio: np.ndarray, sample_rate: int) -> bytes:
        """แปลง numpy array เป็น WAV bytes"""
        buffer = BytesIO()
        
        audio_tensor = torch.from_numpy(audio).float()
        if audio_tensor.dim() == 1:
            audio_tensor = audio_tensor.unsqueeze(0)
        
        torchaudio.save(buffer, audio_tensor, sample_rate, format="wav")
        buffer.seek(0)
        
        return buffer.read()

    def _get_silent_reference(self) -> str:
        """สร้างไฟล์เงียบสำหรับ reference"""
        silent_path = "temp_silent_ref.wav"
        
        if not os.path.exists(silent_path):
            duration = 0.5
            silent_audio = np.zeros(int(self.sample_rate * duration), dtype=np.float32)
            silent_tensor = torch.from_numpy(silent_audio).unsqueeze(0)
            torchaudio.save(silent_path, silent_tensor, self.sample_rate)
            logger.info(f"สร้างไฟล์เงียบ: {silent_path}")
        
        return silent_path

    def _generate_silence(self, duration: float) -> bytes:
        """สร้างเสียงเงียบ"""
        silent_audio = np.zeros(int(self.sample_rate * duration), dtype=np.float32)
        return self._to_wav_bytes(silent_audio, self.sample_rate)