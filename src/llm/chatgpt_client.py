"""
ChatGPT Client with Personality
"""
import os
import openai
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class ChatGPTClient:
    def __init__(self, persona_name: str = "miko"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("⚠️ ไม่มี OPENAI_API_KEY ใช้ LLM แบบ scaffold")
            self.enabled = False
        else:
            openai.api_key = api_key
            self.enabled = True
            logger.info("✅ ChatGPT Client เชื่อมต่อสำเร็จ")
        
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.8"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "80"))
        
        from src.personality.persona import get_persona
        self.system_prompt = get_persona(persona_name)
        
        logger.info(f"🎭 ใช้ Persona: {persona_name}")

    def generate_response(self, user_message: str, context: Optional[str] = None) -> str:
        """
        สร้างคำตอบจาก LLM
        """
        if not self.enabled:
            return self._scaffold_response(user_message)
        
        try:
            messages = [
                {"role": "system", "content": self.system_prompt}
            ]
            
            if context:
                messages.append({"role": "system", "content": f"บริบท: {context}"})
            
            messages.append({"role": "user", "content": user_message})
            
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=15
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