"""
Motion Analyzer - วิเคราะห์ response text โดยไม่มี API call
ใช้ regex + keyword matching เท่านั้น
"""

import re
from .motion_commands import MotionCommand, MotionType, MotionIntensity

class MotionAnalyzer:
    """วิเคราะห์ text และสร้าง motion command"""
    
    def __init__(self):
        """ตั้งค่า patterns"""
        self.patterns = {
            MotionType.EXCITED: [
                "ตื่นเต้น", "สนใจ", "ว้าว", "เจ๋ง", "เยี่ยม", "ยิปปี",
                "excited", "wow", "amazing", "great"
            ],
            MotionType.CONFUSED: [
                "งงๆ", "งง", "ไม่เข้าใจ", "หรือ", "อะไรนะ",
                "confused", "what", "huh", "dunno"
            ],
            MotionType.THINKING: [
                "คิดดู", "เอ่อ", "ให้ฉันคิด", "สักครู่",
                "thinking", "hmm", "let me think"
            ],
            MotionType.SAD: [
                "เศร้า", "ไม่ดี", "ผิดหวัง", "โคตร",
                "sad", "unhappy", "bad", "poor"
            ],
            MotionType.ANGRY: [
                "โกรธ", "เกรี้ยว", "แรง", "ชั่วร้าย",
                "angry", "furious", "mad", "evil"
            ],
            MotionType.HAPPY: [
                "ดีใจ", "ยิ้ม", "สนุก", "ฮฮา", "ชอบ",
                "happy", "smile", "fun", "like", "love"
            ],
        }
        
        self.intensity_high_markers = ["!", "!!!", "ว้าว", "เจ๋ง", "เยี่ยม", "amazing"]
    
    def analyze(self, text: str) -> MotionCommand:
        """วิเคราะห์ response text ให้ motion command"""
        try:
            text_lower = text.lower()
            
            # ✅ Detect emotion type
            motion_type = self._detect_type(text_lower)
            
            # ✅ Calculate intensity
            intensity = self._calculate_intensity(text_lower, motion_type)
            
            # ✅ Set duration
            duration = self._get_duration(motion_type)
            
            # ✅ Micro twitch?
            micro_twitch = motion_type != MotionType.THINKING
            
            return MotionCommand(
                motion_type=motion_type,
                intensity=intensity,
                duration=duration,
                micro_twitch_enabled=micro_twitch
            )
        except Exception as e:
            print(f"⚠️ Motion analyzer error (ignored): {e}")
            return MotionCommand(
                motion_type=MotionType.IDLE,
                intensity=MotionIntensity.LOW,
                duration=2.0
            )
    
    def _detect_type(self, text: str) -> MotionType:
        """ตรวจหา emotion type จาก keywords"""
        for motion_type, keywords in self.patterns.items():
            for keyword in keywords:
                if keyword in text:
                    return motion_type
        
        return MotionType.IDLE
    
    def _calculate_intensity(self, text: str, motion_type: MotionType) -> MotionIntensity:
        """คำนวณ intensity ตาม text"""
        exclamation_count = text.count('!') + text.count('?')
        
        if exclamation_count >= 3:
            return MotionIntensity.VERY_HIGH
        elif exclamation_count >= 2:
            return MotionIntensity.HIGH
        elif exclamation_count == 1:
            return MotionIntensity.MEDIUM
        
        if any(marker in text for marker in self.intensity_high_markers):
            return MotionIntensity.HIGH
        
        if motion_type in [MotionType.EXCITED, MotionType.ANGRY]:
            return MotionIntensity.HIGH
        elif motion_type in [MotionType.THINKING, MotionType.CONFUSED]:
            return MotionIntensity.MEDIUM
        elif motion_type == MotionType.SAD:
            return MotionIntensity.LOW
        
        return MotionIntensity.MEDIUM
    
    def _get_duration(self, motion_type: MotionType) -> float:
        """ระยะเวลาการขยับ (วินาที)"""
        duration_map = {
            MotionType.THINKING: 3.0,
            MotionType.EXCITED: 2.5,
            MotionType.CONFUSED: 2.0,
            MotionType.HAPPY: 2.5,
            MotionType.SAD: 3.5,
            MotionType.ANGRY: 2.5,
            MotionType.IDLE: 2.0,
        }
        return duration_map.get(motion_type, 2.5)

# ✅ Global instance
motion_analyzer = MotionAnalyzer()