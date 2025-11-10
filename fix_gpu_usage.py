"""
GPU Usage Fix
แก้ไขปัญหาโปรเจคไม่ใช้ GPU
"""
import torch
import sys
from pathlib import Path

print("""
╔═══════════════════════════════════════════════════════════╗
║          GPU Usage Fix                                    ║
║          แก้ไขปัญหาไม่ใช้ GPU                             ║
╚═══════════════════════════════════════════════════════════╝
""")

def check_cuda():
    """ตรวจสอบ CUDA"""
    print("\n" + "="*60)
    print("🔍 CUDA Check")
    print("="*60)
    
    print(f"\nPyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    
    if torch.cuda.is_available():
        print(f"CUDA version: {torch.version.cuda}")
        print(f"cuDNN version: {torch.backends.cudnn.version()}")
        print(f"Device count: {torch.cuda.device_count()}")
        
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            print(f"\nGPU {i}:")
            print(f"  Name: {props.name}")
            print(f"  VRAM: {props.total_memory / 1024**3:.1f} GB")
            print(f"  Compute: {props.major}.{props.minor}")
        
        return True
    else:
        print("\n❌ CUDA not available!")
        print("\nPossible causes:")
        print("1. NVIDIA GPU not detected")
        print("2. CUDA not installed")
        print("3. PyTorch CPU version installed")
        
        print("\n💡 Fix:")
        print("Install CUDA PyTorch:")
        print("pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
        
        return False

def test_gpu():
    """ทดสอบ GPU"""
    print("\n" + "="*60)
    print("🧪 GPU Test")
    print("="*60)
    
    if not torch.cuda.is_available():
        print("❌ Cannot test - CUDA not available")
        return False
    
    try:
        # Test tensor operations
        print("\nTesting tensor operations...")
        device = torch.device('cuda:0')
        
        # Create tensor on GPU
        x = torch.randn(1000, 1000, device=device)
        y = torch.randn(1000, 1000, device=device)
        
        # Matrix multiplication
        z = x @ y
        
        print(f"✅ GPU tensor operations work")
        print(f"   Result shape: {z.shape}")
        print(f"   Device: {z.device}")
        
        # Test CUDA memory
        allocated = torch.cuda.memory_allocated() / 1024**2
        reserved = torch.cuda.memory_reserved() / 1024**2
        
        print(f"\n📊 GPU Memory:")
        print(f"   Allocated: {allocated:.1f} MB")
        print(f"   Reserved: {reserved:.1f} MB")
        
        return True
        
    except Exception as e:
        print(f"❌ GPU test failed: {e}")
        return False

def check_env_config():
    """ตรวจสอบ .env config"""
    print("\n" + "="*60)
    print("🔍 Configuration Check")
    print("="*60)
    
    env_path = Path(".env")
    
    if not env_path.exists():
        print("❌ .env not found")
        return False
    
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check device settings
    devices = {
        'TTS_DEVICE': 'cuda' if torch.cuda.is_available() else 'cpu',
        'WHISPER_DEVICE': 'cuda' if torch.cuda.is_available() else 'cpu',
    }
    
    print("\nDevice settings:")
    issues = []
    
    for key, expected in devices.items():
        if key in content:
            # Extract value
            for line in content.split('\n'):
                if line.startswith(key):
                    value = line.split('=')[1].strip()
                    
                    if value == expected:
                        print(f"✅ {key}={value}")
                    else:
                        print(f"⚠️  {key}={value} (should be {expected})")
                        issues.append((key, value, expected))
                    break
        else:
            print(f"❌ {key} not found")
            issues.append((key, None, expected))
    
    return len(issues) == 0, issues

def fix_env_config(issues):
    """แก้ไข .env config"""
    print("\n" + "="*60)
    print("🔧 Fixing Configuration")
    print("="*60)
    
    env_path = Path(".env")
    
    # Backup
    backup_path = env_path.with_suffix('.env.backup')
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"💾 Backup created: {backup_path}")
    
    # Fix issues
    lines = content.split('\n')
    new_lines = []
    fixed = set()
    
    for line in lines:
        modified = False
        
        for key, current, expected in issues:
            if line.startswith(key):
                new_lines.append(f"{key}={expected}")
                print(f"✅ Fixed: {key}={expected}")
                fixed.add(key)
                modified = True
                break
        
        if not modified:
            new_lines.append(line)
    
    # Add missing keys
    for key, current, expected in issues:
        if key not in fixed and current is None:
            new_lines.append(f"{key}={expected}")
            print(f"✅ Added: {key}={expected}")
    
    # Write back
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
    
    print(f"\n✅ Configuration updated")

def create_gpu_test_script():
    """สร้างสคริปต์ทดสอบ GPU"""
    print("\n" + "="*60)
    print("📝 Creating GPU Test Script")
    print("="*60)
    
    script = '''"""
GPU Usage Test
ทดสอบว่าโมดูลต่างๆ ใช้ GPU หรือไม่
"""
import torch
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

print("Testing GPU usage...")

# Test Whisper
try:
    import whisper
    model = whisper.load_model("tiny", device="cuda")
    print(f"✅ Whisper on GPU: {next(model.parameters()).device}")
except Exception as e:
    print(f"❌ Whisper: {e}")

# Test TTS
try:
    from f5_tts_th.tts import TTS
    # Check if TTS uses GPU
    print(f"✅ TTS module loaded")
except Exception as e:
    print(f"❌ TTS: {e}")

# Removed RVC test (TTS-only mode)

print("\\nGPU Memory:")
if torch.cuda.is_available():
    print(f"Allocated: {torch.cuda.memory_allocated()/1024**2:.1f} MB")
    print(f"Cached: {torch.cuda.memory_reserved()/1024**2:.1f} MB")
'''
    
    script_path = Path("test_gpu_usage.py")
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script)
    
    print(f"✅ Created: {script_path}")
    print(f"\nRun: python test_gpu_usage.py")

def main():
    """Main function"""
    
    # Check CUDA
    has_cuda = check_cuda()
    
    if not has_cuda:
        print("\n⚠️  Cannot proceed without CUDA")
        print("Please install CUDA-enabled PyTorch first")
        return
    
    # Test GPU
    gpu_works = test_gpu()
    
    if not gpu_works:
        print("\n⚠️  GPU test failed")
        return
    
    # Check config
    config_ok, issues = check_env_config()
    
    if not config_ok:
        print(f"\n⚠️  Found {len(issues)} configuration issues")
        
        fix = input("\n❓ Fix automatically? (y/n): ").lower()
        
        if fix == 'y':
            fix_env_config(issues)
        else:
            print("\nPlease fix manually:")
            for key, current, expected in issues:
                print(f"  {key}={expected}")
    else:
        print("\n✅ Configuration is correct")
    
    # Create test script
    create_gpu_test_script()
    
    # Summary
    print("\n" + "="*60)
    print("📋 Summary")
    print("="*60)
    
    print(f"\n{'✅' if has_cuda else '❌'} CUDA available")
    print(f"{'✅' if gpu_works else '❌'} GPU works")
    print(f"{'✅' if config_ok else '⚠️'} Configuration {'OK' if config_ok else 'fixed'}")
    
    print(f"\n🚀 Next steps:")
    print(f"   1. Run: python test_gpu_usage.py")
    print(f"   2. Run: python src/main.py")
    print(f"   3. Check logs for 'cuda' device usage")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Cancelled")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()