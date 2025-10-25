from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

PERSONA_FILE = Path(__file__).with_name("persona.json")

class Personality:
    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = data

    @classmethod
    def load(cls) -> "Personality":
        if PERSONA_FILE.exists():
            data = json.loads(PERSONA_FILE.read_text(encoding="utf-8"))
        else:
            data = {
                "name": "AI VTuber",
                "style": "เป็นกันเอง ภาษาง่าย อนุญาตคำหยาบพอประมาณ",
                "boundaries": [
                    "ไม่เล่นมุกเหตุการณ์รุนแรงหรือประเด็นอ่อนไหว",
                    "ไม่เปิดเผยรายละเอียดเทคนิค/การทำงานภายใน",
                ],
                "emotion_map": {
                    "neutral": {"expression": "Neutral", "intensity": 0.5},
                    "happy": {"expression": "Smile", "intensity": 0.8},
                    "sad": {"expression": "Sad", "intensity": 0.6},
                    "angry": {"expression": "Angry", "intensity": 0.7},
                    "surprised": {"expression": "Surprised", "intensity": 0.9},
                    "calm": {"expression": "Calm", "intensity": 0.6},
                },
            }
        return cls(data)

    def get_emotion_config(self, emotion: str) -> Dict[str, Any]:
        return self.data.get("emotion_map", {}).get(emotion, {"expression": "Neutral", "intensity": 0.5})