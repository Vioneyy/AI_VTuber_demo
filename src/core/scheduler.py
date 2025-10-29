from __future__ import annotations
import asyncio
from typing import Callable, Awaitable, Optional
from .types import Message, Source
from .config import get_settings

class PriorityScheduler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._queue: asyncio.PriorityQueue[tuple[int, int, Message]] = asyncio.PriorityQueue()
        self._counter: int = 0
        self._busy: bool = False
        self._pending_youtube: Optional[Message] = None

    @property
    def busy(self) -> bool:
        return self._busy

    def _next_counter(self) -> int:
        self._counter += 1
        return self._counter

    async def enqueue(self, msg: Message) -> None:
        # YouTube: อ่านและตอบเฉพาะข้อความล่าสุดเมื่อพร้อม และต้องเป็นคำถามก่อนตอบ
        if msg.source == Source.YOUTUBE:
            if not msg.is_question:
                return  # ข้ามข้อความที่ไม่ใช่คำถาม
            if self.busy:
                # เก็บไว้เป็นข้อความล่าสุดเพื่อใช้ตอนพร้อม
                self._pending_youtube = msg
                return
        # Discord ได้รับความสำคัญก่อนเสมอ
        effective_priority = msg.priority
        await self._queue.put((effective_priority, self._next_counter(), msg))

    async def get_next_message(self, timeout: Optional[float] = None) -> Optional[Message]:
        """ดึงข้อความถัดไปจากคิวตามลำดับความสำคัญ
        - หากกำหนด `timeout` จะรอไม่เกินเวลาที่ระบุแล้วคืนค่า None ถ้าไม่มี
        - คืนค่า `Message` ที่ต่อคิวอยู่ หรือ None หากหมดเวลา
        """
        try:
            if timeout and timeout > 0:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            else:
                item = await self._queue.get()
            _, _, msg = item
            return msg
        except asyncio.TimeoutError:
            return None

    async def start(self, worker: Callable[[Message], Awaitable[None]]) -> None:
        while True:
            priority, _, msg = await self._queue.get()
            self._busy = True
            try:
                await asyncio.wait_for(worker(msg), timeout=self.settings.RESPONSE_TIMEOUT)
            except asyncio.TimeoutError:
                # การตอบสนองใช้เวลานานเกินไป ให้ข้ามและเคลียร์สถานะ
                pass
            finally:
                self._busy = False
                # เมื่อว่างและมี YouTube pending ให้ใช้เฉพาะรายการล่าสุดเท่านั้น
                if self._pending_youtube:
                    latest = self._pending_youtube
                    self._pending_youtube = None
                    await self._queue.put((self.settings.YOUTUBE_PRIORITY, self._next_counter(), latest))
                self._queue.task_done()