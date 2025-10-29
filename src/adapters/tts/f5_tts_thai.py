"""
F5-TTS-Thai Engine
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
        self.speed = float(os.getenv("F5_TTS_SPEED", "1.1"))
        self.steps = int(os.getenv("F5_TTS_STEPS", "20"))
        self.cfg_strength = float(os.getenv("F5_TTS_CFG_STRENGTH", "2.0"))
        self.sample_rate = int(os.getenv("F5_TTS_SAMPLE_RATE", "24000"))
        
        logger.info(f"F5-TTS-Thai: device={self.device}, use_ref={self.use_reference}, speed={self.speed}")
        
        try:
            # รองรับทั้งสองชื่อโมดูลที่พบในแพ็กเกจต่างเวอร์ชัน: 'f5_tts' และ 'f5_tts_th'
            try:
                from f5_tts_th.utils_infer import infer_process, load_model, load_vocoder
            except ImportError:
                from f5_tts.infer.utils_infer import infer_process, load_model, load_vocoder

            self.load_model = load_model
            self.load_vocoder = load_vocoder
            self.infer_process = infer_process

            self.model = load_model("F5-TTS", "Thai", self.device)
            self.vocoder = load_vocoder("vocos", is_local=False, local_path="", device=self.device)
            logger.info("✅ F5-TTS-Thai โหลดโมเดลสำเร็จ")
        except Exception as e:
            logger.error(f"❌ ไม่สามารถโหลด F5-TTS-Thai: {e}")
            raise

    def set_use_reference(self, use_ref: bool):
        """เปิด/ปิด reference runtime"""
        self.use_reference = use_ref
        logger.info(f"F5-TTS: use_reference = {use_ref}")

    def _sanitize_text(self, text: str) -> str:
        """ทำความสะอาดข้อความก่อนส่งเข้า TTS"""
        text = text.strip()
        import re
        text = re.sub(r'[^\w\s\u0E00-\u0E7F.,!?-]', '', text)
        return text

    def synthesize(self, text: str) -> bytes:
        """
        สังเคราะห์เสียงจากข้อความ
        """
        try:
            text = self._sanitize_text(text)
            
            if not text:
                logger.warning("ข้อความว่างเปล่า ส่งเสียงเงียบ")
                return self._generate_silence(1.0)

            if self.use_reference and os.path.exists(self.ref_audio_path) and self.ref_text:
                ref_audio = self.ref_audio_path
                ref_text = self.ref_text
                logger.info(f"🎙️ ใช้ reference: {ref_text[:30]}...")
            else:
                ref_audio = self._get_silent_reference()
                ref_text = ""
                logger.info("🔇 ไม่ใช้ reference (silent mode)")

            audio_data, final_sr = self.infer_process(
                ref_audio=ref_audio,
                ref_text=ref_text,
                gen_text=text,
                model_obj=self.model,
                vocoder=self.vocoder,
                device=self.device,
                speed=self.speed,
                nfe_step=self.steps,
                cfg_strength=self.cfg_strength,
                target_sample_rate=self.sample_rate,
                remove_silence=True,
                cross_fade_duration=0.15
            )

            audio_data = self._clean_audio(audio_data)
            wav_bytes = self._to_wav_bytes(audio_data, final_sr)
            
            logger.info(f"✅ สังเคราะห์เสียงสำเร็จ: {len(text)} ตัวอักษร → {len(wav_bytes)} bytes")
            return wav_bytes

        except Exception as e:
            logger.error(f"❌ F5-TTS synthesis error: {e}", exc_info=True)
            return self._generate_silence(2.0)

    def _clean_audio(self, audio: np.ndarray) -> np.ndarray:
        """ทำความสะอาดเสียง"""
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        audio = np.clip(audio, -1.0, 1.0)
        
        rms = np.sqrt(np.mean(audio**2))
        if rms > 1e-6:
            target_rms = 0.1
            audio = audio * (target_rms / rms)
        
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


def create_tts_engine():
    """สร้าง TTS engine ตาม config"""
    engine_type = os.getenv("TTS_ENGINE", "f5_tts_thai").lower()
    
    if engine_type == "f5_tts_thai":
        try:
            return F5TTSThai()
        except Exception as e:
            logger.error(f"❌ F5-TTS-Thai ใช้งานไม่ได้ จะใช้ StubTTS แทน: {e}")
            return StubTTS()
    else:
        logger.warning(f"TTS engine '{engine_type}' ไม่รู้จัก ใช้ stub")
        return StubTTS()


class StubTTS:
    """Stub TTS สำหรับทดสอบ"""
    def synthesize(self, text: str) -> bytes:
        logger.warning(f"[Stub TTS] พูด: {text}")
        sample_rate = 24000
        silent_audio = np.zeros(sample_rate * 2, dtype=np.float32)
        buffer = BytesIO()
        audio_tensor = torch.from_numpy(silent_audio).unsqueeze(0)
        torchaudio.save(buffer, audio_tensor, sample_rate, format="wav")
        buffer.seek(0)
        return buffer.read()
    
    def set_use_reference(self, use_ref: bool):
        pass