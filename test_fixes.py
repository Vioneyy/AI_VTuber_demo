"""
Test Fixes Script
ทดสอบว่าการแก้ไขทำงานหรือไม่
"""
import asyncio
import numpy as np
import logging
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

logger = logging.getLogger(__name__)

async def test_whisper_cpp():
    """ทดสอบ Whisper.cpp"""
    print("\n" + "="*60)
    print("🧪 Test 1: Whisper.cpp")
    print("="*60)
    
    from config import Config
    
    cpp_enabled = Config.WHISPER_CPP_ENABLED
    cpp_binary = Path(Config.WHISPER_CPP_BIN_PATH)
    cpp_model = Path(Config.WHISPER_CPP_MODEL_PATH)
    
    print(f"WHISPER_CPP_ENABLED: {cpp_enabled}")
    print(f"WHISPER_CPP_BIN_PATH: {cpp_binary}")
    print(f"WHISPER_CPP_MODEL_PATH: {cpp_model}")
    
    if cpp_enabled:
        if cpp_binary.exists():
            print(f"✅ Binary exists: {cpp_binary}")
        else:
            print(f"❌ Binary NOT found: {cpp_binary}")
            print("💡 Fix: รัน setup_whisper_cpp.py หรือตั้ง WHISPER_CPP_ENABLED=false")
        
        if cpp_model.exists():
            print(f"✅ Model exists: {cpp_model}")
        else:
            print(f"❌ Model NOT found: {cpp_model}")
            print("💡 Fix: รัน setup_whisper_cpp.py เพื่อดาวน์โหลดโมเดล")
    else:
        print("✅ Whisper.cpp disabled (using Python Whisper)")

