import os
import sys
from pathlib import Path

def main():
    # เพิ่ม project root ใน sys.path เพื่อให้ import src ได้เมื่อรันสคริปต์โดยตรง
    project_root = Path(__file__).resolve().parents[1]
    sys.path.append(str(project_root))
    # ปิด reference เพื่อทดสอบกรณีไม่มี ref_audio/ref_text
    os.environ["F5_TTS_USE_REFERENCE"] = "false"

    from src.adapters.tts.f5_tts_thai_real import F5TTSThai

    engine = F5TTSThai()
    engine.set_use_reference(False)

    text = "สวัสดี นี่คือการทดสอบ TTS ภาษาไทย และ English sample sentence."
    wav_bytes = engine.synthesize(text)

    out_path = Path("test_tts_output.wav").resolve()
    with open(out_path, "wb") as f:
        f.write(wav_bytes)

    print(f"✅ เขียนไฟล์ทดสอบ: {out_path}")

if __name__ == "__main__":
    main()