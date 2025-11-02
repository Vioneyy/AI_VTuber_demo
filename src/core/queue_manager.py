"""
ระบบจัดการคิวคำถาม พร้อมลำดับความสำคัญ
ตำแหน่ง: src/core/queue_manager.py (สร้างใหม่)
แทนที่: src/core/scheduler.py (ลบไฟล์เก่า)
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
from datetime import datetime

class MessageSource(Enum):
    """แหล่งที่มาของข้อความ"""
    DISCORD_VOICE = "discord_voice"
    DISCORD_TEXT = "discord_text"
    YOUTUBE_COMMENT = "youtube_comment"
    SYSTEM = "system"

class MessagePriority(Enum):
    """ลำดับความสำคัญ"""
    HIGH = 1      # เสียงจาก Discord/Voice
    NORMAL = 2    # ข้อความจาก Discord
    LOW = 3       # คอมเม้น YouTube

@dataclass
class Message:
    """ข้อความในคิว"""
    content: str
    source: MessageSource
    priority: MessagePriority
    timestamp: float = field(default_factory=time.time)
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    channel_id: Optional[str] = None
    
    def __lt__(self, other):
        """เปรียบเทียบสำหรับ priority queue"""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.timestamp < other.timestamp
    
    def age(self) -> float:
        """อายุของข้อความ (วินาที)"""
        return time.time() - self.timestamp

class QueueManager:
    """จัดการคิวคำถาม"""
    
    def __init__(self, max_size: int = 50, question_delay: float = 2.5):
        self.queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_size)
        self.processing = False
        self.current_message: Optional[Message] = None
        self.question_delay = question_delay
        self.last_process_time = 0
        
        # Statistics
        self.total_processed = 0
        self.total_dropped = 0
        self.source_counts = {source: 0 for source in MessageSource}
        
        # Collab mode
        self.collab_mode = False
        self.youtube_enabled = True
        
    async def add_message(self, message: Message) -> bool:
        """
        เพิ่มข้อความเข้าคิว
        Returns: True ถ้าเพิ่มสำเร็จ, False ถ้าคิวเต็ม
        """
        # Check if processing current message
        if self.processing:
            # รอให้ตอบคำถามปัจจุบันเสร็จก่อน
            current_age = time.time() - self.last_process_time
            if current_age < self.question_delay:
                print(f"⏳ กำลังประมวลผล... รอ {self.question_delay - current_age:.1f}s")
                return False
        
        # Check collab mode for YouTube
        if message.source == MessageSource.YOUTUBE_COMMENT and self.collab_mode:
            print("🎙️ โหมดคอแลป - ข้ามคอมเม้น YouTube")
            return False
        
        # Check if YouTube is disabled
        if message.source == MessageSource.YOUTUBE_COMMENT and not self.youtube_enabled:
            return False
        
        # Try to add to queue
        try:
            self.queue.put_nowait((message.priority.value, message.timestamp, message))
            self.source_counts[message.source] += 1
            print(f"📥 เพิ่มข้อความ: {message.source.value} - '{message.content[:50]}...'")
            return True
        except asyncio.QueueFull:
            self.total_dropped += 1
            print(f"⚠️ คิวเต็ม! ทิ้งข้อความจาก {message.source.value}")
            return False
    
    async def get_next_message(self) -> Optional[Message]:
        """
        ดึงข้อความถัดไปจากคิว
        Returns: Message หรือ None ถ้าคิวว่าง
        """
        if self.queue.empty():
            return None
        
        try:
            _, _, message = await asyncio.wait_for(
                self.queue.get(),
                timeout=0.1
            )
            return message
        except asyncio.TimeoutError:
            return None
    
    async def process_next(self) -> Optional[Message]:
        """
        ประมวลผลข้อความถัดไป
        """
        # Check delay
        time_since_last = time.time() - self.last_process_time
        if time_since_last < self.question_delay:
            await asyncio.sleep(self.question_delay - time_since_last)
        
        # Get next message
        message = await self.get_next_message()
        if not message:
            return None
        
        # Mark as processing
        self.processing = True
        self.current_message = message
        self.last_process_time = time.time()
        
        print(f"▶️ ประมวลผล: {message.source.value} - '{message.content[:50]}...'")
        
        return message
    
    def finish_processing(self):
        """เสร็จสิ้นการประมวลผล"""
        self.processing = False
        self.total_processed += 1
        self.current_message = None
        print(f"✅ ประมวลผลเสร็จ (รวม: {self.total_processed})")
    
    def set_collab_mode(self, enabled: bool):
        """ตั้งค่าโหมดคอแลป"""
        self.collab_mode = enabled
        status = "เปิด" if enabled else "ปิด"
        print(f"🎤 โหมดคอแลป: {status}")
    
    def set_youtube_enabled(self, enabled: bool):
        """เปิด/ปิดการรับคอมเม้น YouTube"""
        self.youtube_enabled = enabled
        status = "เปิด" if enabled else "ปิด"
        print(f"📺 YouTube Comments: {status}")
    
    def clear_queue(self):
        """ล้างคิวทั้งหมด"""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except:
                break
        print("🗑️ ล้างคิวเรียบร้อย")
    
    def get_stats(self) -> dict:
        """ดูสถิติการทำงาน"""
        return {
            "queue_size": self.queue.qsize(),
            "processing": self.processing,
            "total_processed": self.total_processed,
            "total_dropped": self.total_dropped,
            "source_counts": self.source_counts,
            "collab_mode": self.collab_mode,
            "youtube_enabled": self.youtube_enabled
        }
    
    def print_stats(self):
        """แสดงสถิติ"""
        stats = self.get_stats()
        print("\n" + "="*50)
        print("📊 Queue Manager Statistics")
        print("="*50)
        print(f"Queue Size: {stats['queue_size']}")
        print(f"Processing: {stats['processing']}")
        print(f"Total Processed: {stats['total_processed']}")
        print(f"Total Dropped: {stats['total_dropped']}")
        print(f"Collab Mode: {stats['collab_mode']}")
        print(f"YouTube Enabled: {stats['youtube_enabled']}")
        print("\nSource Counts:")
        for source, count in stats['source_counts'].items():
            print(f"  {source.value}: {count}")
        print("="*50 + "\n")

# Global queue manager
queue_manager = QueueManager()