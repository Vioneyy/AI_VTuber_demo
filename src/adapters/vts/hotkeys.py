"""
VTube Studio Hotkeys Manager
จัดการ emotion hotkeys และการวิเคราะห์อารมณ์จากข้อความ
"""
import asyncio
import logging
import random
import re
from typing import Optional, Dict, List
from enum import Enum

logger = logging.getLogger(__name__)


class Emotion(Enum):
    """อารมณ์ที่รองรับ"""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"
    CALM = "calm"
    THINKING = "thinking"


class HotkeyManager:
    """
    จัดการ emotion hotkeys และการวิเคราะห์อารมณ์
    """
    
    def __init__(self, vts_client):
        """
        Args:
            vts_client: instance ของ VTSClient
        """
        self.vts_client = vts_client
        
        # แมป emotion กับ hotkey names (ตรงกับที่ตั้งไว้)
        # ⚠️ คุณมีแค่ 3 hotkeys: thinking (F1), happy (F2), sad (F3)
        self.emotion_hotkeys: Dict[Emotion, str] = {
            Emotion.THINKING: "thinking",   # F1
            Emotion.HAPPY: "happy",         # F2
            Emotion.SAD: "sad",             # F3
            Emotion.NEUTRAL: "thinking",    # ใช้ thinking แทน (ไม่มี neutral)
            # ไม่มี hotkeys เหล่านี้ใน Hiyori_A
            # Emotion.ANGRY: None,
            # Emotion.SURPRISED: None,
            # Emotion.CALM: None,
        }
        
        # คำที่บอกอารมณ์ (เพิ่มคำไทยให้มากขึ้น)
        self.emotion_keywords = {
            Emotion.HAPPY: [
                # ไทย
                "สนุก", "ดีใจ", "ยินดี", "เยี่ยม", "สุดยอด", "เจ๋ง", "วาว", "ชอบ", "รัก",
                "555", "5555", "ฮา", "ฮ่า", "หิหิ", "โอ้โห", "ว้าว", "ดี", "เพราะ",
                "สวย", "น่ารัก", "น่าชื่นชม", "ประทับใจ", "ชื่นใจ",
                # อังกฤษ
                "happy", "joy", "great", "love", "amazing", "awesome", "cool", "nice",
                "haha", "lol", "yay", "wow", "excellent", "wonderful", "fantastic", "good"
            ],
            Emotion.SAD: [
                # ไทย
                "เศร้า", "เสีย", "อาจาร", "แย่", "ผิดหวัง", "น่าเสียดาย", "ร้องไห้", "เสียใจ",
                "เซ็ง", "หดหู่", "ท้อ", "สลด", "เหงา", "โดดเดี่ยว", "ทุกข์", "ลำบาก",
                # อังกฤษ
                "sad", "sorry", "disappointed", "depressed", "unhappy", "cry", "tears",
                "unfortunate", "poor", "pity", "regret", "lonely", "hurt"
            ],
            Emotion.THINKING: [
                # ไทย
                "คิด", "นึก", "สงสัย", "อืม", "เอ่อ", "อะไร", "ไหม", "หรือ", "แล้ว",
                "ทำไม", "อย่างไร", "ยังไง", "เพราะอะไร", "รึเปล่า", "หรือเปล่า",
                "ช่วยอธิบาย", "บอกหน่อย", "แนะนำ",
                # อังกฤษ
                "think", "wonder", "hmm", "uh", "um", "what", "how", "why", "question",
                "maybe", "perhaps", "?", "explain", "tell me", "suggest"
            ],
            Emotion.NEUTRAL: [
                # ใช้เมื่อไม่แน่ใจ
                "โอเค", "ได้", "ครับ", "ค่ะ", "เข้าใจ", "รู้แล้ว",
                "okay", "ok", "alright", "sure", "fine", "understood"
            ]
        }
        
        # Global keyboard hotkeys (F1, F2, F3)
        self.global_hotkeys_enabled = False
        self.keyboard_listener_task: Optional[asyncio.Task] = None
    
    def configure_from_env(self, config):
        """
        ตั้งค่าจาก environment variables
        
        Args:
            config: Config object
        """
        # อ่านการตั้งค่า hotkey names จาก config
        self.emotion_hotkeys[Emotion.NEUTRAL] = getattr(config, "VTS_HK_NEUTRAL", "Neutral")
        self.emotion_hotkeys[Emotion.HAPPY] = getattr(config, "VTS_HK_HAPPY", "Happy")
        self.emotion_hotkeys[Emotion.SAD] = getattr(config, "VTS_HK_SAD", "Sad")
        self.emotion_hotkeys[Emotion.ANGRY] = getattr(config, "VTS_HK_ANGRY", "Angry")
        self.emotion_hotkeys[Emotion.SURPRISED] = getattr(config, "VTS_HK_SURPRISED", "Surprised")
        self.emotion_hotkeys[Emotion.CALM] = getattr(config, "VTS_HK_CALM", "Calm")
        self.emotion_hotkeys[Emotion.THINKING] = getattr(config, "VTS_HK_THINKING", "Thinking")
        
        # Global hotkeys
        self.global_hotkeys_enabled = getattr(config, "ENABLE_GLOBAL_HOTKEYS", False)
        
        logger.info("[Hotkeys] ตั้งค่าจาก .env สำเร็จ")
        for emotion, hotkey_name in self.emotion_hotkeys.items():
            logger.debug(f"  {emotion.value} -> {hotkey_name}")
    
    async def analyze_emotion(self, text: str) -> Emotion:
        """
        วิเคราะห์อารมณ์จากข้อความ
        
        Args:
            text: ข้อความที่จะวิเคราะห์
            
        Returns:
            Emotion ที่ตรวจพบ
        """
        text_lower = text.lower()
        
        # นับคะแนนแต่ละอารมณ์
        scores = {emotion: 0 for emotion in Emotion}
        
        for emotion, keywords in self.emotion_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    scores[emotion] += 1
        
        # หาอารมณ์ที่มีคะแนนสูงสุด
        max_score = max(scores.values())
        
        if max_score > 0:
            # มีอารมณ์ที่เด่นชัด
            top_emotions = [e for e, s in scores.items() if s == max_score]
            return random.choice(top_emotions)
        else:
            # ไม่มีคำที่บอกอารมณ์ชัดเจน
            # ใช้ heuristics อื่น
            
            # มีเครื่องหมายคำถาม -> กำลังคิด
            if "?" in text or "ไหม" in text_lower:
                return Emotion.THINKING
            
            # ข้อความยาว -> กำลังคิด/เป็นกลาง
            if len(text) > 100:
                return Emotion.NEUTRAL if random.random() < 0.7 else Emotion.THINKING
            
            # ข้อความสั้นๆ -> เป็นกลาง
            return Emotion.NEUTRAL
    
    async def trigger_emotion(
        self, 
        emotion: Optional[Emotion] = None, 
        text: str = "",
        auto_analyze: bool = True,
        probability: float = 0.5
    ) -> bool:
        """
        กด emotion hotkey
        
        Args:
            emotion: อารมณ์ที่ต้องการ (ถ้าไม่ระบุจะวิเคราะห์จาก text)
            text: ข้อความสำหรับวิเคราะห์อารมณ์
            auto_analyze: วิเคราะห์อารมณ์อัตโนมัติจาก text
            probability: โอกาสที่จะกด hotkey (0-1)
            
        Returns:
            True ถ้ากด hotkey สำเร็จ
        """
        # สุ่มว่าจะกดหรือไม่
        if random.random() > probability:
            logger.debug("[Hotkeys] สุ่มไม่กด hotkey ครั้งนี้")
            return False
        
        # วิเคราะห์อารมณ์ถ้าไม่ได้ระบุ
        if emotion is None and auto_analyze and text:
            emotion = await self.analyze_emotion(text)
        
        # ถ้ายังไม่มี emotion ใช้ neutral
        if emotion is None:
            emotion = Emotion.NEUTRAL
        
        # ดึง hotkey name
        hotkey_name = self.emotion_hotkeys.get(emotion)
        
        if not hotkey_name:
            logger.warning(f"[Hotkeys] ไม่พบ hotkey สำหรับ {emotion.value}")
            return False
        
        # กด hotkey
        try:
            await self.vts_client.trigger_hotkey(hotkey_name)
            logger.info(f"🎭 [Hotkeys] ใช้อารมณ์: {emotion.value} ({hotkey_name})")
            return True
        except Exception as e:
            logger.error(f"[Hotkeys] Error triggering {emotion.value}: {e}")
            return False
    
    async def trigger_random_emotion(self, exclude: List[Emotion] = None) -> bool:
        """
        กด emotion hotkey แบบสุ่ม
        
        Args:
            exclude: รายการอารมณ์ที่ไม่ต้องการสุ่ม
            
        Returns:
            True ถ้ากด hotkey สำเร็จ
        """
        emotions = list(Emotion)
        
        if exclude:
            emotions = [e for e in emotions if e not in exclude]
        
        if not emotions:
            return False
        
        emotion = random.choice(emotions)
        return await self.trigger_emotion(emotion, probability=1.0)
    
    async def start_emotion_keyboard_listener(self):
        """
        เริ่ม listener สำหรับ global hotkeys (F1, F2, F3)
        สำหรับทดสอบด้วยมือ
        """
        if not self.global_hotkeys_enabled:
            logger.info("[Hotkeys] Global hotkeys ถูกปิดการใช้งาน")
            return
        
        try:
            import keyboard
            
            logger.info("[Hotkeys] 🎹 เริ่ม emotion keyboard listener")
            logger.info("  F1 = Neutral")
            logger.info("  F2 = Happy")
            logger.info("  F3 = Sad")
            
            # ผูก hotkeys
            keyboard.add_hotkey('f1', lambda: asyncio.create_task(
                self.trigger_emotion(Emotion.NEUTRAL, probability=1.0)
            ))
            keyboard.add_hotkey('f2', lambda: asyncio.create_task(
                self.trigger_emotion(Emotion.HAPPY, probability=1.0)
            ))
            keyboard.add_hotkey('f3', lambda: asyncio.create_task(
                self.trigger_emotion(Emotion.SAD, probability=1.0)
            ))
            
        except ImportError:
            logger.warning("[Hotkeys] ⚠️ ไม่พบ 'keyboard' library - ข้าม global hotkeys")
            logger.info("  ติดตั้งด้วย: pip install keyboard")
        except Exception as e:
            logger.error(f"[Hotkeys] Error setting up keyboard listener: {e}")
    
    def stop_emotion_keyboard_listener(self):
        """หยุด keyboard listener"""
        try:
            import keyboard
            keyboard.unhook_all()
            logger.info("[Hotkeys] 🛑 หยุด keyboard listener")
        except:
            pass
    
    async def safe_motion_mode(self, interval: float = 6.0):
        """
        โหมด Safe Motion - กด hotkey สุ่มเป็นระยะ
        แทนการ inject parameters (เสถียรกว่า)
        
        Args:
            interval: ระยะเวลาระหว่างการกด hotkey (วินาที)
        """
        logger.info(f"[Hotkeys] 🔒 เริ่ม Safe Motion Mode (interval={interval}s)")
        
        try:
            while True:
                # สุ่มกด hotkey
                await self.trigger_random_emotion(exclude=[Emotion.ANGRY])
                
                # รอ
                await asyncio.sleep(interval + random.uniform(-1, 1))
                
        except asyncio.CancelledError:
            logger.info("[Hotkeys] Safe Motion Mode ถูกยกเลิก")
        except Exception as e:
            logger.error(f"[Hotkeys] Safe Motion Mode error: {e}")


