"""
ChatGPTClient wrapper ให้เข้ากับ main.py โดยใช้ LLMHandler ภายใน
รองรับพารามิเตอร์ api_key/model/temperature/max_tokens จาก main.py
"""

from typing import Optional

from .llm_handler import LLMHandler, llm_handler
from core.config import config


class ChatGPTClient:
    def __init__(self,
                 api_key: Optional[str] = None,
                 model: Optional[str] = None,
                 temperature: Optional[float] = None,
                 max_tokens: Optional[int] = None,
                 handler: Optional[LLMHandler] = None):
        # อัพเดทการตั้งค่า LLM ตามที่ main.py ส่งมา (ถ้ามี)
        if api_key:
            config.llm.api_key = api_key
        if model:
            config.llm.model = model
        if temperature is not None:
            config.llm.temperature = temperature
        if max_tokens is not None:
            config.llm.max_tokens = max_tokens

        self._handler = handler or llm_handler

    async def get_response(self, text: str, personality: Optional[str] = None) -> str:
        """
        รับข้อความจากผู้ใช้ และคืนคำตอบจาก LLM
        personality ถูกละไว้ เพราะ LLMHandler ใช้ JeedPersona.SYSTEM_PROMPT อยู่แล้ว
        """
        return await self._handler.generate_response(text)

    async def generate(self, text: str, system_prompt: Optional[str] = None) -> str:
        """ให้เข้ากับ ResponseGenerator โดยรองรับ system_prompt แบบ optional"""
        return await self._handler.generate_response(text, system_prompt=system_prompt)

    def clear_history(self):
        self._handler.clear_history()

    def get_stats(self):
        return self._handler.get_stats()