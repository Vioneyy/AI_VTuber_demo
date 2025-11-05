"""
Environment Configuration Checker
ตรวจสอบว่าไฟล์ .env ตั้งค่าครบถ้วนหรือไม่
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import sys

# โหลด .env
load_dotenv()

def print_section(title):
    """พิมพ์หัวข้อ"""
    print("\n" + "=" * 60)
    print(f"🔍 {title}")
    print("=" * 60)

def check_required(name, value, description=""):
    """ตรวจสอบค่าที่บังคับ"""
    if not value or value == "":
        print(f"❌ {name}: ไม่พบ (บังคับ!)")
        if description:
            print(f"   → {description}")
        return False
    elif "your_" in value.lower() or "here" in value.lower():
        print(f"❌ {name}: ยังไม่ได้แก้ไข (ยังเป็นค่า placeholder)")
        return False
    else:
        print(f"✅ {name}: พบแล้ว")
        # แสดงตัวอย่าง (ซ่อนส่วนใหญ่)
        if len(value) > 20:
            print(f"   → {value[:15]}...{value[-5:]}")
        return True

def check_optional(name, value, default=""):
    """ตรวจสอบค่าที่ไม่บังคับ"""
    if not value or value == "":
        print(f"⚠️  {name}: ไม่พบ (ใช้ค่า default: {default})")
        return False
    else:
        print(f"✅ {name}: {value}")
        return True

def check_file_exists(name, path):
    """ตรวจสอบไฟล์"""
    file_path = Path(path)
    if file_path.exists():
        print(f"✅ {name}: พบไฟล์แล้ว")
        print(f"   → {file_path.absolute()}")
        return True
    else:
        print(f"❌ {name}: ไม่พบไฟล์!")
        print(f"   → คาดหวัง: {file_path.absolute()}")
        return False

def main():
    """Main checker"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║        AI VTuber - Configuration Checker                   ║