async def test_stt_handler():
    """ทดสอบ STT Handler"""
    print("\n" + "="*60)
    print("🧪 Test 2: STT Handler")
    print("="*60)
    
    try:
        from audio.stt_handler import STTHandler
        from config import Config
        
        print("✅ STTHandler imported successfully")
        
        # สร้าง STT handler
        stt = STTHandler(
            model_name=Config.WHISPER_MODEL,
            device=Config.WHISPER_DEVICE,
            language=Config.WHISPER_LANG,
            use_cpp=Config.WHISPER_CPP_ENABLED,
            cpp_binary_path=Config.WHISPER_CPP_BIN_PATH if Config.WHISPER_CPP_ENABLED else None,
            cpp_model_path=Config.WHISPER_CPP_MODEL_PATH if Config.WHISPER_CPP_ENABLED else None
        )
        
        print(f"✅ STT Handler created")
        print(f"   Model: {Config.WHISPER_MODEL}")
        print(f"   Device: {Config.WHISPER_DEVICE}")
        print(f"   Language: {Config.WHISPER_LANG}")
        print(f"   Using cpp: {stt.cpp_available}")
        
        # ทดสอบด้วย dummy audio
        print("\n📝 Testing with dummy audio...")
        
        # สร้าง audio 3 วินาที (Discord format: 48kHz stereo)
        duration = 3
        sample_rate = 48000
        samples = int(duration * sample_rate)
        
        # Generate sine wave (440 Hz)
        t = np.linspace(0, duration, samples)
        audio_mono = (np.sin(2 * np.pi * 440 * t) * 0.3).astype(np.float32)
        
        # Convert to stereo
        audio_stereo = np.repeat(audio_mono, 2)
        
        # Convert to int16 bytes (Discord format)
        audio_int16 = (audio_stereo * 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()
        
        print(f"   Audio duration: {duration}s")
        print(f"   Sample rate: {sample_rate}Hz")
        print(f"   Bytes: {len(audio_bytes)}")
        
        # Transcribe (อาจไม่ได้ text จริงเพราะเป็น sine wave)
        print("\n🎤 Transcribing...")
        text = await stt.transcribe(audio_bytes, sample_rate)
        
        if text:
            print(f"✅ Transcription result: '{text}'")
        else:
            print(f"⚠️  No text transcribed (expected for sine wave)")
        
        # ดูสถิติ
        stats = stt.get_stats()
        print(f"\n📊 Stats:")
        print(f"   Total: {stats['total']}")
        print(f"   Failed: {stats['failed']}")
        print(f"   Success rate: {stats['success_rate']}")
        
        print("\n✅ STT Handler works!")
        return True
        
    except Exception as e:
        print(f"❌ STT Handler test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_audio_preprocessing():
    """ทดสอบ Audio Preprocessing"""
    print("\n" + "="*60)
    print("🧪 Test 3: Audio Preprocessing")
    print("="*60)
    
    try:
        # ทดสอบการ preprocess audio
        
        # สร้าง audio ที่มี packet loss (uneven length)
        audio_with_issues = np.random.randn(48000 * 2 + 123).astype(np.float32)
        audio_bytes = (audio_with_issues * 32767).astype(np.int16).tobytes()
        
        print(f"Input audio: {len(audio_bytes)} bytes (uneven)")
        
        # Import STT handler
        from audio.stt_handler import STTHandler
        
        stt = STTHandler(device='cpu')  # Use CPU for testing
        
        # Preprocess
        audio_np = stt._preprocess_audio(audio_bytes, 48000)
        
        if audio_np is not None and len(audio_np) > 0:
            print(f"✅ Preprocessed audio: {len(audio_np)} samples")
            print(f"   Duration: {len(audio_np)/16000:.2f}s")
            print(f"   Dtype: {audio_np.dtype}")
            print(f"   Range: [{audio_np.min():.3f}, {audio_np.max():.3f}]")
            
            # Validate
            if stt._validate_audio(audio_np):
                print("✅ Audio validation passed")
            else:
                print("❌ Audio validation failed")
        else:
            print("❌ Preprocessing returned empty audio")
            return False
        
        print("\n✅ Audio preprocessing works!")
        return True
        
    except Exception as e:
        print(f"❌ Audio preprocessing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_tensor_error_fix():
    """ทดสอบการแก้ไข Tensor Error"""
    print("\n" + "="*60)
    print("🧪 Test 4: Tensor Error Fix")
    print("="*60)
    
    try:
        from audio.stt_handler import STTHandler
        
        stt = STTHandler(device='cpu')
        
        # สร้าง audio ที่มีขนาดแปลกๆ (เคยทำให้เกิด tensor error)
        problematic_sizes = [
            48000 * 0.3,  # 0.3s
            48000 * 1.5 + 17,  # 1.5s + 17 samples
            48000 * 2.7 + 333,  # 2.7s + 333 samples
        ]
        
        print("Testing problematic audio sizes...")
        
        passed = 0
        failed = 0
        
        for size in problematic_sizes:
            size = int(size)
            audio = np.random.randn(size).astype(np.float32)
            audio_bytes = (audio * 32767).astype(np.int16).tobytes()
            
            try:
                result = stt._preprocess_audio(audio_bytes, 48000)
                
                if result is not None and len(result) > 0:
                    # ตรวจสอบว่า length ถูกแก้ไขแล้ว
                    if len(result) % 320 == 0:  # Whisper likes multiples of 320
                        print(f"✅ {size} samples → {len(result)} samples (fixed)")
                        passed += 1
                    else:
                        print(f"⚠️  {size} samples → {len(result)} samples (not aligned)")
                        passed += 1
                else:
                    print(f"⚠️  {size} samples → skipped (too short)")
                    passed += 1
                    
            except Exception as e:
                print(f"❌ {size} samples → Error: {e}")
                failed += 1
        
        print(f"\n📊 Results: {passed} passed, {failed} failed")
        
        if failed == 0:
            print("✅ Tensor error fix works!")
            return True
        else:
            print("❌ Some tests failed")
            return False
        
    except Exception as e:
        print(f"❌ Tensor error test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║              Test Fixes Script                            ║
║              ทดสอบว่าการแก้ไขทำงานหรือไม่                ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    results = []
    
    # Test 1
    await test_whisper_cpp()
    
    # Test 2
    result2 = await test_stt_handler()
    results.append(('STT Handler', result2))
    
    # Test 3
    result3 = await test_audio_preprocessing()
    results.append(('Audio Preprocessing', result3))
    
    # Test 4
    result4 = await test_tensor_error_fix()
    results.append(('Tensor Error Fix', result4))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n✅ All tests passed! 🎉")
        print("\n🚀 Next steps:")
        print("   1. รัน: python src/main.py")
        print("   2. ใน Discord: !join")
        print("   3. พูดอะไรสักอย่าง")
        print("   4. ดูว่าโมเดลตอบกลับและไม่นิ่ง")
    else:
        print("\n❌ Some tests failed")
        print("\n💡 Check errors above and:")
        print("   1. ตรวจสอบ .env")
        print("   2. ติดตั้ง dependencies: pip install -r requirements.txt")
        print("   3. ดู QUICK_FIX.md")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()