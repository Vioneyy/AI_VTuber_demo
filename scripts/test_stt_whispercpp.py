from __future__ import annotations
from pathlib import Path
import sys

# Ensure project root in sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from src.core.config import get_settings
from src.audio.stt_whispercpp import WhisperCppSTT


def pick_audio_file() -> Path:
    # Prefer the processed sample if exists; else use ref_audio.wav
    c1 = BASE_DIR / "output" / "sample_sawasdee.wav"
    c2 = BASE_DIR / "ref_audio.wav"
    if c1.exists():
        return c1
    if c2.exists():
        return c2
    # Fallback: raw
    c3 = BASE_DIR / "output" / "sample_sawasdee_raw.wav"
    if c3.exists():
        return c3
    raise FileNotFoundError("No test wav found. Run scripts/generate_sample.py first or place ref_audio.wav.")


def main():
    settings = get_settings()
    # Show key paths for debugging
    print({
        "bin": settings.WHISPER_CPP_BIN_PATH,
        "model": settings.WHISPER_CPP_MODEL_PATH,
        "lang": settings.WHISPER_CPP_LANG,
        "threads": settings.WHISPER_CPP_THREADS,
        "ngl": settings.WHISPER_CPP_NGL,
    })

    wav = pick_audio_file()
    print(f"[STT] Using wav: {wav}")
    stt = WhisperCppSTT()
    text = stt.transcribe_file(wav, language=settings.WHISPER_CPP_LANG)
    print(f"[STT] Transcript: {text}")


if __name__ == "__main__":
    main()