"""
Whisper Wrapper
แก้ไขปัญหา:
1. Tensor dimension mismatch errors
2. Mel spectrogram dimension issues
3. Fallback ระหว่าง whisper.cpp และ Python whisper
"""
import numpy as np
import torch
import logging
from typing import Optional, Dict, Tuple
from pathlib import Path
import subprocess
import json

logger = logging.getLogger(__name__)

class WhisperWrapper:
    """
    Wrapper สำหรับ Whisper STT
    - ลอง whisper.cpp ก่อน (ถ้ามี)
    - Fallback เป็น Python whisper
    - แก้ไข tensor dimension errors
    """
    
    def __init__(
        self,
        model_name: str = "base",
        device: str = "cuda",
        language: str = "th",
        use_cpp: bool = False,
        cpp_binary_path: Optional[str] = None,
        cpp_model_path: Optional[str] = None
    ):
        """
        Args:
            model_name: Whisper model size (tiny/base/small/medium/large)
            device: Device to use (cpu/cuda)
            language: Language code (th/en/auto)
            use_cpp: พยายามใช้ whisper.cpp ก่อน
            cpp_binary_path: Path to whisper.cpp binary
            cpp_model_path: Path to whisper.cpp model
        """
        self.model_name = model_name
        self.device = device
        self.language = language
        
        # Check CUDA availability
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA not available, using CPU")
            self.device = "cpu"
        
        # Try to use whisper.cpp first
        self.use_cpp = use_cpp
        self.cpp_available = False
        
        if use_cpp:
            self.cpp_available = self._check_cpp_available(
                cpp_binary_path,
                cpp_model_path
            )
            if self.cpp_available:
                self.cpp_binary_path = cpp_binary_path
                self.cpp_model_path = cpp_model_path
                logger.info(f"✅ Using whisper.cpp: {cpp_binary_path}")
            else:
                logger.warning("whisper.cpp not available, using Python whisper")
        
        # Load Python whisper as fallback
        if not self.cpp_available:
            self.model = self._load_python_whisper()
    
    def _check_cpp_available(
        self,
        binary_path: Optional[str],
        model_path: Optional[str]
    ) -> bool:
        """ตรวจสอบว่า whisper.cpp ใช้งานได้หรือไม่"""
        try:
            if not binary_path or not model_path:
                return False
            
            binary = Path(binary_path)
            model = Path(model_path)
            
            if not binary.exists():
                logger.warning(f"whisper.cpp binary not found: {binary}")
                return False
            
            if not model.exists():
                logger.warning(f"whisper.cpp model not found: {model}")
                return False
            
            # Test run
            result = subprocess.run(
                [str(binary), "--help"],
                capture_output=True,
                timeout=5
            )
            
            return result.returncode == 0
            
        except Exception as e:
            logger.warning(f"whisper.cpp check failed: {e}")
            return False
    
    def _load_python_whisper(self):
        """โหลด Python whisper"""
        try:
            import whisper
            
            logger.info(f"Loading Whisper model: {self.model_name} on {self.device}")
            model = whisper.load_model(self.model_name, device=self.device)
            logger.info("✅ Whisper model loaded")
            
            return model
            
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}", exc_info=True)
            raise
    
    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000
    ) -> Optional[str]:
        """
        Transcribe audio to text
        
        Args:
            audio: Audio data (numpy array)
            sample_rate: Sample rate (should be 16000 for Whisper)
        
        Returns:
            Transcribed text or None if failed
        """
        try:
            # Validate input
            if not self._validate_audio(audio, sample_rate):
                return None
            
            # Preprocess audio for Whisper
            audio = self._prepare_audio_for_whisper(audio, sample_rate)
            
            # Try whisper.cpp first
            if self.cpp_available:
                text = self._transcribe_cpp(audio, sample_rate)
                if text:
                    return text
                logger.warning("whisper.cpp failed, falling back to Python")
            
            # Use Python whisper
            return self._transcribe_python(audio)
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            return None
    
    def _validate_audio(self, audio: np.ndarray, sample_rate: int) -> bool:
        """ตรวจสอบความถูกต้องของ audio input"""
        try:
            # Check if empty
            if len(audio) == 0:
                logger.warning("Empty audio")
                return False
            
            # Check sample rate
            if sample_rate != 16000:
                logger.warning(f"Invalid sample rate: {sample_rate} (expected 16000)")
                return False
            
            # Check duration
            duration = len(audio) / sample_rate
            if duration < 0.1:
                logger.warning(f"Audio too short: {duration}s")
                return False
            
            if duration > 30:
                logger.warning(f"Audio too long: {duration}s (will be trimmed)")
            
            # Check dtype
            if audio.dtype not in [np.float32, np.float64]:
                logger.warning(f"Invalid dtype: {audio.dtype}")
                return False
            
            # Check range
            if np.abs(audio).max() > 10:
                logger.warning(f"Audio values out of range: {audio.min()}-{audio.max()}")
                return False
            
            # Check for NaN/Inf
            if np.isnan(audio).any() or np.isinf(audio).any():
                logger.error("Audio contains NaN or Inf")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Audio validation failed: {e}")
            return False
    
    def _prepare_audio_for_whisper(
        self,
        audio: np.ndarray,
        sample_rate: int
    ) -> np.ndarray:
        """
        เตรียม audio สำหรับ Whisper
        แก้ไขปัญหา tensor dimension mismatch
        """
        try:
            # Ensure float32
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)
            
            # Ensure 1D
            if audio.ndim > 1:
                audio = audio.flatten()
            
            # Normalize to [-1, 1]
            max_val = np.abs(audio).max()
            if max_val > 0:
                audio = audio / max_val
            
            # Pad to 30 seconds (Whisper's max)
            max_samples = 30 * sample_rate
            if len(audio) < max_samples:
                # Pad with zeros
                padding = max_samples - len(audio)
                audio = np.pad(audio, (0, padding), mode='constant')
            elif len(audio) > max_samples:
                # Trim
                audio = audio[:max_samples]
            
            # Final validation
            assert audio.shape == (max_samples,), f"Unexpected shape: {audio.shape}"
            assert audio.dtype == np.float32, f"Unexpected dtype: {audio.dtype}"
            assert not np.isnan(audio).any(), "Audio contains NaN"
            assert not np.isinf(audio).any(), "Audio contains Inf"
            
            return audio
            
        except Exception as e:
            logger.error(f"Audio preparation failed: {e}", exc_info=True)
            raise
    
    def _transcribe_python(self, audio: np.ndarray) -> Optional[str]:
        """Transcribe ด้วย Python whisper"""
        try:
            # Whisper expects float32 audio in [-1, 1]
            logger.debug(f"Transcribing with Python Whisper (device: {self.device})")
            
            # Transcribe
            result = self.model.transcribe(
                audio,
                language=self.language if self.language != 'auto' else None,
                task='transcribe',
                fp16=(self.device == 'cuda'),  # Use FP16 on GPU
                verbose=False
            )
            
            text = result['text'].strip()
            
            if text:
                logger.info(f"Transcribed: {text}")
                return text
            else:
                logger.warning("Empty transcription")
                return None
                
        except RuntimeError as e:
            if "size of tensor" in str(e):
                logger.error(
                    "Tensor dimension mismatch - this is likely due to corrupted audio input. "
                    "Try preprocessing the audio better."
                )
            else:
                logger.error(f"Python Whisper transcription failed: {e}", exc_info=True)
            return None
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            return None
    
    def _transcribe_cpp(
        self,
        audio: np.ndarray,
        sample_rate: int
    ) -> Optional[str]:
        """Transcribe ด้วย whisper.cpp"""
        try:
            import tempfile
            import soundfile as sf
            
            # Save audio to temp file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name
                sf.write(temp_path, audio, sample_rate, subtype='PCM_16')
            
            # Run whisper.cpp
            cmd = [
                str(self.cpp_binary_path),
                '-m', str(self.cpp_model_path),
                '-f', temp_path,
                '-l', self.language,
                '--output-txt',
                '--no-timestamps'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)
            
            if result.returncode == 0:
                # Parse output
                text = result.stdout.strip()
                if text:
                    logger.info(f"Transcribed (cpp): {text}")
                    return text
            else:
                logger.error(f"whisper.cpp failed: {result.stderr}")
            
            return None
            
        except Exception as e:
            logger.error(f"whisper.cpp transcription failed: {e}")
            return None
    
    def transcribe_file(self, audio_path: str) -> Optional[str]:
        """Transcribe จากไฟล์"""
        try:
            import soundfile as sf
            
            # Load audio file
            audio, sr = sf.read(audio_path)
            
            # Transcribe
            return self.transcribe(audio, sr)
            
        except Exception as e:
            logger.error(f"Failed to transcribe file: {e}")
            return None


# Helper function
def transcribe_audio(
    audio: np.ndarray,
    sample_rate: int = 16000,
    model_name: str = "base",
    device: str = "cuda",
    language: str = "th"
) -> Optional[str]:
    """
    Convenience function สำหรับ transcribe audio
    
    Args:
        audio: Audio data (numpy array)
        sample_rate: Sample rate
        model_name: Whisper model size
        device: Device to use
        language: Language code
    
    Returns:
        Transcribed text or None
    """
    whisper = WhisperWrapper(
        model_name=model_name,
        device=device,
        language=language
    )
    
    return whisper.transcribe(audio, sample_rate)