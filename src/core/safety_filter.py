"""
ระบบกรองเนื้อหาที่ไม่เหมาะสม + ระบบอนุมัติ
ตำแหน่ง: src/core/safety_filter.py
ให้สอดคล้องกับ ResponseGenerator และ AdminCommands
"""

import re
from typing import Tuple, Optional, List, Dict
from enum import Enum

from core.config import config

class SafetyLevel(Enum):
    """ระดับความปลอดภัยที่ใช้โดย ResponseGenerator"""
    ALLOW = "allow"
    BLOCKED = "blocked"
    NEEDS_APPROVAL = "needs_approval"

class SafetyFilter:
    """กรองเนื้อหาที่ไม่เหมาะสม"""
    
    # คำหยาบ/คำต้องห้าม
    PROFANITY_WORDS = [
        "ควย", "สัส", "เหี้ย", "เชี่ย", "กู", "มึง",
        "ไอ้สัตว์", "ไอ้เวร", "ไอ้บ้า", "shit", "fuck"
    ]
    
    # คำเกี่ยวกับการเมือง
    POLITICAL_KEYWORDS = [
        "รัฐประหาร", "ผู้นำ", "นายกฯ", "พรรคการเมือง",
        "ประชาธิปไตย", "เผด็จการ", "การเลือกตั้ง"
    ]
    
    # คำเกี่ยวกับศาสนา
    RELIGIOUS_KEYWORDS = [
        "พระเจ้า", "พระพุทธเจ้า", "อัลเลาะห์", "ศาสนา",
        "วัด", "โบสถ์", "มัสยิด", "ผิดบาป"
    ]
    
    # คำเกี่ยวกับความรุนแรง
    VIOLENCE_KEYWORDS = [
        "ฆ่า", "ตาย", "ฆาตกร", "สังหาร", "ทรมาน",
        "ทำร้าย", "ระเบิด", "ปืน", "มีด", "อาวุธ"
    ]
    
    # คำเกี่ยวกับข้อมูลระบบ
    SYSTEM_KEYWORDS = [
        "api key", "token", "password", "โค้ด", "code",
        "ไฟล์ระบบ", "config", "database", ".env"
    ]
    
    def __init__(self):
        self.forbidden_topics = config.safety.forbidden_topics
        self.restricted_topics = config.safety.restricted_topics
        # ระบบอนุมัติ
        self._pending_approvals: Dict[str, Dict] = {}
        self._approved: Dict[str, bool] = {}
        
    def check_content(self, text: str) -> Tuple[SafetyLevel, Optional[str]]:
        """
        ตรวจสอบเนื้อหา
        Returns: (ผลการกรอง, เหตุผล)
        """
        text_lower = text.lower()
        
        # 1. Check profanity
        for word in self.PROFANITY_WORDS:
            if word in text_lower:
                return SafetyLevel.BLOCKED, f"พบคำหยาบ: {word}"
        
        # 2. Check forbidden topics
        if self._contains_keywords(text_lower, self.POLITICAL_KEYWORDS, threshold=2):
            return SafetyLevel.BLOCKED, "เนื้อหาเกี่ยวกับการเมือง"
        
        if self._contains_keywords(text_lower, self.RELIGIOUS_KEYWORDS, threshold=2):
            if self._is_extreme_religious(text_lower):
                return SafetyLevel.BLOCKED, "เนื้อหาศาสนาสุดโต่ง"
        
        if self._contains_keywords(text_lower, self.VIOLENCE_KEYWORDS, threshold=2):
            return SafetyLevel.BLOCKED, "เนื้อหาความรุนแรง"
        
        # 3. Check restricted topics (require permission)
        if self._contains_keywords(text_lower, self.SYSTEM_KEYWORDS, threshold=1):
            return SafetyLevel.NEEDS_APPROVAL, "ข้อมูลเกี่ยวกับระบบ"
        
        # 4. Additional checks
        if self._contains_personal_info(text):
            return SafetyLevel.BLOCKED, "ข้อมูลส่วนตัว"
        
        if self._is_spam(text):
            return SafetyLevel.BLOCKED, "ข้อความสแปม"
        
        return SafetyLevel.ALLOW, None
    
    def _contains_keywords(self, text: str, keywords: List[str], threshold: int = 1) -> bool:
        """ตรวจสอบว่ามีคำที่กำหนดหรือไม่"""
        count = 0
        for keyword in keywords:
            if keyword in text:
                count += 1
                if count >= threshold:
                    return True
        return False
    
    def _is_extreme_religious(self, text: str) -> bool:
        """ตรวจสอบเนื้อหาศาสนาสุดโต่ง"""
        extreme_words = ["นรก", "บาป", "ผิดบาป", "สาปแช่ง", "แช่งให้"]
        return any(word in text for word in extreme_words)
    
    def _contains_personal_info(self, text: str) -> bool:
        """ตรวจสอบข้อมูลส่วนตัว"""
        # เบอร์โทร (10 หลัก)
        phone_pattern = r'\b0\d{8,9}\b'
        if re.search(phone_pattern, text):
            return True
        
        # อีเมล
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        if re.search(email_pattern, text):
            return True
        
        # เลขบัตรประชาชน (13 หลัก)
        id_pattern = r'\b\d{13}\b'
        if re.search(id_pattern, text):
            return True
        
        return False
    
    def _is_spam(self, text: str) -> bool:
        """ตรวจสอบสแปม"""
        # ตัวอักษรซ้ำมากเกินไป
        repeat_pattern = r'(.)\1{5,}'
        if re.search(repeat_pattern, text):
            return True
        
        # ข้อความสั้นมากที่ซ้ำกัน
        if len(text) < 5 and len(set(text)) < 3:
            return True
        
        return False
    
    def generate_rejection_message(self, reason: str, personality: Optional[str] = None) -> str:
        """สร้างคำตอบที่ปลอดภัย"""
        responses = [
                "เอ๊ะ หนูคิดว่าเราไม่ควรคุยเรื่องนี้นะ ลองถามเรื่องอื่นดีกว่า~",
                "อุ๊ปส์ เรื่องนี้หนูตอบไม่ได้นะ ขอโทษจ้า 😅",
                "หนูไม่สามารถพูดเรื่องนี้ได้ค่ะ ลองถามเรื่องอื่นไหม~",
            ]
        import random
        return random.choice(responses)
    
    async def request_approval(self, content: str, user: str, source: str) -> str:
        """สร้างคำขออนุมัติและคืน approval_id"""
        import time, uuid
        approval_id = uuid.uuid4().hex[:8]
        self._pending_approvals[approval_id] = {
            "content": content,
            "user": user,
            "source": source,
            "created_at": time.time(),
        }
        print(f"\n🔐 ขออนุมัติ ({approval_id}): {content[:80]} จาก {source}")
        return approval_id

    async def wait_for_approval(self, approval_id: str, timeout: float = 10.0) -> bool:
        """รอผลอนุมัติภายในเวลาที่กำหนด"""
        start = __import__('time').time()
        while __import__('time').time() - start < timeout:
            if approval_id in self._approved:
                return self._approved.pop(approval_id)
            await __import__('asyncio').sleep(0.2)
        # timeout: ปฏิเสธโดยอัตโนมัติ
        self._pending_approvals.pop(approval_id, None)
        return False

    def approve_request(self, approval_id: str, approved: bool) -> bool:
        """ให้แอดมินอนุมัติ/ปฏิเสธคำขอ"""
        if approval_id in self._pending_approvals:
            self._approved[approval_id] = approved
            self._pending_approvals.pop(approval_id, None)
            return True
        return False

    def get_pending_approvals(self) -> List[Dict]:
        return [
            {"id": k, **v} for k, v in sorted(
                self._pending_approvals.items(), key=lambda kv: kv[1]["created_at"], reverse=True
            )
        ]
    
    def approve_permission(self, message_id: str) -> bool:
        """อนุญาตข้อความ"""
        if message_id in self.permission_pending:
            del self.permission_pending[message_id]
            print(f"✅ อนุญาต: {message_id}")
            return True
        return False
    
    def deny_permission(self, message_id: str) -> bool:
        """ปฏิเสธข้อความ"""
        if message_id in self.permission_pending:
            del self.permission_pending[message_id]
            print(f"❌ ปฏิเสธ: {message_id}")
            return True
        return False
    
    def clean_text(self, text: str) -> str:
        """ทำความสะอาดข้อความ"""
        # ลบช่องว่างเกิน
        text = re.sub(r'\s+', ' ', text)
        
        # ลบอักขระพิเศษ
        text = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9\s\.\,\!\?\~\-]', '', text)
        
        return text.strip()

# Global safety filter
_safety_filter: Optional[SafetyFilter] = None

def get_safety_filter() -> SafetyFilter:
    global _safety_filter
    if _safety_filter is None:
        _safety_filter = SafetyFilter()
    return _safety_filter