# ฟังก์ชันทดสอบ
async def test_hotkey_manager():
    """ทดสอบ HotkeyManager"""
    from .vts_client import VTSClient
    
    # สร้าง VTS client
    vts = VTSClient()
    
    if not await vts.connect():
        print("❌ ไม่สามารถเชื่อมต่อ VTS")
        return
    
    # สร้าง HotkeyManager
    hotkeys = HotkeyManager(vts)
    
    # ทดสอบวิเคราะห์อารมณ์
    test_texts = [
        "สวัสดีค่ะ ยินดีที่ได้รู้จักนะคะ",  # -> Happy
        "เศร้ามากเลย ทำไมเป็นแบบนี้",  # -> Sad
        "อืม... ให้คิดดูก่อนนะ",  # -> Thinking
        "โกรธมากเลย! ทำไมทำแบบนี้",  # -> Angry
        "ว้าว! เจ๋งมากเลย!",  # -> Surprised/Happy
    ]
    
    print("\n📝 ทดสอบการวิเคราะห์อารมณ์:")
    print("="*60)
    
    for text in test_texts:
        emotion = await hotkeys.analyze_emotion(text)
        print(f"{text[:40]:<40} -> {emotion.value}")
    
    print("\n🎭 ทดสอบกด hotkeys:")
    print("="*60)
    
    # ทดสอบกด hotkey แต่ละอัน
    for emotion in [Emotion.NEUTRAL, Emotion.HAPPY, Emotion.SAD]:
        await hotkeys.trigger_emotion(emotion, probability=1.0)
        await asyncio.sleep(2)
    
    # ทดสอบวิเคราะห์และกดอัตโนมัติ
    print("\n🤖 ทดสอบ auto-analyze:")
    for text in test_texts[:3]:
        print(f"  Text: {text[:40]}")
        await hotkeys.trigger_emotion(text=text, auto_analyze=True, probability=1.0)
        await asyncio.sleep(3)
    
    await vts.disconnect()
    print("\n✅ ทดสอบเสร็จสิ้น")


if __name__ == "__main__":
    asyncio.run(test_hotkey_manager())