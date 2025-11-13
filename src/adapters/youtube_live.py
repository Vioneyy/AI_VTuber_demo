"""
YouTube Live Adapter (Non-blocking + Low-noise)
ตำแหน่ง: src/adapters/youtube_live.py

- อ่านคอมเมนต์แบบไม่บล็อก event loop ด้วย asyncio.to_thread
- รองรับ backpressure: หยุดพักเมื่อคิวแน่น
- จำกัดจำนวนคอมเมนต์ต่อรอบและกันอ่านซ้ำได้
- ลดระดับการ log บน console ให้กระชับ (INFO → DEBUG ส่วนที่เป็นสถานะรายละเอียด)
"""

import asyncio
import logging
from typing import Optional

import pytchat

import sys
sys.path.append('..')

from core.config import config as core_config

logger = logging.getLogger(__name__)

class YouTubeLiveAdapter:
    """YouTube Live Chat Adapter"""

    def __init__(self, video_id: str, scheduler: Optional[object] = None):
        self.video_id = video_id
        self.chat = None
        self.running = False
        # ใช้ queue manager/scheduler ที่ถูกส่งมา
        self.scheduler = scheduler
        # กันอ่านซ้ำ
        self._seen_keys = set()
        
    async def start(self):
        """เริ่มอ่าน YouTube Live Chat"""
        try:
            # สร้าง client ใน main thread เพื่อหลีกเลี่ยง signal error บน Windows
            self.chat = pytchat.create(video_id=self.video_id)
            self.running = True
            logger.info(f"✅ เชื่อมต่อ YouTube Live: {self.video_id}")

            await self._read_chat_loop()

        except Exception as e:
            logger.warning(f"❌ YouTube Live Error: {e}")
    
    async def _read_chat_loop(self):
        """Loop อ่าน chat แบบไม่บล็อค event loop"""
        # อ่านค่าการตั้งค่า
        yt_cfg = getattr(core_config, 'youtube', None)
        interval = float(getattr(yt_cfg, 'check_interval', 5.0))
        max_batch = int(getattr(yt_cfg, 'max_comments_per_batch', 5))
        read_once = bool(getattr(yt_cfg, 'read_comment_once', True))

        while self.running and self.chat and self.chat.is_alive():
            try:
                # Backpressure guard: หากคิวแน่น ให้พักก่อน
                try:
                    if hasattr(self.scheduler, 'queue'):
                        qsize = self.scheduler.queue.qsize()
                        qmax = getattr(self.scheduler, 'max_size', 50)
                        if qsize >= max(1, int(qmax * 0.7)):
                            await asyncio.sleep(interval)
                            continue
                except Exception:
                    pass

                # อ่านรายการคอมเมนต์ใน thread แยกเพื่อไม่บล็อก event loop
                items = await asyncio.to_thread(lambda: self.chat.get().sync_items())

                processed = 0
                for c in items:
                    if processed >= max_batch:
                        break

                    # กันอ่านซ้ำ
                    key = getattr(c, 'id', None) or (
                        getattr(c.author, 'channelId', ''),
                        getattr(c, 'message', ''),
                        getattr(c, 'elapsedTime', None)
                    )
                    if read_once and key in self._seen_keys:
                        continue

                    # ส่งเข้าคิว: รองรับ SmartQueueManager ที่มี add_to_queue
                    try:
                        if self.scheduler and hasattr(self.scheduler, 'add_to_queue'):
                            await self.scheduler.add_to_queue(
                                content=c.message,
                                source='youtube',
                                user_id=str(getattr(c.author, 'channelId', '')),
                                user_name=getattr(c.author, 'name', 'Unknown')
                            )
                        elif self.scheduler and hasattr(self.scheduler, 'add_message'):
                            # fallback สำหรับ API เดิม
                            await self.scheduler.add_message(
                                text=c.message,
                                source='youtube',
                                metadata={
                                    'user_id': getattr(c.author, 'channelId', ''),
                                    'user_name': getattr(c.author, 'name', 'Unknown')
                                }
                            )
                        else:
                            logger.debug("No scheduler provided; dropping message")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to enqueue YouTube message: {e}")

                    if read_once:
                        self._seen_keys.add(key)
                    processed += 1
                    await asyncio.sleep(0)  # cooperative yield

                await asyncio.sleep(interval)

            except Exception as e:
                logger.warning(f"⚠️ YouTube Chat Error: {e}")
                await asyncio.sleep(max(3.0, interval))
    
    async def stop(self):
        """หยุดอ่าน chat"""
        self.running = False
        if self.chat:
            try:
                self.chat.terminate()
            except Exception:
                pass
        logger.info("👋 ปิดการเชื่อมต่อ YouTube Live")

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