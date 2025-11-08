"""
Complete Fix Script
แก้ไขปัญหาทั้งหมดอัตโนมัติ
"""
from pathlib import Path
import shutil
import sys

print("""
╔═══════════════════════════════════════════════════════════╗
║          Complete Fix - แก้ไขทั้งหมดอัตโนมัติ            ║
╚═══════════════════════════════════════════════════════════╝
""")

def backup_file(file_path: Path):
    """Backup file"""
    if file_path.exists():
        backup = file_path.with_suffix(file_path.suffix + '.backup')
        shutil.copy2(file_path, backup)
        print(f"💾 Backup: {backup}")
        return True
    return False

def fix_env():
    """แก้ไข .env"""
    print("\n" + "="*60)
    print("🔧 Fix 1: .env Configuration")
    print("="*60)
    
    env_path = Path(".env")
    
    if not env_path.exists():
        print("❌ .env not found - creating from .env.example...")
        
        example_path = Path(".env.example")
        if example_path.exists():
            shutil.copy2(example_path, env_path)
            print("✅ Created .env from .env.example")
        else:
            print("❌ .env.example also not found!")
            return False
    
    # Read .env
    with open(env_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Backup
    backup_file(env_path)
    
    # Fix settings
    new_lines = []
    fixes_applied = []
    
    settings_to_fix = {
        'WHISPER_CPP_ENABLED': 'false',
        'TTS_DEVICE': 'cuda',
        'RVC_DEVICE': 'cuda',
        'WHISPER_DEVICE': 'cuda',
    }
    
    found_settings = set()
    
    for line in lines:
        modified = False
        
        for key, value in settings_to_fix.items():
            if line.strip().startswith(key + '='):
                current_value = line.split('=', 1)[1].strip()
                if current_value != value:
                    new_lines.append(f"{key}={value}\n")
                    fixes_applied.append(f"{key}: {current_value} → {value}")
                    modified = True
                else:
                    new_lines.append(line)
                    modified = True
                found_settings.add(key)
                break
        
        if not modified:
            new_lines.append(line)
    
    # Add missing settings
    for key, value in settings_to_fix.items():
        if key not in found_settings:
            new_lines.append(f"\n{key}={value}\n")
            fixes_applied.append(f"{key}: added")
    
    # Write back
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    if fixes_applied:
        print("\n✅ Fixed .env settings:")
        for fix in fixes_applied:
            print(f"   • {fix}")
    else:
        print("✅ .env already correct")
    
    return True

def update_main_py():
    """อัปเดต main.py ให้ใช้ Hybrid STT"""
    print("\n" + "="*60)
    print("🔧 Fix 2: Update main.py imports")
    print("="*60)
    
    main_path = Path("src/main.py")
    
    if not main_path.exists():
        print("❌ src/main.py not found")
        return False
    
    # Backup
    backup_file(main_path)
    
    # Read
    with open(main_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace imports
    replacements = [
        # STT
        (
            "from audio.faster_whisper_stt import FasterWhisperSTT",
            "from audio.hybrid_stt import HybridSTT"
        ),
        (
            "from audio.stt_handler import STTHandler",
            "from audio.hybrid_stt import HybridSTT as STTHandler"
        ),
        # TTS
        (
            "from audio.edge_tts_handler import EdgeTTSHandler",
            "from audio.fixed_tts_rvc_handler import FixedTTSRVCHandler"
        ),
    ]
    
    modified = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            modified = True
            print(f"✅ Replaced: {old.split()[-1]}")
    
    if modified:
        # Write back
        with open(main_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ main.py updated")
    else:
        print("⚠️  No changes needed (or imports not found)")
    
    return True

def create_required_files():
    """สร้างไฟล์ที่จำเป็น"""
    print("\n" + "="*60)
    print("🔧 Fix 3: Create Required Files")
    print("="*60)
    
    required_files = {
        "src/audio/hybrid_stt.py": "HybridSTT (from artifact)",
        "src/audio/fixed_tts_rvc_handler.py": "FixedTTSRVCHandler (from artifact)",
    }
    
    missing = []
    
    for file_path, description in required_files.items():
        path = Path(file_path)
        if path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - MISSING")
            print(f"   Please create from: {description}")
            missing.append(file_path)
    
    if missing:
        print(f"\n⚠️  {len(missing)} files need to be created manually")
        print("   Use the artifacts provided")
        return False
    
    return True

def check_dependencies():
    """ตรวจสอบ dependencies"""
    print("\n" + "="*60)
    print("🔧 Fix 4: Dependencies Check")
    print("="*60)
    
    required_packages = [
        ('torch', 'PyTorch'),
        ('whisper', 'openai-whisper'),
        ('soundfile', 'soundfile'),
        ('scipy', 'scipy'),
        ('numpy', 'numpy'),
    ]
    
    missing = []
    
    for module, package in required_packages:
        try:
            __import__(module)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} - NOT INSTALLED")
            missing.append(package)
    
    if missing:
        print(f"\n⚠️  Install missing packages:")
        print(f"   pip install {' '.join(missing)}")
        return False
    
    # Check CUDA
    try:
        import torch
        if torch.cuda.is_available():
            print(f"✅ CUDA available")
        else:
            print(f"⚠️  CUDA not available - will use CPU")
            print(f"   To enable GPU, run: install_cuda_pytorch.bat")
    except:
        pass
    
    return True

def create_test_script():
    """สร้างสคริปต์ทดสอบ"""
    print("\n" + "="*60)
    print("📝 Creating test script")
    print("="*60)
    
    test_script = '''"""
Test Fixed System
ทดสอบว่าแก้ไขสำเร็จหรือไม่
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

async def test_stt():
    """Test STT"""
    print("\\n🧪 Testing STT...")
    
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
    print("\\n🧪 Testing TTS...")
    
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
'''
    
    script_path = Path("test_fixed_system.py")
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(test_script)
    
    print(f"✅ Created: {script_path}")
    print(f"   Run: python {script_path}")

def main():
    """Main function"""
    
    print("\n🚀 Starting fixes...\n")
    
    results = []
    
    # Fix 1: .env
    results.append(('Environment Config', fix_env()))
    
    # Fix 2: main.py
    results.append(('main.py imports', update_main_py()))
    
    # Fix 3: Required files
    results.append(('Required Files', create_required_files()))
    
    # Fix 4: Dependencies
    results.append(('Dependencies', check_dependencies()))
    
    # Create test script
    create_test_script()
    
    # Summary
    print("\n" + "="*60)
    print("📊 Summary")
    print("="*60)
    
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    all_ok = all(r[1] for r in results)
    
    if all_ok:
        print("\n✅ All fixes applied!")
        print("\n🚀 Next steps:")
        print("   1. Run: python test_fixed_system.py")
        print("   2. If GPU not working: run install_cuda_pytorch.bat")
        print("   3. Run: python src/main.py")
    else:
        print("\n⚠️  Some manual steps required")
        print("\nManual steps:")
        print("   1. Create missing files from artifacts")
        print("   2. Install missing dependencies")
        print("   3. Run this script again")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Cancelled")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()