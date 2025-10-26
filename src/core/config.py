"""
Configuration management
โหลดการตั้งค่าจากไฟล์ .env
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# โหลด .env file
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class Config:
    """การตั้งค่าระบบ"""
    
    # === Discord ===
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
    
    # === OpenAI / LLM ===
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    
    # === VTube Studio ===
    VTS_PLUGIN_NAME = os.getenv("VTS_PLUGIN_NAME", "AI_VTuber")
    VTS_HOST = os.getenv("VTS_HOST", "127.0.0.1")
    VTS_PORT = int(os.getenv("VTS_PORT", "8001"))
    # ⚠️ ไม่ใช้ VTS_PLUGIN_TOKEN จาก .env - ให้ระบบขอใหม่ทุกครั้ง
    VTS_PLUGIN_TOKEN = None
    
    # VTS Motion Settings (สำหรับ Hiyori_A)
    VTS_MOTION_INTENSITY = float(os.getenv("VTS_MOTION_INTENSITY", "0.6"))
    VTS_BLINK_FREQUENCY = float(os.getenv("VTS_BLINK_FREQUENCY", "0.4"))
    VTS_HEAD_MOVEMENT_RANGE = float(os.getenv("VTS_HEAD_MOVEMENT_RANGE", "12"))
    VTS_EYE_MOVEMENT_RANGE = float(os.getenv("VTS_EYE_MOVEMENT_RANGE", "0.6"))
    VTS_BODY_SWAY_RANGE = float(os.getenv("VTS_BODY_SWAY_RANGE", "3"))
    VTS_MOTION_MIN_INTERVAL = float(os.getenv("VTS_MOTION_MIN_INTERVAL", "2.0"))
    VTS_MOTION_MAX_INTERVAL = float(os.getenv("VTS_MOTION_MAX_INTERVAL", "5.0"))
    VTS_BLINK_DURATION = float(os.getenv("VTS_BLINK_DURATION", "0.15"))
    
    # Safe Motion Mode
    SAFE_MOTION_MODE = os.getenv("SAFE_MOTION_MODE", "false").lower() == "true"
    SAFE_HOTKEY_INTERVAL = float(os.getenv("SAFE_HOTKEY_INTERVAL", "8.0"))
    
    # VTS Hotkey Settings (สำหรับ Hiyori_A - มีแค่ 3 hotkeys)
    ENABLE_GLOBAL_HOTKEYS = os.getenv("ENABLE_GLOBAL_HOTKEYS", "false").lower() == "true"
    VTS_HK_THINKING = os.getenv("VTS_HK_THINKING", "thinking")
    VTS_HK_HAPPY = os.getenv("VTS_HK_HAPPY", "happy")
    VTS_HK_SAD = os.getenv("VTS_HK_SAD", "sad")
    
    # Emotion Trigger Settings
    VTS_EMOTION_TRIGGER_PROBABILITY = float(os.getenv("VTS_EMOTION_TRIGGER_PROBABILITY", "0.6"))
    VTS_EMOTION_AUTO_ANALYZE = os.getenv("VTS_EMOTION_AUTO_ANALYZE", "true").lower() == "true"
    
    # === YouTube Live ===
    YOUTUBE_STREAM_ID = os.getenv("YOUTUBE_STREAM_ID", "")
    
    # === TTS ===
    TTS_ENGINE = os.getenv("TTS_ENGINE", "f5_tts_thai")
    TTS_REFERENCE_WAV = os.getenv("TTS_REFERENCE_WAV", "")
    TTS_REFERENCE_TEXT = os.getenv("TTS_REFERENCE_TEXT", "สวัสดีค่ะ ฉันเป็น AI VTuber")
    
    # === RVC ===
    ENABLE_RVC = os.getenv("ENABLE_RVC", "false").lower() == "true"
    VOICE_PRESET = os.getenv("VOICE_PRESET", "anime_girl")
    
    # === Whisper.cpp STT ===
    DISCORD_VOICE_STT_ENABLED = os.getenv("DISCORD_VOICE_STT_ENABLED", "false").lower() == "true"
    WHISPER_CPP_BIN_PATH = os.getenv("WHISPER_CPP_BIN_PATH", "")
    WHISPER_CPP_MODEL_PATH = os.getenv("WHISPER_CPP_MODEL_PATH", "")
    WHISPER_CPP_LANG = os.getenv("WHISPER_CPP_LANG", "th")
    WHISPER_CPP_THREADS = int(os.getenv("WHISPER_CPP_THREADS", "4"))
    WHISPER_CPP_NGL = int(os.getenv("WHISPER_CPP_NGL", "35"))
    WHISPER_CPP_TIMEOUT_MS = int(os.getenv("WHISPER_CPP_TIMEOUT_MS", "5000"))
    
    # === Response Settings ===
    RESPONSE_TIMEOUT = int(os.getenv("RESPONSE_TIMEOUT", "10"))
    
    def __init__(self):
        """ตรวจสอบการตั้งค่าที่จำเป็น"""
        self._validate()
    
    def _validate(self):
        """ตรวจสอบว่ามีการตั้งค่าที่จำเป็นหรือไม่"""
        errors = []
        
        if not self.OPENAI_API_KEY:
            errors.append("❌ OPENAI_API_KEY ไม่ได้ตั้งค่า")
        
        if not self.DISCORD_BOT_TOKEN and not self.YOUTUBE_STREAM_ID:
            errors.append("⚠️ ไม่มี DISCORD_BOT_TOKEN หรือ YOUTUBE_STREAM_ID - ระบบจะไม่สามารถรับข้อความได้")
        
        if self.TTS_ENGINE == "f5_tts_thai":
            if not self.TTS_REFERENCE_WAV or not os.path.exists(self.TTS_REFERENCE_WAV):
                errors.append("⚠️ TTS_REFERENCE_WAV ไม่ได้ตั้งค่าหรือไฟล์ไม่มีอยู่")
        
        if errors:
            print("\n" + "="*60)
            print("⚠️ พบปัญหาในการตั้งค่า:")
            print("="*60)
            for error in errors:
                print(f"  {error}")
            print("="*60 + "\n")
            
            # ถ้ามี critical error ให้หยุดโปรแกรม
            if any("❌" in e for e in errors):
                raise ValueError("การตั้งค่าไม่ครบถ้วน กรุณาตรวจสอบไฟล์ .env")


# สร้าง instance เดียว
config = Config()

def get_settings():
    """คืนค่า settings ปัจจุบันให้สคริปต์ใช้งานแบบง่าย ๆ"""
    return config