"""
ไฟล์คอนฟิกหลักสำหรับ AI VTuber
ตำแหน่ง: src/core/config.py (แทนที่ไฟล์เดิม)
"""

import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent.parent.parent
SRC_DIR = BASE_DIR / "src"

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
    
    # Processing settings
    use_vad: bool = True
    question_delay: float = 2.5
    min_audio_length: float = 0.5
    sample_rate: int = 16000

@dataclass
class LLMConfig:
    """การตั้งค่า Language Model"""
    model: str = os.getenv("LLM_MODEL", "gpt-4-turbo")
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "80"))
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.85"))
    presence_penalty: float = 0.3
    frequency_penalty: float = 0.3
    timeout: int = int(os.getenv("RESPONSE_TIMEOUT", "8"))
    
@dataclass
class TTSConfig:
    """การตั้งค่า Text-to-Speech"""
    engine: str = os.getenv("TTS_ENGINE", "f5_tts_thai")
    reference_wav: str = os.getenv("TTS_REFERENCE_WAV", "reference_audio/jeed_voice.wav")
    sample_rate: int = 24000
    speed: float = 0.95
    use_gpu: bool = True
    noise_reduction: bool = True
    normalize_audio: bool = True
    
    # F5-TTS specific
    f5_tts_checkpoint: str = "models/f5_tts_thai.pth"
    f5_tts_vocab: str = "models/vocab.txt"

@dataclass
class RVCConfig:
    """การตั้งค่า RVC Voice Conversion"""
    enabled: bool = os.getenv("ENABLE_RVC", "true").lower() == "true"
    model_path: str = "rvc_models/jeed_anime.pth"
    index_path: str = "rvc_models/jeed_anime.index"
    voice_preset: str = os.getenv("VOICE_PRESET", "anime_girl")
    pitch: int = 12
    filter_radius: int = 3
    rms_mix_rate: float = 0.8
    protect: float = 0.33
    use_gpu: bool = True

@dataclass
class VTubeStudioConfig:
    """การตั้งค่า VTube Studio"""
    websocket_url: str = "ws://localhost:8001"
    plugin_name: str = os.getenv("VTS_PLUGIN_NAME", "Jeed_AI_VTuber")
    plugin_token: str = os.getenv("VTS_PLUGIN_TOKEN", "")
    model_name: str = "Hiyori_A"
    
    # Animation Settings
    idle_update_rate: float = 0.05
    smooth_factor: float = 0.15
    movement_intensity: tuple = (0.3, 0.8)
    
    # Movement Ranges
    head_rotation_range: tuple = (-15, 15)
    body_rotation_range: tuple = (-8, 8)
    eye_movement_speed: tuple = (1.0, 3.0)
    
@dataclass
class DiscordConfig:
    """การตั้งค่า Discord Bot"""
    token: str = os.getenv("DISCORD_BOT_TOKEN", "")
    command_prefix: str = "!"
    intents_voice: bool = True
    intents_message: bool = True
    stt_enabled: bool = os.getenv("DISCORD_VOICE_STT_ENABLED", "true").lower() == "true"
    audio_bitrate: int = 128000
    voice_timeout: int = 300
    
    # Recording settings
    default_record_duration: int = 5
    max_record_duration: int = 30

@dataclass
class YouTubeConfig:
    """การตั้งค่า YouTube Live"""
    enabled: bool = False
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
        self.rvc = RVCConfig()
        self.vtube = VTubeStudioConfig()
        self.discord = DiscordConfig()
        self.youtube = YouTubeConfig()
        self.safety = SafetyConfig()
        self.system = SystemConfig()
        
        # Create necessary directories
        self._create_directories()
        
    def _create_directories(self):
        """สร้างโฟลเดอร์ที่จำเป็น"""
        dirs = [
            self.system.log_dir,
            str(BASE_DIR / "reference_audio"),
            str(BASE_DIR / "rvc_models"),
            str(BASE_DIR / "models")
        ]
        for dir_path in dirs:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
        
    def validate(self) -> bool:
        """ตรวจสอบการตั้งค่า"""
        errors = []
        warnings = []
        
        # Required checks
        if not self.llm.api_key:
            errors.append("❌ ไม่พบ OPENAI_API_KEY")
            
        if not self.discord.token:
            errors.append("❌ ไม่พบ DISCORD_BOT_TOKEN")
        
        # Warning checks
        if not Path(self.tts.reference_wav).exists():
            warnings.append(f"⚠️ ไม่พบไฟล์เสียงอ้างอิง: {self.tts.reference_wav}")
            
        if self.rvc.enabled and not Path(self.rvc.model_path).exists():
            warnings.append(f"⚠️ ไม่พบโมเดล RVC: {self.rvc.model_path}")
            
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
        print(f"LLM Model: {self.llm.model}")
        print(f"TTS Engine: {self.tts.engine}")
        print(f"RVC Enabled: {self.rvc.enabled}")
        print(f"VTube Studio: {self.vtube.model_name}")
        print(f"Discord Bot: {'Enabled' if self.discord.token else 'Disabled'}")
        print(f"YouTube Live: {'Enabled' if self.youtube.enabled else 'Disabled'}")
        print(f"GPU Acceleration: {self.system.use_gpu}")
        print("="*50 + "\n")

# Global config instance
config = Config()