from __future__ import annotations
from typing import Tuple
from .types import Message

SENSITIVE_KEYWORDS = {
    "เหตุการณ์รุนแรง", "ภัยพิบัติ", "การเหยียด", "การเมืองอ่อนไหว", "สงคราม",
}
INTERNAL_ASK_KEYWORDS = {
    "ทำงานภายใน", "รายละเอียดทางเทคนิค", "ซอร์สโค้ด", "ระบบทำงานอย่างไร", "เบื้องหลัง",
}

class PolicyGuard:
    def __init__(self, allow_mild_profanity: bool = True) -> None:
        self.allow_mild_profanity = allow_mild_profanity

    def check_message_ok(self, msg: Message) -> Tuple[bool, str | None]:
        text = msg.text.lower()
        # ข้ามคำถามภายใน/เทคนิค
        for kw in INTERNAL_ASK_KEYWORDS:
            if kw in text:
                return False, "คำถามเกี่ยวกับการทำงานภายใน ข้ามตามนโยบายความเป็นส่วนตัว"
        # เลี่ยงประเด็นอ่อนไหว
        for kw in SENSITIVE_KEYWORDS:
            if kw in text:
                return False, "ประเด็นอ่อนไหว ข้ามหรือเบนประเด็นตามนโยบายความปลอดภัย"
        return True, None

    def sanitize_output(self, text: str) -> str:
        # อนุญาตคำหยาบพอประมาณ–ที่ชัดเจนมากอาจลดความรุนแรง
        if not self.allow_mild_profanity:
            # ตัวอย่างลดทอน
            text = text.replace("เหี้ย", "เ*ี้ย").replace("สัส", "ส*ส")
        return text