from __future__ import annotations
import asyncio
from typing import Optional

import pytchat

from core.types import Message, Source
from core.config import get_settings
from core.policy import PolicyGuard

class YouTubeLiveAdapter:
    def __init__(self, scheduler) -> None:
        self.settings = get_settings()
        self.scheduler = scheduler
        self.policy = PolicyGuard(allow_mild_profanity=True)
        self._task: Optional[asyncio.Task] = None

    def _is_question(self, text: str) -> bool:
        t = text.strip()
        return any(s in t for s in ("?", "ทำไม", "อย่างไร", "คืออะไร", "ได้ไหม"))

    async def _reader(self):
        stream_id = self.settings.YOUTUBE_STREAM_ID
        if not stream_id:
            print("YOUTUBE_STREAM_ID ไม่ถูกตั้งค่าใน .env")
            return
        chat = pytchat.create(video_id=stream_id)
        try:
            while chat.is_alive():
                # อ่านเฉพาะล่าสุดเมื่อระบบพร้อมตอบ
                if not self.scheduler.busy:
                    latest = None
                    for c in chat.get().items:
                        latest = c
                    if latest:
                        text = latest.message
                        msg = Message(
                            text=text,
                            source=Source.YOUTUBE,
                            author=latest.author.name,
                            is_question=self._is_question(text),
                            priority=self.settings.YOUTUBE_PRIORITY,
                        )
                        ok, _ = self.policy.check_message_ok(msg)
                        if ok:
                            await self.scheduler.enqueue(msg)
                await asyncio.sleep(0.8)
        finally:
            chat.terminate()

    def start(self):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._reader())