# src/core/types.py
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
import time

# หลัก: ให้ชื่อ MessageSource เป็นชื่อ enum ที่ใช้ในโปรเจคใหม่
class MessageSource(Enum):
    DISCORD = "discord"
    YOUTUBE = "youtube"
    VTS = "vts"  # เพิ่มไว้เผื่อใช้กับ VTube Studio โดยตรง

# backward-compatible alias (ถ้ามีที่อื่นใช้ชื่อ Source)
Source = MessageSource

class Emotion(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"
    SLEEPY = "sleepy"
    CONFUSED = "confused"
    EXCITED = "excited"

@dataclass
class IncomingMessage:
    """
    ข้อความที่เข้ามาจากแหล่งต่าง ๆ (Discord / YouTube / VTS ฯลฯ)
    ใช้เป็นชนิดหลักที่ main.py อ้างอิงอยู่
    """
    text: str
    source: MessageSource
    author: Optional[str] = None
    timestamp: float = None
    is_question: bool = False
    priority: int = 0
    meta: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

# backward-compatible alias (ถ้ามีที่อื่นเรียก Message)
Message = IncomingMessage

@dataclass
class Response:
    """
    โครงสำหรับผลลัพธ์ที่ระบบจะส่งกลับ เช่น ข้อความ, อารมณ์ และท่าทาง
    """
    text: str
    emotion: Emotion = Emotion.NEUTRAL
    gestures: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None

# ส่งออกชื่อที่สำคัญ (ไม่จำเป็นแต่ชัดเจน)
__all__ = [
    "MessageSource",
    "Source",
    "Emotion",
    "IncomingMessage",
    "Message",
    "Response",
]
