"""
YouTube Live Adapter - แก้ไข import
ตำแหน่ง: src/adapters/youtube_live.py
"""

import asyncio
import pytchat
from typing import Optional

import sys
sys.path.append('..')

# แก้ไข: เปลี่ยนจาก src.core.queue_manager → core.scheduler
from core.scheduler import scheduler as global_scheduler, Message, MessageSource, MessagePriority

class YouTubeLiveAdapter:
    """YouTube Live Chat Adapter"""
    
    def __init__(self, video_id: str, scheduler: Optional[object] = None):
        self.video_id = video_id
        self.chat = None
        self.running = False
        # รองรับการส่ง scheduler มาจาก main.py ถ้าไม่ส่งใช้ global
        self.scheduler = scheduler or global_scheduler
        
    async def start(self):
        """เริ่มอ่าน YouTube Live Chat"""
        try:
            self.chat = pytchat.create(video_id=self.video_id)
            self.running = True
            print(f"✅ เชื่อมต่อ YouTube Live: {self.video_id}")
            
            await self._read_chat_loop()
            
        except Exception as e:
            print(f"❌ YouTube Live Error: {e}")
    
    async def _read_chat_loop(self):
        """Loop อ่าน chat"""
        while self.running and self.chat.is_alive():
            try:
                for c in self.chat.get().sync_items():
                    # เพิ่มข้อความเข้าคิว
                    message = Message(
                        content=c.message,
                        source=MessageSource.YOUTUBE_COMMENT,
                        priority=MessagePriority.LOW,
                        user_id=c.author.channelId,
                        user_name=c.author.name,
                        channel_id=None
                    )
                    
                    await self.scheduler.add_message(message)
                
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"⚠️ YouTube Chat Error: {e}")
                await asyncio.sleep(5)
    
    async def stop(self):
        """หยุดอ่าน chat"""
        self.running = False
        if self.chat:
            self.chat.terminate()
        print("👋 ปิดการเชื่อมต่อ YouTube Live")

# Global instance
youtube_adapter: Optional[YouTubeLiveAdapter] = None


class YouTubeLive:
    """Wrapper ให้ main.py สามารถ import ชื่อคลาส YouTubeLive ได้"""
    def __init__(self, stream_id: str, scheduler):
        self._adapter = YouTubeLiveAdapter(video_id=stream_id, scheduler=scheduler)
    
    async def start(self):
        await self._adapter.start()
    
    async def stop(self):
        await self._adapter.stop()