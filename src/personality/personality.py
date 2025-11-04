"""
PersonalityManager wrapper ให้ main.py ใช้งานได้
ดึง SYSTEM_PROMPT จาก jeed_persona.py เป็นค่าเริ่มต้น
"""

from pathlib import Path
from typing import Optional

from .jeed_persona import JeedPersona


class PersonalityManager:
    """ตัวจัดการบุคลิกภาพแบบเรียบง่ายสำหรับ main.py"""

    def __init__(self, persona_path: Optional[Path] = None, persona_name: str = "jeed"):
        # รองรับพาธไฟล์ที่เคยใช้ แต่ถ้าไม่พบจะใช้ค่าเริ่มต้น
        self.persona_name = persona_name
        self._prompt = JeedPersona.SYSTEM_PROMPT
        # ถ้าอนาคตมีไฟล์ persona.json จะสามารถโหลดมาแทนได้

    def get_prompt(self) -> str:
        """คืนค่า system prompt สำหรับ LLM"""
        return self._prompt