"""
Motion Commands - ส่งคำสั่งการขยับจาก LLM ไปยัง VTS
ใช้ส่วนต่อประสานระหว่าง LLM ↔ Motion Controller
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

class MotionType(Enum):
    """ประเภทของการขยับ"""
    IDLE = "idle"
    THINKING = "thinking"
    EXCITED = "excited"
    CONFUSED = "confused"
    ANGRY = "angry"
    SAD = "sad"
    HAPPY = "happy"

class MotionIntensity(Enum):
    """ความเข้มของการขยับ"""
    VERY_LOW = 0.1
    LOW = 0.3
    MEDIUM = 0.6
    HIGH = 0.85
    VERY_HIGH = 1.0

@dataclass
class MotionCommand:
    """คำสั่งการขยับ"""
    motion_type: MotionType
    intensity: MotionIntensity
    duration: float = 2.5
    micro_twitch_enabled: bool = True
    
    def __str__(self) -> str:
        return f"Motion({self.motion_type.value}, {self.intensity.value:.1f})"