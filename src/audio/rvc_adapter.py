import os
import asyncio
from pathlib import Path
from typing import Optional
import io
import wave
import numpy as np

# ใช้สคาฟโฟลด์ RVC v2 สำหรับการแปลงเสียงอย่างรวดเร็ว
from .rvc_v2 import convert as rvc_convert


class RVCv2Adapter:
    """
    ตัวแปลงเสียงแบบเบา (RVC v2 scaffold)
    - รับพาธไฟล์ WAV
    - แปลงเสียงตามพรีเซ็ต (เช่น anime_girl)
    - บันทึกไฟล์ใหม่ด้วย suffix _rvc.wav และคืนพาธ
    """

    def __init__(self, preset: Optional[str] = None):
        self.preset = preset or os.getenv("VOICE_PRESET", "anime_girl")
        # ปรับระดับเสียงหลังแปลง (เดซิเบล) ค่าเริ่มต้น 0.0 = ไม่เปลี่ยน
        try:
            self.gain_db = float(os.getenv("RVC_GAIN_DB", "0.0"))
        except Exception:
            self.gain_db = 0.0

    async def convert(self, audio_file_path: str) -> str:
        """แปลงเสียงไฟล์ WAV ตามพรีเซ็ตและคืนพาธไฟล์ใหม่"""
        return await asyncio.to_thread(self._convert_sync, audio_file_path)

    def _convert_sync(self, audio_file_path: str) -> str:
        in_path = Path(audio_file_path)
        if not in_path.exists():
            raise FileNotFoundError(f"Input WAV not found: {in_path}")

        raw = in_path.read_bytes()
        out_bytes = rvc_convert(raw, self.preset)

        # ปรับ gain หากตั้งค่าไว้
        if self.gain_db and abs(self.gain_db) > 0.001:
            out_bytes = self._apply_gain_db(out_bytes, self.gain_db)

        out_path = in_path.with_name(f"{in_path.stem}_rvc{in_path.suffix}")
        out_path.write_bytes(out_bytes)
        return str(out_path)

    def _apply_gain_db(self, wav_bytes: bytes, gain_db: float) -> bytes:
        """ปรับระดับเสียงแบบง่ายในโดเมนตัวอย่าง (PCM int16/int8) แล้วคืน WAV bytes ใหม่"""
        bio = io.BytesIO(wav_bytes)
        with wave.open(bio, 'rb') as w:
            nchannels = w.getnchannels()
            sampwidth = w.getsampwidth()
            framerate = w.getframerate()
            nframes = w.getnframes()
            frames = w.readframes(nframes)
        dtype = np.int16 if sampwidth == 2 else np.int8
        data = np.frombuffer(frames, dtype=dtype)
        if nchannels == 2:
            data = data[::2]

        factor = float(10 ** (gain_db / 20.0))
        if dtype == np.int16:
            adj = np.clip(data.astype(np.float32) * factor, -32768.0, 32767.0).astype(np.int16)
        else:
            adj = np.clip(data.astype(np.float32) * factor, -128.0, 127.0).astype(np.int8)

        out = io.BytesIO()
        with wave.open(out, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(sampwidth)
            w.setframerate(framerate)
            w.writeframes(adj.tobytes())
        return out.getvalue()