║        ตรวจสอบความถูกต้องของไฟล์ .env                     ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    errors = []
    warnings = []
    
    # =================================
    # 1. ตรวจสอบว่ามีไฟล์ .env หรือไม่
    # =================================
    print_section("ตรวจสอบไฟล์ .env")
    
    if not Path(".env").exists():
        print("❌ ไม่พบไฟล์ .env!")
        print("\n💡 วิธีแก้:")
        print("   1. Copy ไฟล์ .env.example เป็น .env")
        print("   2. หรือ: cp .env.example .env")
        print("   3. แก้ไขค่าใน .env ตามคำแนะนำ")
        sys.exit(1)
    else:
        print("✅ พบไฟล์ .env")
    
    # =================================
    # 2. Discord Configuration
    # =================================
    print_section("Discord Configuration (บังคับ)")
    
    discord_token = os.getenv('DISCORD_BOT_TOKEN', '')
    if not check_required('DISCORD_BOT_TOKEN', discord_token, 
                         'ดูวิธีได้ที่ SETUP_GUIDE.md'):
        errors.append('DISCORD_BOT_TOKEN')
    
    admin_ids = os.getenv('ADMIN_USER_IDS', '')
    if not check_required('ADMIN_USER_IDS', admin_ids,
                         'หาได้โดย: เปิด Developer Mode → คลิกขวาชื่อ → Copy User ID'):
        errors.append('ADMIN_USER_IDS')
    
    # =================================
    # 3. OpenAI Configuration
    # =================================
    print_section("OpenAI Configuration (บังคับ)")
    
    openai_key = os.getenv('OPENAI_API_KEY', '')
    if not check_required('OPENAI_API_KEY', openai_key,
                         'สมัครได้ที่ https://platform.openai.com/api-keys'):
        errors.append('OPENAI_API_KEY')
    
    check_optional('LLM_MODEL', os.getenv('LLM_MODEL', ''), 'gpt-4-turbo')
    check_optional('LLM_MAX_TOKENS', os.getenv('LLM_MAX_TOKENS', ''), '150')
    check_optional('LLM_TEMPERATURE', os.getenv('LLM_TEMPERATURE', ''), '0.7')
    
    # =================================
    # 4. TTS Configuration
    # =================================
    print_section("TTS Configuration")
    
    tts_device = os.getenv('TTS_DEVICE', 'cpu')
    check_optional('TTS_DEVICE', tts_device, 'cpu')
    
    if tts_device == 'cuda':
        print("\n💡 คุณใช้ CUDA - ตรวจสอบว่าติดตั้ง CUDA-enabled PyTorch แล้ว")
    
    ref_audio = os.getenv('F5_TTS_REF_AUDIO', 'reference_audio/jeed_voice.wav')
    if not check_file_exists('F5_TTS_REF_AUDIO', ref_audio):
        warnings.append('Reference audio not found')
        print("\n💡 สร้างโฟลเดอร์และวางไฟล์:")
        print(f"   mkdir -p {Path(ref_audio).parent}")
        print(f"   # วางไฟล์เสียงที่ {ref_audio}")
    
    check_optional('F5_TTS_REF_TEXT', os.getenv('F5_TTS_REF_TEXT', ''), 'สวัสดีค่ะ')
    
    # =================================
    # 5. RVC Configuration
    # =================================
    print_section("RVC Configuration")
    
    rvc_model = os.getenv('RVC_MODEL_PATH', 'rvc_models/jeed_anime.pth')
    if not check_file_exists('RVC_MODEL_PATH', rvc_model):
        warnings.append('RVC model not found (optional)')
    
    check_optional('RVC_DEVICE', os.getenv('RVC_DEVICE', ''), 'cpu')
    check_optional('RVC_PITCH', os.getenv('RVC_PITCH', ''), '0')
    
    # =================================
    # 6. Whisper STT Configuration
    # =================================
    print_section("Whisper STT Configuration")
    
    check_optional('WHISPER_MODEL', os.getenv('WHISPER_MODEL', ''), 'base')
    check_optional('WHISPER_DEVICE', os.getenv('WHISPER_DEVICE', ''), 'cpu')
    check_optional('WHISPER_LANG', os.getenv('WHISPER_LANG', ''), 'th')
    
    # =================================
    # 7. VTube Studio Configuration
    # =================================
    print_section("VTube Studio Configuration (optional)")
    
    check_optional('VTS_WS_URL', os.getenv('VTS_WS_URL', ''), 'ws://localhost:8001')
    check_optional('VTS_PLUGIN_NAME', os.getenv('VTS_PLUGIN_NAME', ''), 'Jeed AI VTuber')
    
    vts_token = os.getenv('VTS_PLUGIN_TOKEN', '')
    if vts_token:
        print(f"✅ VTS_PLUGIN_TOKEN: มี token แล้ว")
    else:
        print(f"⚠️  VTS_PLUGIN_TOKEN: ว่าง (จะถูกสร้างอัตโนมัติเมื่อรันครั้งแรก)")
    
    # =================================
    # 8. YouTube Configuration
    # =================================
    print_section("YouTube Live Configuration (optional)")
    
    youtube_enabled = os.getenv('YOUTUBE_ENABLED', 'false').lower() == 'true'
    if youtube_enabled:
        print("✅ YOUTUBE_ENABLED: เปิดใช้งาน")
        video_id = os.getenv('YOUTUBE_VIDEO_ID', '')
        if not video_id:
            warnings.append('YOUTUBE_ENABLED=true but YOUTUBE_VIDEO_ID is empty')
            print("❌ YOUTUBE_VIDEO_ID: ไม่พบ (จำเป็นเมื่อเปิดใช้ YouTube)")
        else:
            print(f"✅ YOUTUBE_VIDEO_ID: {video_id}")
    else:
        print("⚠️  YOUTUBE_ENABLED: ปิดใช้งาน")
    
    # =================================
    # 9. Performance Settings
    # =================================
    print_section("Performance Settings")
    
    check_optional('MAX_CONTEXT_MESSAGES', os.getenv('MAX_CONTEXT_MESSAGES', ''), '3')
    check_optional('QUEUE_MAX_SIZE', os.getenv('QUEUE_MAX_SIZE', ''), '50')
    check_optional('AUDIO_SAMPLE_RATE', os.getenv('AUDIO_SAMPLE_RATE', ''), '22050')
    
    # =================================
    # 10. สรุปผลการตรวจสอบ
    # =================================
    print_section("สรุปผลการตรวจสอบ")
    
    print("\n📊 Summary:")
    print(f"   ✅ ผ่าน: {3 - len(errors)} / 3 (required)")
    print(f"   ⚠️  คำเตือน: {len(warnings)}")
    print(f"   ❌ ข้อผิดพลาด: {len(errors)}")
    
    if errors:
        print("\n❌ ข้อผิดพลาดที่ต้องแก้ไข:")
        for error in errors:
            print(f"   • {error}")
        print("\n💡 กรุณาแก้ไขค่าใน .env ก่อนรัน bot")
        return False
    
    if warnings:
        print("\n⚠️  คำเตือน (ไม่บังคับ):")
        for warning in warnings:
            print(f"   • {warning}")
    
    print("\n" + "=" * 60)
    if not errors:
        print("✅ Configuration ถูกต้อง! พร้อมรัน bot แล้ว")
        print("=" * 60)
        print("\n🚀 Next steps:")
        print("   1. เปิด Discord Intents (MESSAGE CONTENT)")
        print("   2. Re-invite Discord bot ด้วย permissions ถูกต้อง")
        print("   3. เปิด VTube Studio (ถ้าใช้)")
        print("   4. รัน: python src/main.py")
        print("   5. ใน Discord: !join เพื่อเข้าห้องเสียง")
        return True
    else:
        print("❌ พบข้อผิดพลาด - แก้ไขก่อนรัน")
        print("=" * 60)
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)