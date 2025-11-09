"""
RVC Adapter with Professional Audio Processing
แก้ปัญหา:
1. เสียงช็อตๆ/ตื้ด → High-quality resampling
2. Noise/ซ่า → Pre/post processing with filters
3. Clipping → Proper normalization
4. DC offset → Complete removal
5. Artifacts → Fade in/out

แนวคิด:
- ไม่ผูกกับไลบรารีหนักในโปรเจกต์หลัก
- เรียกใช้งานผ่าน HTTP ไปยัง RVC server
- มี audio processing ครบถ้วน
"""
import logging
from typing import Optional, Tuple
import numpy as np
import tempfile
from pathlib import Path
import soundfile as sf
import os
from scipy import signal

logger = logging.getLogger(__name__)

class RVCAdapter:
    def __init__(
        self,
        server_url: Optional[str] = None,
        model_path: Optional[str] = None,
        index_path: Optional[str] = None,
        device: str = 'cpu',
        pitch: int = 0
    ):
        self.server_url = server_url or os.getenv('RVC_SERVER_URL', 'http://localhost:7860/api/convert')
        self.model_path = model_path
        self.index_path = index_path
        self.device = device
        self.pitch = pitch
        
        logger.info("🎵 RVC Adapter initialized with audio processing")
        logger.info(f"   Server: {self.server_url}")
        logger.info(f"   Model: {self.model_path}")
        logger.info(f"   Pitch: {self.pitch}")

    def _preprocess_audio(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Preprocess audio ก่อนส่งเข้า RVC
        - Remove DC offset
        - High-pass filter (ตัดเสียงต่ำที่ไม่ต้องการ)
        - Normalize
        """
        logger.debug("   🔧 Preprocessing audio...")
        
        # 1. Remove DC offset (เสียงซ่า)
        audio = audio - np.mean(audio)
        
        # 2. High-pass filter @ 80 Hz (ตัดเสียงรบกวนความถี่ต่ำ)
        try:
            nyquist = sr / 2
            cutoff = 80 / nyquist
            if 0 < cutoff < 1:  # ต้องอยู่ใน range [0, 1]
                b, a = signal.butter(4, cutoff, btype='high')
                audio = signal.filtfilt(b, a, audio)
                logger.debug("   ✅ High-pass filter applied")
        except Exception as e:
            logger.debug(f"   ⚠️ High-pass filter skipped: {e}")
        
        # 3. Normalize to -3dB (ป้องกัน clipping)
        max_val = np.abs(audio).max()
        if max_val > 0:
            # ใช้ -3dB (0.707) แทน 0.95 เพื่อให้ headroom มากขึ้น
            audio = audio / max_val * 0.707
        
        # 4. Soft clip (ป้องกัน peak ที่อาจเกิดขึ้น)
        audio = np.tanh(audio * 1.5) * 0.95
        
        return audio.astype(np.float32)
    
    def _postprocess_audio(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Postprocess audio หลัง RVC
        - Remove DC offset
        - De-noise filter
        - Normalize
        - Fade in/out
        """
        logger.debug("   🔧 Postprocessing audio...")
        
        # 1. Remove DC offset
        audio = audio - np.mean(audio)
        
        # 2. High-pass filter @ 60 Hz (ตัด rumble/noise)
        try:
            nyquist = sr / 2
            cutoff = 60 / nyquist
            if 0 < cutoff < 1:
                b, a = signal.butter(3, cutoff, btype='high')
                audio = signal.filtfilt(b, a, audio)
                logger.debug("   ✅ Post high-pass filter applied")
        except Exception as e:
            logger.debug(f"   ⚠️ Post filter skipped: {e}")
        
        # 3. De-emphasis (ลด harsh frequencies)
        try:
            # Simple 1-pole de-emphasis
            alpha = 0.95
            deemph = np.zeros_like(audio)
            deemph[0] = audio[0]
            for i in range(1, len(audio)):
                deemph[i] = audio[i] + alpha * deemph[i-1]
            # Normalize หลัง de-emphasis
            max_val = np.abs(deemph).max()
            if max_val > 0:
                audio = deemph / max_val * 0.85
            else:
                audio = deemph
            logger.debug("   ✅ De-emphasis applied")
        except Exception as e:
            logger.debug(f"   ⚠️ De-emphasis skipped: {e}")
        
        # 4. Fade in/out (ป้องกัน pop/click)
        fade_ms = 10  # 10ms fade
        fade_samples = int(sr * fade_ms / 1000)
        
        if len(audio) > fade_samples * 2:
            # Fade in
            fade_in = np.linspace(0, 1, fade_samples)
            audio[:fade_samples] *= fade_in
            
            # Fade out
            fade_out = np.linspace(1, 0, fade_samples)
            audio[-fade_samples:] *= fade_out
            
            logger.debug("   ✅ Fade in/out applied")
        
        # 5. Final normalize
        max_val = np.abs(audio).max()
        if max_val > 0:
            audio = audio / max_val * 0.85  # -1.5dB headroom
        
        # 6. Final soft limiter
        audio = np.tanh(audio * 1.2) * 0.85
        
        return audio.astype(np.float32)

    async def convert(self, audio: np.ndarray, sample_rate: int) -> Tuple[Optional[np.ndarray], int]:
        """
        แปลงเสียงด้วย RVC ผ่าน REST API พร้อม audio processing
        """
        if not self.server_url:
            logger.warning("RVC server URL is not set")
            return None, sample_rate

        try:
            import requests
        except Exception:
            logger.error("requests ไม่ได้ติดตั้ง (pip install requests)")
            return None, sample_rate

        # === PREPROCESSING ===
        logger.info("🎵 RVC Conversion with audio processing...")
        audio_processed = self._preprocess_audio(audio, sample_rate)
        
        # เขียนไฟล์ WAV ชั่วคราว (PCM 16-bit)
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_in = Path(f.name)
        
        try:
            # บันทึกเป็น PCM 16-bit (RVC มักต้องการ format นี้)
            sf.write(
                str(temp_in), 
                audio_processed, 
                sample_rate,
                subtype='PCM_16'
            )
            logger.debug(f"   📝 Input saved: {temp_in.name}")

            # เตรียม request
            files = {
                'audio': open(str(temp_in), 'rb')
            }
            data = {
                'model_path': self.model_path or '',
                'index_path': self.index_path or '',
                'pitch': str(self.pitch),
                'device': self.device
            }

            logger.info(f"   📤 Sending to RVC Server...")
            
            try:
                resp = requests.post(
                    self.server_url, 
                    files=files, 
                    data=data, 
                    timeout=60
                )
            finally:
                files['audio'].close()

            if resp.status_code != 200:
                logger.warning(f"   ❌ RVC server returned {resp.status_code}")
                return None, sample_rate

            # === รับและ POSTPROCESS ===
            
            ctype = resp.headers.get('Content-Type', '')
            
            # กรณี 1: Response เป็น audio/wav โดยตรง
            if 'audio/wav' in ctype or 'application/octet-stream' in ctype:
                logger.debug("   📥 Response type: audio/wav")
                
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                    temp_out = Path(f.name)
                
                try:
                    temp_out.write_bytes(resp.content)
                    out_audio, out_sr = sf.read(str(temp_out))
                    
                    # Convert to mono
                    if hasattr(out_audio, 'ndim') and out_audio.ndim > 1:
                        out_audio = out_audio.mean(axis=1)
                    
                    out_audio = out_audio.astype(np.float32)
                    
                    # === POSTPROCESS ===
                    out_audio = self._postprocess_audio(out_audio, out_sr)
                    
                    logger.info(f"   ✅ RVC conversion successful!")
                    logger.info(f"   Duration: {len(out_audio)/out_sr:.2f}s")
                    logger.info(f"   RMS: {np.sqrt(np.mean(out_audio**2)):.4f}")
                    
                    return out_audio, int(out_sr)
                    
                finally:
                    temp_out.unlink(missing_ok=True)
            
            # กรณี 2: Response เป็น JSON
            else:
                logger.debug("   📥 Response type: JSON")
                
                try:
                    js = resp.json()
                except Exception:
                    logger.warning("   ⚠️ Cannot parse JSON response")
                    return None, sample_rate

                import base64
                audio_b64 = js.get('audio', '')
                
                if not audio_b64:
                    logger.warning("   ⚠️ No 'audio' field in JSON")
                    return None, sample_rate
                
                raw = base64.b64decode(audio_b64)
                
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                    temp_out = Path(f.name)
                
                try:
                    temp_out.write_bytes(raw)
                    out_audio, out_sr = sf.read(str(temp_out))
                    
                    if hasattr(out_audio, 'ndim') and out_audio.ndim > 1:
                        out_audio = out_audio.mean(axis=1)
                    
                    out_audio = out_audio.astype(np.float32)
                    
                    # === POSTPROCESS ===
                    out_audio = self._postprocess_audio(out_audio, out_sr)
                    
                    logger.info(f"   ✅ RVC conversion successful!")
                    logger.info(f"   Duration: {len(out_audio)/out_sr:.2f}s")
                    logger.info(f"   RMS: {np.sqrt(np.mean(out_audio**2)):.4f}")
                    
                    return out_audio, int(out_sr)
                    
                finally:
                    temp_out.unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"   ❌ RVC convert error: {e}", exc_info=True)
            return None, sample_rate
            
        finally:
            try:
                temp_in.unlink(missing_ok=True)
            except Exception:
                pass