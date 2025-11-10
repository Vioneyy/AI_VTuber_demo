"""
ทดสอบ TTS - F5-TTS-Thai
"""
import asyncio
from pathlib import Path

async def test_f5_tts():
    """ทดสอบ F5-TTS-Thai"""
    print("🔊 Testing F5-TTS-Thai...")

    try:
        from src.audio.f5_tts_handler import F5TTSHandler
        tts = F5TTSHandler()
        text = "สวัสดีค่ะ ฉันชื่อจีด ยินดีที่ได้รู้จัก"
        audio, sr = await tts.generate_speech(text)
        out = Path("test_f5_tts.wav")
        if audio is not None and len(audio) > 0:
            import soundfile as sf
            sf.write(str(out), audio.astype('float32'), sr)
            print(f"✅ F5-TTS-Thai สำเร็จ: {out}")
            return True
        else:
            print("❌ F5-TTS-Thai generated empty audio")
            return False
    except Exception as e:
        print(f"❌ F5-TTS-Thai ล้มเหลว: {e}")
        return False

async def main():
    print("=" * 60)
    print("🧪 TTS Testing Suite")
    print("=" * 60)

    ok = await test_f5_tts()

    print("\n" + "=" * 60)
    print("📊 Results:")
    print(f"  F5-TTS-Thai: {'✅ OK' if ok else '❌ FAILED'}")
    print("=" * 60)

    if ok:
        print("\n✅ TTS ทำงานได้! ตอนนี้ลองเล่นไฟล์เสียงที่สร้างดู")
    else:
        print("\n❌ TTS ไม่ทำงาน ตรวจสอบการติดตั้ง f5-tts-th และไฟล์อ้างอิง")

if __name__ == "__main__":
    asyncio.run(main())