"""
Hybrid STT Handler
- ใช้ Whisper ปกติ (ไม่ต้องดาวน์โหลดจาก HuggingFace)
- แก้ปัญหา audio preprocessing
- รองรับ GPU
- ไม่มี tensor errors
"""
import numpy as np
import torch
import logging
from typing import Optional
from pathlib import Path
import soundfile as sf
import asyncio

logger = logging.getLogger(__name__)

class HybridSTT:
    """
    Hybrid STT Handler
    แก้ปัญหา:
    1. 401 Unauthorized → ใช้ Whisper ปกติ
    2. Audio preprocessing → แก้ให้ถูกต้อง
    3. GPU support → ใช้ CUDA ได้
    4. Sample rate mismatch → Resample อัตโนมัติ
    """
    
    def __init__(
        self,
        model_size: str = "base",
        device: str = "cuda",
        language: str = "th"
    ):
        """
        Args:
            model_size: tiny, base, small, medium, large
            device: cuda หรือ cpu
            language: th, en, auto
        """
        self.model_size = model_size
        self.language = language
        
        # Check CUDA
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA not available, using CPU")
            device = "cpu"
        
        self.device = device
        
        # Load model
        self.model = self._load_model()
        
        logger.info(f"✅ Hybrid STT ready: {model_size} on {device}")
    
    def _load_model(self):
        """Load Whisper model"""
        try:
            import whisper
            
            logger.info(f"Loading Whisper: {self.model_size} on {self.device}")
            
            model = whisper.load_model(self.model_size, device=self.device)
            
            logger.info("✅ Whisper model loaded")
            
            return model
            
        except Exception as e:
            logger.error(f"Failed to load Whisper: {e}")
            raise
    
    async def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate: int = 48000
    ) -> Optional[str]:
        """
        Transcribe audio to text
        
        Args:
            audio_bytes: Raw audio from Discord
            sample_rate: Sample rate (Discord = 48000)
        
        Returns:
            Transcribed text or None
        """
        try:
            # 1. Preprocess audio (แก้ปัญหา sample rate mismatch + clipping)
            audio = self._preprocess_audio(audio_bytes, sample_rate)
            
            if audio is None or len(audio) == 0:
                logger.warning("Audio preprocessing failed")
                return None
            
            # 2. Transcribe (run in executor เพื่อไม่ block)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                audio
            )
            
            if result:
                text = result['text'].strip()
                if text:
                    logger.info(f"✅ Transcribed: {text}")
                    return text
            
            logger.warning("Empty transcription")
            return None
            
        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            return None
    
    def _transcribe_sync(self, audio: np.ndarray) -> Optional[dict]:
        """Synchronous transcribe (for executor)"""
        try:
            # ใช้ fp16 ถ้าเป็น CUDA, ไม่งั้นใช้ fp32
            fp16 = (self.device == "cuda")
            
            result = self.model.transcribe(
                audio,
                language=self.language if self.language != 'auto' else None,
                task='transcribe',
                fp16=fp16,
                verbose=False,
                # เพิ่ม options เพื่อลด hallucination
                condition_on_previous_text=False,
                initial_prompt=None
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            return None
    
    def _preprocess_audio(
        self,
        audio_bytes: bytes,
        source_sr: int
    ) -> Optional[np.ndarray]:
        """
        Preprocess audio
        แก้ปัญหา:
        1. Sample rate mismatch (48000 → 16000)
        2. Audio clipping
        3. DC offset
        4. Noise
        """
        try:
            # 1. Convert bytes to numpy (Discord = int16 PCM stereo)
            audio = np.frombuffer(audio_bytes, dtype=np.int16)
            
            if len(audio) == 0:
                return None
            
            # 2. Convert to float32 [-1, 1]
            audio = audio.astype(np.float32) / 32768.0
            
            # 3. Convert stereo to mono
            if len(audio) % 2 == 0:
                audio = audio.reshape(-1, 2).mean(axis=1)
            
            # 4. Remove DC offset
            audio = audio - audio.mean()
            
            # 5. แก้ปัญหา clipping: normalize ถ้า clipping
            max_val = np.abs(audio).max()
            if max_val >= 0.99:  # Clipping detected
                logger.debug(f"Clipping detected: {max_val:.3f}, normalizing...")
                audio = audio / max_val * 0.95
            elif max_val > 0:
                # Amplify ถ้าเบาเกินไป
                if max_val < 0.1:
                    audio = audio / max_val * 0.5
                else:
                    audio = audio / max_val * 0.95
            
            # 6. Resample to 16kHz (แก้ปัญหา sample rate mismatch)
            if source_sr != 16000:
                from scipy import signal as scipy_signal
                num_samples = int(len(audio) * 16000 / source_sr)
                audio = scipy_signal.resample(audio, num_samples)
            
            # 7. Trim silence
            audio = self._trim_silence(audio)
            
            # 8. Check duration
            duration = len(audio) / 16000
            if duration < 0.3:
                logger.debug(f"Audio too short: {duration:.2f}s")
                return None
            
            if duration > 30:
                logger.debug(f"Audio too long: {duration:.2f}s, trimming")
                audio = audio[:30*16000]
            
            # 9. Final validation
            if np.isnan(audio).any() or np.isinf(audio).any():
                logger.error("Audio contains NaN or Inf")
                return None
            
            # 10. Ensure float32
            audio = audio.astype(np.float32)
            
            logger.debug(
                f"Audio preprocessed: {duration:.2f}s, "
                f"RMS={np.sqrt(np.mean(audio**2)):.4f}, "
                f"Range=[{audio.min():.3f}, {audio.max():.3f}]"
            )
            
            return audio
            
        except Exception as e:
            logger.error(f"Audio preprocessing error: {e}")
            return None
    
    def _trim_silence(
        self,
        audio: np.ndarray,
        threshold: float = 0.01
    ) -> np.ndarray:
        """ตัดความเงียบที่ต้นท้าย"""
        try:
            energy = np.abs(audio)
            
            # Find start
            for start in range(len(energy)):
                if energy[start] > threshold:
                    break
            
            # Find end
            for end in range(len(energy) - 1, -1, -1):
                if energy[end] > threshold:
                    break
            
            # Add small padding
            start = max(0, start - 160)
            end = min(len(audio), end + 160)
            
            return audio[start:end]
            
        except:
            return audio
    
    def get_stats(self) -> dict:
        """Get statistics"""
        return {
            'model': self.model_size,
            'device': self.device,
            'language': self.language
        }


# Helper function
async def transcribe_audio(
    audio_bytes: bytes,
    sample_rate: int = 48000,
    model_size: str = "base",
    device: str = "cuda",
    language: str = "th"
) -> Optional[str]:
    """
    Convenience function
    
    Args:
        audio_bytes: Raw audio bytes
        sample_rate: Sample rate
        model_size: Whisper model size
        device: cuda or cpu
        language: Language code
    
    Returns:
        Transcribed text or None
    """
    stt = HybridSTT(
        model_size=model_size,
        device=device,
        language=language
    )
    
    return await stt.transcribe(audio_bytes, sample_rate)