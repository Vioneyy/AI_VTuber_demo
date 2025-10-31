"""
response_generator.py - Response Generation System
ระบบสร้างคำตอบด้วย LLM + Personality + Safety
"""

import logging
from typing import Optional, Tuple
from .safety_filter import SafetyFilter, SafetyLevel, get_safety_filter
from .admin_commands import get_admin_handler

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """สร้างคำตอบด้วย LLM พร้อมระบบ safety"""
    
    def __init__(self, llm_client, personality_system):
        self.llm = llm_client
        self.personality = personality_system
        self.safety_filter = get_safety_filter()
        self.admin_handler = get_admin_handler()
    
    async def generate_response(
        self,
        user_message: str,
        user: str,
        source: str,
        repeat_question: bool = False
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        สร้างคำตอบ
        
        Args:
            user_message: ข้อความจากผู้ใช้
            user: ชื่อผู้ใช้
            source: แหล่งที่มา (discord/youtube)
            repeat_question: ทวนคำถามหรือไม่ (สำหรับ YouTube)
        
        Returns:
            (response_text, rejection_reason)
            - response_text: คำตอบ หรือ None ถ้าถูกปฏิเสธ
            - rejection_reason: เหตุผลที่ถูกปฏิเสธ
        """
        
        # 1. Safety check
        safety_level, reason = self.safety_filter.check_content(user_message)
        
        # 1.1 ถ้า BLOCKED = ปฏิเสธทันที
        if safety_level == SafetyLevel.BLOCKED:
            rejection_msg = self.safety_filter.generate_rejection_message(
                reason,
                personality=self.personality.get_current_personality()
            )
            logger.warning(f"🚫 BLOCKED: {user_message[:50]}")
            return rejection_msg, reason
        
        # 1.2 ถ้า NEEDS_APPROVAL = ขออนุญาต admin
        if safety_level == SafetyLevel.NEEDS_APPROVAL:
            logger.info(f"⚠️ Needs approval: {user_message[:50]}")
            
            # แจ้งให้ user รู้ว่ากำลังขออนุญาต
            asking_msg = self._generate_asking_approval_message()
            
            # TODO: ส่งข้อความ asking_msg ไปยัง user
            # await send_message(asking_msg)
            
            # สร้าง approval request
            approval_id = await self.safety_filter.request_approval(
                user_message, user, source
            )
            
            # รอการอนุมัติ
            approved = await self.safety_filter.wait_for_approval(approval_id)
            
            if not approved:
                rejection_msg = self.safety_filter.generate_rejection_message(
                    "ไม่ได้รับอนุมัติจาก admin",
                    personality=self.personality.get_current_personality()
                )
                return rejection_msg, "Not approved by admin"
            
            # ถ้าอนุมัติแล้ว = ไปต่อ
            logger.info(f"✅ Approved: {user_message[:50]}")
        
        # 2. เช็คว่าเป็นคำถามเกี่ยวกับโปรเจคหรือไม่
        if not self.admin_handler.can_reveal_project_info():
            if self._is_project_related(user_message):
                rejection_msg = self._generate_project_rejection_message()
                return rejection_msg, "Project info locked"
        
        # 3. สร้าง system prompt
        system_prompt = self._build_system_prompt()
        
        # 4. สร้างคำตอบด้วย LLM
        try:
            # ทวนคำถาม (สำหรับ YouTube)
            prefix = ""
            if repeat_question and source == "youtube":
                prefix = f'"{user_message}" เหรอคะ? '
            
            # เรียก LLM
            llm_response = await self.llm.generate(
                user_message,
                system_prompt=system_prompt
            )
            
            # ตรวจสอบความยาว (ถ้ายาวเกินไป ให้สั้นลง)
            llm_response = self._ensure_concise(llm_response)
            
            # รวม prefix + response
            final_response = prefix + llm_response
            
            logger.info(f"💬 Response: {final_response[:100]}")
            return final_response, None
        
        except Exception as e:
            logger.error(f"❌ LLM error: {e}", exc_info=True)
            error_msg = self._generate_error_message()
            return error_msg, str(e)
    
    def _build_system_prompt(self) -> str:
        """สร้าง system prompt"""
        personality_prompt = self.personality.get_system_prompt()
        
        safety_rules = """
คุณต้องปฏิบัติตามกฎเหล่านี้อย่างเคร่งครัด:
- ห้ามพูดเหยียดเชื้อชาติ ผิว รสนิยม รูปร่าง
- ห้ามพูดถึงเหตุการณ์ทางการเมืองที่รุนแรง
- ห้ามพูดถึงสงคราม ความขัดแย้งระหว่างประเทศ
- ห้ามพูดไม่รู้เรื่อง ต้องสื่อความหมายได้ชัดเจน
- ห้ามพูดถึงข้อมูลส่วนตัว โค้ด ไฟล์ หรือระบบของโปรเจค
- ตอบสั้น กระชับ แต่รู้เรื่อง (ไม่เกิน 2-3 ประโยค)
"""
        
        return f"{personality_prompt}\n\n{safety_rules}"
    
    def _is_project_related(self, text: str) -> bool:
        """เช็คว่าเป็นคำถามเกี่ยวกับโปรเจคหรือไม่"""
        keywords = [
            "โค้ด", "code", "ไฟล์", "file", "api", "key", "token",
            "โปรเจค", "project", "ระบบ", "system", "ทำงาน", "work"
        ]
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)
    
    def _generate_asking_approval_message(self) -> str:
        """สร้างข้อความขออนุญาต admin"""
        templates = [
            "เอ่อ... คำถามนี้ขอถามคนควบคุมไลฟ์ก่อนนะคะ~ รอแป๊บนึงน้า 😊",
            "อุ๊ย! คำถามนี้ต้องถามแอดมินก่อนนะ รอสักครู่น้า~",
            "ขอถามเจ้าของก่อนนะคะ รอแป๊บนึง! 💭"
        ]
        import random
        return random.choice(templates)
    
    def _generate_project_rejection_message(self) -> str:
        """สร้างข้อความปฏิเสธคำถามเกี่ยวกับโปรเจค"""
        templates = [
            "ขอโทษนะคะ เรื่องระบบฉันไม่สามารถบอกได้~ 🙊",
            "อุ๊ย! นี่เป็นความลับของโปรเจคน้า บอกไม่ได้จ้า 🤫",
            "เอ่อ... เรื่องเทคนิคฉันไม่มีสิทธิ์เปิดเผยนะ ขอโทษด้วย~ 😅"
        ]
        import random
        return random.choice(templates)
    
    def _generate_error_message(self) -> str:
        """สร้างข้อความเมื่อเกิด error"""
        templates = [
            "อุ๊ย! สมองฉันค้างนิดหน่อย ลองถามใหม่อีกทีนะคะ~ 😵",
            "เอ๊ะ? มีอะไรผิดพลาด ขอโทษนะคะ ถามใหม่ได้มั้ย? 🥺",
            "หยุดทำงานสักครู่~ ลองถามอีกทีนะ! 💫"
        ]
        import random
        return random.choice(templates)
    
    def _ensure_concise(self, text: str, max_sentences: int = 3) -> str:
        """ตัดข้อความให้สั้น กระชับ"""
        # แยกประโยค
        sentences = text.split('.')
        
        # เอาแค่ n ประโยคแรก
        if len(sentences) > max_sentences:
            sentences = sentences[:max_sentences]
            text = '.'.join(sentences) + '.'
        
        # ตัดถ้ายาวเกิน 200 ตัวอักษร
        if len(text) > 200:
            text = text[:197] + "..."
        
        return text.strip()


# Singleton
_response_generator = None

def get_response_generator(llm_client, personality_system) -> ResponseGenerator:
    """ดึง ResponseGenerator instance"""
    global _response_generator
    if _response_generator is None:
        _response_generator = ResponseGenerator(llm_client, personality_system)
    return _response_generator