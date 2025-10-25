from __future__ import annotations
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # Platform tokens
    DISCORD_BOT_TOKEN: str | None = None
    OPENAI_API_KEY: str | None = None
    YOUTUBE_STREAM_ID: str | None = None

    # VTube Studio
    VTS_PLUGIN_NAME: str = Field(default="AI VTuber Demo")
    VTS_PLUGIN_TOKEN: str | None = None
    VTS_HOST: str = Field(default="localhost")
    VTS_PORT: int = Field(default=8001)
    VTS_INJECT_MAX_FPS: float = Field(default=30.0)
    VTS_RECONNECT_BACKOFF_MS: int = Field(default=500)

    # Idle motion settings
    IDLE_MOTION_ENABLED: bool = Field(default=True)
    IDLE_MOTION_INTERVAL: float = Field(default=2.0)
    IDLE_MOTION_AMPLITUDE: float = Field(default=0.4)
    IDLE_MOTION_SENSITIVITY: float = Field(default=1.0)
    # Blink settings
    BLINK_ENABLED: bool = Field(default=True)
    BLINK_MIN_INTERVAL: float = Field(default=3.0)
    BLINK_MAX_INTERVAL: float = Field(default=6.0)
    BLINK_CLOSE_MS: int = Field(default=120)
    BLINK_DOUBLE_PROB: float = Field(default=0.2)

    # Breathing settings
    BREATHING_ENABLED: bool = Field(default=True)
    BREATHING_MIN_INTERVAL: float = Field(default=2.5)
    BREATHING_MAX_INTERVAL: float = Field(default=8.0)
    BREATHING_MIN_INTENSITY: float = Field(default=0.1)
    BREATHING_MAX_INTENSITY: float = Field(default=0.4)
    BREATHING_MIN_DURATION: float = Field(default=1.2)
    BREATHING_MAX_DURATION: float = Field(default=3.5)

    # Random smile settings
    RANDOM_SMILE_ENABLED: bool = Field(default=True)
    RANDOM_SMILE_MIN_INTERVAL: float = Field(default=15.0)
    RANDOM_SMILE_MAX_INTERVAL: float = Field(default=45.0)
    RANDOM_SMILE_MIN_INTENSITY: float = Field(default=0.2)
    RANDOM_SMILE_MAX_INTENSITY: float = Field(default=0.6)
    RANDOM_SMILE_MIN_DURATION: float = Field(default=2.0)
    RANDOM_SMILE_MAX_DURATION: float = Field(default=8.0)
    RANDOM_SMILE_FADE_TIME: float = Field(default=0.8)

    # Auto gaze settings
    AUTO_GAZE_ENABLED: bool = Field(default=True)
    
    # Micro expressions settings
    MICRO_EXPRESSIONS_ENABLED: bool = Field(default=True)
    MICRO_EXPR_MIN_INTERVAL: float = Field(default=5.0)
    MICRO_EXPR_MAX_INTERVAL: float = Field(default=18.0)

    # Random animations settings (ใช้ไฟล์อนิเมชันที่ให้มา)
    AUTO_ANIMATIONS_ENABLED: bool = Field(default=True)
    ANIM_MIN_INTERVAL_SEC: float = Field(default=25.0)  # นานขึ้น - สุ่มนานๆครั้ง
    ANIM_MAX_INTERVAL_SEC: float = Field(default=60.0)  # นานขึ้น - สุ่มนานๆครั้ง
    ANIM_TRIGGER_CHANCE: float = Field(default=0.3)     # ลดโอกาส - สุ่มนานๆครั้ง

    # Manual emotion settings
    MANUAL_EMOTIONS_ENABLED: bool = Field(default=True)
    MANUAL_EMOTION_DURATION_SEC: float = Field(default=5.0)  # ระยะเวลาที่อีโมทจะแสดง (วินาที)
    MANUAL_EMOTION_AUTO_RESET: bool = Field(default=True)   # รีเซ็ตอีโมทอัตโนมัติหรือไม่

    # Emotion hotkey mapping
    VTS_HK_THINKING: str | None = Field(default="thinking")
    VTS_HK_NEUTRAL: str | None = Field(default="Neutral")
    VTS_HK_HAPPY: str | None = Field(default="happy")
    VTS_HK_SAD: str | None = Field(default="sad")
    VTS_HK_ANGRY: str | None = Field(default="Angry")
    VTS_HK_SURPRISED: str | None = Field(default="Surprised")
    VTS_HK_CALM: str | None = Field(default="Calm")

    # Global hotkeys
    ENABLE_GLOBAL_HOTKEYS: bool = Field(default=True)
    F1_EMOTION: str = Field(default="Neutral")
    F2_EMOTION: str = Field(default="Happy")
    F3_EMOTION: str = Field(default="Sad")
    # Emotion trigger probabilities (ลดลงเพื่อให้แสดงอีโมทนานๆครั้ง)
    EMOTION_TRIGGER_PROBABILITY: float = Field(default=0.15)  # ความน่าจะเป็นพื้นฐาน - ลดลงมาก
    EMOTION_TRIGGER_PROB_HAPPY: float = Field(default=0.2)    # ลดลงจาก 0.6
    EMOTION_TRIGGER_PROB_SAD: float = Field(default=0.15)     # ลดลงจาก 0.5
    EMOTION_TRIGGER_PROB_ANGRY: float = Field(default=0.1)    # ลดลงจาก 0.4
    EMOTION_TRIGGER_PROB_SURPRISED: float = Field(default=0.25) # ลดลงจาก 0.5
    EMOTION_TRIGGER_PROB_CALM: float = Field(default=0.1)     # ลดลงจาก 0.3
    EMOTION_SAD_FALLBACK_NEUTRAL_PROB: float = Field(default=0.5)

    # LLM & runtime
    LLM_MODEL: str | None = None
    RESPONSE_TIMEOUT: int = Field(default=10)
    DISCORD_PRIORITY: int = Field(default=0)
    YOUTUBE_PRIORITY: int = Field(default=1)

    # TTS engine config
    TTS_ENGINE: str = Field(default="f5_tts_thai")
    TTS_VOICE_ID: str = Field(default="default")
    TTS_EMOTION_DEFAULT: str = Field(default="neutral")
    TTS_REFERENCE_WAV: str | None = None

    # Hugging Face token
    HF_TOKEN: str | None = None
    HUGGINGFACE_HUB_TOKEN: str | None = None

    # F5-TTS-THAI specific
    F5_TTS_MODEL: str = Field(default="v1")
    F5_TTS_STEP: int = Field(default=32)
    F5_TTS_CFG: float = Field(default=2.0)
    F5_TTS_SPEED: float = Field(default=1.0)
    F5_TTS_SR: int = Field(default=24000)
    F5_TTS_REF_TEXT: str = Field(default="")
    F5_TTS_TIMEOUT_MS: int = Field(default=5000)
    F5_TTS_PREWARM: bool = Field(default=True)
    RVC_TIMEOUT_MS: int = Field(default=2000)

    # Voice conversion (RVC) presets
    ENABLE_RVC: bool = Field(default=False)
    VOICE_PRESET: str = Field(default="neutral")

    # Lipsync settings
    LIPSYNC_PARAM: str = Field(default="MouthOpen")
    LIPSYNC_FRAME_MS: float = Field(default=30.0)

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()