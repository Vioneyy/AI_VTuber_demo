"""
YouTube Live Adapter
"""
import asyncio
import logging
from typing import Optional
import os

logger = logging.getLogger(__name__)

class YouTubeLiveAdapter:
    def __init__(self, orchestrator, stream_id: Optional[str] = None):
        self.orchestrator = orchestrator
        self.stream_id = stream_id
        self.should_stop = False
        self.task = None
        
        self.mock_mode = os.getenv("YOUTUBE_MOCK_MODE", "false").lower() == "true"
        
        if self.mock_mode:
            logger.info("🧪 YouTube Mock Mode: เปิด")
        elif not stream_id:
            logger.warning("⚠️ ไม่มี YOUTUBE_STREAM_ID ใน .env")
        else:
            logger.info(f"✅ YouTube Live: Stream ID = {stream_id}")

    async def start(self):
        """เริ่มอ่านแชท YouTube"""
        if self.task and not self.task.done():
            logger.warning("YouTube adapter กำลังทำงานอยู่แล้ว")
            return
        
        self.should_stop = False
        
        if self.mock_mode:
            self.task = asyncio.create_task(self._mock_chat_loop())
            logger.info("🧪 Mock chat loop เริ่มทำงาน")
        elif self.stream_id:
            self.task = asyncio.create_task(self._real_chat_loop())
            logger.info("📺 YouTube chat loop เริ่มทำงาน")
        else:
            logger.warning("ไม่สามารถเริ่ม YouTube adapter")

    async def stop(self):
        """หยุดอ่านแชท"""
        self.should_stop = True
        if self.task:
            try:
                await asyncio.wait_for(self.task, timeout=3.0)
            except asyncio.TimeoutError:
                logger.warning("YouTube task timeout")
            self.task = None
        logger.info("⏹️ YouTube adapter หยุดแล้ว")

    async def _mock_chat_loop(self):
        """Mock Chat Loop: จำลองข้อความจาก YouTube"""
        logger.info("🧪 Mock YouTube Chat เริ่มต้น")
        
        mock_messages = [
            {"author": "TestUser1", "message": "สวัสดีครับ!", "is_question": False},
            {"author": "TestUser2", "message": "เธอชื่ออะไร?", "is_question": True},
            {"author": "TestUser3", "message": "วันนี้อากาศเป็นไงบ้าง?", "is_question": True},
            {"author": "TestUser4", "message": "น่ารักจัง~", "is_question": False},
            {"author": "TestUser5", "message": "ช่วยอธิบาย AI หน่อย", "is_question": True},
            {"author": "TestUser6", "message": "เก่งมาก!", "is_question": False},
            {"author": "TestUser7", "message": "ร้องเพลงได้มั้ย?", "is_question": True},
        ]
        
        idx = 0
        
        while not self.should_stop:
            try:
                await asyncio.sleep(20)
                
                msg = mock_messages[idx % len(mock_messages)]
                idx += 1
                
                logger.info(f"🧪 [Mock] {msg['author']}: {msg['message']}")
                
                if msg['is_question']:
                    from src.core.scheduler import Message
                    
                    message_obj = Message(
                        priority=5,
                        source="youtube",
                        is_question=True,
                        author=msg['author'],
                        text=msg['message'],
                        channel_id="mock_yt_channel"
                    )
                    
                    await self.orchestrator.scheduler.add_message(message_obj)
                    logger.info(f"📨 [Mock] ส่งคำถามเข้าคิว: {msg['message']}")
                else:
                    logger.info(f"⏭️ [Mock] ข้ามข้อความที่ไม่ใช่คำถาม")
                
            except Exception as e:
                logger.error(f"Mock chat loop error: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        logger.info("🧪 Mock chat loop หยุด")

    async def _real_chat_loop(self):
        """Real Chat Loop: อ่านแชทจาก YouTube Live จริง"""
        try:
            import pytchat

            chat = pytchat.create(video_id=self.stream_id)
            logger.info(f"📺 เชื่อมต่อ YouTube Live: {self.stream_id}")
            
            while not self.should_stop and chat.is_alive():
                try:
                    items = chat.get().sync_items()
                    pending_questions = []
                    for c in items:
                        if self.should_stop:
                            break

                        author = c.author.name
                        message = c.message

                        logger.info(f"💬 [YT] {author}: {message}")

                        if self._is_question(message):
                            pending_questions.append((author, message))
                        else:
                            logger.debug(f"⏭️ [YT] ข้ามข้อความที่ไม่ใช่คำถาม")

                    # อ่านครบหนึ่งรอบแล้วจึงค่อยส่งเข้าคิวตามเงื่อนไขที่ต้องเป็นคำถาม
                    if pending_questions:
                        from src.core.types import IncomingMessage, MessageSource
                        for author, message in pending_questions:
                            msg_obj = IncomingMessage(
                                priority=5,
                                source=MessageSource.YOUTUBE,
                                is_question=True,
                                author=author,
                                text=message,
                                meta={"channel_id": self.stream_id}
                            )
                            try:
                                await self.orchestrator.scheduler.enqueue(msg_obj)
                            except Exception as e:
                                logger.error(f"enqueue error: {e}", exc_info=True)
                        logger.info(f"📨 [YT] ส่งคำถามเข้าคิว {len(pending_questions)} รายการหลังอ่านครบหนึ่งรอบ")

                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Chat parsing error: {e}")
                    await asyncio.sleep(2)
            
            chat.terminate()
            logger.info("📺 YouTube chat loop หยุด")
            
        except ImportError:
            logger.error("ต้องติดตั้ง pytchat: pip install pytchat")
        except Exception as e:
            logger.error(f"YouTube chat error: {e}", exc_info=True)

    def _is_question(self, text: str) -> bool:
        """ตรวจสอบว่าข้อความเป็นคำถามหรือไม่"""
        question_markers = ["?", "ไหม", "มั้ย", "หรือ", "อะไร", "ทำไม", "ยังไง", "ช่วย", "แนะนำ"]
        
        text_lower = text.lower()
        
        for marker in question_markers:
            if marker in text_lower:
                return True
        
        return False


def create_youtube_adapter(orchestrator):
    """สร้าง YouTube adapter จาก config"""
    stream_id = os.getenv("YOUTUBE_STREAM_ID")
    return YouTubeLiveAdapter(orchestrator, stream_id)

# Alias ให้ Orchestrator เรียกชื่อ YouTubeAdapter ได้
YouTubeAdapter = YouTubeLiveAdapter