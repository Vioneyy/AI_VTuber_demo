"""
RVC Client Adapter
- เชื่อมต่อกับเซิร์ฟเวอร์ RVC ภายนอกผ่าน HTTP
- รับ numpy float32 audio และคืนค่า audio หลังแปลงเสียง

คอนฟิกจาก .env:
- RVC_ENABLED=true/false
- RVC_SERVER_URL=http://localhost:7865
- RVC_MODEL_PTH=rvc_models/jeed_anime.pth
- RVC_MODEL_INDEX=rvc_models/jeed_anime.index
- RVC_F0=true/false
- RVC_TRANSPOSE=0 (semitones)
- RVC_MODEL_NAME=jeed_anime (สำหรับ FastAPI server ที่ใช้ชื่อโมเดลใน logs/)
- RVC_F0_METHOD=crepe (สำหรับ FastAPI server)

รูปแบบ API ที่รองรับ:
- แบบ WebUI bridge เดิม: POST {SERVER_URL}/api/v1/convert
  files: { audio: ("input.wav", bytes, "audio/wav") }
  data: { model_path, index_path, f0, transpose }
  คืนค่าเป็น audio/wav หรือ JSON ที่มีคีย์ "audio_wav_base64"

- แบบ FastAPI ทางเลือก: POST {SERVER_URL}/voice2voice
  files: { input_file: ("input.wav", bytes, "audio/wav") }
  data: { model_name, index_path, f0up_key, f0method, index_rate, ... }
  คืนค่าเป็น audio/wav
"""

import os
import io
import base64
import logging
from typing import Tuple, Optional

import numpy as np
import requests

logger = logging.getLogger(__name__)


class RVCClient:
    def __init__(self,
                 server_url: Optional[str] = None,
                 model_path: Optional[str] = None,
                 index_path: Optional[str] = None,
                 use_f0: Optional[bool] = None,
                 transpose: Optional[int] = None):
        self.server_url = server_url or os.getenv("RVC_SERVER_URL", "http://localhost:7865")
        self.model_path = model_path or os.getenv("RVC_MODEL_PTH", "rvc_models/jeed_anime.pth")
        self.index_path = index_path or os.getenv("RVC_MODEL_INDEX", "rvc_models/jeed_anime.index")
        self.use_f0 = os.getenv("RVC_F0", "true").lower() == "true" if use_f0 is None else use_f0
        try:
            self.transpose = int(os.getenv("RVC_TRANSPOSE", "0")) if transpose is None else int(transpose)
        except Exception:
            self.transpose = 0
        # สำหรับ FastAPI server
        self.model_name = os.getenv("RVC_MODEL_NAME", "")
        self.f0method = os.getenv("RVC_F0_METHOD", "crepe")

    def _wav_bytes(self, audio: np.ndarray, sample_rate: int) -> bytes:
        """แปลง float32 mono เป็น WAV bytes"""
        import soundfile as sf
        buf = io.BytesIO()
        # บังคับ mono
        if audio.ndim == 2:
            audio = audio.mean(axis=1).astype(np.float32)
        sf.write(buf, audio.astype(np.float32), sample_rate, format='WAV', subtype='PCM_16')
        return buf.getvalue()

    def _bytes_to_float(self, wav_bytes: bytes) -> Tuple[np.ndarray, int]:
        import soundfile as sf
        buf = io.BytesIO(wav_bytes)
        data, sr = sf.read(buf, dtype='float32')
        # หากเป็นหลายแชนเนล แปลงเป็น mono
        if isinstance(data, np.ndarray) and data.ndim == 2:
            data = data.mean(axis=1).astype(np.float32)
        return data.astype(np.float32), int(sr)

    def convert(self, audio: np.ndarray, sample_rate: int) -> Tuple[np.ndarray, int]:
        """
        ส่งเสียงเข้า RVC server เพื่อแปลงเสียง
        หากล้มเหลวจะคืนค่าเดิมแบบ passthrough
        """
        try:
            # 1) ลองรูปแบบ WebUI bridge เดิม
            endpoint_v1 = self.server_url.rstrip('/') + "/api/v1/convert"
            files_v1 = {
                'audio': ('input.wav', self._wav_bytes(audio, sample_rate), 'audio/wav')
            }
            data_v1 = {
                'model_path': self.model_path,
                'index_path': self.index_path,
                'f0': 'true' if self.use_f0 else 'false',
                'transpose': str(self.transpose),
            }
            logger.info(f"🎛️ ส่งไป RVC(v1): url={endpoint_v1}, model={self.model_path}, index={self.index_path}, f0={data_v1['f0']}, pitch={data_v1['transpose']}")
            try:
                resp = requests.post(endpoint_v1, files=files_v1, data=data_v1, timeout=30)
                resp.raise_for_status()
                ct = resp.headers.get('Content-Type', '')
                if 'audio/wav' in ct:
                    return self._bytes_to_float(resp.content)
                else:
                    try:
                        js = resp.json()
                        b64 = js.get('audio_wav_base64')
                        if b64:
                            return self._bytes_to_float(base64.b64decode(b64))
                    except Exception:
                        pass
                    logger.warning("RVC(v1) response not WAV/JSON; จะลอง FastAPI")
            except Exception as e_v1:
                logger.info(f"ℹ️ RVC(v1) ล้มเหลว/ไม่พบ endpoint: {e_v1}; จะลอง FastAPI")

            # 2) ลองรูปแบบ FastAPI /voice2voice
            endpoint_fastapi = self.server_url.rstrip('/') + "/voice2voice"
            files_v2 = {
                'input_file': ('input.wav', self._wav_bytes(audio, sample_rate), 'audio/wav')
            }
            # map transpose -> f0up_key
            data_v2 = {
                'model_name': self.model_name or os.path.splitext(os.path.basename(self.model_path))[0],
                'index_path': self.index_path,
                'f0up_key': str(self.transpose),
                'f0method': self.f0method,
                'index_rate': '0.66',
            }
            logger.info(f"🎛️ ส่งไป RVC(FastAPI): url={endpoint_fastapi}, model_name={data_v2['model_name']}, index={self.index_path}, f0up_key={data_v2['f0up_key']}, method={data_v2['f0method']}")
            resp2 = requests.post(endpoint_fastapi, files=files_v2, data=data_v2, timeout=60)
            resp2.raise_for_status()
            ct2 = resp2.headers.get('Content-Type', '')
            if 'audio/wav' in ct2:
                return self._bytes_to_float(resp2.content)

            logger.warning("RVC(FastAPI) response ไม่ใช่ WAV; passthrough")
            return audio.astype(np.float32), sample_rate

        except Exception as e:
            logger.warning(f"⚠️ RVC convert failed ทั้งสองรูปแบบ: {e}")
            return audio.astype(np.float32), sample_rate


def is_enabled() -> bool:
    return os.getenv("RVC_ENABLED", "false").lower() == "true"