"""
ไฟล์คอนฟิกหลักสำหรับ AI VTuber
ตำแหน่ง: src/core/config.py (แทนที่ไฟล์เดิม)
"""

import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).parent.parent.parent
SRC_DIR = BASE_DIR / "src"

# Load .env explicitly from project root
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=str(ENV_PATH), override=False)
else:
    # Try loading from current working directory as fallback
    load_dotenv()

@dataclass
class STTConfig:
    """การตั้งค่า Speech-to-Text"""
    # Whisper.cpp settings
    whisper_bin_path: str = os.getenv("WHISPER_CPP_BIN_PATH", "whisper.cpp/main.exe")
    whisper_model_path: str = os.getenv("WHISPER_CPP_MODEL_PATH", "models/ggml-large-v3.bin")
    language: str = os.getenv("WHISPER_CPP_LANG", "th")
    threads: int = int(os.getenv("WHISPER_CPP_THREADS", "4"))
    n_gpu_layers: int = int(os.getenv("WHISPER_CPP_NGL", "35"))
    timeout_ms: int = int(os.getenv("WHISPER_CPP_TIMEOUT_MS", "5000"))
    # Decoder tuning
    beam_size: int = int(os.getenv("WHISPER_CPP_BEAM_SIZE", "5"))
    best_of: int = int(os.getenv("WHISPER_CPP_BEST_OF", "5"))
    temperature: float = float(os.getenv("WHISPER_CPP_TEMPERATURE", "0.0"))
    temperature_inc: float = float(os.getenv("WHISPER_CPP_TEMPERATURE_INC", "0.2"))
    no_speech_thold: float = float(os.getenv("WHISPER_CPP_NO_SPEECH_THOLD", "0.6"))
    
    # Processing settings
    use_vad: bool = True
    # Whisper.cpp VAD parameters (effective only when use_vad=True)
    vad_model_path: Optional[str] = os.getenv("WHISPER_CPP_VAD_MODEL", "")
    vad_threshold: float = float(os.getenv("WHISPER_CPP_VAD_THOLD", "0.5"))
    vad_min_speech_duration_ms: int = int(os.getenv("WHISPER_CPP_VAD_MIN_SPEECH_MS", "300"))
    vad_min_silence_duration_ms: int = int(os.getenv("WHISPER_CPP_VAD_MIN_SILENCE_MS", "200"))
    vad_max_speech_duration_s: float = float(os.getenv("WHISPER_CPP_VAD_MAX_SPEECH_S", "600.0"))
    vad_speech_pad_ms: int = int(os.getenv("WHISPER_CPP_VAD_SPEECH_PAD_MS", "30"))
    vad_samples_overlap: float = float(os.getenv("WHISPER_CPP_VAD_SAMPLES_OVERLAP", "0.1"))
    question_delay: float = 2.5
    min_audio_length: float = 0.5
    sample_rate: int = 16000

@dataclass
class LLMConfig:
    """การตั้งค่า Language Model"""
    model: str = os.getenv("LLM_MODEL", "gpt-4-turbo")
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "60"))
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    presence_penalty: float = 0.2
    frequency_penalty: float = 0.2
    timeout: int = int(os.getenv("RESPONSE_TIMEOUT", "6"))
    
@dataclass
class TTSConfig:
    """การตั้งค่า Text-to-Speech"""
    engine: str = os.getenv("TTS_ENGINE", "f5_tts_thai")
    reference_wav: str = os.getenv("TTS_REFERENCE_WAV", "reference_audio/jeed_voice.wav")
    # ใช้ค่าใน .env หากตั้งไว้ ไม่เช่นนั้นตั้งเป็น 48000 เพื่อให้ตรงกับ Discord
    sample_rate: int = int(os.getenv("TTS_SAMPLE_RATE", "48000"))
    speed: float = 0.95
    use_gpu: bool = True
    noise_reduction: bool = True
    normalize_audio: bool = True
    
    # F5-TTS specific
    f5_tts_checkpoint: str = "models/f5_tts_thai.pth"
    f5_tts_vocab: str = "models/vocab.txt"


