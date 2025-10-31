"""
vts_integration.py - Complete VTuber System Integration
รวมทุกอย่างเข้าด้วยกัน: Motion + Lip Sync + Emotion
"""

import asyncio
import logging
import random
from typing import Optional, Dict, Any
from .motion_controller import VTSMotionController, EmotionType
from .lipsync_system import LipSyncController, SimpleLipSyncFromTTS

logger = logging.getLogger(__name__)


class CompleteVTuberSystem:
    """ระบบ VTuber ที่สมบูรณ์"""
    
    def __init__(
        self,
        vts_host: str = "localhost",
        vts_port: int = 8001,
        enable_lipsync: bool = True,
        enable_auto_emotion: bool = False
    ):
        self.motion = VTSMotionController(vts_host, vts_port)
        self.lipsync = LipSyncController(self.motion)
        self.simple_lipsync = SimpleLipSyncFromTTS(self.motion)
        
        self.enable_lipsync = enable_lipsync
        self.enable_auto_emotion = enable_auto_emotion
        
        self.is_running = False
        self.is_speaking = False
        
        # Watchdog
        self.last_activity = 0.0
        self.watchdog_timeout = 5.0
        self.watchdog_task: Optional[asyncio.Task] = None
        
        # Stats
        self.stats = {
            "speech_count": 0,
            "emotion_changes": 0,
            "restarts": 0,
            "errors": 0
        }
    
    async def initialize(self) -> bool:
        """เริ่มต้นระบบ"""
        logger.info("=" * 60)
        logger.info("🚀 เริ่มต้น Complete VTuber System")
        logger.info("=" * 60)
        
        try:
            # เริ่ม Motion Controller
            if not await self.motion.start():
                logger.error("❌ ไม่สามารถเริ่ม Motion Controller ได้")
                return False
            
            # เริ่ม Lip Sync
            if self.enable_lipsync:
                await self.lipsync.start(mode="text")
            
            # เริ่ม Watchdog
            self.watchdog_task = asyncio.create_task(self.system_watchdog())
            
            self.is_running = True
            self.last_activity = asyncio.get_event_loop().time()
            
            logger.info("=" * 60)
            logger.info("✅ ระบบพร้อมใช้งาน!")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาด: {e}")
            self.stats["errors"] += 1
            return False
    
    async def system_watchdog(self):
        """เฝ้าระวังระบบ"""
        while self.is_running:
            try:
                await asyncio.sleep(1.0)
                
                current_time = asyncio.get_event_loop().time()
                time_since_activity = current_time - self.last_activity
                
                if time_since_activity > self.watchdog_timeout:
                    logger.warning(f"⚠️ System freeze! ({time_since_activity:.1f}s)")
                    await self.emergency_restart()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Watchdog error: {e}")
    
    async def emergency_restart(self):
        """รีสตาร์ทฉุกเฉิน"""
        logger.warning("🔄 กำลังรีสตาร์ทระบบ...")
        self.stats["restarts"] += 1
        
        try:
            self.motion.motion_active = False
            await asyncio.sleep(1.0)
            
            if not await self.motion.start():
                logger.error("❌ รีสตาร์ทล้มเหลว")
                return
            
            self.last_activity = asyncio.get_event_loop().time()
            logger.info("✅ รีสตาร์ทสำเร็จ!")
            
        except Exception as e:
            logger.error(f"❌ รีสตาร์ทล้มเหลว: {e}")
    
    def update_activity(self):
        """อัพเดทเวลา activity"""
        self.last_activity = asyncio.get_event_loop().time()
    
    async def set_emotion(self, emotion: str):
        """เปลี่ยนอารมณ์"""
        try:
            emotion_type = EmotionType(emotion)
            self.motion.set_emotion(emotion_type)
            self.stats["emotion_changes"] += 1
            self.update_activity()
            logger.info(f"😊 เปลี่ยนอารมณ์: {emotion}")
            
        except Exception as e:
            logger.error(f"❌ ไม่สามารถเปลี่ยนอารมณ์ได้: {e}")
    
    async def speak(
        self,
        text: str,
        emotion: Optional[str] = None,
        audio_file: Optional[str] = None
    ):
        """พูดพร้อมขยับปากและอารมณ์"""
        if self.is_speaking:
            logger.warning("⚠️ กำลังพูดอยู่แล้ว")
            return
        
        self.is_speaking = True
        self.stats["speech_count"] += 1
        self.update_activity()
        
        try:
            # เปลี่ยนอารมณ์
            if emotion:
                await self.set_emotion(emotion)
            
            logger.info(f"💬 พูด: {text[:50]}...")
            
            # ใช้ simple lip sync
            await self.simple_lipsync.speak_text(text, speaking_rate=10.0)
            
            logger.info("✅ พูดเสร็จแล้ว")
            self.update_activity()
            
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาด: {e}")
            self.stats["errors"] += 1
        finally:
            self.is_speaking = False
    
    def get_statistics(self) -> Dict[str, Any]:
        """ดูสถิติ"""
        return {
            "speech_count": self.stats["speech_count"],
            "emotion_changes": self.stats["emotion_changes"],
            "restarts": self.stats["restarts"],
            "errors": self.stats["errors"],
            "is_running": self.is_running,
            "is_speaking": self.is_speaking
        }
    
    async def shutdown(self):
        """ปิดระบบ"""
        logger.info("=" * 60)
        logger.info("🛑 กำลังปิดระบบ...")
        logger.info("=" * 60)
        
        self.is_running = False
        
        try:
            if self.watchdog_task:
                self.watchdog_task.cancel()
                try:
                    await self.watchdog_task
                except asyncio.CancelledError:
                    pass
            
            if self.enable_lipsync:
                await self.lipsync.stop()
            
            await self.motion.stop()
            
            stats = self.get_statistics()
            logger.info("📊 สถิติ:")
            for key, value in stats.items():
                logger.info(f"  {key}: {value}")
            
            logger.info("=" * 60)
            logger.info("✅ ปิดระบบเรียบร้อย!")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาด: {e}")