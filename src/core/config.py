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
    # ปรับความกระชับ/ความเร็วของคำตอบ
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "128"))
    
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
    # โหมดสไตล์และพรีเซ็ตสำหรับการขยับให้ดูเป็นมนุษย์มากขึ้น
    VTS_NEURO_STYLE = os.getenv("VTS_NEURO_STYLE", "0").lower() in ("1", "true", "yes")
    VTS_USE_TIMELINE_STYLE = os.getenv("VTS_USE_TIMELINE_STYLE", "1").lower() in ("1", "true", "yes")
    # ปรับจูนพฤติกรรม idle ให้คล้ายมนุษย์: ความถี่การส่ายหัวตามแกนต่าง ๆ (Hz)
    VTS_IDLE_YAW_FREQ_HZ = float(os.getenv("VTS_IDLE_YAW_FREQ_HZ", "0.055"))
    VTS_IDLE_PITCH_FREQ_HZ = float(os.getenv("VTS_IDLE_PITCH_FREQ_HZ", "0.045"))
    VTS_IDLE_ROLL_FREQ_HZ = float(os.getenv("VTS_IDLE_ROLL_FREQ_HZ", "0.065"))
    # เวลา look-away ขั้นต่ำ/ขั้นสูงสุด (วินาที)
    VTS_LOOK_AWAY_MIN_INTERVAL = float(os.getenv("VTS_LOOK_AWAY_MIN_INTERVAL", "13.0"))
    VTS_LOOK_AWAY_MAX_INTERVAL = float(os.getenv("VTS_LOOK_AWAY_MAX_INTERVAL", "17.0"))
    # โอกาสทำ blink เป็นคลัสเตอร์, โอกาส pulse รอยยิ้ม, และเปิด nod ตอนพูด
    VTS_BLINK_CLUSTER_PROB = float(os.getenv("VTS_BLINK_CLUSTER_PROB", "0.35"))
    VTS_SMILE_PULSE_PROB = float(os.getenv("VTS_SMILE_PULSE_PROB", "0.60"))
    VTS_NOD_ON_TALK = os.getenv("VTS_NOD_ON_TALK", "1").lower() in ("1", "true", "yes")

    # การลดอาการสั่น/สั่นไหวและทำให้การขยับนุ่มขึ้น (ค่าเริ่มต้นเน้นนิ่งขึ้น)
    VTS_SMOOTHING_ALPHA = float(os.getenv("VTS_SMOOTHING_ALPHA", "0.12"))  # 0..1, ยิ่งต่ำยิ่งนุ่ม
    VTS_DISABLE_NOISE = os.getenv("VTS_DISABLE_NOISE", "1").lower() in ("1", "true", "yes")
    VTS_NOISE_HEAD_SCALE = float(os.getenv("VTS_NOISE_HEAD_SCALE", "0.00"))
    VTS_NOISE_HEAD_Z_SCALE = float(os.getenv("VTS_NOISE_HEAD_Z_SCALE", "0.00"))
    VTS_NOISE_BODY_X_SCALE = float(os.getenv("VTS_NOISE_BODY_X_SCALE", "0.00"))
    VTS_NOISE_BODY_Z_SCALE = float(os.getenv("VTS_NOISE_BODY_Z_SCALE", "0.00"))
    VTS_IDLE_JITTER_X = float(os.getenv("VTS_IDLE_JITTER_X", "0.00"))
    VTS_IDLE_JITTER_Y = float(os.getenv("VTS_IDLE_JITTER_Y", "0.00"))
    VTS_MICROSACCADE_PROB = float(os.getenv("VTS_MICROSACCADE_PROB", "0.005"))
    # ตัวเลือกสำหรับการดีบัก/ปิด motion ชั่วคราว
    VTS_DISABLE_ALL_MOTION = os.getenv("VTS_DISABLE_ALL_MOTION", "0").lower() in ("1", "true", "yes")
    VTS_ENABLE_RANDOM_MOTION = os.getenv("VTS_ENABLE_RANDOM_MOTION", "1").lower() in ("1", "true", "yes")
    # บันทึกข้อมูลการ inject เป็น CSV เพื่อวิเคราะห์ jitter
    VTS_DUMP_CSV = os.getenv("VTS_DUMP_CSV", "0").lower() in ("1", "true", "yes")
    VTS_DUMP_CSV_PATH = os.getenv("VTS_DUMP_CSV_PATH", str((Path(__file__).parent.parent.parent / "logs" / "vts_motion_dump.csv")))
    # โหมดสคริปต์ (เล่นพรีเซ็ต Neuro แบบไม่ใช้ motion loop)
    VTS_SCRIPTED_PRESET = os.getenv("VTS_SCRIPTED_PRESET", "0").lower() in ("1", "true", "yes")
    # โหมดสุ่มเหตุการณ์ (ไม่ใช้ลูปอัปเดตต่อเนื่อง): สุ่ม tilt/look/nod/smile/half‑lid
    VTS_RANDOM_EVENTS_PRESET = os.getenv("VTS_RANDOM_EVENTS_PRESET", "0").lower() in ("1", "true", "yes")
    # โหมดสุ่มเหตุการณ์แบบต่อเนื่อง (ไม่มีเวลาจำกัด จนกว่าจะสั่งหยุด)
    VTS_RANDOM_EVENTS_CONTINUOUS = os.getenv("VTS_RANDOM_EVENTS_CONTINUOUS", "0").lower() in ("1", "true", "yes")
    # ระยะเวลาเล่นพรีเซ็ต (วินาที) สำหรับทั้งโหมดสคริปต์และสุ่มเหตุการณ์
    VTS_PRESET_DURATION_SEC = float(os.getenv("VTS_PRESET_DURATION_SEC", "0.0"))
    # โปรไฟล์สไตล์และวิดีโออ้างอิง (ใช้ปรับ motion ให้เป็นธรรมชาติ)
    VTS_STYLE_PROFILE_NAME = os.getenv("VTS_STYLE_PROFILE_NAME", "neuro_like")
    VTS_STYLE_PROFILE_FILE = os.getenv(
        "VTS_STYLE_PROFILE_FILE",
        str((Path(__file__).parent.parent / "adapters" / "vts" / "styles" / "neuro_like.json").resolve())
    )
    # ระบุไฟล์วิดีโออ้างอิงแบบ comma-separated path
    _style_ref_videos_raw = os.getenv("VTS_STYLE_REF_VIDEOS", "")
    VTS_STYLE_REF_VIDEOS = [p.strip() for p in _style_ref_videos_raw.split(",") if p.strip()]
    
    # Safe Motion Mode
    SAFE_MOTION_MODE = os.getenv("SAFE_MOTION_MODE", "false").lower() == "true"
    SAFE_HOTKEY_INTERVAL = float(os.getenv("SAFE_HOTKEY_INTERVAL", "8.0"))
    
    # VTS Hotkey Settings (สำหรับ Hiyori_A - มีแค่ 3 hotkeys)
    ENABLE_GLOBAL_HOTKEYS = os.getenv("ENABLE_GLOBAL_HOTKEYS", "false").lower() == "true"
    VTS_HK_NEUTRAL = os.getenv("VTS_HK_NEUTRAL", "thinking")
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
    # เสียงและความเร็วสำหรับ TTS
    TTS_VOICE_ID = os.getenv("TTS_VOICE_ID", "default")
    F5_TTS_SPEED = float(os.getenv("F5_TTS_SPEED", "1.0"))
    # ควบคุมการใช้เสียง/ข้อความอ้างอิงสำหรับ F5-TTS-Thai
    # หากปิด (false) จะไม่ส่ง ref_audio/ref_text เข้าโมเดล เพื่อหลีกเลี่ยงการพูด ref_text ติดมาด้วย
    F5_TTS_USE_REFERENCE = os.getenv("F5_TTS_USE_REFERENCE", "false").lower() in ("1", "true", "yes")
    # ข้อความอ้างอิงสำหรับการจัดวางเสียง (ถ้าเว้นว่าง บางโมเดลจะใช้ ASR กับ ref_audio)
    # รองรับทั้งชื่อคีย์ใหม่และถอยหลังเข้ากันกับ TTS_REFERENCE_TEXT
    F5_TTS_REF_TEXT = os.getenv("F5_TTS_REF_TEXT", "")
    
    # === RVC ===
    ENABLE_RVC = os.getenv("ENABLE_RVC", "false").lower() == "true"
    VOICE_PRESET = os.getenv("VOICE_PRESET", "anime_girl")
    RVC_GAIN_DB = float(os.getenv("RVC_GAIN_DB", "0.0"))
    
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
            # บังคับตรวจไฟล์อ้างอิงเฉพาะกรณีเปิดใช้ reference เท่านั้น
            if self.F5_TTS_USE_REFERENCE:
                if not self.TTS_REFERENCE_WAV or not os.path.exists(self.TTS_REFERENCE_WAV):
                    errors.append("⚠️ TTS_REFERENCE_WAV ไม่ได้ตั้งค่าหรือไฟล์ไม่มีอยู่ (เปิดใช้ reference)")
        
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