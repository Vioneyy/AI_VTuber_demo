"""
lipsync_system.py - Lip Sync System
ระบบขยับปากให้ตรงกับคำพูด
"""

import asyncio
import numpy as np
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SimpleLipSyncFromTTS:
    """Lip Sync แบบง่ายจากข้อความ"""
    
    def __init__(self, vts_controller):
        self.vts = vts_controller
        self.is_speaking = False
    
    async def speak_text(self, text: str, speaking_rate: float = 10.0):
        """พูดข้อความ (speaking_rate = ตัวอักษร/วินาที)"""
        if self.is_speaking:
            logger.warning("กำลังพูดอยู่แล้ว")
            return
        
        self.is_speaking = True
        logger.info(f"💬 พูด: {text[:50]}...")
        
        try:
            duration = len(text) / speaking_rate
            syllables = len(text)
            syllable_duration = duration / syllables if syllables > 0 else 0.1
            
            vowels = 'aeiouแอะาิีึืุูเโไใไอ็'
            
            for char in text:
                if not self.is_speaking:
                    break
                
                # กำหนดการเปิดปาก
                if char.lower() in vowels or char in 'าิีึืุู':
                    mouth_open = np.random.uniform(0.6, 1.0)
                elif char.isalpha():
                    mouth_open = np.random.uniform(0.3, 0.6)
                else:
                    mouth_open = 0.1
                
                await self.vts.set_parameter_value("MouthOpen", mouth_open)
                await asyncio.sleep(syllable_duration)
            
            # ปิดปาก
            await self.vts.set_parameter_value("MouthOpen", 0.0)
            
        except Exception as e:
            logger.error(f"เกิดข้อผิดพลาด: {e}")
        finally:
            self.is_speaking = False


class LipSyncController:
    """ตัวควบคุม Lip Sync หลัก"""
    
    def __init__(self, vts_controller, config=None):
        self.vts = vts_controller
        self.simple_sync = SimpleLipSyncFromTTS(vts_controller)
        self.is_active = False
    
    async def start(self, mode: str = "text"):
        """เริ่ม lip sync"""
        self.is_active = True
        logger.info("✅ Lip Sync เริ่มทำงาน")
        return True
    
    async def stop(self):
        """หยุด lip sync"""
        self.is_active = False
        await self.vts.set_parameter_value("MouthOpen", 0.0)
        logger.info("🛑 Lip Sync หยุดแล้ว")
    
    async def speak_with_file(self, audio_file_path: str):
        """พูดจากไฟล์เสียง (สำหรับอนาคต)"""
        logger.info(f"🎵 เล่นไฟล์: {audio_file_path}")
        # TODO: Implement audio file sync
        await asyncio.sleep(2)  # placeholder