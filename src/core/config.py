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
    VTS_RECONNECT_ATTEMPTS: int = Field(default=5)
    VTS_PING_INTERVAL: int = Field(default=30)
    VTS_PING_TIMEOUT: int = Field(default=20)

    # Idle motion settings
    IDLE_MOTION_ENABLED: bool = Field(default=True)
    IDLE_MOTION_INTERVAL: float = Field(default=1.5)
    IDLE_MOTION_AMPLITUDE: float = Field(default=8.0)
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
    BREATHING_MIN_INTENSITY: float = Field(default=1.5)
    BREATHING_MAX_INTENSITY: float = Field(default=4.0)

    # Safe motion (hotkey-only) fallback
    SAFE_MOTION_MODE: bool = Field(default=False)
    SAFE_HOTKEY_INTERVAL: float = Field(default=6.0)
    SAFE_HOTKEY_WEIGHT: float = Field(default=1.0)
    SAFE_HOTKEY_NAMES: str | None = Field(default=None, description="Comma-separated hotkey names to cycle")

    # TTS
    ENABLE_TTS: bool = Field(default=True)
    # TTS engine config (retain legacy field for compatibility)
    TTS_ENGINE: str = Field(default="f5_tts_thai")
    TTS_VOICE_ID: str = Field(default="default")
    TTS_EMOTION_DEFAULT: str = Field(default="neutral")
    TTS_REFERENCE_WAV: str | None = None
    F5_TTS_MODEL: str = Field(default="VIZINTZOR/F5-TTS-THAI")
    F5_TTS_PROMPT: str = Field(default="")
    F5_TTS_SPEAKER: str = Field(default="hiyori")
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

    # Discord voice STT toggle
    DISCORD_VOICE_STT_ENABLED: bool = Field(default=True)

    # Whisper.cpp STT settings
    WHISPER_CPP_BIN_PATH: str | None = None
    WHISPER_CPP_MODEL_PATH: str | None = None
    WHISPER_CPP_LANG: str = Field(default="th")
    WHISPER_CPP_THREADS: int = Field(default=4)
    WHISPER_CPP_NGL: int = Field(default=35)
    WHISPER_CPP_TIMEOUT_MS: int = Field(default=5000)

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()