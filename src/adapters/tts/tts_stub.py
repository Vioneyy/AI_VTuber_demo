from __future__ import annotations
from typing import Optional, Dict, Any

from .tts_interface import TTSEngine

class StubTTSEngine(TTSEngine):
    def speak(self, text: str, *, voice_id: str, emotion: str, prosody: Optional[Dict[str, Any]] = None) -> Optional[bytes]:
        # สตับ: คืนค่า None เพื่อบอกว่ายังไม่เชื่อมต่อโมเดลจริง
        # ที่นี่สามารถต่อยอด: เรียกโมเดล TTS ที่กำลังฝึกด้วยพารามิเตอร์ voice_id/emotion/prosody
        return None