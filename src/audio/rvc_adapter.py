"""
RVC Adapter
แปลงเสียง TTS ให้เป็นเสียงเป้าหมายด้วย RVC ผ่านเซิร์ฟเวอร์ภายนอก

แนวคิด:
- ไม่ผูกกับไลบรารีหนักในโปรเจกต์หลัก (Torch/Fairseq ฯลฯ)
- เรียกใช้งานผ่าน HTTP ไปยัง RVC server (เช่น Mangio-RVC-WebUI หรือ fork ที่รองรับ REST)
- ถ้าแปลงไม่สำเร็จ จะส่งคืนเสียงเดิมเพื่อให้ระบบทำงานต่อได้
"""
import logging
from typing import Optional, Tuple
import numpy as np
import tempfile
from pathlib import Path
import soundfile as sf
import os

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

    async def convert(self, audio: np.ndarray, sample_rate: int) -> Tuple[Optional[np.ndarray], int]:
        """
        แปลงเสียงด้วย RVC ผ่าน REST API
        - ส่งไฟล์ wav ชั่วคราวไปยังเซิร์ฟเวอร์
        - รับไฟล์เสียงที่แปลงแล้วกลับมา
        """
        # ตรวจสอบพารามิเตอร์พื้นฐาน
        if not self.server_url:
            logger.warning("RVC server URL is not set")
            return None, sample_rate

        try:
            import requests
        except Exception:
            logger.error("requests ไม่ได้ติดตั้ง (ต้องการสำหรับ RVC REST)")
            return None, sample_rate

        # เขียนไฟล์ WAV ชั่วคราว
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_in = Path(f.name)
        try:
            sf.write(str(temp_in), audio.astype(np.float32), sample_rate, subtype='PCM_16')

            # เตรียม multipart/form-data
            files = {
                'audio': open(str(temp_in), 'rb')
            }
            data = {
                'model_path': self.model_path or '',
                'index_path': self.index_path or '',
                'pitch': str(self.pitch),
                'device': self.device
            }

            logger.info(f"📤 ส่งเสียงไปแปลงที่ RVC Server: {self.server_url}")
            try:
                resp = requests.post(self.server_url, files=files, data=data, timeout=60)
            finally:
                files['audio'].close()

            if resp.status_code != 200:
                logger.warning(f"RVC server returned non-200: {resp.status_code}")
                return None, sample_rate

            # ตรวจสอบ content-type
            ctype = resp.headers.get('Content-Type', '')
            if 'audio/wav' in ctype or 'application/octet-stream' in ctype:
                # บางเซิร์ฟเวอร์ส่งไฟล์ wav ตรง ๆ
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                    temp_out = Path(f.name)
                try:
                    temp_out.write_bytes(resp.content)
                    out_audio, out_sr = sf.read(str(temp_out))
                    # mono
                    if hasattr(out_audio, 'ndim') and out_audio.ndim > 1:
                        out_audio = out_audio.mean(axis=1)
                    # float32
                    out_audio = out_audio.astype(np.float32)
                    # normalize
                    m = np.abs(out_audio).max()
                    if m > 0:
                        out_audio = out_audio / m * 0.95
                    return out_audio, int(out_sr)
                finally:
                    temp_out.unlink(missing_ok=True)
            else:
                # บางเซิร์ฟเวอร์ส่ง JSON พร้อม base64 หรือพาธไฟล์
                try:
                    js = resp.json()
                except Exception:
                    logger.warning("RVC response is not JSON or WAV; cannot parse")
                    return None, sample_rate

                import base64
                audio_b64 = js.get('audio', '')
                if audio_b64:
                    raw = base64.b64decode(audio_b64)
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                        temp_out = Path(f.name)
                    try:
                        temp_out.write_bytes(raw)
                        out_audio, out_sr = sf.read(str(temp_out))
                        if hasattr(out_audio, 'ndim') and out_audio.ndim > 1:
                            out_audio = out_audio.mean(axis=1)
                        out_audio = out_audio.astype(np.float32)
                        m = np.abs(out_audio).max()
                        if m > 0:
                            out_audio = out_audio / m * 0.95
                        return out_audio, int(out_sr)
                    finally:
                        temp_out.unlink(missing_ok=True)

                logger.warning("RVC JSON response missing 'audio' base64")
                return None, sample_rate

        except Exception as e:
            logger.error(f"RVC convert error: {e}")
            return None, sample_rate
        finally:
            try:
                temp_in.unlink(missing_ok=True)
            except Exception:
                pass