from __future__ import annotations
from typing import Optional
import io
import wave
import numpy as np

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
    ปรับ pitch/speed แบบง่ายโดยเปลี่ยน "ความยาวข้อมูล" ให้ผล playback เทียบเท่าการเปลี่ยน sample rate
    แต่คงค่า sample rate เดิมไว้ เพื่อหลีกเลี่ยงปัญหา player/ffmpeg กับค่า sample rate แปลก ๆ.

    เดิม: new_sr = sr * (pitch_factor * speed) และไม่แตะ data
    ปรับใหม่: new_len = len(data) / (pitch_factor * speed) และคง sr เดิม
    """
    pitch_factor = float(2 ** (semitones / 12.0))
    k = float(pitch_factor * speed)
    if k <= 0.0:
        # ไม่ปรับ หากพารามิเตอร์ผิดปกติ
        return data, sr

    # คำนวณความยาวใหม่ และทำ interpolation อย่างง่าย
    new_len = max(1, int(len(data) / k))
    # แปลงเป็น float เพื่อความแม่นยำในการ interpolate
    x = np.arange(len(data), dtype=np.float32)
    xi = np.linspace(0, float(len(data) - 1), new_len, dtype=np.float32)
    y = np.interp(xi, x, data.astype(np.float32))

    # clip และแปลงกลับเป็น int16 หากต้นฉบับเป็น int16
    if data.dtype == np.int16:
        y = np.clip(y, -32768.0, 32767.0).astype(np.int16)
    else:
        # กรณี int8 หรืออื่น ๆ
        y = np.clip(y, -128.0, 127.0).astype(np.int8)

    return y, sr

def _read_wav_bytes(raw: bytes) -> tuple[np.ndarray, int, int]:
    bio = io.BytesIO(raw)
    with wave.open(bio, 'rb') as w:
        nchannels = w.getnchannels()
        sampwidth = w.getsampwidth()
        framerate = w.getframerate()
        nframes = w.getnframes()
        frames = w.readframes(nframes)
    dtype = np.int16 if sampwidth == 2 else np.int8
    data = np.frombuffer(frames, dtype=dtype)
    if nchannels == 2:
        data = data[::2]  # แปลงเป็นโมโนแบบง่าย
    return data, framerate, sampwidth

def _write_wav_bytes(data: np.ndarray, sr: int, sampwidth: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(sampwidth)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    return out.getvalue()

def convert(audio_wav_bytes: bytes, preset: str) -> Optional[bytes]:
    cfg = PRESETS.get(preset, PRESETS["neutral"])
    data, sr, sampwidth = _read_wav_bytes(audio_wav_bytes)
    data2, sr2 = _pitch_shift_resample(data, sr, cfg["pitch_semitones"], cfg["speed"])
    return _write_wav_bytes(data2, sr2, sampwidth)