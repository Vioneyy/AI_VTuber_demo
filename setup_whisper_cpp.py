"""
Setup Whisper.cpp for Windows
ดาวน์โหลดและติดตั้ง Whisper.cpp พร้อมโมเดล
"""
import os
import sys
import urllib.request
import zipfile
import subprocess
from pathlib import Path
import shutil

def download_file(url: str, destination: str):
    """ดาวน์โหลดไฟล์"""
    print(f"📥 Downloading: {url}")
    print(f"   → {destination}")
    
    try:
        urllib.request.urlretrieve(url, destination)
        print(f"✅ Downloaded!")
        return True
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False

def extract_zip(zip_path: str, extract_to: str):
    """แตกไฟล์ zip"""
    print(f"📦 Extracting: {zip_path}")
    print(f"   → {extract_to}")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print(f"✅ Extracted!")
        return True
    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        return False

def main():
    """Main setup"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║          Whisper.cpp Setup for Windows                    ║
║          ติดตั้ง Whisper.cpp พร้อมโมเดล                  ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    base_dir = Path.cwd()
    whisper_dir = base_dir / "whisper.cpp"
    models_dir = whisper_dir / "models"
    
    # สร้างโฟลเดอร์
    whisper_dir.mkdir(exist_ok=True)
    models_dir.mkdir(exist_ok=True)
    
    print(f"📁 Whisper.cpp directory: {whisper_dir}")
    print(f"📁 Models directory: {models_dir}")
    
    # ============================================
    # Option 1: ดาวน์โหลด Pre-compiled Binary
    # ============================================
    print("\n" + "="*60)
    print("Option 1: Download Pre-compiled Binary (แนะนำ)")
    print("="*60)
    
    # URL สำหรับ pre-compiled binary (ถ้ามี)
    # หมายเหตุ: whisper.cpp ไม่มี official pre-compiled binary
    # ต้อง compile เอง
    
    print("⚠️  Whisper.cpp ไม่มี pre-compiled binary official")
    print("   คุณมี 2 ทางเลือก:")
    print("   1. Compile เอง (ต้องมี Visual Studio)")
    print("   2. ใช้ Python Whisper แทน (ช้ากว่าแต่ใช้งานได้)")
    
    choice = input("\n❓ ต้องการ compile whisper.cpp เองหรือไม่? (y/n): ").lower()
    
    if choice == 'y':
        print("\n" + "="*60)
        print("Compile Whisper.cpp")
        print("="*60)
        
        # ตรวจสอบว่ามี Git
        print("\n1️⃣ ตรวจสอบ Git...")
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print(f"✅ {result.stdout.strip()}")
            else:
                print("❌ Git ไม่พบ - ติดตั้งจาก https://git-scm.com/")
                return
        except FileNotFoundError:
            print("❌ Git ไม่พบ - ติดตั้งจาก https://git-scm.com/")
            return
        
        # ตรวจสอบว่ามี CMake
        print("\n2️⃣ ตรวจสอบ CMake...")
        try:
            result = subprocess.run(
                ["cmake", "--version"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print(f"✅ {result.stdout.strip().split()[0:3]}")
            else:
                print("❌ CMake ไม่พบ - ติดตั้งจาก https://cmake.org/download/")
                return
        except FileNotFoundError:
            print("❌ CMake ไม่พบ - ติดตั้งจาก https://cmake.org/download/")
            return
        
        # Clone whisper.cpp
        print("\n3️⃣ Clone whisper.cpp repository...")
        if not (whisper_dir / ".git").exists():
            try:
                subprocess.run(
                    ["git", "clone", "https://github.com/ggerganov/whisper.cpp.git", str(whisper_dir)],
                    check=True
                )
                print("✅ Cloned!")
            except Exception as e:
                print(f"❌ Clone failed: {e}")
                return
        else:
            print("✅ Repository already exists")
        
        # Build
        print("\n4️⃣ Building whisper.cpp...")
        print("⚠️  This may take 5-10 minutes...")
        
        build_dir = whisper_dir / "build"
        build_dir.mkdir(exist_ok=True)
        
        try:
            # Configure with CMake
            print("   📝 Configuring with CMake...")
            subprocess.run(
                ["cmake", "..", "-DWHISPER_CUDA=ON"],  # เปิด CUDA ถ้ามี
                cwd=build_dir,
                check=True
            )
            
            # Build
            print("   🔨 Building...")
            subprocess.run(
                ["cmake", "--build", ".", "--config", "Release"],
                cwd=build_dir,
                check=True
            )
            
            print("✅ Build completed!")
            
            # หา main.exe
            main_exe = None
            for path in build_dir.rglob("main.exe"):
                main_exe = path
                break
            
            if main_exe:
                print(f"✅ Found main.exe: {main_exe}")
                
                # Copy ไปที่ root
                target = whisper_dir / "main.exe"
                shutil.copy2(main_exe, target)
                print(f"✅ Copied to: {target}")
            else:
                print("❌ main.exe not found after build")
                
        except Exception as e:
            print(f"❌ Build failed: {e}")
            print("\n💡 Alternative: ใช้ Python Whisper แทน")
            print("   แก้ไขใน .env:")
            print("   WHISPER_CPP_ENABLED=false")
            return
    
    # ============================================
    # ดาวน์โหลดโมเดล
    # ============================================
    print("\n" + "="*60)
    print("📥 Download Whisper Models")
    print("="*60)
    
    models = {
        'tiny': 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin',
        'base': 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin',
        'small': 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin'
    }
    
    print("\nAvailable models:")
    print("  tiny  - 75 MB  (เร็วที่สุด, แม่นน้อย)")
    print("  base  - 142 MB (แนะนำ)")
    print("  small - 466 MB (แม่นกว่า, ช้ากว่า)")
    
    model_choice = input("\n❓ เลือกโมเดล (tiny/base/small) [base]: ").lower() or 'base'
    
    if model_choice not in models:
        print(f"❌ Invalid choice: {model_choice}")
        return
    
    model_url = models[model_choice]
    model_path = models_dir / f"ggml-{model_choice}.bin"
    
    if model_path.exists():
        print(f"✅ Model already exists: {model_path}")
    else:
        if download_file(model_url, str(model_path)):
            print(f"✅ Model downloaded: {model_path}")
        else:
            print("❌ Model download failed")
            return
    
    # ============================================
    # อัปเดต .env
    # ============================================
    print("\n" + "="*60)
    print("📝 Update .env")
    print("="*60)
    
    env_path = Path(".env")
    
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            env_content = f.read()
        
        # อัปเดตค่า
        lines = env_content.split('\n')
        new_lines = []
        
        updated = {
            'WHISPER_CPP_ENABLED': False,
            'WHISPER_CPP_BIN_PATH': False,
            'WHISPER_CPP_MODEL_PATH': False
        }
        
        for line in lines:
            if line.startswith('WHISPER_CPP_ENABLED='):
                new_lines.append('WHISPER_CPP_ENABLED=true')
                updated['WHISPER_CPP_ENABLED'] = True
            elif line.startswith('WHISPER_CPP_BIN_PATH='):
                new_lines.append(f'WHISPER_CPP_BIN_PATH={whisper_dir}/main.exe')
                updated['WHISPER_CPP_BIN_PATH'] = True
            elif line.startswith('WHISPER_CPP_MODEL_PATH='):
                new_lines.append(f'WHISPER_CPP_MODEL_PATH={model_path}')
                updated['WHISPER_CPP_MODEL_PATH'] = True
            else:
                new_lines.append(line)
        
        # เพิ่มค่าที่ยังไม่มี
        if not updated['WHISPER_CPP_ENABLED']:
            new_lines.append('WHISPER_CPP_ENABLED=true')
        if not updated['WHISPER_CPP_BIN_PATH']:
            new_lines.append(f'WHISPER_CPP_BIN_PATH={whisper_dir}/main.exe')
        if not updated['WHISPER_CPP_MODEL_PATH']:
            new_lines.append(f'WHISPER_CPP_MODEL_PATH={model_path}')
        
        # บันทึก
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        
        print("✅ .env updated")
    else:
        print("⚠️  .env not found - create it manually")
    
    # ============================================
    # ทดสอบ
    # ============================================
    print("\n" + "="*60)
    print("🧪 Test Whisper.cpp")
    print("="*60)
    
    main_exe = whisper_dir / "main.exe"
    
    if main_exe.exists():
        try:
            result = subprocess.run(
                [str(main_exe), "--help"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                print("✅ Whisper.cpp works!")
            else:
                print("⚠️  Whisper.cpp may have issues")
                print(result.stderr)
        except Exception as e:
            print(f"⚠️  Test failed: {e}")
    else:
        print("⚠️  main.exe not found")
        print(f"   Expected: {main_exe}")
    
    # ============================================
    # สรุป
    # ============================================
    print("\n" + "="*60)
    print("✅ Setup Complete!")
    print("="*60)
    
    print(f"\n📁 Whisper.cpp location: {whisper_dir}")
    print(f"📁 Model location: {model_path}")
    print(f"🔧 Binary: {main_exe}")
    
    print("\n🚀 Next steps:")
    print("   1. ตรวจสอบ .env ว่ามีค่าเหล่านี้:")
    print(f"      WHISPER_CPP_ENABLED=true")
    print(f"      WHISPER_CPP_BIN_PATH={whisper_dir}/main.exe")
    print(f"      WHISPER_CPP_MODEL_PATH={model_path}")
    print("   2. รัน: python src/main.py")
    
    if not main_exe.exists():
        print("\n⚠️  Alternative: ถ้า whisper.cpp ใช้ไม่ได้")
        print("   ใช้ Python Whisper แทน:")
        print("   ใน .env ตั้งเป็น: WHISPER_CPP_ENABLED=false")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()