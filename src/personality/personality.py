# src/personality/personality.py
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# import types defined earlier in src/core/types.py
try:
    from core.types import IncomingMessage, Response, Emotion, MessageSource
except Exception:
    # Fallback minimal stubs (in case core.types ยังไม่ถูกแก้หรือ import ผิด)
    @dataclass
    class IncomingMessage:
        text: str
        source: Any = None
        author: Optional[str] = None
        timestamp: Optional[float] = None
        is_question: bool = False
        priority: int = 0
        meta: Optional[Dict[str, Any]] = None

    class Emotion:
        NEUTRAL = "neutral"
        HAPPY = "happy"
        SAD = "sad"
        ANGRY = "angry"
        SURPRISED = "surprised"
        SLEEPY = "sleepy"
        CONFUSED = "confused"
        EXCITED = "excited"

    @dataclass
    class Response:
        text: str
        emotion: str = Emotion.NEUTRAL
        gestures: Optional[Dict[str, Any]] = None
        meta: Optional[Dict[str, Any]] = None

logger = logging.getLogger("PersonalityManager")
if not logger.handlers:
    # basic logging configuration if not setup by main app
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


class PersonalityManager:
    """
    จัดการ 'บุคลิก' ของ VTuber — โหลดบุคลิกจากไฟล์/พาราม หรือใช้ default
    Interface ที่คาดหวังจาก main.py:
      - PersonalityManager()  # สร้าง
      - set_personality(name)
      - get_personality(name)
      - handle_message(incoming: IncomingMessage) -> Response
      - generate_vts_commands(response: Response) -> List[Dict]   # (optional helper)
    """

    def __init__(self, personalities: Optional[Dict[str, Dict]] = None, default: str = "default"):
        # รูปแบบ personalities:
        # {
        #   "default": {
        #       "display_name": "Default",
        #       "mood_map": {"happy": ["ขอบคุณ","ดีใจ"], ...},
        #       "default_emotion": "neutral",
        #       "gesture_map": {"happy": {"smile": 1.0}},
        #       "meta": {...}
        #    }, ...
        # }
        self.personalities: Dict[str, Dict] = personalities or {}
        self.current: str = default
        if not self.personalities:
            self._load_builtin_personalities()
        if self.current not in self.personalities:
            self.current = next(iter(self.personalities.keys()))
        logger.info(f"PersonalityManager initialized. current='{self.current}'")

    def _load_builtin_personalities(self):
        # บุคลิกพื้นฐาน — ปรับได้ตามต้องการ
        self.personalities = {
            "default": {
                "display_name": "Default",
                "default_emotion": Emotion.NEUTRAL,
                "mood_map": {
                    "happy": ["ขอบคุณ", "เยี่ยม", "ดีใจ", "สุดยอด", "love", "nice"],
                    "sad": ["เสียใจ", "เศร้า", "เหงา"],
                    "angry": ["โกรธ", "แค้น", "โมโห"],
                    "surprised": ["ว้าว", "อะไรนะ", "จริงหรอ", "what"],
                },
                "gesture_map": {
                    "happy": {"smile": 1.0, "eyes": "open"},
                    "sad": {"head_down": 0.8},
                    "angry": {"brow_down": 1.0},
                    "surprised": {"eyes_wide": 1.0},
                    "neutral": {"idle": 1.0},
                },
                "meta": {}
            },
            "gentle": {
                "display_name": "Gentle",
                "default_emotion": Emotion.NEUTRAL,
                "mood_map": {
                    "happy": ["ขอบคุณ", "ดีใจ", "น่ารัก"],
                    "sad": ["เสียใจ", "เศร้า"],
                    "surprised": ["ว้าว", "โอ้"],
                },
                "gesture_map": {
                    "happy": {"smile": 0.8, "hand_wave": 0.3},
                    "neutral": {"idle": 1.0}
                },
                "meta": {"tone": "soft"}
            }
        }

    def load_personalities_from_file(self, path: str):
        """
        โหลด personalities จากไฟล์ JSON (รูปแบบเดียวกับ self.personalities)
        """
        p = Path(path)
        if not p.exists():
            logger.warning("Personality file not found: %s", path)
            return False
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.personalities.update(data)
                logger.info("Loaded personalities from %s", path)
                return True
            else:
                logger.error("Personality file must contain a dict at top-level.")
                return False
        except Exception as e:
            logger.exception("Failed to load personalities: %s", e)
            return False

    def list_personalities(self) -> List[str]:
        return list(self.personalities.keys())

    def get_personality(self, name: Optional[str] = None) -> Dict:
        name = name or self.current
        return self.personalities.get(name, {})

    def set_personality(self, name: str) -> bool:
        if name in self.personalities:
            self.current = name
            logger.info("Personality changed to '%s'", name)
            return True
        logger.error("Personality '%s' not found", name)
        return False

    def _detect_emotion_from_text(self, text: str, mood_map: Dict[str, List[str]]) -> str:
        # heuristic: ค้นหาคีย์เวิร์ดใน mood_map
        t = (text or "").lower()
        for mood, keywords in mood_map.items():
            for kw in keywords:
                if kw.lower() in t:
                    return mood
        # punctuation/word heuristics
        if "?" in text:
            return "surprised"
        return mood_map and "neutral" or "neutral"

    def handle_message(self, incoming: IncomingMessage) -> Response:
        """
        รับ IncomingMessage แล้วคืน Response (text, emotion, gestures)
        - ใช้ heuristic ง่าย ๆ เพื่อให้โมเดลขยับ/แสดงอารมณ์
        - main.py สามารถเอา Response นี้แปลงเป็นคำสั่ง VTS ต่อได้
        """
        if incoming is None:
            logger.warning("handle_message called with None")
            return Response(text="", emotion=Emotion.NEUTRAL, gestures={})

        personality = self.get_personality()
        mood_map = personality.get("mood_map", {})
        default_emotion = personality.get("default_emotion", Emotion.NEUTRAL)
        gesture_map = personality.get("gesture_map", {})

        text = incoming.text or ""
        # ตรวจ is_question flag ด้วย
        is_q = getattr(incoming, "is_question", False)
        if not is_q and ("?" in text):
            is_q = True

        mood = self._detect_emotion_from_text(text, mood_map)
        if not mood:
            mood = default_emotion

        # ตอบกลับแบบพื้นฐาน — main.py อาจ override หรือส่งข้อความผ่านโมดูล NLP/AI จริง ๆ
        reply_text = self._build_reply_text(text, mood, is_q, personality)

        gestures = gesture_map.get(mood, gesture_map.get("neutral", {}))

        resp = Response(
            text=reply_text,
            emotion=getattr(Emotion, mood.upper(), mood) if hasattr(Emotion, mood.upper()) else mood,
            gestures=gestures,
            meta={"source": getattr(incoming, "source", None), "personality": self.current}
        )
        logger.debug("handle_message -> %s", resp)
        return resp

    def _build_reply_text(self, incoming_text: str, mood: str, is_question: bool, personality: Dict) -> str:
        # แบบง่าย: ถ้าเป็นคำถาม ตอบกลับสั้น ๆ ถ้าไม่ใช่ ให้ยืนยัน/ขอบคุณ ฯลฯ
        if is_question:
            # ถ้าโค้ดหลักมี AI/LLM ให้เอา incoming_text ไปประมวลผลแทน
            return "ขอตอบแป๊บนะ… (ยังไม่มีโมดูลตอบคำถาม)"  # placeholder
        if mood == "happy":
            return "ขอบคุณมากจ้า! ❤️"
        if mood == "sad":
            return "อุ๊ย เสียใจด้วยนะ…"
        if mood == "angry":
            return "อืม… เข้าใจแล้ว"
        if mood == "surprised":
            return "ว้าว!! จริงหรอ?"
        return "รับทราบแล้วครับ/ค่ะ"

    def generate_vts_commands(self, response: Response) -> List[Dict[str, Any]]:
        """
        แปลง Response เป็น list ของคำสั่งที่จะส่งไปยัง VTube Studio API
        (รูปแบบนี้เป็นเพียงตัวอย่าง — ให้แก้ให้ตรงกับ API ของคุณ)
        ตัวอย่างคำสั่ง:
            {"type":"SetExpression","name":"smile","value":0.8}
            {"type":"SetParameter","name":"MouthOpen","value":0.5}
            {"type":"LoadCustomImage","layer":"face","path":"C:/..."}
        """
        cmds: List[Dict[str, Any]] = []
        emotion = getattr(response, "emotion", None)
        gestures = getattr(response, "gestures", {}) or {}

        # แปลง emotion -> expression parameter (ตัวอย่าง)
        if emotion:
            # ถ้า emotion เป็น Enum (จาก core.types.Emotion) ให้ใช้ .value หรือ str()
            em_val = getattr(emotion, "value", None) or str(emotion)
            cmds.append({"type": "SetExpression", "name": "emotion", "value": em_val})

        # แปลง gestures -> parameter updates
        for gname, gval in gestures.items():
            # ถ้า gval เป็น dict ซับซ้อน ให้ flatten ตามความเหมาะสม
            if isinstance(gval, dict):
                # ใส่แต่ชื่อ gesture เป็นตัวอย่าง
                cmds.append({"type": "Gesture", "name": gname, "value": gval})
            else:
                cmds.append({"type": "SetParameter", "name": gname, "value": gval})

        # placeholder: ให้ main app แปลคำสั่งเหล่านี้เป็น API calls จริง ๆ
        logger.debug("Generated VTS commands: %s", cmds)
        return cmds


