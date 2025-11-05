"""
Script สำหรับแก้ไขปัญหา Dependencies
รันก่อนติดตั้ง requirements.txt

ปัญหาที่แก้:
1. numpy dtype size incompatibility
2. pandas/sklearn version conflicts
3. torchvision nms operator missing
"""
import subprocess
import sys
import os

def run_command(cmd, description):
    """รันคำสั่งและแสดงผล"""
    print(f"\n{'='*60}")
    print(f"🔧 {description}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✅ Success!")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        if e.stderr:
            print(e.stderr)
        return False

def main():
    """Main function"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║          AI VTuber - Dependency Fixer                      ║
║          แก้ไขปัญหา Dependencies อัตโนมัติ                 ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # 1. อัปเดต pip
    run_command(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        "อัปเดต pip"
    )
    
    # 2. ถอนการติดตั้ง packages ที่ขัดแย้งกัน
    print("\n🗑️  Uninstalling conflicting packages...")
    packages_to_uninstall = [
        'numpy',
        'pandas', 
        'scikit-learn',
        'torch',
        'torchvision',
        'torchaudio',
        # CRITICAL: uninstall third-party asyncio which shadows stdlib
        'asyncio'
    ]
    
    for pkg in packages_to_uninstall:
        run_command(
            [sys.executable, "-m", "pip", "uninstall", "-y", pkg],
            f"Uninstalling {pkg}"
        )
    
    # 3. ติดตั้ง numpy เวอร์ชันที่ compatible
    run_command(
        [sys.executable, "-m", "pip", "install", "numpy==1.24.3"],
        "ติดตั้ง numpy==1.24.3 (compatible version)"
    )
    
    # 4. ติดตั้ง PyTorch (CPU version)
    print("\n🔥 ติดตั้ง PyTorch...")
    print("⚠️  Note: ถ้าต้องการใช้ GPU (CUDA), ต้องติดตั้งแยก")
    
    run_command(
        [
            sys.executable, "-m", "pip", "install",
            "torch==2.1.0",
            "torchvision==0.16.0", 
            "torchaudio==2.1.0",
            "--index-url", "https://download.pytorch.org/whl/cpu"
        ],
        "ติดตั้ง PyTorch CPU"
    )
    
    # 5. ติดตั้ง pandas และ scikit-learn
    run_command(
        [sys.executable, "-m", "pip", "install", "pandas==2.0.3"],
        "ติดตั้ง pandas==2.0.3"
    )
    
    run_command(
        [sys.executable, "-m", "pip", "install", "scikit-learn==1.3.2"],
        "ติดตั้ง scikit-learn==1.3.2"
    )
    
    # 6. ติดตั้ง requirements.txt
    if os.path.exists("requirements.txt"):
        run_command(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            "ติดตั้ง packages จาก requirements.txt"
        )
    else:
        print("⚠️  ไม่พบไฟล์ requirements.txt")

    # 6.1 เตือนห้ามติดตั้ง asyncio จาก PyPI
    print("\n⚠️  ตรวจสอบ asyncio ที่ติดตั้งจาก PyPI (ควรถอนออก)")
    run_command(
        [sys.executable, "-m", "pip", "show", "asyncio"],
        "ตรวจสอบ asyncio (ควรไม่พบ)"
    )
    print("\nหมายเหตุ: Python มี asyncio อยู่แล้วใน stdlib. การติดตั้ง 'asyncio' จาก PyPI จะทำให้ event loop พัง โดยเฉพาะบน Windows.")
    
    # 7. ตรวจสอบการติดตั้ง
    print("\n" + "="*60)
    print("✅ Verification")
    print("="*60)
    
    test_imports = [
        "numpy",
        "pandas", 
        "sklearn",
        "torch",
        "discord"
    ]
    
    for module in test_imports:
        try:
            __import__(module)
            print(f"✅ {module} - OK")
        except ImportError as e:
            print(f"❌ {module} - FAILED: {e}")
    
    # 8. แสดงข้อมูลเวอร์ชัน
    print("\n" + "="*60)
    print("📦 Installed Versions")
    print("="*60)
    
    try:
        import numpy as np
        print(f"numpy: {np.__version__}")
    except:
        pass
    
    try:
        import pandas as pd
        print(f"pandas: {pd.__version__}")
    except:
        pass
    
    try:
        import torch
        print(f"torch: {torch.__version__}")
        print(f"CUDA available: {torch.cuda.is_available()}")
    except:
        pass
    
    try:
        import discord
        print(f"discord.py: {discord.__version__}")
    except:
        pass
    
    print("\n" + "="*60)
    print("✅ Dependency fixing completed!")
    print("="*60)
    print("\nถ้ายังมีปัญหา:")
    print("1. ลองสร้าง virtual environment ใหม่")
    print("2. ติดตั้ง Python 3.9-3.11 (แนะนำ 3.10)")
    print("3. บน Windows: ติดตั้ง Visual C++ Build Tools")
    print("\nสำหรับ GPU support (CUDA):")
    print("pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")

if __name__ == "__main__":
    main()