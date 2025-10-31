"""
youtube_live.py - YouTube Live Chat Integration
แก้ไขเพื่อรองรับ: Queue Manager, Safety Filter, ทวนคำถาม
"""

import asyncio
import logging
from typing import Optional, Callable
from pytchat import LiveChat
import time

from src.core.queue_manager import QueuedMessage, MessageSource, get_queue_manager

logger = logging.getLogger(__name__)


class YouTubeLiveAdapter:
    """YouTube Live Chat Adapter"""
    
    def __init__(
        self,
        stream_id: str,
        motion_controller=None
    ):
        self.stream_id = stream_id
        self.motion_controller = motion_controller
        
        # Queue manager
        self.queue_manager = get_queue_manager()
        
        # Chat client
        self.chat: Optional[LiveChat] = None
        self.is_running = False
        self.chat_task: Optional[asyncio.Task] = None
        
        # Last processed message (เพื่อไม่ให้ซ้ำ)
        self.last_message_id = None
        self.last_message_time = 0.0
        
        # Message cooldown (รับข้อความใหม่ล่าสุดเท่านั้น)
        self.message_cooldown = 2.0  # รับข้อความใหม่ทุก 2 วินาที
    
    async def start(self):
        """เริ่มต้น YouTube Live chat monitoring"""
        if self.is_running:
            logger.warning("YouTube Live adapter กำลังทำงานอยู่แล้ว")
            return
        
        try:
            logger.info(f"🎥 เริ่มต้น YouTube Live Chat: {self.stream_id}")
            
            # สร้าง LiveChat instance
            self.chat = LiveChat(video_id=self.stream_id)
            
            self.is_running = True
            self.chat_task = asyncio.create_task(self._monitor_chat())
            
            logger.info("✅ YouTube Live Chat เริ่มทำงานแล้ว")
        
        except Exception as e:
            logger.error(f"❌ ไม่สามารถเริ่ม YouTube Live Chat ได้: {e}", exc_info=True)
            self.is_running = False
    
    async def _monitor_chat(self):
        """Monitor YouTube Live chat"""
        logger.info("👀 กำลังติดตาม YouTube Live chat...")
        
        while self.is_running:
            try:
                if not self.chat or not self.chat.is_alive():
                    logger.warning("⚠️ LiveChat ไม่ active")
                    await asyncio.sleep(5.0)
                    continue
                
                # อ่าน chat messages
                for chat_item in self.chat.get().sync_items():
                    await self._process_chat_message(chat_item)
                
                # รอก่อนอ่านรอบต่อไป
                await asyncio.sleep(1.0)
            
            except asyncio.CancelledError:
                logger.info("YouTube Live chat monitor cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Monitor chat error: {e}", exc_info=True)
                await asyncio.sleep(5.0)
    
    async def _process_chat_message(self, chat_item):
        """ประมวลผล chat message"""
        try:
            message_id = chat_item.id
            author = chat_item.author.name
            message = chat_item.message
            timestamp = chat_item.timestamp / 1000.0  # convert to seconds
            
            # ข้าม message ที่เคยประมวลผลแล้ว
            if message_id == self.last_message_id:
                return
            
            # เช็ค cooldown (รับแค่ข้อความล่าสุด)
            current_time = time.time()
            if current_time - self.last_message_time < self.message_cooldown:
                logger.debug(f"⏱️ Cooldown: ข้าม message จาก {author}")
                return
            
            # กรองข้อความ (ข้าม spam, bot, etc.)
            if self._should_ignore_message(message, author):
                return
            
            logger.info(f"💬 [YouTube] {author}: {message}")
            
            # บันทึก last message
            self.last_message_id = message_id
            self.last_message_time = current_time
            
            # เพิ่มเข้าคิว
            queued_message = QueuedMessage(
                text=message,
                source=MessageSource.YOUTUBE_CHAT,
                user=author,
                timestamp=timestamp,
                metadata={
                    "repeat_question": True,  # ทวนคำถามก่อนตอบ
                    "message_id": message_id
                }
            )
            await self.queue_manager.add_message(queued_message)
        
        except Exception as e:
            logger.error(f"❌ Process chat message error: {e}", exc_info=True)
    
    def _should_ignore_message(self, message: str, author: str) -> bool:
        """
        ตรวจสอบว่าควรข้าม message นี้หรือไม่
        
        Returns:
            True = ข้าม, False = ประมวลผล
        """
        # ข้าม message ว่าง
        if not message or message.strip() == "":
            return True
        
        # ข้าม message สั้นเกินไป (น่าจะเป็น spam)
        if len(message) < 3:
            return True
        
        # ข้าม message ที่เป็น emoji อย่างเดียว
        if all(not c.isalnum() for c in message):
            return True
        
        # ข้าม message ที่มีลิงก์ (spam)
        if 'http://' in message.lower() or 'https://' in message.lower():
            return True
        
        # ข้าม message ที่ซ้ำ ๆ (spam)
        # TODO: Implement spam detection
        
        return False
    
    async def stop(self):
        """หยุด YouTube Live chat monitoring"""
        logger.info("🛑 หยุด YouTube Live Chat...")
        
        self.is_running = False
        
        if self.chat_task:
            self.chat_task.cancel()
            try:
                await self.chat_task
            except asyncio.CancelledError:
                pass
        
        if self.chat:
            try:
                self.chat.terminate()
            except Exception:
                pass
        
        logger.info("✅ YouTube Live Chat หยุดแล้ว")
    
    def get_status(self) -> dict:
        """ดูสถานะ"""
        return {
            "is_running": self.is_running,
            "stream_id": self.stream_id,
            "last_message_time": self.last_message_time,
            "chat_alive": self.chat.is_alive() if self.chat else False
        }


# Factory function
def create_youtube_live_adapter(
    stream_id: str,
    motion_controller=None
) -> Optional[YouTubeLiveAdapter]:
    """สร้าง YouTube Live adapter"""
    if not stream_id:
        logger.warning("⚠️ YouTube Stream ID ไม่ได้ระบุ")
        return None
    
    try:
        return YouTubeLiveAdapter(
            stream_id=stream_id,
            motion_controller=motion_controller
        )
    except Exception as e:
        logger.error(f"❌ ไม่สามารถสร้าง YouTube adapter ได้: {e}")
        return None