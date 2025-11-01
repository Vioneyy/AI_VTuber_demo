"""
ระบบกรองเนื้อหาที่ไม่เหมาะสม
ตำแหน่ง: src/core/safety_filter.py (สร้างใหม่)
แทนที่: src/core/policy.py (ลบไฟล์เก่า)
"""

import re
from typing import Tuple, Optional, List
from enum import Enum

from core.config import config

class FilterResult(Enum):
    """ผลการกรอง"""
    ALLOW = "allow"              # อนุญาต
    BLOCK = "block"              # บล็อก
    REQUIRE_PERMISSION = "require_permission"  # ต้องขออนุญาต

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
        self.permission_pending = {}  # {message_id: content}
        
    def check_content(self, text: str) -> Tuple[FilterResult, Optional[str]]:
        """
        ตรวจสอบเนื้อหา
        Returns: (ผลการกรอง, เหตุผล)
        """
        text_lower = text.lower()
        
        # 1. Check profanity
        for word in self.PROFANITY_WORDS:
            if word in text_lower:
                return FilterResult.BLOCK, f"พบคำหยาบ: {word}"
        
        # 2. Check forbidden topics
        if self._contains_keywords(text_lower, self.POLITICAL_KEYWORDS, threshold=2):
            return FilterResult.BLOCK, "เนื้อหาเกี่ยวกับการเมือง"
        
        if self._contains_keywords(text_lower, self.RELIGIOUS_KEYWORDS, threshold=2):
            if self._is_extreme_religious(text_lower):
                return FilterResult.BLOCK, "เนื้อหาศาสนาสุดโต่ง"
        
        if self._contains_keywords(text_lower, self.VIOLENCE_KEYWORDS, threshold=2):
            return FilterResult.BLOCK, "เนื้อหาความรุนแรง"
        
        # 3. Check restricted topics (require permission)
        if self._contains_keywords(text_lower, self.SYSTEM_KEYWORDS, threshold=1):
            return FilterResult.REQUIRE_PERMISSION, "ข้อมูลเกี่ยวกับระบบ"
        
        # 4. Additional checks
        if self._contains_personal_info(text):
            return FilterResult.BLOCK, "ข้อมูลส่วนตัว"
        
        if self._is_spam(text):
            return FilterResult.BLOCK, "ข้อความสแปม"
        
        return FilterResult.ALLOW, None
    
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
    
    def create_safe_response(self, filter_result: FilterResult, reason: str) -> str:
        """สร้างคำตอบที่ปลอดภัย"""
        if filter_result == FilterResult.BLOCK:
            responses = [
                "เอ๊ะ หนูคิดว่าเราไม่ควรคุยเรื่องนี้นะ ลองถามเรื่องอื่นดีกว่า~",
                "อุ๊ปส์ เรื่องนี้หนูตอบไม่ได้นะ ขอโทษจ้า 😅",
                "หนูไม่สามารถพูดเรื่องนี้ได้ค่ะ ลองถามเรื่องอื่นไหม~",
            ]
            import random
            return random.choice(responses)
        
        elif filter_result == FilterResult.REQUIRE_PERMISSION:
            return "หนูต้องขออนุญาตผู้ควบคุมก่อนนะ รอแป๊บนึง~"
        
        return ""
    
    async def request_permission(self, content: str, message_id: str) -> bool:
        """
        ขออนุญาตจากผู้ควบคุม
        TODO: ต้องเชื่อมกับระบบ Discord/Console
        """
        self.permission_pending[message_id] = content
        print(f"\n🔐 ขออนุญาต: {content[:100]}")
        print("พิมพ์ 'approve' เพื่ออนุญาต หรือ 'deny' เพื่อปฏิเสธ")
        
        # ในเวอร์ชันจริงควรรอการตอบกลับ
        # ตอนนี้ return False ไว้ก่อน
        return False
    
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
safety_filter = SafetyFilter()