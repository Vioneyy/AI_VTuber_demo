from __future__ import annotations
from pathlib import Path
import sys

# Ensure project root is in sys.path so we can import 'src.*'
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from src.core.config import get_settings
from src.adapters.tts.f5_tts_thai import F5TTSThaiEngine
from src.adapters.tts.tts_stub import StubTTSEngine
from src.audio.rvc_v2 import convert as rvc_convert


def _select_tts(settings):
    name = str(getattr(settings, "TTS_ENGINE", "f5_tts_thai")).lower()
    if name == "f5_tts_thai":
        try:
            eng = F5TTSThaiEngine()
            if eng.tts:
                return eng
        except Exception:
            pass
        return StubTTSEngine()
    else:
        try:
            eng = F5TTSThaiEngine()
            if eng.tts:
                return eng
        except Exception:
            pass
        return StubTTSEngine()


def main():
    settings = get_settings()
    text = "สวัสดีครับ ตอนนี้ผมพูดช้าลงแล้วนะครับ เพื่อให้ฟังง่ายขึ้น"

    # ตั้งค่าไฟล์อ้างอิงเสียงผู้พูด (ถ้ามี)
    ref = Path(r"d:\AI_VTuber_demo\ref_audio.wav")
    if ref.exists():
        # บันทึกค่าไปใน settings runtime เพื่อให้ engine ใช้
        settings.TTS_REFERENCE_WAV = str(ref)

    tts = _select_tts(settings)
    audio = tts.speak(
        text,
        voice_id=settings.TTS_VOICE_ID,
        emotion=settings.TTS_EMOTION_DEFAULT,
        prosody={"rate": 0.9},
    )
    if not audio:
        # สร้างเสียงทดสอบแบบ sine wave 1kHz 1 วินาที เพื่อยืนยันพาธเสียง
        import numpy as np, io, wave
        sr = 24000
        t = np.linspace(0, 1.0, sr, endpoint=False)
        x = (0.2*np.sin(2*np.pi*1000*t)).astype(np.float32)
        pcm = (x*32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm.tobytes())
        audio = buf.getvalue()

    # เขียนไฟล์ RAW ก่อนแปลง RVC
    out_dir = BASE_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "sample_sawasdee_raw.wav"
    raw_path.write_bytes(audio)

    # Apply RVC preset if enabled (with timeout)
    rvc_audio = audio
    if settings.ENABLE_RVC:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
        with ThreadPoolExecutor(max_workers=1) as pool:
            try:
                fut = pool.submit(rvc_convert, audio, settings.VOICE_PRESET)
                rvc_audio = fut.result(timeout=max(0.5, float(settings.RVC_TIMEOUT_MS) / 1000.0))
            except FuturesTimeout:
                rvc_audio = audio
            except Exception:
                rvc_audio = audio

    # เขียนไฟล์หลัง RVC
    out_path = out_dir / "sample_sawasdee.wav"
    out_path.write_bytes(rvc_audio)
    print(f"สร้างไฟล์ตัวอย่างเรียบร้อย: RAW={raw_path.resolve()} RVC={out_path.resolve()}")


if __name__ == "__main__":
    main()