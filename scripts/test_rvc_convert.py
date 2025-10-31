import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ทำให้สามารถ import โมดูลจากโฟลเดอร์รากโปรเจกต์ได้
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.audio.rvc_adapter import RVCv2Adapter


def main():
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"d:\AI_VTuber_demo\test_tts_output.wav")
    if not in_path.exists():
        print(f"❌ ไม่พบไฟล์อินพุต: {in_path}")
        sys.exit(1)

    preset = os.getenv("VOICE_PRESET", "anime_girl")
    gain_db = os.getenv("RVC_GAIN_DB", "0.0")
    print(f"🎛️ RVC preset={preset}, gain_db={gain_db}")

    rvc = RVCv2Adapter(preset)
    t0 = time.time()
    out_path = rvc._convert_sync(str(in_path))
    dt = time.time() - t0
    print(f"✅ เขียนไฟล์: {out_path} (ใช้เวลา {dt:.2f}s)")


if __name__ == "__main__":
    main()