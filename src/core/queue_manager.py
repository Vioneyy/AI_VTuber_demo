"""
Smart Queue Manager
จัดการคิวคำสั่งแบบมี priority และไม่ให้ซ้ำซ้อน
"""
import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
import time
import logging

logger = logging.getLogger(__name__)

class Priority(IntEnum):
    """ระดับความสำคัญของคำสั่ง"""
    ADMIN = 0      # คำสั่งแอดมิน - สำคัญที่สุด
    VOICE = 1      # เสียงจาก Discord - สำคัญรอง
    YOUTUBE = 2    # แชทจาก YouTube Live - สำคัญน้อยสุด
    SYSTEM = 3     # คำสั่งระบบ

@dataclass(order=True)
class QueueItem:
    """รายการในคิว"""
    priority: int
    source: str = field(compare=False)
    content: str = field(compare=False)
    user_id: str = field(compare=False)
    timestamp: float = field(default_factory=time.time, compare=False)
    user_name: str = field(compare=False, default="Unknown")
    metadata: dict = field(default_factory=dict, compare=False)

class SmartQueueManager:
    """
    Queue Manager แบบ smart
    - มี priority (admin > voice > youtube)
    - ทำทีละ 1 รายการ (ไม่ซ้ำซ้อน)
    - มี timeout protection
    - มีการจำกัดขนาด queue
    """
    
    def __init__(self, max_size: int = 50, admin_ids: set = None):
        """
        Args:
            max_size: จำนวน items สูงสุดใน queue
            admin_ids: Set ของ admin user IDs
        """
        self.queue = asyncio.PriorityQueue(maxsize=max_size)
        self.max_size = max_size
        self.admin_ids = admin_ids or set()
        
        # Processing state
        self.is_processing = False
        self.current_item: QueueItem = None
        self.processing_lock = asyncio.Lock()
        
        # Status flags (สำหรับ admin commands)
        self.youtube_enabled = True
        self.voice_enabled = True
        self.queue_enabled = True
        
        # Statistics
        self.total_processed = 0
        self.total_errors = 0
        self.last_process_time = 0
        
        logger.debug("✅ Queue Manager initialized")
    
    async def add_to_queue(
        self, 
        content: str, 
        source: str, 
        user_id: str,
        user_name: str = "Unknown",
        priority: Priority = None,
        **metadata
    ) -> bool:
        """
        เพิ่มรายการเข้า queue
        
        Args:
            content: เนื้อหาคำสั่ง/ข้อความ
            source: แหล่งที่มา ('voice', 'youtube', 'admin', 'system')
            user_id: ID ของผู้ใช้
            user_name: ชื่อผู้ใช้
            priority: ระดับความสำคัญ (optional, จะถูกกำหนดอัตโนมัติ)
            **metadata: ข้อมูลเพิ่มเติม
        
        Returns:
            bool: True ถ้าเพิ่มสำเร็จ
        """
        # ตรวจสอบว่า queue เปิดใช้งานหรือไม่
        if not self.queue_enabled:
            logger.warning("⚠️  Queue is disabled")
            return False
        
        # กำหนด priority อัตโนมัติ
        if priority is None:
            # ตรวจสอบว่าเป็น admin หรือไม่
            if user_id in self.admin_ids:
                priority = Priority.ADMIN
            elif source == 'voice':
                priority = Priority.VOICE
            elif source == 'youtube':
                priority = Priority.YOUTUBE
            elif source == 'system':
                priority = Priority.SYSTEM
            else:
                priority = Priority.YOUTUBE  # default
        
        # ตรวจสอบว่าแหล่งข้อมูลเปิดใช้งานหรือไม่
        if source == 'youtube' and not self.youtube_enabled:
            logger.debug(f"⚠️  YouTube disabled, skipping: {content[:30]}")
            return False
        
        if source == 'voice' and not self.voice_enabled:
            logger.debug(f"⚠️  Voice disabled, skipping: {content[:30]}")
            return False
        
        # ตรวจสอบว่า queue เต็มหรือไม่
        if self.queue.full():
            logger.warning(f"⚠️  Queue is full ({self.max_size}), dropping oldest item")
            # ลบ item เก่าสุดออก
            try:
                self.queue.get_nowait()
            except:
                pass
        
        # สร้าง queue item
        item = QueueItem(
            priority=priority.value,
            timestamp=time.time(),
            source=source,
            content=content,
            user_id=user_id,
            user_name=user_name,
            metadata=metadata
        )
        
        # เพิ่มเข้า queue
        try:
            await self.queue.put(item)
            logger.debug(
                f"📥 Added to queue: [{item.source}] {item.user_name}: "
                f"{item.content[:40]}... (Priority: {Priority(priority).name}, "
                f"Queue size: {self.queue.qsize()})"
            )
            return True
        except asyncio.QueueFull:
            logger.error("❌ Queue is full, cannot add item")
            return False
        except Exception as e:
            logger.error(f"❌ Error adding to queue: {e}")
            return False
    
    async def process_queue(self, processor_callback):
        """
        ประมวลผล queue ทีละรายการ
        
        Args:
            processor_callback: Async function ที่จะประมวลผล item
                                รูปแบบ: async def process(item: QueueItem) -> None
        """
        logger.debug("🔄 Queue processing started")
        
        while True:
            try:
                # ตรวจสอบว่า queue เปิดใช้งานหรือไม่
                if not self.queue_enabled:
                    await asyncio.sleep(0.5)
                    continue
                
                # รอ item ใหม่ (timeout 1 วินาที)
                try:
                    item = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Lock เพื่อไม่ให้ประมวลผลซ้อน
                async with self.processing_lock:
                    self.is_processing = True
                    self.current_item = item
                    
                    start_time = time.time()
                    
                    # ลดรูปแบบ output ให้กระชับและไม่สแปม
                    logger.debug(
                        f"🔄 Processing [{item.source}] {item.user_name} | size={self.queue.qsize()} | text='{item.content[:80]}'"
                    )
                    
                    try:
                        # ประมวลผล item
                        await processor_callback(item)
                        
                        # อัปเดต statistics
                        self.total_processed += 1
                        self.last_process_time = time.time() - start_time
                        
                        logger.debug(
                            f"✅ Processed in {self.last_process_time:.2f}s"
                        )
                        
                    except Exception as e:
                        self.total_errors += 1
                        logger.error(f"❌ Error processing item: {e}", exc_info=True)
                    
                    finally:
                        self.is_processing = False
                        self.current_item = None
                        
                        # หน่วงเวลาเล็กน้อยเพื่อไม่ให้ทำงานเร็วเกินไป
                        await asyncio.sleep(0.3)
            
            except asyncio.CancelledError:
                logger.info("🛑 Queue processing cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in queue loop: {e}", exc_info=True)
                await asyncio.sleep(1)
        
        logger.debug("👋 Queue processing stopped")
    
    def get_status(self) -> dict:
        """
        ดึงสถานะของ queue
        
        Returns:
            dict: สถานะต่างๆ
        """
        return {
            'queue_size': self.queue.qsize(),
            'is_processing': self.is_processing,
            'youtube_enabled': self.youtube_enabled,
            'voice_enabled': self.voice_enabled,
            'queue_enabled': self.queue_enabled,
            'total_processed': self.total_processed,
            'total_errors': self.total_errors,
            'last_process_time': self.last_process_time,
            'current_item': {
                'source': self.current_item.source,
                'user': self.current_item.user_name,
                'content': self.current_item.content[:50]
            } if self.current_item else None
        }
    
    async def clear_queue(self):
        """ล้าง queue"""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except:
                break
        logger.info("🗑️  Queue cleared")
    
    def enable_source(self, source: str):
        """เปิดการรับข้อมูลจากแหล่งที่มา"""
        if source == 'youtube':
            self.youtube_enabled = True
            logger.info("✅ YouTube enabled")
        elif source == 'voice':
            self.voice_enabled = True
            logger.info("✅ Voice enabled")
    
    def disable_source(self, source: str):
        """ปิดการรับข้อมูลจากแหล่งที่มา"""
        if source == 'youtube':
            self.youtube_enabled = False
            logger.info("🛑 YouTube disabled")
        elif source == 'voice':
            self.voice_enabled = False
            logger.info("🛑 Voice disabled")
    
    def enable_queue(self):
        """เปิดใช้งาน queue"""
        self.queue_enabled = True
        logger.info("✅ Queue enabled")
    
    def disable_queue(self):
        """ปิดใช้งาน queue"""
        self.queue_enabled = False
        logger.info("🛑 Queue disabled")
    
    async def stop(self):
        """หยุดการทำงาน"""
        self.queue_enabled = False
        await self.clear_queue()
        logger.info("👋 Queue Manager stopped")