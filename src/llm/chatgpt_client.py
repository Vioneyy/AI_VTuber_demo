"""
ChatGPT Client with Personality
รองรับพารามิเตอร์จาก orchestrator และมีเมธอด generate ตามที่ ResponseGenerator ต้องการ
ปรับให้เข้ากับ openai>=1.0.0 โดยใช้ AsyncOpenAI
"""
import os
import logging
from typing import Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class ChatGPTClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        personality_system: Optional[object] = None,
        persona_name: Optional[str] = None,
    ):
        # ตั้งค่า API key
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            logger.warning("⚠️ ไม่มี OPENAI_API_KEY ใช้ LLM แบบ scaffold")
            self.enabled = False
        else:
            # ใช้ไคลเอนต์ใหม่ของ openai>=1.0.0
            self.client = AsyncOpenAI(api_key=key)
            self.enabled = True
            logger.info("✅ ChatGPT Client เชื่อมต่อสำเร็จ")

        # ตั้งค่าโมเดลและพารามิเตอร์
        self.model = (model or os.getenv("LLM_MODEL", "gpt-4o-mini"))
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.8"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "80"))

        # กำหนด system prompt
        if personality_system and hasattr(personality_system, "get_system_prompt"):
            self.system_prompt = personality_system.get_system_prompt()
            logger.info("🎭 ใช้ System Prompt จาก PersonalitySystem")
        else:
            from src.personality.persona import get_persona
            name = persona_name or os.getenv("PERSONA_NAME", "miko")
            self.system_prompt = get_persona(name)
            logger.info(f"🎭 ใช้ Persona: {name}")

    async def generate(self, user_message: str, system_prompt: Optional[str] = None) -> str:
        """
        สร้างคำตอบจาก LLM ตามอินเทอร์เฟซที่ ResponseGenerator เรียกใช้
        """
        if not self.enabled:
            return self._scaffold_response(user_message)

        try:
            messages = [{"role": "system", "content": system_prompt or self.system_prompt}]

            messages.append({"role": "user", "content": user_message})

            # ใช้ API ใหม่: client.chat.completions.create (async)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            answer = response.choices[0].message.content.strip()
            logger.info(f"💬 LLM ตอบ: {answer[:50]}...")
            return answer

        except Exception as e:
            logger.error(f"❌ LLM error: {e}")
            return self._scaffold_response(user_message)

    def _scaffold_response(self, message: str) -> str:
        """
        คำตอบสำรอง
        """
        import random

        responses = [
            "เอ๊ะ ไม่เข้าใจเลย~ ถามใหม่ได้มั้ย?",
            "อืม... คิดไม่ออกจัง ฮ่าๆ",
            "ไม่แน่ใจเหมือนกันนะ แต่น่าสนใจดี!",
            "โอ้โห คำถามยากเลย ขอคิดก่อนสักพัก~",
            "เฮ้ย~ ฉันไม่ได้เก่งขนาดนั้นหรอก ลองถามใหม่ดูมั้ย?",
            "อะฮ่า ฉันก็ไม่รู้เหมือนกัน แต่น่าสนุกนะเรื่องนี้!"
        ]

        return random.choice(responses)

    def set_persona(self, persona_name: str):
        """
        เปลี่ยนบุคลิก
        """
        from src.personality.persona import get_persona

        self.system_prompt = get_persona(persona_name)
        logger.info(f"🎭 เปลี่ยนเป็น Persona: {persona_name}")