@dataclass
class VTubeStudioConfig:
    """การตั้งค่า VTube Studio"""
    enabled: bool = os.getenv("VTS_ENABLED", "true").lower() == "true"
    websocket_url: str = os.getenv("VTS_WS_URL", "ws://localhost:8001")
    plugin_name: str = os.getenv("VTS_PLUGIN_NAME", "Jeed_AI_VTuber")
    plugin_token: str = os.getenv("VTS_PLUGIN_TOKEN", "")
    model_name: str = "Hiyori_A"
    
    # Animation Settings
    # เพิ่มความถี่การอัปเดตเพื่อลดอาการดีเลย์ใน lip sync
    idle_update_rate: float = 0.02
    # เปิดการขยับสุ่มตอน idle (ปิดได้ผ่าน .env ถ้าต้องการ)
    idle_motion_enabled: bool = True
    smooth_factor: float = 0.15
    movement_intensity: tuple = (0.3, 0.8)
    
    # Movement Ranges
    head_rotation_range: tuple = (-15, 15)
    body_rotation_range: tuple = (-8, 8)
    eye_movement_speed: tuple = (1.0, 3.0)
    
@dataclass
class DiscordConfig:
    """การตั้งค่า Discord Bot"""
    enabled: bool = os.getenv("DISCORD_ENABLED", "true").lower() == "true"
    token: str = os.getenv("DISCORD_BOT_TOKEN", "")
    command_prefix: str = "!"
    intents_voice: bool = True
    intents_message: bool = True
    stt_enabled: bool = os.getenv("DISCORD_VOICE_STT_ENABLED", "true").lower() == "true"
    audio_bitrate: int = 128000
    voice_timeout: int = 300
    # Voice reception tuning
    voice_silence_threshold: float = float(os.getenv("DISCORD_VOICE_SILENCE_THRESHOLD", "0.7"))
    voice_min_audio_duration: float = float(os.getenv("DISCORD_VOICE_MIN_AUDIO_DURATION", "0.35"))
    # Test mode: reply with fixed TTS text upon any voice input
    voice_test_reply_text: Optional[str] = os.getenv("DISCORD_VOICE_TEST_REPLY_TEXT", "")

    # Recording settings
    default_record_duration: int = 5
    max_record_duration: int = 30
    voice_record_enabled: bool = os.getenv("DISCORD_VOICE_RECORD_ENABLED", "true").lower() == "true"
    voice_record_dir: str = os.getenv("DISCORD_VOICE_RECORD_DIR", "temp/recordings/discord_in")
    # Recording bot playback (outgoing TTS to Discord)
    voice_playback_record_enabled: bool = os.getenv("DISCORD_PLAYBACK_RECORD_ENABLED", "true").lower() == "true"
    voice_playback_record_dir: str = os.getenv("DISCORD_PLAYBACK_RECORD_DIR", "temp/recordings/discord_out")
    # Debug: save pre/post processed playback audio and log stats
    voice_playback_debug_enabled: bool = os.getenv("DISCORD_PLAYBACK_DEBUG_ENABLED", "false").lower() == "true"
    voice_playback_debug_dir: str = os.getenv("DISCORD_PLAYBACK_DEBUG_DIR", "temp/recordings/discord_out")

@dataclass
class YouTubeConfig:
    """การตั้งค่า YouTube Live"""
    # อ่านค่าจาก .env ให้ถูกต้อง
    enabled: bool = os.getenv("YOUTUBE_ENABLED", "false").lower() == "true"
    # รองรับทั้ง VIDEO_ID และ STREAM_ID (เลือกใช้ตัวที่มีค่า)
    video_id: str = os.getenv("YOUTUBE_VIDEO_ID", "")
    stream_id: str = os.getenv("YOUTUBE_STREAM_ID", "")
    check_interval: float = 5.0
    read_comment_once: bool = True
    max_comments_per_batch: int = 5

@dataclass
class SafetyConfig:
    """การตั้งค่าความปลอดภัย"""
    forbidden_topics: list = None
    restricted_topics: list = None
    
    def __post_init__(self):
        if self.forbidden_topics is None:
            self.forbidden_topics = [
                "เหยียดผิว", "เหยียดเชื้อชาติ", "การเมืองสุดโต่ง",
                "ศาสนาสุดโต่ง", "ก่อการร้าย", "สงคราม",
                "ความรุนแรง", "อนาจาร", "คำหยาบคาย",
                "ข้อมูลส่วนตัว", "การพนัน", "ยาเสพติด"
            ]
        if self.restricted_topics is None:
            self.restricted_topics = [
                "ระบบโปรเจค", "โค้ด", "ไฟล์ระบบ",
                "api key", "token", "password", "configuration"
            ]

