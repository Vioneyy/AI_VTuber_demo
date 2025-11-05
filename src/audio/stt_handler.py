"""
STT Handler - แก้ไข Tensor Error และป้องกันโมเดลนิ่ง
"""
import numpy as np
import torch
import logging
import asyncio
from pathlib import Path
import subprocess
import tempfile
import soundfile as sf
from typing import Optional, Tuple

# โหลดค่า config จาก .env ถ้ามี เพื่อสร้าง singleton ให้ main.py ใช้งาน
try:
    # main.py เพิ่ม src ลงใน sys.path แล้ว จึง import แบบ absolute ได้
    from config import Config as AppConfig
except Exception:
    AppConfig = None

logger = logging.getLogger(__name__)

class STTHandler:
    """
    Speech-to-Text Handler
    แก้ไขปัญหา:
    1. Tensor dimension mismatch (size a != size b)
    2. โมเดลนิ่งเมื่อ error
    3. Fallback ระหว่าง whisper.cpp และ Python Whisper
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
            model_name: Whisper model (tiny/base/small/medium/large)
            device: Device (cpu/cuda)
            language: Language (th/en/auto)
            use_cpp: ใช้ whisper.cpp หรือไม่
            cpp_binary_path: Path ไปยัง whisper.cpp binary
            cpp_model_path: Path ไปยัง whisper.cpp model
        """
        self.model_name = model_name
        self.device = device
        self.language = language
        
        # Check CUDA
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA not available, using CPU")
            self.device = "cpu"
        
        # Whisper.cpp
        self.use_cpp = use_cpp
        self.cpp_available = False
        
        if use_cpp:
            self.cpp_available = self._check_cpp_available(
                cpp_binary_path,
                cpp_model_path
            )
            if self.cpp_available:
                self.cpp_binary_path = Path(cpp_binary_path)
                self.cpp_model_path = Path(cpp_model_path)
                logger.info(f"✅ ใช้ Whisper.cpp: {cpp_binary_path}")
            else:
                logger.warning(f"⚠️ ไม่พบ Whisper.cpp: {cpp_binary_path}")
                logger.info("🔁 ใช้ Python Whisper fallback")
        
        # Load Python Whisper
        self.model = None
        if not self.cpp_available:
            self.model = self._load_python_whisper()
        
        # Stats
        self.total_transcriptions = 0
        self.failed_transcriptions = 0
    
    def _check_cpp_available(
        self,
        binary_path: Optional[str],
        model_path: Optional[str]
    ) -> bool:
        """ตรวจสอบ whisper.cpp"""
        try:
            if not binary_path or not model_path:
                return False
            
            binary = Path(binary_path)
            model = Path(model_path)
            
            if not binary.exists():
                logger.debug(f"Binary not found: {binary}")
                return False
            
            if not model.exists():
                logger.debug(f"Model not found: {model}")
                return False
            
            # Test run
            result = subprocess.run(
                [str(binary), "--help"],
                capture_output=True,
                timeout=5
            )
            
            return result.returncode == 0
            
        except Exception as e:
            logger.debug(f"Whisper.cpp check failed: {e}")
            return False
    
    def _load_python_whisper(self):
        """โหลด Python Whisper"""
        try:
            import whisper
            
            logger.info(f"⬇️ กำลังโหลดโมเดล Python Whisper: {self.model_name} ({self.device})")
            model = whisper.load_model(self.model_name, device=self.device)
            logger.info("✅ Python Whisper พร้อมใช้งาน")
            
            return model
            
        except Exception as e:
            logger.error(f"❌ โหลด Python Whisper ล้มเหลว: {e}", exc_info=True)
            raise
    
    async def transcribe(
        self,
        audio_data: bytes,
        sample_rate: int = 48000
    ) -> Optional[str]:
        """
        Transcribe audio to text
        
        Args:
            audio_data: Raw audio bytes (จาก Discord)
            sample_rate: Sample rate (Discord = 48000)
        
        Returns:
            Transcribed text or None
        """
        try:
            self.total_transcriptions += 1
            
            # 1. Preprocess audio (แก้ไข tensor dimension issues)
            audio_np = self._preprocess_audio(audio_data, sample_rate)
            
            if audio_np is None or len(audio_np) == 0:
                logger.warning("⚠️ Audio preprocessing failed")
                self.failed_transcriptions += 1
                return None
            
            # 2. Validate audio
            if not self._validate_audio(audio_np):
                logger.warning("⚠️ Audio validation failed")
                self.failed_transcriptions += 1
                return None
            
            # 3. Transcribe
            if self.cpp_available:
                logger.debug("🔁 ใช้ Whisper.cpp")
                text = await self._transcribe_cpp(audio_np)
                if text:
                    return text
                logger.warning("⚠️ Whisper.cpp ล้มเหลว, ใช้ Python Whisper")
            
            # Fallback to Python Whisper
            logger.debug("🔁 ใช้ Python Whisper fallback (ไม่พบ Whisper.cpp)")
            text = await self._transcribe_python(audio_np)
            
            return text
            
        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}", exc_info=True)
            self.failed_transcriptions += 1
            return None

    async def transcribe_audio(
        self,
        audio_data: bytes,
        sample_rate: int = 48000
    ) -> Optional[str]:
        """alias ให้เข้ากับ main.py/Discord adapter"""
        return await self.transcribe(audio_data, sample_rate)
    
    def _preprocess_audio(
        self,
        audio_bytes: bytes,
        source_sr: int
    ) -> Optional[np.ndarray]:
        """
        Preprocess audio สำหรับ Whisper
        แก้ไขปัญหา tensor dimension mismatch
        """
        try:
            # 1. Convert bytes to numpy (Discord = int16 PCM stereo)
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
            
            if len(audio_np) == 0:
                return None
            
            # 2. Convert to float32 [-1, 1]
            audio_np = audio_np.astype(np.float32) / 32768.0
            
            # 3. Convert stereo to mono (Discord = 2 channels)
            if len(audio_np) % 2 == 0:  # Stereo
                audio_np = audio_np.reshape(-1, 2).mean(axis=1)
            
            # 4. Resample to 16kHz (Whisper requirement)
            if source_sr != 16000:
                from scipy import signal as scipy_signal
                num_samples = int(len(audio_np) * 16000 / source_sr)
                audio_np = scipy_signal.resample(audio_np, num_samples)
            
            # 5. Normalize
            max_val = np.abs(audio_np).max()
            if max_val > 0:
                audio_np = audio_np * (0.95 / max_val)
            
            # 6. Remove silence
            audio_np = self._remove_silence(audio_np)
            
            # 7. Fix length (สำคัญ! แก้ tensor dimension error)
            audio_np = self._fix_length_for_whisper(audio_np)
            
            # 8. Final validation
            if len(audio_np) == 0:
                return None
            
            # Ensure float32
            audio_np = audio_np.astype(np.float32)
            
            return audio_np
            
        except Exception as e:
            logger.error(f"Audio preprocessing error: {e}", exc_info=True)
            return None
    
    def _remove_silence(
        self,
        audio: np.ndarray,
        threshold: float = 0.01
    ) -> np.ndarray:
        """ตัดช่วงเงียบออก"""
        try:
            # หา energy
            window_size = int(0.02 * 16000)  # 20ms
            hop_size = window_size // 2
            
            if len(audio) < window_size:
                return audio
            
            energy = np.array([
                np.sqrt(np.mean(audio[i:i+window_size]**2))
                for i in range(0, len(audio) - window_size, hop_size)
            ])
            
            # หาส่วนที่มีเสียง
            voice_mask = energy > threshold
            
            if not voice_mask.any():
                return audio
            
            # Expand mask
            voice_indices = np.repeat(voice_mask, hop_size)
            voice_indices = voice_indices[:len(audio)]
            
            # Pad ถ้าสั้นเกินไป
            if len(voice_indices) < len(audio):
                voice_indices = np.pad(
                    voice_indices,
                    (0, len(audio) - len(voice_indices)),
                    constant_values=True
                )
            
            # ตัดเงียบออก
            audio = audio[voice_indices]
            
            return audio
            
        except Exception as e:
            logger.warning(f"Silence removal failed: {e}")
            return audio
    
    def _fix_length_for_whisper(
        self,
        audio: np.ndarray,
        min_duration: float = 0.5,
        max_duration: float = 30.0
    ) -> np.ndarray:
        """
        แก้ไขความยาวให้เหมาะกับ Whisper
        สำคัญมาก! นี่คือจุดที่แก้ tensor dimension error
        """
        try:
            sr = 16000
            min_samples = int(min_duration * sr)
            max_samples = int(max_duration * sr)
            
            current_samples = len(audio)
            
            # ถ้าสั้นเกินไป: pad ด้วย zeros ให้ถึงขั้นต่ำ
            if current_samples < min_samples:
                padding = min_samples - current_samples
                logger.debug(
                    f"Audio too short: {current_samples/sr:.2f}s (min: {min_duration}s), "
                    f"padding {padding} samples"
                )
                audio = np.pad(audio, (0, padding), mode='constant', constant_values=0)
            
            # ถ้ายาวเกินไป: ตัด
            if current_samples > max_samples:
                logger.debug(f"Audio too long: {current_samples/sr:.2f}s, trimming to {max_duration}s")
                audio = audio[:max_samples]
            
            # สำคัญ! Pad ให้เป็นความยาวที่ Whisper ชอบ
            # Whisper ทำงานดีกับ audio ที่มีความยาวเป็นจำนวนเต็มของ 0.02s (320 samples)
            target_length = ((len(audio) + 319) // 320) * 320
            
            if len(audio) < target_length:
                padding = target_length - len(audio)
                audio = np.pad(audio, (0, padding), mode='constant', constant_values=0)
            
            return audio
            
        except Exception as e:
            logger.error(f"Length fixing failed: {e}")
            return audio
    
    def _validate_audio(self, audio: np.ndarray) -> bool:
        """Validate audio"""
        try:
            # Check empty
            if len(audio) == 0:
                return False
            
            # Check duration
            duration = len(audio) / 16000
            if duration < 0.5:
                logger.debug(f"Audio too short: {duration:.2f}s")
                return False
            
            if duration > 30:
                logger.warning(f"Audio too long: {duration:.2f}s")
                return False
            
            # Check dtype
            if audio.dtype != np.float32:
                logger.warning(f"Invalid dtype: {audio.dtype}")
                return False
            
            # Check range
            if np.abs(audio).max() > 10:
                logger.warning(f"Audio out of range: {audio.min():.2f} to {audio.max():.2f}")
                return False
            
            # Check for NaN/Inf
            if np.isnan(audio).any() or np.isinf(audio).any():
                logger.error("Audio contains NaN or Inf")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
    async def _transcribe_python(self, audio: np.ndarray) -> Optional[str]:
        """
        Transcribe ด้วย Python Whisper
        มี retry logic เพื่อแก้ tensor errors
        """
        if self.model is None:
            logger.error("Python Whisper model not loaded")
            return None
        
        try:
            # ลอง transcribe (อาจเกิด tensor error)
            loop = asyncio.get_event_loop()
            
            result = await loop.run_in_executor(
                None,
                self._transcribe_with_retry,
                audio
            )
            
            if result:
                text = result['text'].strip()
                if text:
                    logger.info(f"✅ Transcribed: {text}")
                    return text
            
            logger.warning("⚠️ Empty transcription")
            return None
            
        except Exception as e:
            logger.error(f"❌ Python Whisper error: {e}", exc_info=True)
            return None
    
    def _transcribe_with_retry(self, audio: np.ndarray) -> Optional[dict]:
        """
        Transcribe with retry logic
        แก้ไข tensor dimension errors โดยลอง config ต่างๆ
        """
        configs = [
            # Config 1: fp16 on GPU (default)
            {'fp16': True, 'device': self.device},
            
            # Config 2: fp32 on GPU
            {'fp16': False, 'device': self.device},
            
            # Config 3: CPU fallback
            {'fp16': False, 'device': 'cpu'}
        ]
        
        for i, config in enumerate(configs):
            try:
                logger.debug(f"Attempt {i+1}: fp16={config['fp16']}, device={config['device']}")
                
                result = self.model.transcribe(
                    audio,
                    language=self.language if self.language != 'auto' else None,
                    task='transcribe',
                    fp16=config['fp16'],
                    verbose=False
                )
                
                return result
                
            except RuntimeError as e:
                error_msg = str(e)
                
                if "size of tensor" in error_msg:
                    logger.warning(f"⚠️ Attempt {i+1} failed: Tensor dimension mismatch")
                    
                    if i < len(configs) - 1:
                        logger.info(f"   🔄 Retrying with different config...")
                        continue
                    else:
                        logger.error("❌ All retry attempts failed")
                        return None
                else:
                    logger.error(f"❌ Whisper error: {e}")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}")
                return None
        
        return None
    
    async def _transcribe_cpp(self, audio: np.ndarray) -> Optional[str]:
        """Transcribe ด้วย whisper.cpp"""
        try:
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = Path(f.name)
            
            # Save audio
            sf.write(str(temp_path), audio, 16000, subtype='PCM_16')
            
            # Run whisper.cpp
            cmd = [
                str(self.cpp_binary_path),
                '-m', str(self.cpp_model_path),
                '-f', str(temp_path),
                '-l', self.language,
                '--output-txt',
                '--no-timestamps'
            ]
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            )
            
            # Clean up
            temp_path.unlink(missing_ok=True)
            
            if result.returncode == 0:
                text = result.stdout.strip()
                if text:
                    logger.info(f"✅ Transcribed (cpp): {text}")
                    return text
            else:
                logger.error(f"whisper.cpp error: {result.stderr}")
            
            return None
            
        except Exception as e:
            logger.error(f"whisper.cpp transcription failed: {e}")
            return None
    
    def get_stats(self) -> dict:
        """ดูสถิติ"""
        success_rate = 0
        if self.total_transcriptions > 0:
            success_rate = (
                (self.total_transcriptions - self.failed_transcriptions) 
                / self.total_transcriptions 
                * 100
            )
        
        return {
            'total': self.total_transcriptions,
            'failed': self.failed_transcriptions,
            'success_rate': f"{success_rate:.1f}%",
            'using_cpp': self.cpp_available
        }

