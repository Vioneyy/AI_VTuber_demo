"""
Simple Test Script
ทดสอบการแก้ไขแบบง่ายๆ ไม่ซับซ้อน
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

print("""
╔═══════════════════════════════════════════════════════════╗
║              Simple Test Script                           ║
║              ทดสอบการตั้งค่าและไฟล์                      ║
╚═══════════════════════════════════════════════════════════╝
""")

def test_env_file():
    """ทดสอบไฟล์ .env"""
    print("="*60)
    print("🧪 Test 1: .env File")
    print("="*60)
    
    env_path = Path(__file__).parent / ".env"
    
    if not env_path.exists():
        print("❌ .env file not found!")
        print("💡 Create .env from .env.example")
        return False
    
    print(f"✅ .env file exists: {env_path.absolute()}")
    
    # โหลด .env
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=str(env_path))
    
    # ตรวจสอบค่าสำคัญ
    checks = {
        'DISCORD_BOT_TOKEN': os.getenv('DISCORD_BOT_TOKEN', ''),
        'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY', ''),
        'WHISPER_MODEL': os.getenv('WHISPER_MODEL', 'base'),
        'WHISPER_DEVICE': os.getenv('WHISPER_DEVICE', 'cuda'),
        'WHISPER_CPP_ENABLED': os.getenv('WHISPER_CPP_ENABLED', 'false'),
    }
    
    print("\n📋 Configuration:")
    for key, value in checks.items():
        if key in ['DISCORD_BOT_TOKEN', 'OPENAI_API_KEY']:
            if value and 'your_' not in value.lower():
                print(f"   ✅ {key}: {'*' * 20}...{value[-5:]}")
            else:
                print(f"   ❌ {key}: Not set or placeholder")
        else:
            print(f"   ✅ {key}: {value}")
    
    return True

def test_whisper_cpp_path():
    """ทดสอบ Whisper.cpp path"""
    print("\n" + "="*60)
    print("🧪 Test 2: Whisper.cpp")
    print("="*60)
    
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=str(Path(__file__).parent / ".env"))
    
    cpp_enabled = os.getenv('WHISPER_CPP_ENABLED', 'false').lower() == 'true'
    cpp_binary = os.getenv('WHISPER_CPP_BIN_PATH', 'whisper.cpp/main.exe')
    cpp_model = os.getenv('WHISPER_CPP_MODEL_PATH', 'whisper.cpp/models/ggml-base.bin')
    
    print(f"WHISPER_CPP_ENABLED: {cpp_enabled}")
    
    if cpp_enabled:
        print(f"WHISPER_CPP_BIN_PATH: {cpp_binary}")
        print(f"WHISPER_CPP_MODEL_PATH: {cpp_model}")
        
        binary_path = Path(cpp_binary)
        model_path = Path(cpp_model)
        
        if binary_path.exists():
            print(f"✅ Binary found: {binary_path.absolute()}")
        else:
            print(f"❌ Binary NOT found: {binary_path.absolute()}")
            print(f"💡 Fix:")
            print(f"   Option 1: รัน setup_whisper_cpp.py")
            print(f"   Option 2: ตั้ง WHISPER_CPP_ENABLED=false ใน .env")
        
        if model_path.exists():
            print(f"✅ Model found: {model_path.absolute()}")
        else:
            print(f"❌ Model NOT found: {model_path.absolute()}")
            print(f"💡 Fix: รัน setup_whisper_cpp.py")
    else:
        print("✅ Whisper.cpp disabled - will use Python Whisper")
        print("   This is OK and recommended for stability!")
    
    return True

def test_stt_handler_file():
    """ทดสอบว่ามีไฟล์ STT Handler หรือไม่"""
    print("\n" + "="*60)
    print("🧪 Test 3: STT Handler File")
    print("="*60)
    
    stt_file = Path("src/audio/stt_handler.py")
    
    if not stt_file.exists():
        print(f"❌ STT Handler NOT found: {stt_file}")
        print(f"💡 Fix: สร้างไฟล์ src/audio/stt_handler.py จากไฟล์ที่ให้ไป")
        return False
    
    print(f"✅ STT Handler exists: {stt_file.absolute()}")
    
    # ตรวจสอบว่ามี methods ที่จำเป็น
    with open(stt_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    required_methods = [
        '_preprocess_audio',
        '_validate_audio',
        '_fix_length_for_whisper',
        '_transcribe_with_retry',
    ]
    
    print("\n📝 Checking required methods:")
    all_found = True
    for method in required_methods:
        if method in content:
            print(f"   ✅ {method}")
        else:
            print(f"   ❌ {method} NOT found")
            all_found = False
    
    if all_found:
        print("\n✅ STT Handler has all required methods!")
    else:
        print("\n❌ STT Handler is missing some methods")
        print("💡 Fix: แทนที่ด้วยไฟล์ใหม่ที่ให้ไป")
    
    return all_found

def test_python_imports():
    """ทดสอบการ import Python modules"""
    print("\n" + "="*60)
    print("🧪 Test 4: Python Dependencies")
    print("="*60)
    
    required_modules = [
        ('numpy', 'numpy'),
        ('torch', 'PyTorch'),
        ('scipy', 'scipy'),
        ('soundfile', 'soundfile'),
        ('dotenv', 'python-dotenv'),
    ]
    
    all_ok = True
    
    for module_name, package_name in required_modules:
        try:
            __import__(module_name)
            print(f"✅ {package_name}")
        except ImportError:
            print(f"❌ {package_name} NOT installed")
            print(f"   Fix: pip install {package_name}")
            all_ok = False
    
    if all_ok:
        print("\n✅ All dependencies installed!")
    else:
        print("\n❌ Some dependencies missing")
        print("💡 Fix: pip install -r requirements.txt")
    
    return all_ok

def test_cuda():
    """ทดสอบ CUDA"""
    print("\n" + "="*60)
    print("🧪 Test 5: CUDA")
    print("="*60)
    
    try:
        import torch
        
        cuda_available = torch.cuda.is_available()
        
        if cuda_available:
            print(f"✅ CUDA available")
            print(f"   Devices: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                print(f"   GPU {i}: {props.name}")
                print(f"          VRAM: {props.total_memory / 1024**3:.1f} GB")
        else:
            print(f"⚠️  CUDA not available - will use CPU")
            print(f"   This is OK but slower")
            print(f"   For faster performance, install CUDA-enabled PyTorch")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking CUDA: {e}")
        return False

def test_directory_structure():
    """ทดสอบโครงสร้างโฟลเดอร์"""
    print("\n" + "="*60)
    print("🧪 Test 6: Directory Structure")
    print("="*60)
    
    required_dirs = [
        'src',
        'src/audio',
        'src/core',
        'src/adapters',
        'reference_audio',
        'logs',
    ]
    
    all_ok = True
    
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            print(f"✅ {dir_path}/")
        else:
            print(f"❌ {dir_path}/ NOT found")
            print(f"   Creating...")
            path.mkdir(parents=True, exist_ok=True)
            print(f"   ✅ Created")
    
    return True

def main():
    """Main function"""
    
    results = []
    
    # Test 1
    results.append(('Environment File', test_env_file()))
    
    # Test 2
    results.append(('Whisper.cpp Path', test_whisper_cpp_path()))
    
    # Test 3
    results.append(('STT Handler File', test_stt_handler_file()))
    
    # Test 4
    results.append(('Python Dependencies', test_python_imports()))
    
    # Test 5
    results.append(('CUDA', test_cuda()))
    
    # Test 6
    results.append(('Directory Structure', test_directory_structure()))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n✅ All basic tests passed! 🎉")
        print("\n🚀 Next steps:")
        print("   1. แก้ไขปัญหาใน Test ที่ fail (ถ้ามี)")
        print("   2. รัน: python src/main.py")
        print("   3. ใน Discord: !join")
        print("   4. พูดอะไรสักอย่าง")
    else:
        print("\n❌ Some tests failed")
        print("\n💡 แก้ไขปัญหาตาม Fix ที่แสดงด้านบน")
        print("   แล้วรันทดสอบอีกครั้ง: python simple_test.py")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()