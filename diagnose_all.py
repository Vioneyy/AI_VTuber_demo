"""
Complete Diagnostic Script
วิเคราะห์ปัญหาทั้งหมดของ STT, TTS, และ GPU (ปรับใหม่ให้ใช้ Faster-Whisper + Edge-TTS)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

import torch
import numpy as np
import soundfile as sf
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("""
╔═══════════════════════════════════════════════════════════╗
║          Complete System Diagnostic                       ║
║          วิเคราะห์ปัญหา STT, TTS, GPU                    ║
╚═══════════════════════════════════════════════════════════╝
""")

def check_gpu():
    """ตรวจสอบ GPU"""
    print("\n" + "="*60)
    print("🔍 1. GPU Check")
    print("="*60)
    
    cuda_available = torch.cuda.is_available()
    
    if cuda_available:
        print(f"✅ CUDA Available: YES")
        print(f"   Device count: {torch.cuda.device_count()}")
        
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            print(f"\n   GPU {i}:")
            print(f"   └─ Name: {props.name}")
            print(f"   └─ VRAM: {props.total_memory / 1024**3:.1f} GB")
            print(f"   └─ Compute Capability: {props.major}.{props.minor}")
            
            # Test GPU
            try:
                test_tensor = torch.randn(1000, 1000).cuda(i)
                result = test_tensor @ test_tensor.t()
                print(f"   └─ Test: ✅ PASS")
            except Exception as e:
                print(f"   └─ Test: ❌ FAIL - {e}")
    else:
        print(f"❌ CUDA Available: NO")
        print(f"   Will use CPU (slower)")
        print(f"\n💡 To enable GPU:")
        print(f"   1. Install CUDA Toolkit")
        print(f"   2. Install CUDA-enabled PyTorch:")
        print(f"      pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
    
    return cuda_available

def check_audio_files():
    """ตรวจสอบไฟล์เสียง"""
    print("\n" + "="*60)
    print("🔍 2. Audio Files Check")
    print("="*60)
    
    # Check Discord input recordings
    discord_in_path = Path("temp/recordings/discord_in")
    if discord_in_path.exists():
        audio_files = list(discord_in_path.glob("*.wav"))
        print(f"\n📁 Discord Input: {len(audio_files)} files")
        
        if audio_files:
            # Analyze first file
            sample_file = audio_files[0]
            print(f"\n   Analyzing: {sample_file.name}")
            
            try:
                audio, sr = sf.read(sample_file)
                duration = len(audio) / sr
                
                print(f"   ├─ Sample rate: {sr} Hz")
                print(f"   ├─ Duration: {duration:.2f}s")
                print(f"   ├─ Channels: {audio.ndim if audio.ndim == 1 else audio.shape[1]}")
                print(f"   ├─ Dtype: {audio.dtype}")
                print(f"   ├─ Range: [{audio.min():.3f}, {audio.max():.3f}]")
                
                # Check if audio is mostly silent
                rms = np.sqrt(np.mean(audio**2))
                print(f"   └─ RMS: {rms:.6f}")
                
                if rms < 0.001:
                    print(f"      ⚠️  WARNING: Audio is very quiet/silent!")
                elif rms > 1.0:
                    print(f"      ⚠️  WARNING: Audio is clipping!")
                else:
                    print(f"      ✅ Audio level OK")
                    
            except Exception as e:
                print(f"   └─ ❌ Error reading: {e}")
    else:
        print(f"📁 Discord Input: Not found (no recordings yet)")
    
    # Check Discord output recordings
    discord_out_path = Path("temp/recordings/discord_out")
    if discord_out_path.exists():
        audio_files = list(discord_out_path.glob("*.wav"))
        print(f"\n📁 Discord Output: {len(audio_files)} files")
        
        if audio_files:
            sample_file = audio_files[0]
            print(f"\n   Analyzing: {sample_file.name}")
            
            try:
                audio, sr = sf.read(sample_file)
                duration = len(audio) / sr
                
                print(f"   ├─ Sample rate: {sr} Hz")
                print(f"   ├─ Duration: {duration:.2f}s")
                print(f"   ├─ Dtype: {audio.dtype}")
                print(f"   └─ Range: [{audio.min():.3f}, {audio.max():.3f}]")
                
                # Check if file is silent
                if np.abs(audio).max() < 0.001:
                    print(f"      ❌ PROBLEM: Output file is SILENT!")
                    print(f"      This explains why you hear nothing")
                else:
                    print(f"      ✅ Output has audio")
                    
            except Exception as e:
                print(f"   └─ ❌ Error reading: {e}")
    else:
        print(f"📁 Discord Output: Not found")

def check_stt():
    """ตรวจสอบ STT (Faster-Whisper)"""
    print("\n" + "="*60)
    print("🔍 3. STT (Faster-Whisper) Check")
    print("="*60)
    
    try:
        from faster_whisper import WhisperModel
        print("✅ faster-whisper installed")
        
        model_name = os.getenv('WHISPER_MODEL', 'base')
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"   → Using model: {model_name} on {device}")
        
        try:
            model = WhisperModel(model_name, device=device)
            print("✅ Model initialized")
            
            discord_in = Path("temp/recordings/discord_in")
            if discord_in.exists():
                audio_files = list(discord_in.glob("*.wav"))
                if audio_files:
                    test_file = audio_files[0]
                    print(f"\n   Testing with: {test_file.name}")
                    
                    segments, info = model.transcribe(str(test_file), language=os.getenv('WHISPER_LANG', 'th'))
                    text = "".join([seg.text for seg in segments]).strip()
                    print(f"   └─ Transcription: '{text}'")
                    
                    if not text:
                        print("      ❌ PROBLEM: Empty transcription!")
                    else:
                        print("      ✅ Transcription looks OK")
        except Exception as e:
            print(f"❌ Faster-Whisper test failed: {e}")
    except ImportError:
        print("❌ faster-whisper not installed")

def check_tts():
    """ตรวจสอบ TTS (Edge-TTS)"""
    print("\n" + "="*60)
    print("🔍 4. TTS Check (Edge-TTS)")
    print("="*60)
    
    try:
        import asyncio
        import edge_tts
        print("✅ edge-tts installed")
        
        voice = os.getenv('EDGE_TTS_VOICE', 'th-TH-PremwadeeNeural')
        text = "สวัสดีค่ะ กำลังทดสอบเสียงพูดจากเอดจ์ทีทีเอส"
        out_path = Path("temp/diagnose_edge_tts.mp3")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        async def run_test():
            communicate = edge_tts.Communicate(text=text, voice=voice)
            await communicate.save(str(out_path))
        
        asyncio.run(run_test())
        
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"✅ Synthesized audio: {out_path}")
        else:
            print("❌ TTS output file missing or empty")
    except ImportError:
        print("❌ edge-tts not installed")
    except Exception as e:
        print(f"❌ Edge-TTS test failed: {e}")

def analyze_problem():
    """วิเคราะห์ปัญหา"""
    print("\n" + "="*60)
    print("📊 Problem Analysis")
    print("="*60)
    
    # Check Discord input files
    discord_in = Path("temp/recordings/discord_in")
    has_input = discord_in.exists() and list(discord_in.glob("*.wav"))
    
    # Check Discord output files
    discord_out = Path("temp/recordings/discord_out")
    has_output = discord_out.exists() and list(discord_out.glob("*.wav"))
    
    if has_input:
        # Analyze input audio quality
        audio_file = list(discord_in.glob("*.wav"))[0]
        audio, sr = sf.read(audio_file)
        
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        
        rms = np.sqrt(np.mean(audio**2))
        
        print(f"\n🎤 STT Input Analysis:")
        print(f"   Sample rate: {sr} Hz")
        print(f"   RMS level: {rms:.6f}")
        
        if sr != 16000:
            print(f"   ⚠️  PROBLEM 1: Sample rate mismatch!")
            print(f"   Expected: 16000 Hz, Got: {sr} Hz")
            print(f"   Fix: Need resampling")
        
        if rms < 0.01:
            print(f"   ⚠️  PROBLEM 2: Audio too quiet!")
            print(f"   Fix: Need amplification")
        
        # Check for clipping
        if np.abs(audio).max() >= 0.99:
            print(f"   ⚠️  PROBLEM 3: Audio clipping!")
            print(f"   Fix: Need normalization")
    
    if has_output:
        # Analyze output audio
        audio_file = list(discord_out.glob("*.wav"))[0]
        audio, sr = sf.read(audio_file)
        
        print(f"\n🔊 TTS Output Analysis:")
        print(f"   Sample rate: {sr} Hz")
        print(f"   Max amplitude: {np.abs(audio).max():.6f}")
        
        if np.abs(audio).max() < 0.001:
            print(f"   ❌ CRITICAL PROBLEM: Output is SILENT!")
            print(f"   Possible causes:")
            print(f"   1. TTS generation failed")
            print(f"   2. Normalization error")
            print(f"   3. Format/Playback error")

def recommendations():
    """แนะนำการแก้ไข"""
    print("\n" + "="*60)
    print("💡 Recommendations")
    print("="*60)
    
    print(f"\n🔧 Immediate Fixes:")
    print(f"   1. ใช้ Faster-Whisper สำหรับ STT (แนะนำ)")
    print(f"   2. ใช้ Edge-TTS สำหรับ TTS (แนะนำ)")
    print(f"   3. ตรวจสอบระดับเสียงและการจัดรูปแบบไฟล์")
    print(f"   4. เปิดใช้ GPU หากรองรับ เพื่อความเร็ว")
    
    print(f"\n🚀 ตัวเลือกอื่น (ถ้าต้องการทดแทน):")
    print(f"\n   STT Options:")
    print(f"   • Vosk - เร็วมาก, offline, แต่ accuracy ต่ำกว่า")
    print(f"   • Google Speech-to-Text API - แม่นที่สุด แต่ต้องใช้ API")
    
    print(f"\n   TTS Options:")
    print(f"   • ElevenLabs API - คุณภาพสูง แต่มีค่าใช้จ่าย")

def main():
    """Main function"""
    results = {}
    
    # Run checks
    results['gpu'] = check_gpu()
    check_audio_files()
    check_stt()
    check_tts()
    analyze_problem()
    recommendations()
    
    # Summary
    print("\n" + "="*60)
    print("📋 Summary")
    print("="*60)
    
    print(f"\n{'✅' if results['gpu'] else '❌'} GPU: {'Available' if results['gpu'] else 'Not available (using CPU)'}")
    
    print(f"\n💡 Next Steps:")
    print(f"   1. Review audio files in temp/recordings/")
    print(f"   2. Check if files are silent/corrupted")
    print(f"   3. Run the fix scripts provided")
    print(f"   4. Consider switching to Faster-Whisper + Edge-TTS (recommended)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Cancelled")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()