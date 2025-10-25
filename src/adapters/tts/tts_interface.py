from __future__ import annotations
from typing import Optional, Dict, Any

class TTSEngine:
    def speak(self, text: str, *, voice_id: str, emotion: str, prosody: Optional[Dict[str, Any]] = None) -> Optional[bytes]:
        """แปลงข้อความเป็นเสียง
        - voice_id: ระบุเสียงที่จะใช้
        - emotion: อารมณ์หลัก เช่น neutral/happy/sad
        - prosody: ตัวเลือกปรับน้ำหนัก, ความเร็ว, pitch ฯลฯ
        return: ข้อมูลเสียงเป็น bytes (หรือ None ถ้ายังไม่พร้อม)
        """
        raise NotImplementedError