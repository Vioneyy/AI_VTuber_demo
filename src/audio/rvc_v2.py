from __future__ import annotations
from typing import Optional
import io
import wave
import numpy as np
try:
    import torchaudio
    _HAS_TORCHAUDIO = True
except Exception:
    _HAS_TORCHAUDIO = False

# หมายเหตุ: นี่เป็นสคาฟโฟลด์ RVC v2 (ไม่ใช่โมเดลจริง)
# เป้าหมาย: ให้พรีเซ็ตเสียงทำงานแบบเร็ว โดยปรับ pitch/speed แบบเบา ๆ
# เมื่อเชื่อมต่อ RVC v2 จริง ให้แทนที่ฟังก์ชัน convert() ด้วยการเรียกใช้โมเดล

PRESETS = {
    "anime_girl": {"pitch_semitones": 3.0, "speed": 1.10},
    "deep_male": {"pitch_semitones": -3.0, "speed": 0.95},
    "narrator": {"pitch_semitones": -1.0, "speed": 1.00},
    "neutral": {"pitch_semitones": 0.0, "speed": 1.00},
}

def _pitch_shift_resample(data: np.ndarray, sr: int, semitones: float, speed: float) -> tuple[np.ndarray, int]:
    """
    ปรับ pitch/speed แบบง่าย โดยทำงานในโดเมน float (-1..1)
    - เปลี่ยนความยาวสัญญาณตามปัจจัยรวม k = pitch_factor * speed
    - คง sample rate เดิมไว้
    - คืนค่าเป็น float32 ในช่วง [-1, 1]
    """
    pitch_factor = float(2 ** (semitones / 12.0))
    k = float(pitch_factor * speed)
    if k <= 0.0:
        return data.astype(np.float32), sr

    new_len = max(1, int(len(data) / k))
    x = np.arange(len(data), dtype=np.float32)
    xi = np.linspace(0, float(len(data) - 1), new_len, dtype=np.float32)
    y = np.interp(xi, x, data.astype(np.float32))
    # ป้องกัน clipping ให้อยู่ในช่วง -1..1
    y = np.clip(y, -1.0, 1.0).astype(np.float32)
    return y, sr

def _read_wav_bytes(raw: bytes) -> tuple[np.ndarray, int, int]:
    """อ่าน WAV bytes รองรับทั้ง PCM int และ float ด้วย torchaudio หากมี"""
    if _HAS_TORCHAUDIO:
        bio = io.BytesIO(raw)
        wav, sr = torchaudio.load(bio)
        # wav: [channels, time]
        # ใช้ channel แรก
        if wav.shape[0] > 1:
            wav = wav[0:1, :]
        data = wav.squeeze(0).numpy().astype(np.float32)  # -1..1
        sampwidth = 4  # ใช้ float32 ภายใน
        return data, sr, sampwidth

    # fallback: wave module (รองรับเฉพาะ PCM int)
    bio = io.BytesIO(raw)
    with wave.open(bio, 'rb') as w:
        nchannels = w.getnchannels()
        sampwidth = w.getsampwidth()
        framerate = w.getframerate()
        nframes = w.getnframes()
        frames = w.readframes(nframes)
    dtype = np.int16 if sampwidth == 2 else np.int8
    data = np.frombuffer(frames, dtype=dtype).astype(np.float32)
    # ปรับสเกลเป็น -1..1 สำหรับ int16/int8
    if dtype == np.int16:
        data = data / 32768.0
    else:
        data = data / 128.0
    if nchannels == 2:
        data = data[::2]  # แปลงเป็นโมโนแบบง่าย
    return data, framerate, sampwidth

def _write_wav_bytes(data: np.ndarray, sr: int, sampwidth: int) -> bytes:
    """เขียน WAV กลับเป็น PCM16 เพื่อความเข้ากันได้กับ player ทั่วไป พร้อม fade in/out ป้องกัน pop"""
    d = data.astype(np.float32)
    # Fade in/out 10ms เพื่อลดเสียง pop ที่หัว/ท้ายไฟล์
    fade = max(1, int(sr * 0.010))
    if len(d) > fade * 2:
        d[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        d[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    # Clamp
    d = np.clip(d, -1.0, 1.0)
    pcm16 = (d * 32767.0).astype(np.int16)
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit PCM
        w.setframerate(sr)
        w.writeframes(pcm16.tobytes())
    return out.getvalue()

def convert(audio_wav_bytes: bytes, preset: str) -> Optional[bytes]:
    cfg = PRESETS.get(preset, PRESETS["neutral"])
    data, sr, _sampwidth = _read_wav_bytes(audio_wav_bytes)
    data2, sr2 = _pitch_shift_resample(data, sr, cfg["pitch_semitones"], cfg["speed"])
    return _write_wav_bytes(data2.astype(np.float32), sr2, 2)


class RVCProcessor:
    """Wrapper ให้ main.py ใช้งานชื่อคลาส RVCProcessor ได้
    convert(audio_bytes) -> bytes โดยใช้พรีเซ็ตจาก config หรือ 'neutral'
    """
    def __init__(self, model_path: Optional[str] = None, device: Optional[str] = None, preset: str = "neutral"):
        self.model_path = model_path
        self.device = device
        self.preset = preset

    async def convert(self, audio_wav_bytes: bytes) -> Optional[bytes]:
        return convert(audio_wav_bytes, self.preset)