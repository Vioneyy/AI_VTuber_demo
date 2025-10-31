"""
ทดสอบ Whisper.cpp STT ผ่านตัวห่อในโปรเจกต์ เพื่อยืนยันการตั้งค่าพาธ, ภาษา,
และค่า GPU offload (-ngl) ว่าทำงานได้จริงบนเครื่อง

การใช้งาน:
  1) เปิด venv
     .\.venv\Scripts\Activate.ps1

  2) รันสคริปต์
     python scripts\test_stt_whispercpp.py

หมายเหตุ:
- หากมีไฟล์เสียงพูดภาษาไทยสำหรับทดสอบ ให้ตั้งพาธด้วย ENV `TEST_WAV_PATH`
- หากไม่ตั้งค่า จะลองใช้ `ref_audio.wav` ที่รากโปรเจกต์
- ถ้าไม่พบไฟล์เสียง จะสร้างไฟล์ beep สั้น ๆ เพื่อทดสอบการเรียก CLI เท่านั้น
"""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def make_beep_wav(path: Path, duration_sec: float = 1.0, freq: float = 440.0):
    import wave
    import numpy as np
    sample_rate = 16000
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    x = (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    # แปลงเป็น int16
    y = (x * 32767.0).clip(-32768, 32767).astype(np.int16)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(y.tobytes())

def main():
    from src.audio.stt_whispercpp import WhisperCppSTT

    # แสดงค่าที่สำคัญจาก ENV
    bin_path = os.getenv("WHISPER_CPP_BIN_PATH", "")
    model_path = os.getenv("WHISPER_CPP_MODEL_PATH", "")
    lang = os.getenv("WHISPER_CPP_LANG", "th")
    threads = os.getenv("WHISPER_CPP_THREADS", "")
    ngl = os.getenv("WHISPER_CPP_NGL", "")
    timeout_ms = os.getenv("WHISPER_CPP_TIMEOUT_MS", "")

    print("==== Whisper.cpp Settings ====")
    print(f"WHISPER_CPP_BIN_PATH = {bin_path}")
    print(f"WHISPER_CPP_MODEL_PATH = {model_path}")
    print(f"WHISPER_CPP_LANG = {lang}")
    print(f"WHISPER_CPP_THREADS = {threads}")
    print(f"WHISPER_CPP_NGL = {ngl}")
    print(f"WHISPER_CPP_TIMEOUT_MS = {timeout_ms}")
    print("==============================")

    stt = WhisperCppSTT()

    # เลือกไฟล์สำหรับทดสอบ
    test_wav_env = os.getenv("TEST_WAV_PATH", "")
    candidates = [
        Path(test_wav_env) if test_wav_env else None,
        Path("ref_audio.wav"),
        Path("output/sample_sawasdee.wav")
    ]
    wav_path = None
    for c in candidates:
        if c and c.exists():
            wav_path = c
            break

    if not wav_path:
        # สร้างไฟล์ beep ชั่วคราว
        tmp_dir = Path("output")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        wav_path = tmp_dir / "beep_test.wav"
        make_beep_wav(wav_path)
        print(f"⚠️ ไม่พบไฟล์เสียงพูด ใช้ไฟล์ beep ชั่วคราว: {wav_path}")

    print(f"🎧 ทดสอบถอดความจากไฟล์: {wav_path}")
    text = stt.transcribe_file(wav_path)

    if text:
        print("✅ ผลการถอดความ:")
        print(text)
    else:
        print("❌ ไม่ได้ผลลัพธ์ (อาจเป็นเพราะไม่มีเสียงพูด หรือการตั้งค่าบางอย่างผิดพลาด)")

if __name__ == "__main__":
    sys.exit(main())