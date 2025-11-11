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
import os

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
        # อนุญาตให้ override ด้วย .env หากมีค่า (และไม่ได้ส่งค่าเข้ามาเฉพาะกิจ)
        env_model = os.getenv("WHISPER_MODEL")
        env_device = os.getenv("WHISPER_DEVICE")
        env_lang = os.getenv("WHISPER_LANG")

        self.model_size = env_model or model_size
        self.language = env_lang or language
        
        # Check CUDA
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA not available, using CPU")
            device = "cpu"
        
        self.device = env_device or device

        # ตั้งค่า compute_type จาก .env เพื่อควบคุมความแม่นยำ/ความเร็ว
        # ดีฟอลต์: cuda → float16, cpu → int8 (สำหรับความเร็ว)
        default_compute = "float16" if self.device == "cuda" else "int8"
        self.compute_type = os.getenv("WHISPER_COMPUTE_TYPE", default_compute)

        # เลือก backend: พยายามใช้ faster-whisper ก่อน ถ้าไม่พร้อมให้ fallback เป็น whisper ปกติ
        self.backend = None
        self.model = self._load_model()
        
        logger.info(f"✅ Hybrid STT ready: {self.model_size} on {self.device} ({self.compute_type})")

    def _switch_to_cpu_faster_whisper(self) -> bool:
        """สลับไปใช้ Faster-Whisper แบบ CPU เมื่อ CUDA ล้มเหลว"""
        try:
            from faster_whisper import WhisperModel
            # หากผู้ใช้ต้องการความแม่นยำสูงสุด ให้ตั้ง WHISPER_COMPUTE_TYPE=float32 ใน .env
            fallback_compute = os.getenv("WHISPER_COMPUTE_TYPE", "float32")
            logger.info(f"🔁 Switching Faster-Whisper to CPU ({fallback_compute})")
            self.device = "cpu"
            self.compute_type = fallback_compute
            self.model = WhisperModel(self.model_size, device="cpu", compute_type=self.compute_type)
            self.backend = "faster_whisper"
            logger.info("✅ Faster-Whisper CPU model ready")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Failed to switch Faster-Whisper to CPU: {e}")
            return False
    
    def _load_model(self):
        """โหลดโมเดล STT โดยเลือก backend อัตโนมัติ"""
        # ลอง faster-whisper ก่อน
        try:
            from faster_whisper import WhisperModel
            logger.info(f"Loading Faster-Whisper: {self.model_size} on {self.device} ({self.compute_type})")
            model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            self.backend = "faster_whisper"
            logger.info("✅ Faster-Whisper model loaded")
            return model
        except Exception as fe:
            logger.info(f"⚠️ Faster-Whisper not available or failed: {fe}. Falling back to whisper.")

        # fallback: whisper ปกติ
        try:
            import whisper
            logger.info(f"Loading Whisper: {self.model_size} on {self.device}")
            model = whisper.load_model(self.model_size, device=self.device)
            self.backend = "whisper"
            logger.info("✅ Whisper model loaded")
            return model
        except Exception as e:
            logger.error(f"Failed to load any Whisper backend: {e}")
            raise

    def get_status(self) -> dict:
        """คืนค่าภาพรวมสถานะของ STT ณ ปัจจุบัน"""
        return {
            "backend": self.backend,
            "device": self.device,
            "compute_type": getattr(self, "compute_type", None),
            "model_size": self.model_size,
            "language": self.language,
        }
    
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
            text = ""
            if self.backend == "faster_whisper":
                text = await loop.run_in_executor(None, self._transcribe_sync_faster, audio)
                # ถ้าล้มเหลวหรือว่าง ลอง fallback เป็น whisper ปกติ
                if not text:
                    logger.info("🔁 Fallback to Python Whisper backend after Faster-Whisper failure")
                    result = await loop.run_in_executor(None, self._transcribe_sync_whisper, audio)
                    text = (result or {}).get('text', '').strip() if result else ''
            else:
                result = await loop.run_in_executor(None, self._transcribe_sync_whisper, audio)
                text = (result or {}).get('text', '').strip() if result else ''

            if text:
                logger.info(f"✅ Transcribed: {text}")
                return text
            
            logger.warning("Empty transcription")
            return None
            
        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            return None
    
    def _transcribe_sync_whisper(self, audio: np.ndarray) -> Optional[dict]:
        """Synchronous transcribe สำหรับ backend whisper ปกติ"""
        try:
            fp16 = (self.device == "cuda")
            result = self.model.transcribe(
                audio,
                language=self.language if self.language != 'auto' else None,
                task='transcribe',
                fp16=fp16,
                verbose=False,
                condition_on_previous_text=False,
                initial_prompt=None
            )
            return result
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            return None

    def _transcribe_sync_faster(self, audio: np.ndarray) -> str:
        """Synchronous transcribe สำหรับ backend faster-whisper"""
        try:
            lang = None if self.language == 'auto' else self.language
            # ปรับพารามิเตอร์สำหรับความแม่นยำและรวดเร็ว
            beam_size = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
            temperature = float(os.getenv("WHISPER_TEMPERATURE", "0.0"))

            segments, info = self.model.transcribe(
                audio,
                language=lang,
                beam_size=beam_size,
                temperature=temperature,
                vad_filter=True
            )
            # รวมข้อความจากทุก segment
            texts = []
            for seg in segments:
                try:
                    texts.append(seg.text)
                except Exception:
                    continue
            return (" ".join(t.strip() for t in texts)).strip()
        except Exception as e:
            msg = str(e)
            logger.error(f"Faster-Whisper transcription error: {msg}")
            # ตรวจจับปัญหา CUDA/cuBLAS → ลองสลับ CPU แล้วลองอีกครั้ง
            if ("cublas" in msg.lower()) or ("cuda" in msg.lower()) or ("dll" in msg.lower() and "cublas" in msg.lower()):
                if self._switch_to_cpu_faster_whisper():
                    try:
                        lang = None if self.language == 'auto' else self.language
                        beam_size = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
                        temperature = float(os.getenv("WHISPER_TEMPERATURE", "0.0"))
                        segments, info = self.model.transcribe(
                            audio,
                            language=lang,
                            beam_size=beam_size,
                            temperature=temperature,
                            vad_filter=True
                        )
                        texts = []
                        for seg in segments:
                            try:
                                texts.append(seg.text)
                            except Exception:
                                continue
                        return (" ".join(t.strip() for t in texts)).strip()
                    except Exception as e2:
                        logger.error(f"Faster-Whisper CPU fallback error: {e2}")
                        return ""
            return ""
    
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
            # 1. Convert bytes to numpy (Discord PCM int16, mono @48kHz)
            audio = np.frombuffer(audio_bytes, dtype=np.int16)
            
            if len(audio) == 0:
                return None
            
            # 2. Convert to float32 [-1, 1]
            audio = audio.astype(np.float32) / 32768.0

            # ไม่แปลง stereo->mono โดยเดาอีกต่อไป (Discord BasicSink ให้ mono อยู่แล้ว)

            # 3. Remove DC offset
            audio = audio - audio.mean()

            # 4. แก้ปัญหา clipping: normalize ถ้า clipping
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

            # 5. Resample to 16kHz (แก้ปัญหา sample rate mismatch)
            if source_sr != 16000:
                from scipy import signal as scipy_signal
                num_samples = int(len(audio) * 16000 / source_sr)
                audio = scipy_signal.resample(audio, num_samples)

            # 6. Trim silence
            audio = self._trim_silence(audio)

            # 7. Check duration
            duration = len(audio) / 16000
            if duration < 0.3:
                logger.debug(f"Audio too short: {duration:.2f}s")
                return None
            
            if duration > 30:
                logger.debug(f"Audio too long: {duration:.2f}s, trimming")
                audio = audio[:30*16000]

            # 8. Final validation
            if np.isnan(audio).any() or np.isinf(audio).any():
                logger.error("Audio contains NaN or Inf")
                return None

            # 9. Ensure float32
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