@dataclass
class SystemConfig:
    """การตั้งค่าระบบ"""
    max_processing_time: float = 10.0
    use_gpu: bool = True
    log_level: str = "INFO"
    save_logs: bool = True
    log_dir: str = str(BASE_DIR / "logs")
    
    # Performance
    enable_caching: bool = True
    cache_size: int = 100
    parallel_processing: bool = True
    max_workers: int = 4
    
    # Queue settings
    max_queue_size: int = 50
    priority_voice: int = 1
    priority_text: int = 2

class Config:
    """คลาสหลักที่รวมการตั้งค่าทั้งหมด"""
    def __init__(self):
        self.stt = STTConfig()
        self.llm = LLMConfig()
        self.tts = TTSConfig()
        self.vtube = VTubeStudioConfig()
        self.discord = DiscordConfig()
        self.youtube = YouTubeConfig()
        self.safety = SafetyConfig()
        self.system = SystemConfig()
        
        # Create necessary directories
        self._create_directories()

        # Auto-fix known paths if missing
        self._apply_path_fallbacks()
        
    def _create_directories(self):
        """สร้างโฟลเดอร์ที่จำเป็น"""
        dirs = [
            self.system.log_dir,
            str(BASE_DIR / "reference_audio"),
            str(BASE_DIR / "models")
        ]
        for dir_path in dirs:
            Path(dir_path).mkdir(parents=True, exist_ok=True)

    def _apply_path_fallbacks(self):
        """ปรับพาธที่พบบ่อยให้ถูกต้องอัตโนมัติ (เช่น Whisper.cpp)"""
        # Whisper.cpp fallback
        whisper_path = Path(self.stt.whisper_bin_path)
        if not whisper_path.exists():
            # Common installation path suggested by user
            alt_path = Path("D:/whisper.cpp-master/main.exe")
            alt_path_win = Path("D:\\whisper.cpp-master\\main.exe")
            if alt_path.exists():
                self.stt.whisper_bin_path = str(alt_path)
                print(f"🔧 ใช้ Whisper.cpp จาก: {self.stt.whisper_bin_path}")
            elif alt_path_win.exists():
                self.stt.whisper_bin_path = str(alt_path_win)
                print(f"🔧 ใช้ Whisper.cpp จาก: {self.stt.whisper_bin_path}")
        
    def validate(self) -> bool:
        """ตรวจสอบการตั้งค่า"""
        errors = []
        warnings = []
        
        # Required checks
        if not self.llm.api_key:
            errors.append("❌ ไม่พบ OPENAI_API_KEY")
            
        # Discord token required only when Discord is enabled
        if getattr(self.discord, "enabled", True):
            if not self.discord.token:
                errors.append("❌ ไม่พบ DISCORD_BOT_TOKEN (เปิดใช้งาน Discord)\n   - หากไม่ต้องการใช้ Discord ให้ตั้งค่า DISCORD_ENABLED=false ใน .env")
        
        # Warning checks
        if not Path(self.tts.reference_wav).exists():
            warnings.append(f"⚠️ ไม่พบไฟล์เสียงอ้างอิง: {self.tts.reference_wav}")
        if not Path(self.stt.whisper_bin_path).exists():
            warnings.append(f"⚠️ ไม่พบ Whisper.cpp: {self.stt.whisper_bin_path}")
        
        # Print results
        if errors:
            for error in errors:
                print(error)
            return False
            
        if warnings:
            for warning in warnings:
                print(warning)
        
        if not errors and not warnings:
            print("✅ การตั้งค่าถูกต้องทั้งหมด")
        elif not errors:
            print("✅ การตั้งค่าพื้นฐานถูกต้อง (มี warnings)")
            
        return True
    
    def print_config(self):
        """แสดงการตั้งค่าทั้งหมด"""
        print("\n" + "="*50)
        print("🎮 Jeed AI VTuber Configuration")
        print("="*50)
        try:
            print(f"LLM Model: {self.llm.model}")
            print(f"TTS Engine: {self.tts.engine}")
            print(f"VTube Studio: {'Enabled' if getattr(self.vtube, 'enabled', True) else 'Disabled'}")
            print(f"Discord Bot: {'Enabled' if getattr(self.discord, 'enabled', True) else 'Disabled'}")
            print(f"YouTube Live: {'Enabled' if getattr(self.youtube, 'enabled', False) else 'Disabled'}")
            print(f"GPU Acceleration: {self.system.use_gpu}")
        except Exception:
            pass
        print("="*50 + "\n")

    # ===== Compatibility aliases (uppercase names expected by main.py) =====
    @property
    def LLM_MODEL(self) -> str:
        return self.llm.model

    @property
    def OPENAI_API_KEY(self) -> str:
        return self.llm.api_key

    @property
    def LLM_MAX_TOKENS(self) -> int:
        return self.llm.max_tokens

    @property
    def LLM_TEMPERATURE(self) -> float:
        return self.llm.temperature

    @property
    def RESPONSE_TIMEOUT(self) -> int:
        return self.llm.timeout

    @property
    def TTS_ENGINE(self) -> str:
        return self.tts.engine

    @property
    def TTS_REFERENCE_WAV(self) -> str:
        return self.tts.reference_wav


    @property
    def VTS_PLUGIN_NAME(self) -> str:
        return self.vtube.plugin_name

    @property
    def VTS_MODEL_NAME(self) -> str:
        return self.vtube.model_name

    @property
    def DISCORD_BOT_TOKEN(self) -> str:
        return self.discord.token

    @property
    def DISCORD_VOICE_STT_ENABLED(self) -> bool:
        return self.discord.stt_enabled

    @property
    def YOUTUBE_STREAM_ID(self) -> str:
        return self.youtube.stream_id

    @property
    def AUDIO_DEVICE(self) -> str:
        # Simple mapping: use_gpu → 'cuda', else 'cpu'
        return 'cuda' if self.system.use_gpu else 'cpu'

    # ===== Compatibility: device selection from .env =====
    @property
    def TTS_DEVICE(self) -> str:
        """Device for TTS engine. Falls back to GPU flag if not set."""
        # Prefer explicit .env override; else map from use_gpu
        return os.getenv("TTS_DEVICE", 'cuda' if self.system.use_gpu else 'cpu')


    # ===== Additional compatibility for STT/Python Whisper and admin/queue =====
    @property
    def WHISPER_MODEL(self) -> str:
        return os.getenv("WHISPER_MODEL", "base")

    @property
    def WHISPER_DEVICE(self) -> str:
        return os.getenv("WHISPER_DEVICE", "cpu")

    @property
    def WHISPER_LANG(self) -> str:
        return os.getenv("WHISPER_LANG", "th")

    @property
    def WHISPER_CPP_ENABLED(self) -> bool:
        return os.getenv("WHISPER_CPP_ENABLED", "false").lower() == "true"

    @property
    def ADMIN_USER_IDS(self) -> set:
        return set([u.strip() for u in os.getenv("ADMIN_USER_IDS", "").split(",") if u.strip()])

    @property
    def QUEUE_MAX_SIZE(self) -> int:
        return int(self.system.max_queue_size)

    @property
    def WHISPER_CPP_BIN_PATH(self) -> str:
        return self.stt.whisper_bin_path

    @property
    def WHISPER_CPP_MODEL_PATH(self) -> str:
        return self.stt.whisper_model_path

    @property
    def WHISPER_CPP_LANG(self) -> str:
        return self.stt.language

    @property
    def WHISPER_CPP_THREADS(self) -> int:
        return self.stt.threads

    @property
    def WHISPER_CPP_NGL(self) -> int:
        return self.stt.n_gpu_layers

    # Toggle aliases
    @property
    def DISCORD_ENABLED(self) -> bool:
        return getattr(self.discord, "enabled", True)

    @property
    def VTS_ENABLED(self) -> bool:
        return getattr(self.vtube, "enabled", True)

# Global config instance
config = Config()