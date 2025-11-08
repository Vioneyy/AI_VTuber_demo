"""
ทดสอบ TTS - Edge TTS และ gTTS
"""
import asyncio
import edge_tts
from pathlib import Path

async def test_edge_tts():
    """ทดสอบ Edge TTS"""
    print("🔊 Testing Edge TTS...")
    
    text = "สวัสดีค่ะ ฉันชื่อจีด ยินดีที่ได้รู้จัก"
    output_file = "test_edge.mp3"
    
    # Thai voices available in Edge TTS
    voice = "th-TH-PremwadeeNeural"  # Female voice
    # voice = "th-TH-NiwatNeural"  # Male voice
    
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
        print(f"✅ Edge TTS สำเร็จ: {output_file}")
        return True
    except Exception as e:
        print(f"❌ Edge TTS ล้มเหลว: {e}")
        return False

def test_gtts():
    """ทดสอบ gTTS"""
    print("\n🔊 Testing gTTS...")
    
    from gtts import gTTS
    
    text = "สวัสดีค่ะ ฉันชื่อจีด ยินดีที่ได้รู้จัก"
    output_file = "test_gtts.mp3"
    
    try:
        tts = gTTS(text=text, lang='th', slow=False)
        tts.save(output_file)
        print(f"✅ gTTS สำเร็จ: {output_file}")
        return True
    except Exception as e:
        print(f"❌ gTTS ล้มเหลว: {e}")
        return False

async def main():
    print("=" * 60)
    print("🧪 TTS Testing Suite")
    print("=" * 60)
    
    # Test Edge TTS
    edge_ok = await test_edge_tts()
    
    # Test gTTS
    gtts_ok = test_gtts()
    
    print("\n" + "=" * 60)
    print("📊 Results:")
    print(f"  Edge TTS: {'✅ OK' if edge_ok else '❌ FAILED'}")
    print(f"  gTTS: {'✅ OK' if gtts_ok else '❌ FAILED'}")
    print("=" * 60)
    
    if edge_ok or gtts_ok:
        print("\n✅ TTS ทำงานได้! ตอนนี้ลองเล่นไฟล์เสียงที่สร้างดู")
    else:
        print("\n❌ TTS ไม่ทำงาน ตรวจสอบการติดตั้ง library")

if __name__ == "__main__":
    asyncio.run(main())