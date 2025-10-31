"""
safety_filter.py - Content Safety & Moderation System
ระบบกรองและตรวจสอบความปลอดภัยของเนื้อหา
"""

import re
import logging
from typing import Optional, Tuple, Dict
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class SafetyLevel(Enum):
    """ระดับความปลอดภัย"""
    SAFE = "safe"                    # ปลอดภัย พูดได้
    NEEDS_APPROVAL = "needs_approval"  # ต้องขออนุญาต admin
    BLOCKED = "blocked"              # ห้ามพูดเด็ดขาด


class SafetyFilter:
    """ระบบกรองความปลอดภัยของเนื้อหา"""
    
    def __init__(self):
        # คำห้ามเด็ดขาด (BLOCKED)
        self.blocked_patterns = [
            # เหยียดเชื้อชาติ/ผิว
            r'(ดำ|ขาว|เหลือง).*(ด้อย|กว่า|แย่)',
            r'(พวก|เผ่า).*(ชาติ|พันธุ์).*(ห่า|แย่)',
            
            # เหยียดรสนิยม
            r'(เกย์|เลส|ทอม|ดี้).*(แย่|ห่า|สกปรก)',
            
            # เหยียดรูปร่าง
            r'(อ้วน|ผอม|เตี้ย).*(น่าเกลียด|แย่)',
            
            # การเมืองรุนแรง
            r'(รัฐประหาร|ฆ่า|ลอบ).*(นายก|ผู้นำ|ประธาน)',
            r'(ทหาร|ตำรวจ).*(ยิง|ฆ่า|ตี)',
            
            # ความขัดแย้งระหว่างประเทศ
            r'(สงคราม|รบ|โจมตี).*(ไทย|จีน|อเมริกา|รัสเซีย)',
            r'(ทำลาย|บึ้ม|ระเบิด).*(ประเทศ|เมือง)',
            
            # ข้อมูลส่วนตัว/โปรเจค
            r'(โค้ด|ไฟล์|api|key|token)',
            r'(โปรเจค|ระบบ).*(ทำงาน|code)',
        ]
        
        # คำที่ต้องขออนุญาต (NEEDS_APPROVAL)
        self.approval_patterns = [
            # การเมืองเล็กน้อย
            r'(นายก|รัฐบาล|พรรค|การเมือง)',
            r'(เลือกตั้ง|โหวต|ลงคะแนน)',
            
            # ประเด็นละเอียดอ่อน
            r'(ศาสนา|พระ|วัด|ฆ่า)',
            r'(เพศ|xxx|porn)',
        ]
        
        # Pending approvals
        self.pending_approvals: Dict[str, Dict] = {}
        self.approval_timeout = 60.0  # timeout 60 วินาที
    
    def check_content(self, text: str) -> Tuple[SafetyLevel, Optional[str]]:
        """
        ตรวจสอบความปลอดภัยของเนื้อหา
        Returns: (SafetyLevel, reason)
        """
        text_lower = text.lower()
        
        # เช็คคำห้ามเด็ดขาด
        for pattern in self.blocked_patterns:
            if re.search(pattern, text_lower):
                reason = f"พบเนื้อหาที่ไม่เหมาะสม: {pattern[:20]}..."
                logger.warning(f"🚫 BLOCKED: {text[:50]} | {reason}")
                return SafetyLevel.BLOCKED, reason
        
        # เช็คคำที่ต้องขออนุญาต
        for pattern in self.approval_patterns:
            if re.search(pattern, text_lower):
                reason = f"ต้องขออนุญาต: พบคำว่า '{pattern[:20]}'"
                logger.info(f"⚠️ NEEDS_APPROVAL: {text[:50]} | {reason}")
                return SafetyLevel.NEEDS_APPROVAL, reason
        
        # ปลอดภัย
        return SafetyLevel.SAFE, None
    
    async def request_approval(self, text: str, user: str, source: str) -> str:
        """
        สร้าง approval request และรอการตอบกลับ
        Returns: approval_id
        """
        approval_id = f"approval_{int(asyncio.get_event_loop().time() * 1000)}"
        
        self.pending_approvals[approval_id] = {
            "text": text,
            "user": user,
            "source": source,
            "timestamp": asyncio.get_event_loop().time(),
            "approved": None,  # None = pending, True = approved, False = rejected
            "event": asyncio.Event()
        }
        
        logger.info(f"📋 Approval Request [{approval_id}]: {text[:50]}")
        return approval_id
    
    async def wait_for_approval(self, approval_id: str) -> bool:
        """
        รอการอนุมัติจาก admin
        Returns: True = approved, False = rejected/timeout
        """
        if approval_id not in self.pending_approvals:
            return False
        
        approval = self.pending_approvals[approval_id]
        event = approval["event"]
        
        try:
            # รอ event หรือ timeout
            await asyncio.wait_for(event.wait(), timeout=self.approval_timeout)
            result = approval.get("approved", False)
            logger.info(f"✅ Approval [{approval_id}]: {result}")
            return result
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Approval timeout [{approval_id}]")
            return False
        finally:
            # ลบ approval ออก
            self.pending_approvals.pop(approval_id, None)
    
    def approve_request(self, approval_id: str, approved: bool = True):
        """Admin อนุมัติหรือปฏิเสธ request"""
        if approval_id not in self.pending_approvals:
            logger.warning(f"⚠️ Approval ID not found: {approval_id}")
            return False
        
        approval = self.pending_approvals[approval_id]
        approval["approved"] = approved
        approval["event"].set()
        
        status = "✅ APPROVED" if approved else "❌ REJECTED"
        logger.info(f"{status} [{approval_id}]")
        return True
    
    def get_pending_approvals(self) -> Dict:
        """ดูรายการ approval ที่รออยู่"""
        return {
            aid: {
                "text": data["text"],
                "user": data["user"],
                "source": data["source"]
            }
            for aid, data in self.pending_approvals.items()
        }
    
    def generate_rejection_message(self, reason: str, personality: str = "friendly") -> str:
        """สร้างข้อความปฏิเสธที่เข้ากับบุคลิก"""
        
        templates = {
            "friendly": [
                "อุ๊ปส์! คำถามนี้ฉันตอบไม่ได้นะ 😅",
                "เอ่อ... คำถามนี้ไม่เหมาะนะคะ ลองถามอย่างอื่นมั้ย?",
                "ขอโทษนะคะ คำถามนี้เกินขอบเขตของฉัน~"
            ],
            "cute": [
                "อ้าว! คำถามนี้ตอบไม่ได้น้า >< ถามอย่างอื่นมั้ยคะ?",
                "อุ๊ย! นี่มันเกินความสามารถของฉันแล้วละ~ 😳",
                "หยิก! ถามอย่างนี้ไม่ได้นะคะ ขอโทษนะ 🥺"
            ],
            "tsundere": [
                "ก็บอกแล้วไง! คำถามแบบนี้ฉันไม่ตอบ!",
                "อะไรกัน! นี่มันคำถามที่ไม่เหมาะสมนะ!",
                "ฮึ! ไม่ตอบหรอก ถามอย่างอื่นมาซะ!"
            ]
        }
        
        import random
        messages = templates.get(personality, templates["friendly"])
        return random.choice(messages)


# Singleton instance
_safety_filter = None

def get_safety_filter() -> SafetyFilter:
    """ดึง SafetyFilter instance (singleton)"""
    global _safety_filter
    if _safety_filter is None:
        _safety_filter = SafetyFilter()
    return _safety_filter