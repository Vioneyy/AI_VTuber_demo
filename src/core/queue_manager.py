"""
queue_manager.py - Sequential Message Queue Manager
จัดการคิวข้อความแบบลำดับ (ตอบทีละข้อความ)
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class MessageSource(Enum):
    """แหล่งที่มาของข้อความ"""
    DISCORD_VOICE = "discord_voice"
    DISCORD_TEXT = "discord_text"
    YOUTUBE_CHAT = "youtube_chat"


@dataclass
class QueuedMessage:
    """ข้อความในคิว"""
    text: str
    source: MessageSource
    user: str
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None


class SequentialQueueManager:
    """
    จัดการคิวข้อความแบบลำดับ
    - ประมวลผลทีละข้อความ
    - รอให้ข้อความก่อนหน้าเสร็จก่อน
    """
    
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.is_processing = False
        self.current_message: Optional[QueuedMessage] = None
        self.worker_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.total_processed = 0
        self.total_errors = 0
    
    async def add_message(self, message: QueuedMessage):
        """เพิ่มข้อความเข้าคิว"""
        await self.queue.put(message)
        logger.info(f"📥 Added to queue: [{message.source.value}] {message.text[:50]}")
    
    async def process_queue(self, processor_func):
        """
        ประมวลผลคิวแบบลำดับ
        processor_func: async function(message) -> bool
        """
        logger.info("🎬 Queue processor เริ่มทำงาน")
        
        while True:
            try:
                # รอข้อความจากคิว
                message = await self.queue.get()
                
                self.is_processing = True
                self.current_message = message
                
                logger.info(f"▶️ Processing: [{message.source.value}] {message.text[:50]}")
                
                try:
                    # ประมวลผลข้อความ
                    success = await processor_func(message)
                    
                    if success:
                        self.total_processed += 1
                        logger.info(f"✅ Processed successfully: {message.text[:50]}")
                    else:
                        self.total_errors += 1
                        logger.warning(f"⚠️ Processing failed: {message.text[:50]}")
                
                except Exception as e:
                    self.total_errors += 1
                    logger.error(f"❌ Error processing message: {e}", exc_info=True)
                
                finally:
                    self.queue.task_done()
                    self.is_processing = False
                    self.current_message = None
            
            except asyncio.CancelledError:
                logger.info("🛑 Queue processor cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Queue processor error: {e}", exc_info=True)
    
    def start(self, processor_func):
        """เริ่มต้น queue processor"""
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self.process_queue(processor_func))
            logger.info("✅ Queue processor started")
    
    async def stop(self):
        """หยุด queue processor"""
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        logger.info("✅ Queue processor stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """ดูสถานะคิว"""
        return {
            "queue_size": self.queue.qsize(),
            "is_processing": self.is_processing,
            "current_message": self.current_message.text[:50] if self.current_message else None,
            "total_processed": self.total_processed,
            "total_errors": self.total_errors
        }


# Singleton
_queue_manager = None

def get_queue_manager() -> SequentialQueueManager:
    """ดึง SequentialQueueManager instance"""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = SequentialQueueManager()
    return _queue_manager