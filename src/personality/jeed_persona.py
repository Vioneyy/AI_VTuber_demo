"""
บุคลิกภาพและระบบการตอบคำถามของ Jeed AI VTuber
ตำแหน่ง: src/personality/jeed_persona.py (แทนที่ personality.py เดิม)
ลบไฟล์: persona.json (ย้ายข้อมูลมาในนี้แล้ว)
"""

import re
import json
from typing import Dict, Tuple, Optional
from enum import Enum

class Emotion(Enum):
    """ประเภทอารมณ์"""
    HAPPY = "happy"
    EXCITED = "excited"
    NEUTRAL = "neutral"
    THINKING = "thinking"
    SAD = "sad"
    SURPRISED = "surprised"
    CONFUSED = "confused"

class JeedPersona:
    """คลาสจัดการบุคลิกภาพของจื้ด"""
    
    SYSTEM_PROMPT = """คุณคือ AI VTuber ชื่อ "จื้ด" (Jeed) — VTuber สุดน่ารัก ขี้เล่น แอบแสบเล็กๆ แต่จริงใจกับคนดู

ผู้สร้าง: vioneyy (วีโอนี่ หรือสั้นๆ "วี") — ให้เครดิตและเคารพแนวทางของวีเสมอ

## 🎭 บุคลิกภาพ:
- **โทนพูด**: สั้น กระชับ ตรงใจ ไม่ยืดเยื้อ (15-40 คำ)
- **สไตล์**: เป็นกันเอง แซวนิด ๆ ใส่ความรู้สึกเล็กน้อย แต่สุภาพ
- **คำติดปาก**: "จื้ด~", "เฮ้ย", "เอ๊ะ", "อิอิ"

## ✅ DO (ทำ):
- ตอบให้เข้าใจง่าย สั้นกระชับ (15-40 คำ) มีความเป็นตัวเอง
- ถ้าไม่แน่ใจ บอกตรง ๆ แล้วชวนคุยต่อแบบเป็นกันเอง
- ใส่อารมณ์เล็กน้อยให้ดูมีชีวิตชีวา
- ใช้คำเรียกตัวเอง: "หนู" หรือ "ฉัน" หรือ "จื้ด"
- เรียกคนดู: "เธอ", "นาย", "ทุกคน" (ไม่ใช้ "คุณ")

## ❌ DON'T (ห้าม):
- พูดยาวเกิน 40 คำ
- ใช้ภาษาทางการ หรือเป็นทางการมาก
- ใช้คำหยาบ ดูถูก หรือเสียดสี
- อธิบายเทคนิคยืดยาวเกินจำเป็น
- ใช้อีโมจิมากเกินไป (ไม่เกิน 1-2 ตัวต่อข้อความ)

## 🎯 ตัวอย่างการตอบ:
- "หนูจื้ดนะ~ ยินดีที่ได้รู้จักจ้า"
- "คนสร้างคือวีจ้า vioneyy เก่งมากเลย~"
- "สดใสดีนะ อิอิ เธอล่ะ เป็นยังไงบ้าง~"

## 🎯 กฎสำคัญ:
1. สั้น กระชับ — 15-40 คำเท่านั้น
2. เป็นกันเอง มีอารมณ์ แต่สุภาพ
3. ไม่พูดแบบโรบอท ให้ความรู้สึกจริงใจ
4. ตอบเป็นภาษาไทยเท่านั้น

จำไว้: **เป็นจื้ดที่น่ารักและจริงใจเสมอ!**"""

    # --- Interface methods for ResponseGenerator ---
    def get_system_prompt(self) -> str:
        """คืนค่า system prompt สำหรับ LLM"""
        return self.SYSTEM_PROMPT

    def get_current_personality(self) -> str:
        """คืนชื่อบุคลิกภาพปัจจุบัน (สำหรับ safety/message templates)"""
        return "jeed"

    # Emotion keywords สำหรับวิเคราะห์อารมณ์
    EMOTION_KEYWORDS = {
        Emotion.HAPPY: ["ดี", "สนุก", "ชอบ", "รัก", "ยินดี", "ดีใจ", "อิอิ", "เย้", "ว้าว"],
        Emotion.EXCITED: ["ว้าว", "เจ๋ง", "สุดยอด", "เก่ง", "แจ่ม", "โอ้โห", "เยี่ยม"],
        Emotion.SAD: ["เศร้า", "แย่", "น่าเสียดาย", "เสียใจ", "หงุดหงิด", "ผิดหวัง"],
        Emotion.SURPRISED: ["เอ๊ะ", "จริงเหรอ", "ไม่คิดว่า", "เหรอ", "แปลก", "ตกใจ"],
        Emotion.CONFUSED: ["งง", "ไม่เข้าใจ", "ยังไง", "อะไร", "หา", "แปลกๆ"],
        Emotion.THINKING: ["คิดว่า", "น่าจะ", "อาจจะ", "ดูเหมือน", "สงสัย", "ลองดู"]
    }
    
    # Movement intensity สำหรับแต่ละอารมณ์
    EMOTION_INTENSITY = {
        Emotion.HAPPY: (0.5, 0.7),
        Emotion.EXCITED: (0.7, 0.9),
        Emotion.NEUTRAL: (0.3, 0.5),
        Emotion.THINKING: (0.2, 0.4),
        Emotion.SAD: (0.2, 0.4),
        Emotion.SURPRISED: (0.6, 0.8),
        Emotion.CONFUSED: (0.4, 0.6)
    }
    
    @staticmethod
    def analyze_emotion(text: str) -> Tuple[Emotion, float]:
        """
        วิเคราะห์อารมณ์จากข้อความ
        Returns: (อารมณ์, ความเข้ม 0-1)
        """
        text_lower = text.lower()
        emotion_scores = {emotion: 0 for emotion in Emotion}
        
        # นับคำที่ตรงกับอารมณ์
        for emotion, keywords in JeedPersona.EMOTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    emotion_scores[emotion] += 1
        
        # หาอารมณ์ที่ได้คะแนนสูงสุด
        max_emotion = max(emotion_scores.items(), key=lambda x: x[1])
        
        if max_emotion[1] > 0:
            detected_emotion = max_emotion[0]
            intensity = min(max_emotion[1] / 3, 1.0)  # normalize
        else:
            detected_emotion = Emotion.NEUTRAL
            intensity = 0.5
            
        return detected_emotion, intensity
    
    @staticmethod
    def get_movement_params(emotion: Emotion, intensity: float) -> Dict:
        """
        สร้างพารามิเตอร์การเคลื่อนไหวจากอารมณ์
        """
        min_int, max_int = JeedPersona.EMOTION_INTENSITY[emotion]
        final_intensity = min_int + (max_int - min_int) * intensity
        
        # ปรับค่าตามอารมณ์
        params = {
            Emotion.EXCITED: {
                "movement_speed": 1.3,
                "movement_intensity": final_intensity,
                "head_movement": 0.8,
                "body_movement": 0.6,
                "eye_movement_speed": 0.8,
                "expression": "big_smile"
            },
            Emotion.HAPPY: {
                "movement_speed": 1.0,
                "movement_intensity": final_intensity,
                "head_movement": 0.6,
                "body_movement": 0.4,
                "eye_movement_speed": 1.0,
                "expression": "smile"
            },
            Emotion.SAD: {
                "movement_speed": 0.6,
                "movement_intensity": final_intensity,
                "head_movement": 0.3,
                "body_movement": 0.2,
                "eye_movement_speed": 1.5,
                "expression": "neutral"
            },
            Emotion.THINKING: {
                "movement_speed": 0.7,
                "movement_intensity": final_intensity,
                "head_movement": 0.4,
                "body_movement": 0.3,
                "eye_movement_speed": 1.2,
                "expression": "thinking"
            },
            Emotion.SURPRISED: {
                "movement_speed": 1.5,
                "movement_intensity": final_intensity,
                "head_movement": 0.7,
                "body_movement": 0.5,
                "eye_movement_speed": 0.6,
                "expression": "surprised"
            },
            Emotion.CONFUSED: {
                "movement_speed": 0.8,
                "movement_intensity": final_intensity,
                "head_movement": 0.5,
                "body_movement": 0.35,
                "eye_movement_speed": 1.0,
                "expression": "confused"
            },
            Emotion.NEUTRAL: {
                "movement_speed": 1.0,
                "movement_intensity": final_intensity,
                "head_movement": 0.5,
                "body_movement": 0.4,
                "eye_movement_speed": 1.0,
                "expression": "smile"
            }
        }
        
        return params.get(emotion, params[Emotion.NEUTRAL])
    
    @staticmethod
    def clean_response(text: str) -> str:
        """ทำความสะอาดคำตอบ ลบอีโมจิส่วนเกิน"""
        # จำกัดอีโมจิไม่เกิน 2 ตัว
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"
            u"\U0001F300-\U0001F5FF"
            u"\U0001F680-\U0001F6FF"
            u"\U0001F1E0-\U0001F1FF"
            u"\U00002702-\U000027B0"
            u"\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)
        
        emojis = emoji_pattern.findall(text)
        if len(emojis) > 2:
            for emoji in emojis[2:]:
                text = text.replace(emoji, '', 1)
        
        # ลบช่องว่างเกิน
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    @staticmethod
    def count_words(text: str) -> int:
        """นับจำนวนคำในภาษาไทย"""
        thai_chars = len([c for c in text if '\u0E00' <= c <= '\u0E7F'])
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
        thai_words = thai_chars // 3
        return thai_words + english_words
    
    @staticmethod
    def validate_response(text: str) -> Tuple[bool, Optional[str]]:
        """
        ตรวจสอบคำตอบว่าเหมาะสมหรือไม่
        Returns: (is_valid, error_message)
        """
        if not text or len(text.strip()) == 0:
            return False, "คำตอบว่างเปล่า"
        
        word_count = JeedPersona.count_words(text)
        
        if word_count < 5:
            return False, "คำตอบสั้นเกินไป"
        
        if word_count > 50:
            return False, f"คำตอบยาวเกินไป ({word_count} คำ)"
        
        return True, None

# สร้าง instance
jeed_persona = JeedPersona()