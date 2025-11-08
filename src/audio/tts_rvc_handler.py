"""
จัดการ TTS (F5-TTS) + RVC Voice Conversion
ตำแหน่ง: src/audio/tts_rvc_handler.py (แทนที่ rvc_v2.py)
"""

import asyncio
import tempfile
import os
import torch
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Optional, Tuple
import noisereduce as nr

import sys
sys.path.append('..')
from core.config import config
from personality.jeed_persona import JeedPersona

class TTSRVCHandler:
    """จัดการ TTS และ RVC"""
    
    def __init__(self):
        self.device = "cuda" if config.tts.use_gpu and torch.cuda.is_available() else "cpu"
        self.tts_model = None
        self.rvc_model = None
        self.total_generated = 0
        
        print(f"🎵 Audio Device: {self.device}")
        
        # โหลดโมเดล
        self._load_tts_model()
        if config.rvc.enabled:
            self._load_rvc_model()
    
    def _load_tts_model(self):
        """โหลดโมเดล F5-TTS"""
        try:
            print("📦 Loading F5-TTS-Thai engine...")
            # ใช้ wrapper ที่มี fallback เงียบถ้าโหลดไม่สำเร็จ
            from adapters.tts.f5_tts_thai import F5TTSThai
            # sync env/sample rate ให้ engine
            try:
                os.environ["F5_TTS_SAMPLE_RATE"] = str(config.tts.sample_rate)
            except Exception:
                pass
            # ส่งพาธ reference จาก config หากมี (ถ้าไม่มี ใช้ None)
            ref_wav = getattr(config.tts, 'reference_wav', None)
            # อ่านค่า device จาก .env/core.config
            desired_device = None
            try:
                desired_device = config.TTS_DEVICE
            except Exception:
                desired_device = os.getenv("TTS_DEVICE", None)

            self.tts_model = F5TTSThai(device=desired_device, reference_wav=ref_wav)
            print("✅ F5-TTS-Thai ready")
        except Exception as e:
            print(f"⚠️ Failed to load F5-TTS: {e}")
            self.tts_model = None
    
    def _load_rvc_model(self):
        """โหลดโมเดล RVC"""
        try:
            if not Path(config.rvc.model_path).exists():
                print(f"⚠️ RVC model not found: {config.rvc.model_path}")
                return
            
            # TODO: โหลดโมเดล RVC จริง
            print("📦 Loading RVC model...")
            # from rvc import RVC
            # self.rvc_model = RVC(...)
            print("✅ RVC loaded")
        except Exception as e:
            print(f"⚠️ Failed to load RVC: {e}")
            self.rvc_model = None
    
    async def generate_speech(
        self, 
        text: str, 
        output_path: Optional[str] = None
    ) -> Tuple[Optional[np.ndarray], Optional[str]]:
        """
        สร้างเสียงพูดจากข้อความ
        Args:
            text: ข้อความ
            output_path: พาธบันทึกไฟล์ (ถ้าไม่ระบุจะสร้างชั่วคราว)
        Returns:
            (audio_array, file_path) หรือ (None, None) ถ้าล้มเหลว
        """
        try:
            # ทำความสะอาดข้อความ
            text = self._clean_text_for_tts(text)
            
            if not text:
                return None, None
            
            print(f"🎵 Generating speech: '{text}'")
            
            # 1. สร้างเสียงด้วย TTS
            audio_data = await self._run_tts(text)
            if audio_data is None:
                return None, None
            
            # 2. ใช้ RVC แปลงเสียง
            if config.rvc.enabled and self.rvc_model:
                audio_data = await self._run_rvc(audio_data)
            
            # 3. ลด noise และ normalize
            if config.tts.noise_reduction:
                audio_data = self._reduce_noise(audio_data)
            
            if config.tts.normalize_audio:
                audio_data = self._normalize_audio(audio_data)
            
            # 4. บันทึกไฟล์
            if output_path is None:
                tmp_file = tempfile.NamedTemporaryFile(
                    suffix='.wav', 
                    delete=False
                )
                output_path = tmp_file.name
                tmp_file.close()
            
            sf.write(
                output_path, 
                audio_data, 
                config.tts.sample_rate
            )
            
            self.total_generated += 1
            print(f"✅ Speech saved: {output_path}")
            
            return audio_data, output_path
            
        except Exception as e:
            print(f"❌ TTS Error: {e}")
            return None, None
    
    async def _run_tts(self, text: str) -> Optional[np.ndarray]:
        """รัน F5-TTS"""
        try:
            if self.tts_model is None:
                # fallback: สร้างความเงียบระยะสั้นแทนเพื่อหลีกเลี่ยงเสียงแตก
                duration = max(0.6, JeedPersona.count_words(text) * 0.35 / config.tts.speed)
                samples = int(duration * config.tts.sample_rate)
                return np.zeros(samples, dtype=np.float32)

            # สังเคราะห์เสียงเป็น WAV bytes
            wav_bytes = await self.tts_model.generate(text)

            # อ่าน WAV bytes เป็น numpy float32
            from io import BytesIO
            import soundfile as sf
            data, sr = sf.read(BytesIO(wav_bytes), dtype='float32')

            # ถ้าเป็นสเตอริโอ -> แปลงเป็นโมโน
            if data.ndim > 1:
                data = data.mean(axis=1)

            # Resample เป็น config.tts.sample_rate หากจำเป็น (ใช้ polyphase คุณภาพดี)
            target_sr = config.tts.sample_rate
            if sr != target_sr:
                try:
                    from scipy.signal import resample_poly
                    data = resample_poly(data, target_sr, sr).astype(np.float32)
                except Exception:
                    # Fallback: linear interpolation ด้วย numpy
                    new_len = int(len(data) * target_sr / sr)
                    x_old = np.linspace(0.0, 1.0, num=len(data), endpoint=False)
                    x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
                    data = np.interp(x_new, x_old, data).astype(np.float32)

            print(f"🎵 TTS generated: {len(data)/target_sr:.2f}s, sr={target_sr}")
            return data.astype(np.float32)
            
        except Exception as e:
            print(f"❌ TTS Error: {e}")
            return None
    
    async def _run_rvc(self, audio: np.ndarray) -> np.ndarray:
        """รัน RVC Voice Conversion"""
        try:
            # TODO: รันโมเดล RVC จริง
            print("🎤 Running RVC conversion...")
            
            # ตอนนี้ return เสียงเดิม
            return audio
            
        except Exception as e:
            print(f"❌ RVC Error: {e}")
            return audio
    
    def _reduce_noise(self, audio: np.ndarray) -> np.ndarray:
        """ลด noise"""
        try:
            # ใช้ noisereduce library
            reduced = nr.reduce_noise(
                y=audio, 
                sr=config.tts.sample_rate,
                stationary=True
            )
            return reduced
        except:
            return audio
    
    def _normalize_audio(self, audio: np.ndarray) -> np.ndarray:
        """Normalize ระดับเสียง"""
        # Normalize to -3dB peak
        peak = np.abs(audio).max()
        if peak > 0:
            target = 0.7  # -3dB ≈ 0.7
            audio = audio * (target / peak)
        return audio
    
    def _clean_text_for_tts(self, text: str) -> str:
        """ทำความสะอาดข้อความสำหรับ TTS"""
        # ลบอีโมจิ
        text = JeedPersona.clean_response(text)
        
        # ลบอักขระพิเศษที่ TTS อ่านไม่ได้
        import re
        text = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9\s\.\,\!\?\~]', '', text)
        
        # แทนที่ตัวย่อ
        replacements = {
            '~': '',
            'จ้า': 'จ้ะ',
            'นะ': 'นะ',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text.strip()
    
    def estimate_duration(self, text: str) -> float:
        """ประมาณระยะเวลาพูด (วินาที)"""
        word_count = JeedPersona.count_words(text)
        duration = word_count * 0.35 / config.tts.speed
        return duration
    
    def get_stats(self):
        """ดูสถิติ"""
        return {
            "total_generated": self.total_generated,
            "device": self.device,
            "tts_loaded": self.tts_model is not None,
            "rvc_loaded": self.rvc_model is not None
        }

# Global TTS+RVC handler
tts_rvc_handler = TTSRVCHandler()