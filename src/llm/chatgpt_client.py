from __future__ import annotations
from typing import Dict, Any
from . import __init__ as _llm_pkg  # noqa: F401
from core.types import Response, Emotion
from core.config import get_settings

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

class ChatGPTClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = None
        if OpenAI and self.settings.OPENAI_API_KEY:
            self.client = OpenAI(api_key=self.settings.OPENAI_API_KEY)

    def _pick_emotion(self, text: str) -> Emotion:
        t = text.lower()
        if any(k in t for k in ("ดีใจ", "เยี่ยม", "สุดยอด", "ขอบคุณ")):
            return Emotion.HAPPY
        if any(k in t for k in ("เสียใจ", "เศร้า", "แย่")):
            return Emotion.SAD
        if any(k in t for k in ("โกรธ", "โมโห")):
            return Emotion.ANGRY
        if any(k in t for k in ("ว้าว", "ตกใจ")):
            return Emotion.SURPRISED
        return Emotion.NEUTRAL

    def generate_reply(self, user_text: str, system_prompt: str, persona: Dict[str, Any] | None = None) -> Response:
        # หากไม่มี client หรือไม่ได้ตั้งค่า ให้ตอบแบบสั้นด้วยโทนมาตรฐานเป็นสคาฟโฟลด์
        if not self.client or not self.settings.LLM_MODEL:
            txt = f"รับทราบ: {user_text.strip()}"
            return Response(text=txt, emotion=self._pick_emotion(txt), gestures={"hint": "scaffold"})

        # ใช้รูปแบบข้อความเฉพาะที่เหมาะกับงานนี้
        sys_content = system_prompt
        # แนบ persona หากมี เพื่อปรับบริบทการตอบโดยไม่บังคับ
        try:
            if persona:
                style = str(persona.get("style", "")).strip()
                boundaries = persona.get("boundaries", []) or []
                if style:
                    sys_content += f"\nสไตล์การพูด: {style}"
                if boundaries:
                    try:
                        btxt = "; ".join([str(b) for b in boundaries])
                        sys_content += f"\nข้อจำกัด: {btxt}"
                    except Exception:
                        pass
        except Exception:
            # ไม่ให้ persona ทำให้รันพัง หากโครงสร้างไม่ตรง ให้ข้ามไป
            pass

        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_text},
        ]

        # หมายเหตุ: ไม่เปิดเผยชื่อโมเดลภายในโลจิกการใช้งานระดับผู้ใช้
        comp = self.client.chat.completions.create(
            model=self.settings.LLM_MODEL,
            messages=messages,
            temperature=float(getattr(self.settings, "LLM_TEMPERATURE", 0.3)),
            max_tokens=int(getattr(self.settings, "LLM_MAX_TOKENS", 128)),
        )
        txt = comp.choices[0].message.content if comp and comp.choices else ""
        return Response(text=txt, emotion=self._pick_emotion(txt), gestures={"from": "llm"})