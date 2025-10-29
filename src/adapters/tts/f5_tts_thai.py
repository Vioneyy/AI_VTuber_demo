from __future__ import annotations
from typing import Optional, Dict, Any
from pathlib import Path
import io
import wave
import numpy as np
import os

from .tts_interface import TTSEngine
from core.config import get_settings

try:
    from f5_tts_th.tts import TTS as F5ThaiTTS  # type: ignore
except Exception:  # pragma: no cover
    F5ThaiTTS = None  # type: ignore

# Optional Hugging Face login if available
try:
    from huggingface_hub import login as hf_login  # type: ignore
except Exception:  # pragma: no cover
    hf_login = None  # type: ignore


def _float_to_int16_wav_bytes(data: np.ndarray, sr: int) -> bytes:
    # Ensure mono float array in [-1,1]
    if data.ndim > 1:
        data = data.squeeze()
    data = np.clip(data.astype(np.float32), -1.0, 1.0)
    pcm = (data * 32767.0).astype(np.int16)
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # int16
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return out.getvalue()


def _normalize_and_fade(x: np.ndarray, sr: int, target_dbfs: float = -16.0) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    # Normalize RMS to target dBFS
    rms = float(np.sqrt(np.mean(np.square(x))) + 1e-9)
    current_dbfs = 20.0 * np.log10(rms)
    gain_db = float(target_dbfs - current_dbfs)
    linear = float(10.0 ** (gain_db / 20.0))
    y = np.clip(x * linear, -1.0, 1.0)
    # Short fade-in/out to reduce clicks (10 ms)
    n_fade = max(1, int(sr * 0.010))
    ramp_in = np.linspace(0.0, 1.0, n_fade, dtype=np.float32)
    ramp_out = np.linspace(1.0, 0.0, n_fade, dtype=np.float32)
    if y.size >= 2 * n_fade:
        y[:n_fade] *= ramp_in
        y[-n_fade:] *= ramp_out
    return y


