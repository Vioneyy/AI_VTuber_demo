"""
tts_factory.py
ตัวเลือกสร้าง TTS engine ตามค่า .env/TTS_ENGINE

ปัจจุบันรองรับเฉพาะ "f5_tts_thai" และจัดการข้อความบอกผู้ใช้ให้ตั้งค่าให้ถูกต้อง
"""
from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)


def create_tts_engine(engine_type: str | None = None):
    """
    คืนอ็อบเจ็กต์ TTS ที่มีเมธอด `async generate(text) -> str` คืนพาธไฟล์ WAV

    รองรับ:
    - f5_tts_thai: ใช้ F5-TTS-Thai adapter ภายใน

    หากระบุชนิดอื่น จะยกเว้นด้วยข้อความชัดเจนเพื่อให้ตั้งค่า .env ให้ถูกต้อง
    """
    et = (engine_type or os.getenv("TTS_ENGINE", "f5_tts_thai")).lower()
    logger.info(f"🎯 TTS Engine: {et}")

    if et == "f5_tts_thai":
        # ใช้ factory ของ f5_tts_thai โดยตรง (คืน F5ThaiAdapter)
        from .f5_tts_thai import create_tts_engine as create_f5
        return create_f5(et)

    # ยังไม่รองรับ engine อื่นในโปรเจกต์นี้
    logger.error(
        "❌ ยังไม่รองรับ TTS_ENGINE='%s' กรุณาตั้งค่า TTS_ENGINE=f5_tts_thai ใน .env",
        et,
    )
    raise RuntimeError("Unsupported TTS_ENGINE. Set TTS_ENGINE=f5_tts_thai")