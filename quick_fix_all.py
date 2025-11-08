"""
Quick Fix All Problems
แก้ไขปัญหาทั้งหมดอัตโนมัติ
"""
from pathlib import Path
import shutil

print("""
╔═══════════════════════════════════════════════════════════╗
║          Quick Fix All - แก้ไขปัญหาอัตโนมัติ             ║
╚═══════════════════════════════════════════════════════════╝
""")

def backup_file(file_path: Path):
    """สำรองไฟล์"""
    if file_path.exists():
        backup_path = file_path.with_suffix(file_path.suffix + '.backup')
        shutil.copy2(file_path, backup_path)
        print(f"💾 Backup: {backup_path}")
        return True
    return False

def fix_env():
    """แก้ไข .env"""
    print("\n" + "="*60)
    print("🔧 Fix 1: .env Configuration")
    print("="*60)
    
    env_path = Path(".env")
    
    if not env_path.exists():
        print("❌ .env not found")
        return False
    
    # Backup
    backup_file(env_path)
    
    # Read
    with open(env_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Modify
    new_lines = []
    modified = False
    
    for line in lines:
        # Fix Whisper.cpp
        if line.startswith('WHISPER_CPP_ENABLED='):
            if 'true' in line.lower():
                new_lines.append('WHISPER_CPP_ENABLED=false\n')
                modified = True
                print("✅ Changed WHISPER_CPP_ENABLED to false")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    # Write
    if modified:
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print("✅ .env updated")
    else:
        print("✅ .env already correct")
    
    return True

def fix_discord_bot():
    """แก้ไข Discord bot"""
    print("\n" + "="*60)
    print("🔧 Fix 2: Discord Bot (Voice Reception)")
    print("="*60)
    
    bot_file = Path("src/adapters/discord_bot.py")
    
    if not bot_file.exists():
        print("❌ Discord bot file not found")
        return False
    
    # Backup
    backup_file(bot_file)
    
    # Read current file
    with open(bot_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already fixed
    if 'user_audio_buffers' in content and 'silence_threshold' in content:
        print("✅ Discord bot already has voice activity detection")
        return True
    
    print("⚠️  Discord bot needs manual update")
    print("💡 Replace src/adapters/discord_bot.py with the fixed version")
    print("   (artifact id: discord_bot_voice_fix)")
    
    return False

def fix_stt_handler():
    """แก้ไข STT Handler"""
    print("\n" + "="*60)
    print("🔧 Fix 3: STT Handler (Tensor Errors)")
    print("="*60)
    
    stt_file = Path("src/audio/stt_handler.py")
    
    if not stt_file.exists():
        print("❌ STT handler not found")
        print("💡 Create src/audio/stt_handler.py from artifact: stt_handler_fixed")
        return False
    
    # Check if has fix
    with open(stt_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if '_transcribe_with_retry' in content and '_fix_length_for_whisper' in content:
        print("✅ STT handler already has retry logic")
        return True
    
    print("⚠️  STT handler needs update")
    print("💡 Replace src/audio/stt_handler.py with artifact: stt_handler_fixed")
    
    return False

def check_dependencies():
    """Check dependencies"""
    print("\n" + "="*60)
    print("🔧 Check: Dependencies")
    print("="*60)
    
    required = [
        'numpy',
        'scipy',
        'soundfile',
        'torch',
        'discord'
    ]
    
    missing = []
    
    for module in required:
        try:
            __import__(module)
            print(f"✅ {module}")
        except ImportError:
            print(f"❌ {module} - MISSING")
            missing.append(module)
    
    if missing:
        print(f"\n💡 Install missing: pip install {' '.join(missing)}")
        return False
    
    return True

def main():
    """Main function"""
    
    print("\n🚀 Starting fixes...\n")
    
    results = []
    
    # Fix 1: .env
    results.append(('Environment Config', fix_env()))
    
    # Fix 2: Discord bot
    results.append(('Discord Bot', fix_discord_bot()))
    
    # Fix 3: STT Handler
    results.append(('STT Handler', fix_stt_handler()))
    
    # Check dependencies
    results.append(('Dependencies', check_dependencies()))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Summary")
    print("="*60)
    
    auto_fixed = 0
    manual_needed = 0
    
    for name, result in results:
        if result:
            print(f"✅ {name}")
            auto_fixed += 1
        else:
            print(f"❌ {name} - Needs manual fix")
            manual_needed += 1
    
    print(f"\n✅ Auto-fixed: {auto_fixed}")
    print(f"⚠️  Manual fixes needed: {manual_needed}")
    
    if manual_needed > 0:
        print("\n" + "="*60)
        print("📝 Manual Steps Required:")
        print("="*60)
        print("\n1. Replace src/adapters/discord_bot.py")
        print("   Copy from artifact: discord_bot_voice_fix")
        print("\n2. Replace src/audio/stt_handler.py")
        print("   Copy from artifact: stt_handler_fixed")
        print("\n3. Run: python src/main.py")
    else:
        print("\n✅ All fixes applied! Run: python src/main.py")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Cancelled")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()