# ===== Global singleton สำหรับใช้งานทั้งแอป =====
# ตรงกับรูปแบบใน main.py: from audio.stt_handler import stt_handler
def _create_global_stt_handler() -> STTHandler:
    """สร้างอินสแตนซ์ STTHandler โดยอิงค่าจาก .env ผ่าน Config"""
    # ค่าเริ่มต้นที่ปลอดภัย
    model_name = "base"
    device = "cpu"
    language = "th"
    use_cpp = False
    cpp_bin = None
    cpp_model = None

    # ใช้ค่าในไฟล์ .env ผ่าน Config หากมี
    try:
        if AppConfig is not None:
            model_name = getattr(AppConfig, 'WHISPER_MODEL', model_name)
            device = getattr(AppConfig, 'WHISPER_DEVICE', device)
            language = getattr(AppConfig, 'WHISPER_LANG', language)
            use_cpp = bool(getattr(AppConfig, 'WHISPER_CPP_ENABLED', False))
            cpp_bin = getattr(AppConfig, 'WHISPER_CPP_BIN_PATH', None)
            cpp_model = getattr(AppConfig, 'WHISPER_CPP_MODEL_PATH', None)
    except Exception:
        # หากอ่านค่าไม่ได้ ให้ใช้ดีฟอลต์
        pass

    return STTHandler(
        model_name=model_name,
        device=device,
        language=language,
        use_cpp=use_cpp,
        cpp_binary_path=cpp_bin,
        cpp_model_path=cpp_model,
    )


# สร้าง singleton เมื่อโมดูลถูก import
stt_handler: STTHandler = _create_global_stt_handler()

__all__ = ["STTHandler", "stt_handler"]