class F5TTSThaiEngine(TTSEngine):
    def __init__(self) -> None:
        self.settings = get_settings()
        # Try to login Hugging Face if token provided
        token = (
            getattr(self.settings, "HUGGINGFACE_HUB_TOKEN", None)
            or getattr(self.settings, "HF_TOKEN", None)
            or os.getenv("HUGGINGFACE_HUB_TOKEN")
            or os.getenv("HF_TOKEN")
        )
        if token:
            try:
                if hf_login:
                    hf_login(token=token)
                # Always set env var so downstream libraries pick it up
                os.environ["HUGGINGFACE_HUB_TOKEN"] = token
            except Exception as e:
                print(f"Hugging Face login failed: {e}")
        else:
            # Provide hint if model access errors occur later
            pass

        self.tts = None
        if F5ThaiTTS:
            try:
                # เลือกโมเดล "v1" เป็นค่าเริ่มต้น (อ่านไทยดี) หรือ "v2" (ลดอ่านข้ามคำ ด้วย IPA)
                model_ver = getattr(self.settings, "F5_TTS_MODEL", "v1")
                self.tts = F5ThaiTTS(model=model_ver)
            except Exception as e:
                print(f"โหลด F5-TTS-THAI ไม่สำเร็จ: {e}")
                self.tts = None

    def speak(self, text: str, *, voice_id: str, emotion: str, prosody: Optional[Dict[str, Any]] = None) -> Optional[bytes]:
        if not self.tts:
            return None
        # ค่าเริ่มต้นของพารามิเตอร์ตามที่โมเดลรองรับ
        step = getattr(self.settings, "F5_TTS_STEP", 32)
        cfg = getattr(self.settings, "F5_TTS_CFG", 2.0)
        speed = getattr(self.settings, "F5_TTS_SPEED", 1.0)
        sr = getattr(self.settings, "F5_TTS_SR", 24000)

        # Prosody overrides per-call
        gain_db = 0.0
        if prosody:
            # Support both 'speed' and 'rate' keys
            if "speed" in prosody:
                try:
                    speed = float(prosody["speed"])  # override speed
                except Exception:
                    pass
            elif "rate" in prosody:
                try:
                    speed = float(prosody["rate"])  # override speed
                except Exception:
                    pass
            # Optional gain in dB applied post-synthesis
            if "gain_db" in prosody:
                try:
                    gain_db = float(prosody["gain_db"])  # e.g., +3.0 increases loudness
                except Exception:
                    gain_db = 0.0

        ref_wav_path = self.settings.TTS_REFERENCE_WAV
        ref_text = getattr(self.settings, "F5_TTS_REF_TEXT", "")  # ว่างจะใช้ ASR (ต้องใช้ทรัพยากรเพิ่ม)
        use_reference = bool(getattr(self.settings, "F5_TTS_USE_REFERENCE", True))

        speaker_wav = None
        if ref_wav_path and use_reference:
            p = Path(ref_wav_path)
            if p.exists():
                speaker_wav = str(p)

        def _ensure_silent_ref_wav(seconds: float = 0.3, sample_rate: int = sr) -> str:
            """สร้างไฟล์ WAV เงียบชั่วคราว เพื่อใช้เป็น ref_audio เมื่อปิด reference
            บางไลบรารีต้องการพารามิเตอร์แบบบังคับ (positional) จึงใส่ไฟล์ที่ถูกต้องเข้าไปเสมอ
            """
            try:
                out_dir = Path(os.getenv("OUTPUT_DIR", "output"))
                out_dir.mkdir(parents=True, exist_ok=True)
                path = out_dir / f"silent_ref_{sample_rate}_{int(seconds*1000)}ms.wav"
                if not path.exists():
                    n = int(seconds * sample_rate)
                    pcm = np.zeros(n, dtype=np.int16)
                    with wave.open(str(path), 'wb') as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(sample_rate)
                        w.writeframes(pcm.tobytes())
                return str(path)
            except Exception:
                # fallback: ใช้ไฟล์อ้างอิงเดิมถ้ามี หรือคืนค่าเป็นไฟล์ใน output ที่สร้างไม่สำเร็จ (จะให้ lib จัดการเอาเอง)
                return str(Path(ref_wav_path)) if ref_wav_path else str(Path("output/silent_ref.wav"))

        try:
            # ไลบรารี F5-TTS-Thai ต้องการ ref_audio/ref_text เป็นพารามิเตอร์บังคับ
            # เมื่อปิด reference ให้ส่งไฟล์เงียบและ ref_text ว่าง เพื่อไม่ให้มีข้อความอ้างอิงติดมา
            if use_reference and speaker_wav:
                ref_audio_arg = speaker_wav
                ref_text_arg = ref_text
            else:
                ref_audio_arg = _ensure_silent_ref_wav(sample_rate=sr)
                ref_text_arg = ""

            wav = self.tts.infer(
                ref_audio=ref_audio_arg,
                ref_text=ref_text_arg,
                gen_text=text,
                step=step,
                cfg=cfg,
                speed=speed,
            )
            # Apply post gain if requested
            wav_arr = np.array(wav, dtype=np.float32)
            if gain_db != 0.0:
                linear = float(10.0 ** (gain_db / 20.0))
                wav_arr = np.clip(wav_arr * linear, -1.0, 1.0)
            # Normalize and fade to improve perceived quality
            wav_arr = _normalize_and_fade(wav_arr, sr)
            return _float_to_int16_wav_bytes(wav_arr, sr)
        except Exception as e:
            print(
                "F5-TTS-THAI สังเคราะห์เสียงล้มเหลว: {}. "
                "หากเป็น 401 (Unauthorized) โปรดตั้งค่า HUGGINGFACE_HUB_TOKEN หรือ HF_TOKEN ใน .env และยอมรับเงื่อนไขโมเดลบน Hugging Face.".format(e)
            )
            return None