# ปรับให้โหลด persona จาก persona.py เป็นค่าเริ่มต้น และรองรับ JSON ถ้าระบุ path
@dataclass
class Personality:
    data: Dict[str, Any]

    @staticmethod
    def load(persona_name: Optional[str] = "miko", path: Optional[str] = None) -> "Personality":
        """
        โหลดข้อมูล persona ในรูปแบบ dict เพื่อความเข้ากันได้กับโค้ดเดิม
        ลำดับความสำคัญ:
        1) ถ้าให้ path เป็นไฟล์ .json และมีอยู่จริง จะอ่านจาก JSON นั้น
        2) ไม่เช่นนั้น จะโหลดจากโมดูล persona.py โดยใช้ชื่อ persona ที่ระบุ (default: "miko")
        """
        payload: Dict[str, Any] = {}

        # 1) explicit JSON path
        if path:
            try:
                p = Path(path)
                if p.exists() and p.suffix.lower() == ".json":
                    payload = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                payload = {}

        # 2) fallback to persona.py
        if not payload:
            try:
                # import แบบ lazy เพื่อหลีกเลี่ยงปัญหาแพ็กเกจระหว่างรันแบบสคริปต์
                from .persona import get_persona, get_available_personas  # type: ignore
            except Exception:
                try:
                    # เผื่อกรณีถูกเรียกโดยอิมพอร์ตแบบ absolute
                    from personality.persona import get_persona, get_available_personas  # type: ignore
                except Exception:
                    get_persona = None  # type: ignore
                    get_available_personas = lambda: []  # type: ignore

            try:
                style_text = (get_persona(persona_name or "miko") if get_persona else "")
                payload = {
                    "name": (persona_name or "miko"),
                    "style": style_text,
                    "available": (get_available_personas() if callable(get_available_personas) else []),
                }
            except Exception:
                payload = {"name": (persona_name or "miko"), "style": ""}

        return Personality(data=payload)

