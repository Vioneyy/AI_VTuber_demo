"""
Configuration Manager
โหลดและจัดการค่าคอนฟิกจาก .env
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# โหลด .env
load_dotenv()

class Config:
    """Configuration class สำหรับ AI VTuber"""
    
    # ===============================
    # Discord Configuration
    # ===============================
    DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN', '')
    ADMIN_USER_IDS = set(os.getenv('ADMIN_USER_IDS', '').split(','))
    
    # ===============================
    # OpenAI Configuration
    # ===============================
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    LLM_MODEL = os.getenv('LLM_MODEL', 'gpt-4-turbo')
    LLM_MAX_TOKENS = int(os.getenv('LLM_MAX_TOKENS', '150'))
    LLM_TEMPERATURE = float(os.getenv('LLM_TEMPERATURE', '0.7'))
    RESPONSE_TIMEOUT = int(os.getenv('RESPONSE_TIMEOUT', '10'))
    
    # ===============================
    # TTS Configuration
    # ===============================
    TTS_DEVICE = os.getenv('TTS_DEVICE', 'cpu')
    TTS_SPEED = float(os.getenv('TTS_SPEED', '1.0'))
    TTS_STEPS = int(os.getenv('TTS_STEPS', '32'))
    F5_TTS_REF_AUDIO = os.getenv('F5_TTS_REF_AUDIO', 'reference_audio/jeed_voice.wav')
    F5_TTS_REF_TEXT = os.getenv('F5_TTS_REF_TEXT', 'สวัสดีค่ะ')
    
    # ===============================
    # (ลบ RVC ออกแล้ว ใช้งานเฉพาะ TTS เท่านั้น)
    
    # ===============================
    # Whisper STT Configuration
    # ===============================
    WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'base')
    WHISPER_DEVICE = os.getenv('WHISPER_DEVICE', 'cpu')
    WHISPER_LANG = os.getenv('WHISPER_LANG', 'th')
    
    # Whisper.cpp (optional)
    WHISPER_CPP_ENABLED = os.getenv('WHISPER_CPP_ENABLED', 'false').lower() == 'true'
    WHISPER_CPP_BIN_PATH = os.getenv('WHISPER_CPP_BIN_PATH', 'whisper.cpp/main.exe')
    WHISPER_CPP_MODEL_PATH = os.getenv('WHISPER_CPP_MODEL_PATH', 'whisper.cpp/models/ggml-base.bin')
    WHISPER_CPP_THREADS = int(os.getenv('WHISPER_CPP_THREADS', '4'))
    WHISPER_CPP_NGL = int(os.getenv('WHISPER_CPP_NGL', '32'))
    
    # ===============================
    # VTube Studio Configuration
    # ===============================
    VTS_WS_URL = os.getenv('VTS_WS_URL', 'ws://localhost:8001')
    VTS_PLUGIN_NAME = os.getenv('VTS_PLUGIN_NAME', 'Jeed AI VTuber')
    VTS_PLUGIN_DEVELOPER = os.getenv('VTS_PLUGIN_DEVELOPER', 'AI VTuber Team')
    VTS_PLUGIN_TOKEN = os.getenv('VTS_PLUGIN_TOKEN', '')
    VTS_SEND_MIN_INTERVAL_MS = int(os.getenv('VTS_SEND_MIN_INTERVAL_MS', '16'))
    
    # ===============================
    # YouTube Live Configuration
    # ===============================
    YOUTUBE_VIDEO_ID = os.getenv('YOUTUBE_VIDEO_ID', '')
    YOUTUBE_ENABLED = os.getenv('YOUTUBE_ENABLED', 'false').lower() == 'true'
    
    # ===============================
    # AI Personality
    # ===============================
    AI_NAME = os.getenv('AI_NAME', 'จีด')
    AI_PERSONALITY = os.getenv('AI_PERSONALITY', 'cute,energetic,friendly')
    AI_LANGUAGE = os.getenv('AI_LANGUAGE', 'th')
    
    # ===============================
    # Performance Settings
    # ===============================
    MAX_CONTEXT_MESSAGES = int(os.getenv('MAX_CONTEXT_MESSAGES', '3'))
    QUEUE_MAX_SIZE = int(os.getenv('QUEUE_MAX_SIZE', '50'))
    AUDIO_SAMPLE_RATE = int(os.getenv('AUDIO_SAMPLE_RATE', '22050'))
    AUDIO_CHUNK_SIZE = int(os.getenv('AUDIO_CHUNK_SIZE', '1024'))
    
    # ===============================
    # Safety Settings
    # ===============================
    SAFETY_FILTER_ENABLED = os.getenv('SAFETY_FILTER_ENABLED', 'true').lower() == 'true'
    PROFANITY_FILTER_ENABLED = os.getenv('PROFANITY_FILTER_ENABLED', 'true').lower() == 'true'
    
    # ===============================
    # Internal Paths
    # ===============================
    BASE_DIR = Path(__file__).parent.parent
    LOGS_DIR = BASE_DIR / "logs"
    TEMP_DIR = BASE_DIR / "temp"
    MODELS_DIR = BASE_DIR / "models"
    
    @classmethod
    def validate(cls) -> tuple[bool, list[str]]:
        """
        ตรวจสอบว่าค่าคอนฟิกครบถ้วนหรือไม่
        
        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors = []
        
        # ตรวจสอบค่าที่จำเป็น
        if not cls.DISCORD_BOT_TOKEN:
            errors.append("❌ DISCORD_BOT_TOKEN is required")
        
        if not cls.OPENAI_API_KEY:
            errors.append("❌ OPENAI_API_KEY is required")
        
        # ตรวจสอบไฟล์ที่จำเป็น
        ref_audio_path = cls.BASE_DIR / cls.F5_TTS_REF_AUDIO
        if not ref_audio_path.exists():
            errors.append(f"⚠️  Reference audio not found: {cls.F5_TTS_REF_AUDIO}")
        
        # ตรวจสอบค่าที่ถูกต้อง
        if cls.TTS_DEVICE not in ['cpu', 'cuda', 'mps']:
            errors.append(f"❌ Invalid TTS_DEVICE: {cls.TTS_DEVICE} (must be cpu/cuda/mps)")
        
        if cls.LLM_MAX_TOKENS < 50 or cls.LLM_MAX_TOKENS > 500:
            errors.append(f"⚠️  LLM_MAX_TOKENS={cls.LLM_MAX_TOKENS} (recommended: 100-200)")
        
        if cls.RESPONSE_TIMEOUT < 5 or cls.RESPONSE_TIMEOUT > 30:
            errors.append(f"⚠️  RESPONSE_TIMEOUT={cls.RESPONSE_TIMEOUT}s (recommended: 8-15s)")
        
        return len(errors) == 0, errors
    
    @classmethod
    def print_config(cls):
        """แสดงค่าคอนฟิกปัจจุบัน"""
        print("=" * 60)
        print("📋 Configuration Summary")
        print("=" * 60)
        print(f"🤖 AI Name: {cls.AI_NAME}")
        print(f"🗣️  Language: {cls.AI_LANGUAGE}")
        print(f"🧠 LLM Model: {cls.LLM_MODEL} (max_tokens={cls.LLM_MAX_TOKENS})")
        print(f"🎤 TTS Device: {cls.TTS_DEVICE}")
        print(f"👂 STT Model: {cls.WHISPER_MODEL}")
        print(f"🎮 VTube Studio: {cls.VTS_WS_URL}")
        print(f"📺 YouTube: {'Enabled' if cls.YOUTUBE_ENABLED else 'Disabled'}")
        print(f"⏱️  Timeout: {cls.RESPONSE_TIMEOUT}s")
        print("=" * 60)
    
    @classmethod
    def create_directories(cls):
        """สร้าง directories ที่จำเป็น"""
        cls.LOGS_DIR.mkdir(exist_ok=True)
        cls.TEMP_DIR.mkdir(exist_ok=True)
        cls.MODELS_DIR.mkdir(exist_ok=True)


# สร้าง instance เพื่อใช้งาน
config = Config()