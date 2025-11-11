"""
Export TTS Quality Sample
- สร้างไฟล์เสียงตัวอย่างจาก F5-TTS-Thai เพื่อทดสอบคุณภาพและความพร้อมใช้งาน
- อ่านค่าอ้างอิงจาก .env: F5_TTS_REF_AUDIO, F5_TTS_REF_TEXT, TTS_DEVICE
"""
import os
import asyncio
import sys
from pathlib import Path

# ให้สามารถ import จากโฟลเดอร์ src ได้โดยตรง
sys.path.insert(0, str(Path(__file__).parent / 'src'))


async def synthesize_and_save(text: str, out_path: Path, ref_audio: str | None = None):
    from audio.f5_tts_handler import F5TTSHandler
    import soundfile as sf

    # เตรียมโฟลเดอร์ปลายทาง
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # สร้าง engine พร้อม reference audio ถ้ามี
    tts = F5TTSHandler(reference_wav=ref_audio)

    audio, sr = await tts.generate_speech(text)
    if audio is None or len(audio) == 0:
        raise RuntimeError("TTS generated empty audio")

    # เขียนเป็นไฟล์ WAV float32
    sf.write(str(out_path), audio.astype('float32'), int(sr))
    return out_path, int(sr), len(audio)


def main():
    # ค่าเริ่มต้นและอ่านจาก .env
    default_text = "สวัสดี ฉันทดสอบคุณภาพเสียงของ F5-TTS-Thai"
    text = os.getenv("TTS_TEXT", os.getenv("F5_TTS_REF_TEXT", default_text)).strip()
    ref_audio = os.getenv("F5_TTS_REF_AUDIO", "reference_audio/Jeed_anime.wav").strip()

    # ไฟล์ปลายทาง
    out_path = Path("temp/tts_quality.wav")

    try:
        out_file, sr, n_samples = asyncio.run(synthesize_and_save(text, out_path, ref_audio))
        print(f"✅ Exported TTS sample: {out_file} | {n_samples} samples @ {sr}Hz")
        print(f"ℹ️ Text: {text}")
        print(f"ℹ️ Ref Audio: {ref_audio}")
    except Exception as e:
        print(f"❌ TTS export failed: {e}")
        raise


if __name__ == "__main__":
    main()