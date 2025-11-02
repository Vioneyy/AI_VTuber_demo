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
            # TODO: โหลดโมเดล F5-TTS จริง
            # ตอนนี้เป็น placeholder
            print("📦 Loading F5-TTS model...")
            # from f5_tts import F5TTS
            # self.tts_model = F5TTS(...)
            print("✅ F5-TTS loaded")
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
            # TODO: รันโมเดล F5-TTS จริง
            # สำหรับตอนนี้ใช้ placeholder
            
            # ประมาณเวลาพูด
            word_count = JeedPersona.count_words(text)
            duration = word_count * 0.35 / config.tts.speed
            
            # สร้างเสียงจำลอง (sine wave)
            sample_rate = config.tts.sample_rate
            samples = int(duration * sample_rate)
            t = np.linspace(0, duration, samples)
            audio = np.sin(2 * np.pi * 440 * t) * 0.3  # 440 Hz
            
            print(f"🎵 TTS generated: {duration:.2f}s, {samples} samples")
            
            return audio.astype(np.float32)
            
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