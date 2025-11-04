"""
Compatibility shim for legacy imports
This module provides a minimal PriorityScheduler used by main.py and
re-exports queue manager APIs so existing code importing `core.scheduler`
keeps working.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from .queue_manager import (
    QueueManager,
    Message,
    MessageSource,
    MessagePriority,
    queue_manager,
)


@dataclass
class SimpleMessage:
    """Minimal message used by PriorityScheduler.
    Provides a `.text` attribute expected by main.py.
    """
    text: str
    source: str
    metadata: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)


class PriorityScheduler:
    """Minimal scheduler to satisfy main.py expected API.

    - FIFO queue of `SimpleMessage` objects
    - `add_message(text=..., source=..., metadata=...)` → bool
    - `get_next()` → Optional[SimpleMessage]
    """

    def __init__(self, response_timeout: float = 2.0, max_size: int = 100):
        self.response_timeout = response_timeout
        self.queue: asyncio.Queue[SimpleMessage] = asyncio.Queue(maxsize=max_size)
        # single-command mode indicators
        self._last_selected_at: float = 0.0

    def _source_priority(self, source: str) -> int:
        """กำหนดลำดับความสำคัญของแหล่งข้อความ (ยิ่งน้อยยิ่งสำคัญ)"""
        s = (source or '').lower()
        if 'voice' in s:
            return 0  # discord voice มาก่อน
        if 'discord' in s and 'text' in s:
            return 1
        if 'youtube' in s:
            return 2
        return 3

    async def add_message(
        self,
        text: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        priority: Optional[str] = None,  # accepted for compatibility, unused
    ) -> bool:
        """Add a message to the internal queue."""
        try:
            self.queue.put_nowait(SimpleMessage(text=text, source=source, metadata=metadata))
            return True
        except asyncio.QueueFull:
            return False

    async def get_next(self) -> Optional[SimpleMessage]:
        """เลือกรายการล่าสุดตาม priority และเคลียร์รายการคงค้างอื่น ๆ

        นโยบาย:
        - ให้เสียงมาก่อน (discord voice)
        - ถ้า priority เท่ากัน เลือกอันที่ใหม่ที่สุด
        - โหมด single-command: คืนรายการเดียวและทิ้งรายการอื่น ๆ ในรอบเดียวกัน
        """
        if self.queue.empty():
            return None

        drained: list[SimpleMessage] = []
        # ดึงทุกข้อความที่มีอย่างรวดเร็ว (non-blocking)
        while not self.queue.empty():
            try:
                drained.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not drained:
            return None

        # เลือกตาม priority และ timestamp
        def sort_key(m: SimpleMessage):
            return (self._source_priority(m.source), -m.timestamp)

        drained.sort(key=sort_key)
        selected = drained[0]

        # ทิ้งที่เหลือ (ไม่คืนกลับคิว เพื่อให้รอบใหม่รับรายการใหม่เท่านั้น)
        self._last_selected_at = time.time()
        return selected


# Backward-compatible alias to the global queue manager used elsewhere
scheduler = queue_manager