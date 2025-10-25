from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
import time

class Source(Enum):
    DISCORD = "discord"
    YOUTUBE = "youtube"

class Emotion(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"
    CALM = "calm"

@dataclass
class Message:
    text: str
    source: Source
    author: Optional[str] = None
    timestamp: float = time.time()
    is_question: bool = False
    priority: int = 0
    meta: Optional[Dict[str, Any]] = None

@dataclass
class Response:
    text: str
    emotion: Emotion = Emotion.NEUTRAL
    gestures: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None