class PersonalitySystem:
    """
    PersonalitySystem แบบบาง เพื่อให้เข้ากับ Orchestrator/ResponseGenerator
    - จัดเก็บชื่อ persona ปัจจุบัน
    - คืน system prompt ผ่าน persona.get_persona
    - ใช้ได้กับ SafetyFilter ที่ต้องการ personality ชื่อสั้น ๆ
    """

    def __init__(self, persona_name: str = "miko"):
        self._persona_name = persona_name
        try:
            # มีไว้เผื่ออนาคตจะใช้ PersonalityManager สำหรับ mapping อารมณ์/ท่าทาง
            self._manager = PersonalityManager()
        except Exception:
            self._manager = None

    def get_system_prompt(self) -> str:
        """คืน system prompt ตาม persona ปัจจุบัน"""
        try:
            from .persona import get_persona  # type: ignore
        except Exception:
            from src.personality.persona import get_persona  # type: ignore
        return get_persona(self._persona_name)

    def get_current_personality(self) -> str:
        """คืนชื่อ personality/persona ปัจจุบัน (string)"""
        return self._persona_name

    def set_persona(self, persona_name: str) -> None:
        """เปลี่ยน persona"""
        self._persona_name = persona_name


__all__ = ["PersonalityManager", "PersonalitySystem", "Personality"]
