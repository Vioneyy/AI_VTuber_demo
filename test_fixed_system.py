"""
Test Fixed System
ทดสอบว่าแก้ไขสำเร็จหรือไม่
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

async def test_stt():
    """Test STT"""
    print("\n🧪 Testing STT...")
    
    try:
        from audio.hybrid_stt import HybridSTT
        import numpy as np
        
        stt = HybridSTT(device="cpu")  # Use CPU for testing
        
        # Create dummy audio (1 second)
        audio_bytes = (np.random.randn(48000 * 2) * 0.3 * 32767).astype(np.int16).tobytes()
        
        result = await stt.transcribe(audio_bytes, 48000)
        
        print(f"✅ STT works! Result: {result}")
        
    except Exception as e:
        print(f"❌ STT failed: {e}")

async def test_tts():
    """Test TTS"""
    print("\n🧪 Testing TTS...")
    
    try:
        from audio.fixed_tts_rvc_handler import FixedTTSRVCHandler
        
        tts = FixedTTSRVCHandler(tts_device="cpu", rvc_device="cpu")
        
        audio, sr = await tts.generate_speech("สวัสดีครับ", apply_rvc=False)
        
        if audio is not None and len(audio) > 0:
            print(f"✅ TTS works! Generated {len(audio)} samples at {sr}Hz")
        else:
            print(f"❌ TTS generated empty audio")
        
    except Exception as e:
        print(f"❌ TTS failed: {e}")

async def main():
    await test_stt()
    await test_tts()

if __name__ == "__main__":
    asyncio.run(main())
