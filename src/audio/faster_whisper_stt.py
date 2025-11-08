"""
Faster-Whisper STT Handler
- 3-5x เร็วกว่า Whisper ปกติ
- GPU support ดีกว่า
- Accuracy เท่าเดิม
- ไม่มี tensor dimension errors
"""
import numpy as np
import logging
from typing import Optional
from pathlib import Path
import soundfile as sf

logger = logging.getLogger(__name__)

class FasterWhisperSTT:
    """
    Faster-Whisper STT Handler
    แก้ปัญหา:
    1. รับเสียงไม่ตรงกับที่พูด → audio preprocessing ดีกว่า
    2. Tensor errors → ไม่มีใน Faster-Whisper
    3. ช้า → เร็วกว่า 3-5x
    """
    
    def __init__(
        self,
        model_size: str = "base",
        device: str = "cuda",
        compute_type: str = "float16",
        language: str = "th"
    ):
        """
        Args:
            model_size: tiny, base, small, medium, large-v2
            device: cuda หรือ cpu
            compute_type: float16 (GPU), int8 (CPU)
            language: th, en, auto
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        
        # Auto-adjust compute type
        if device == "cpu" and compute_type == "float16":
            self.compute_type = "int8"
            logger.info("CPU detected, using int8 instead of float16")
        
        # Load model
        self.model = self._load_model()
        
        logger.info(f"✅ Faster-Whisper ready: {model_size} on {device}")
    
    def _load_model(self):
        """Load Faster-Whisper model"""
        try:
            from faster_whisper import WhisperModel
            
            logger.info(f"Loading Faster-Whisper: {self.model_size}")
            
            model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root="models/faster-whisper"
            )
            
            return model
            
        except ImportError:
            logger.error("Faster-Whisper not installed!")
            logger.error("Install: pip install faster-whisper")
            raise
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
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
            # 1. Preprocess audio
            audio = self._preprocess_audio(audio_bytes, sample_rate)
            
            if audio is None or len(audio) == 0:
                logger.warning("Audio preprocessing failed")
                return None
            
            # 2. Save to temp file (Faster-Whisper needs file)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = Path(f.name)
            
            try:
                # Save audio
                sf.write(str(temp_path), audio, 16000, subtype='PCM_16')
                
                # 3. Transcribe
                segments, info = self.model.transcribe(
                    str(temp_path),
                    language=self.language if self.language != 'auto' else None,
                    beam_size=5,
                    vad_filter=True,  # Voice Activity Detection
                    vad_parameters=dict(
                        min_silence_duration_ms=500,  # ความเงียบขั้นต่ำ
                        threshold=0.5
                    )
                )
                
                # 4. Join segments
                text = " ".join([segment.text for segment in segments]).strip()
                
                if text:
                    logger.info(f"✅ Transcribed: {text}")
                    return text
                else:
                    logger.warning("Empty transcription")
                    return None
                    
            finally:
                # Cleanup temp file
                temp_path.unlink(missing_ok=True)
                
        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            return None
    
    def _preprocess_audio(
        self,
        audio_bytes: bytes,
        source_sr: int
    ) -> Optional[np.ndarray]:
        """
        Preprocess audio สำหรับ Whisper
        แก้ปัญหา: รับเสียงไม่ตรงกับที่พูด
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
            
            # 5. Normalize (สำคัญ! แก้ปัญหาเสียงเบาเกินไป)
            max_val = np.abs(audio).max()
            if max_val > 0:
                # Amplify if too quiet
                if max_val < 0.1:
                    audio = audio / max_val * 0.5
                else:
                    audio = audio / max_val * 0.95
            
            # 6. Resample to 16kHz
            if source_sr != 16000:
                from scipy import signal as scipy_signal
                num_samples = int(len(audio) * 16000 / source_sr)
                audio = scipy_signal.resample(audio, num_samples)
            
            # 7. Remove silence at start/end
            audio = self._trim_silence(audio)
            
            # 8. Check duration
            duration = len(audio) / 16000
            if duration < 0.3:
                logger.debug(f"Audio too short: {duration:.2f}s")
                return None
            
            if duration > 30:
                logger.debug(f"Audio too long: {duration:.2f}s, trimming")
                audio = audio[:30*16000]
            
            # 9. Final checks
            if np.isnan(audio).any() or np.isinf(audio).any():
                logger.error("Audio contains NaN or Inf")
                return None
            
            logger.debug(f"Audio preprocessed: {duration:.2f}s, RMS={np.sqrt(np.mean(audio**2)):.4f}")
            
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
            # Find non-silent regions
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
            start = max(0, start - 160)  # 10ms padding
            end = min(len(audio), end + 160)
            
            return audio[start:end]
            
        except:
            return audio
    
    def get_stats(self) -> dict:
        """Get statistics"""
        return {
            'model': self.model_size,
            'device': self.device,
            'compute_type': self.compute_type,
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
    Convenience function for transcription
    
    Args:
        audio_bytes: Raw audio bytes
        sample_rate: Sample rate
        model_size: Whisper model size
        device: cuda or cpu
        language: Language code
    
    Returns:
        Transcribed text or None
    """
    stt = FasterWhisperSTT(
        model_size=model_size,
        device=device,
        language=language
    )
    
    return await stt.transcribe(audio_bytes, sample_rate)


# Installation instructions
"""
To use Faster-Whisper:

1. Install:
   pip install faster-whisper

2. For GPU support:
   pip install nvidia-cublas-cu11  # CUDA 11.x
   # or
   pip install nvidia-cublas-cu12  # CUDA 12.x

3. Usage:
   from audio.faster_whisper_stt import FasterWhisperSTT
   
   stt = FasterWhisperSTT(model_size="base", device="cuda")
   text = await stt.transcribe(audio_bytes, sample_rate=48000)

Benefits over regular Whisper:
- 3-5x faster
- Better GPU utilization
- Built-in VAD (Voice Activity Detection)
- No tensor dimension errors
- More stable
"""