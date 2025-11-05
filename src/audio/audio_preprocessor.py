"""
Audio Preprocessor
แก้ไขปัญหา:
1. FFmpeg packet loss
2. Sample rate/channel mismatch
3. Tensor dimension errors in Whisper
4. Float/Int16 format issues
"""
import numpy as np
import logging
from typing import Tuple, Optional
import io

logger = logging.getLogger(__name__)

class AudioPreprocessor:
    """
    ประมวลผลเสียงก่อนส่งไปยัง STT
    - Normalize sample rate
    - Convert to mono
    - Fix format issues
    - Pad/trim to correct length
    """
    
    def __init__(
        self,
        target_sample_rate: int = 16000,
        target_channels: int = 1,
        target_dtype: str = 'float32'
    ):
        """
        Args:
            target_sample_rate: Sample rate ที่ต้องการ (Whisper = 16000)
            target_channels: จำนวนช่อง (1=mono, 2=stereo)
            target_dtype: Data type ('float32' หรือ 'int16')
        """
        self.target_sample_rate = target_sample_rate
        self.target_channels = target_channels
        self.target_dtype = target_dtype
        
        logger.info(
            f"Audio Preprocessor: {target_sample_rate}Hz, "
            f"{target_channels}ch, {target_dtype}"
        )
    
    def preprocess_discord_audio(
        self,
        audio_data: bytes,
        source_sample_rate: int = 48000,
        source_channels: int = 2
    ) -> Tuple[np.ndarray, int]:
        """
        ประมวลผลเสียงจาก Discord
        
        Args:
            audio_data: Raw audio bytes จาก Discord
            source_sample_rate: Sample rate ต้นทาง (Discord = 48000)
            source_channels: จำนวนช่องต้นทาง (Discord = 2)
        
        Returns:
            (processed_audio, sample_rate)
        """
        try:
            # 1. แปลง bytes เป็น numpy array
            audio_np = self._bytes_to_numpy(
                audio_data,
                source_sample_rate,
                source_channels
            )
            
            # 2. ตรวจสอบว่ามีข้อมูลหรือไม่
            if len(audio_np) == 0:
                logger.warning("Empty audio data")
                return None, None
            
            # 3. Convert to mono ถ้าจำเป็น
            if source_channels > 1 and self.target_channels == 1:
                audio_np = self._to_mono(audio_np, source_channels)
            
            # 4. Resample ถ้าจำเป็น
            if source_sample_rate != self.target_sample_rate:
                audio_np = self._resample(
                    audio_np,
                    source_sample_rate,
                    self.target_sample_rate
                )
            
            # 5. Normalize
            audio_np = self._normalize(audio_np)
            
            # 6. Remove silence (optional)
            audio_np = self._remove_silence(audio_np)
            
            # 7. Pad/Trim to valid length
            audio_np = self._fix_length(audio_np)
            
            # 8. Convert dtype
            audio_np = self._convert_dtype(audio_np, self.target_dtype)
            
            logger.info(
                f"Preprocessed audio: {len(audio_np)} samples, "
                f"{len(audio_np)/self.target_sample_rate:.2f}s"
            )
            
            return audio_np, self.target_sample_rate
            
        except Exception as e:
            logger.error(f"Audio preprocessing failed: {e}", exc_info=True)
            return None, None
    
    def _bytes_to_numpy(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        channels: int
    ) -> np.ndarray:
        """แปลง bytes เป็น numpy array"""
        try:
            # Discord ส่งมาเป็น int16 PCM
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
            
            # Convert to float32 (-1.0 to 1.0)
            audio_np = audio_np.astype(np.float32) / 32768.0
            
            return audio_np
            
        except Exception as e:
            logger.error(f"Bytes to numpy conversion failed: {e}")
            return np.array([], dtype=np.float32)
    
    def _to_mono(self, audio: np.ndarray, channels: int) -> np.ndarray:
        """แปลงเป็น mono"""
        try:
            if channels == 2:
                # Reshape to (samples, 2) และเอาค่าเฉลี่ย
                audio = audio.reshape(-1, 2)
                audio = audio.mean(axis=1)
            elif channels > 2:
                # Multi-channel: reshape และเอาค่าเฉลี่ย
                audio = audio.reshape(-1, channels)
                audio = audio.mean(axis=1)
            
            return audio
            
        except Exception as e:
            logger.error(f"To mono conversion failed: {e}")
            return audio
    
    def _resample(
        self,
        audio: np.ndarray,
        orig_sr: int,
        target_sr: int
    ) -> np.ndarray:
        """Resample audio"""
        try:
            from scipy import signal
            
            # คำนวณจำนวน samples ใหม่
            num_samples = int(len(audio) * target_sr / orig_sr)
            
            # Resample
            audio = signal.resample(audio, num_samples)
            
            return audio
            
        except Exception as e:
            logger.error(f"Resampling failed: {e}")
            return audio
    
    def _normalize(self, audio: np.ndarray) -> np.ndarray:
        """Normalize audio to [-1, 1]"""
        try:
            # หา max absolute value
            max_val = np.abs(audio).max()
            
            if max_val > 0:
                # Normalize with headroom (0.95 instead of 1.0)
                audio = audio * (0.95 / max_val)
            
            return audio
            
        except Exception as e:
            logger.error(f"Normalization failed: {e}")
            return audio
    
    def _remove_silence(
        self,
        audio: np.ndarray,
        threshold: float = 0.01,
        min_silence_duration: float = 0.5
    ) -> np.ndarray:
        """
        ตัดช่วงเงียบออก
        
        Args:
            threshold: ระดับเสียงต่ำกว่านี้ถือว่าเงียบ
            min_silence_duration: ช่วงเงียบขั้นต่ำที่จะตัด (วินาที)
        """
        try:
            # คำนวณ RMS energy
            window_size = int(0.02 * self.target_sample_rate)  # 20ms
            hop_size = window_size // 2
            
            energy = np.array([
                np.sqrt(np.mean(audio[i:i+window_size]**2))
                for i in range(0, len(audio) - window_size, hop_size)
            ])
            
            # หาจุดที่มีเสียง
            voice_mask = energy > threshold
            
            # Expand mask กลับเป็นขนาดเดิม
            voice_indices = np.repeat(voice_mask, hop_size)
            voice_indices = voice_indices[:len(audio)]
            
            # Pad ถ้าสั้นเกินไป
            if len(voice_indices) < len(audio):
                voice_indices = np.pad(
                    voice_indices,
                    (0, len(audio) - len(voice_indices)),
                    constant_values=True
                )
            
            # เก็บแค่ส่วนที่มีเสียง
            if voice_indices.any():
                audio = audio[voice_indices]
            
            return audio
            
        except Exception as e:
            logger.warning(f"Silence removal failed: {e}")
            return audio
    
    def _fix_length(
        self,
        audio: np.ndarray,
        min_length: float = 0.5,
        max_length: float = 30.0
    ) -> np.ndarray:
        """
        แก้ไขความยาวของเสียง
        
        Args:
            min_length: ความยาวขั้นต่ำ (วินาที)
            max_length: ความยาวสูงสุด (วินาที)
        """
        try:
            min_samples = int(min_length * self.target_sample_rate)
            max_samples = int(max_length * self.target_sample_rate)
            
            current_samples = len(audio)
            
            # ถ้าสั้นเกินไป: pad ด้วย zeros
            if current_samples < min_samples:
                padding = min_samples - current_samples
                audio = np.pad(audio, (0, padding), mode='constant')
                logger.debug(f"Padded audio: {current_samples} -> {len(audio)} samples")
            
            # ถ้ายาวเกินไป: trim
            elif current_samples > max_samples:
                audio = audio[:max_samples]
                logger.debug(f"Trimmed audio: {current_samples} -> {len(audio)} samples")
            
            return audio
            
        except Exception as e:
            logger.error(f"Length fixing failed: {e}")
            return audio
    
    def _convert_dtype(self, audio: np.ndarray, dtype: str) -> np.ndarray:
        """แปลง data type"""
        try:
            if dtype == 'float32':
                return audio.astype(np.float32)
            elif dtype == 'int16':
                # Convert to int16 range
                audio = np.clip(audio, -1.0, 1.0)
                return (audio * 32767).astype(np.int16)
            else:
                return audio
                
        except Exception as e:
            logger.error(f"Dtype conversion failed: {e}")
            return audio
    
    def validate_for_whisper(self, audio: np.ndarray) -> bool:
        """
        ตรวจสอบว่าเสียงพร้อมสำหรับ Whisper หรือไม่
        
        Returns:
            True ถ้าพร้อม
        """
        try:
            # Check dtype
            if audio.dtype not in [np.float32, np.float64]:
                logger.warning(f"Invalid dtype for Whisper: {audio.dtype}")
                return False
            
            # Check range
            if audio.max() > 1.5 or audio.min() < -1.5:
                logger.warning(f"Audio out of range: [{audio.min()}, {audio.max()}]")
                return False
            
            # Check length
            duration = len(audio) / self.target_sample_rate
            if duration < 0.1:
                logger.warning(f"Audio too short: {duration}s")
                return False
            
            if duration > 30:
                logger.warning(f"Audio too long: {duration}s")
                return False
            
            # Check for NaN or Inf
            if np.isnan(audio).any() or np.isinf(audio).any():
                logger.warning("Audio contains NaN or Inf")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False
    
    def save_debug_audio(self, audio: np.ndarray, filename: str):
        """บันทึกไฟล์เสียงเพื่อ debug"""
        try:
            import soundfile as sf
            
            sf.write(
                filename,
                audio,
                self.target_sample_rate,
                subtype='PCM_16'
            )
            logger.info(f"Debug audio saved: {filename}")
            
        except Exception as e:
            logger.error(f"Failed to save debug audio: {e}")


# Helper function
def preprocess_discord_audio(
    audio_bytes: bytes,
    source_sr: int = 48000,
    target_sr: int = 16000
) -> Tuple[Optional[np.ndarray], Optional[int]]:
    """
    Convenience function สำหรับ preprocess เสียงจาก Discord
    
    Args:
        audio_bytes: Raw audio bytes
        source_sr: Source sample rate (Discord = 48000)
        target_sr: Target sample rate (Whisper = 16000)
    
    Returns:
        (processed_audio, sample_rate) or (None, None) if failed
    """
    preprocessor = AudioPreprocessor(
        target_sample_rate=target_sr,
        target_channels=1,
        target_dtype='float32'
    )
    
    return preprocessor.preprocess_discord_audio(
        audio_bytes,
        source_sample_rate=source_sr,
        source_channels=2
    )