"""
Compatibility + Performance Scheduler

ปรับปรุงให้รองรับทั้ง API แบบเดิมที่เรียกใช้ผ่าน `add_message()/get_next()`
และเพิ่มโหมดประมวลผลแบบเร็วตาม `scheduler_optimized.py` (priority + parallel).

ยังคงส่งออก alias `scheduler = queue_manager` เพื่อให้โค้ดเก่าใช้ได้เหมือนเดิม。
"""

import asyncio
import time
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, Dict, Any, Callable

from .queue_manager import (
    QueueManager,
    Message,
    MessageSource,
    MessagePriority as _QMMessagePriority,  # re-exported elsewhere
    queue_manager,
)

logger = logging.getLogger(__name__)


class MessagePriority(IntEnum):
    """ระดับความสำคัญของข้อความ (ยิ่งน้อยยิ่งสำคัญ)"""
    URGENT = 0      # Discord voice commands
    HIGH = 1        # Discord text messages
    MEDIUM = 2      # YouTube Live superchats
    LOW = 3         # YouTube Live regular chats


@dataclass(order=True)
class QueuedMessage:
    """โครงสร้างข้อความภายในคิว สำหรับโหมด optimized"""
    priority: int
    timestamp: float = field(compare=True)
    message_data: object = field(compare=False)
    message_id: str = field(default="", compare=False)


@dataclass
class SimpleMessage:
    """Minimal message used by compatibility API.
    Provides a `.text` attribute expected by main.py.
    """
    text: str
    source: str
    metadata: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)


class PriorityScheduler:
    """Scheduler ที่เร็วขึ้นพร้อมรองรับ API แบบเดิมและแบบ optimized.

    โหมดใช้งาน:
    - Compatibility API: `add_message(text, source, metadata)`, `get_next()`
    - Optimized API: ตั้ง `set_message_processor()` แล้ว `start()` เพื่อให้รัน loop
      ประมวลผลตาม priority (รองรับ parallel ด้วย)
    """

    def __init__(
        self,
        response_timeout: float = 2.0,
        max_size: int = 200,
        max_wait_time: float = 8.0,
        enable_parallel: bool = False,
        max_concurrent: int = 2,
    ):
        # Compatibility queue (ใช้กับ get_next)
        self._compat_queue: asyncio.Queue[SimpleMessage] = asyncio.Queue(maxsize=max_size)

        # Optimized queue
        self.queue: asyncio.PriorityQueue[QueuedMessage] = asyncio.PriorityQueue()
        self.max_wait_time = max_wait_time
        self.enable_parallel = enable_parallel
        self.max_concurrent = max_concurrent
        self.message_processor: Optional[Callable] = None
        self.processing_tasks: set = set()

        # State
        self.response_timeout = response_timeout
        self.is_running = False
        # single-command mode indicators
        self._last_selected_at: float = 0.0

        # Stats
        self.stats = {
            'total_received': 0,
            'total_processed': 0,
            'total_skipped': 0,
            'total_errors': 0,
            'avg_wait_time': 0.0,
            'avg_processing_time': 0.0,
        }

    # ---------- Compatibility helpers ----------
    def _source_priority(self, source: str) -> int:
        s = (source or '').lower()
        if 'voice' in s:
            return MessagePriority.URGENT
        if 'discord' in s and 'text' in s:
            return MessagePriority.HIGH
        if 'youtube' in s:
            return MessagePriority.MEDIUM
        return MessagePriority.LOW

    async def add_message(
        self,
        text: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        priority: Optional[str] = None,  # accepted for compatibility
    ) -> bool:
        """เพิ่มข้อความเข้าคิว (compatibility API)

        ใส่ทั้งในคิวแบบเดิม (_compat_queue) และคิว optimized (queue) เพื่อให้
        ทั้งสองโหมดใช้งานได้พร้อมกันโดยไม่ต้องแก้โค้ดที่เรียกใช้เดิม
        """
        try:
            msg = SimpleMessage(text=text, source=source, metadata=metadata)
            # สำหรับ API เดิม
            self._compat_queue.put_nowait(msg)
            # สำหรับโหมด optimized
            ts = msg.timestamp
            qm = QueuedMessage(
                priority=int(self._source_priority(source)),
                timestamp=ts,
                message_data=msg,
                message_id=f"{source}_{ts}",
            )
            await self.queue.put(qm)
            self.stats['total_received'] += 1
            return True
        except asyncio.QueueFull:
            return False

    async def get_next(self) -> Optional[SimpleMessage]:
        """เลือกข้อความตาม priority และความใหม่ (compatibility API)

        - ให้เสียงมาก่อน (discord voice)
        - ถ้า priority เท่ากัน เลือกอันที่ใหม่ที่สุด
        - โหมด single-command: คืนรายการเดียวและทิ้งรายการอื่น ๆ ในรอบเดียวกัน
        """
        if self._compat_queue.empty():
            return None

        drained: list[SimpleMessage] = []
        while not self._compat_queue.empty():
            try:
                drained.append(self._compat_queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not drained:
            return None

        drained.sort(key=lambda m: (int(self._source_priority(m.source)), -m.timestamp))
        selected = drained[0]
        self._last_selected_at = time.time()
        return selected

    # ---------- Optimized processing loop ----------
    def set_message_processor(self, processor: Callable):
        self.message_processor = processor
        logger.info("Message processor set (optimized mode)")

    async def start(self):
        if self.is_running:
            logger.warning("Scheduler already running")
            return
        if not self.message_processor:
            raise ValueError("Message processor not set")
        self.is_running = True
        logger.info("🚀 Scheduler started (optimized mode)")
        asyncio.create_task(self._processing_loop())

    async def stop(self):
        self.is_running = False
        if self.processing_tasks:
            await asyncio.gather(*self.processing_tasks, return_exceptions=True)
        logger.info("Scheduler stopped")

    async def _processing_loop(self):
        logger.info("Processing loop started")
        while self.is_running:
            try:
                try:
                    queued_msg = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                current_time = time.time()
                wait_time = current_time - queued_msg.timestamp
                if wait_time > self.max_wait_time:
                    logger.debug(
                        f"Skip stale message: waited {wait_time:.2f}s > {self.max_wait_time}s"
                    )
                    self.stats['total_skipped'] += 1
                    self.queue.task_done()
                    continue

                if self.enable_parallel:
                    await self._process_parallel(queued_msg, wait_time)
                else:
                    await self._process_sequential(queued_msg, wait_time)
                self.queue.task_done()

            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)
                await asyncio.sleep(0.3)
        logger.info("Processing loop stopped")

    async def _process_sequential(self, queued_msg: QueuedMessage, wait_time: float):
        start_time = time.time()
        try:
            await self.message_processor(queued_msg.message_data)
            processing_time = time.time() - start_time
            self.stats['total_processed'] += 1
            self._update_stats(wait_time, processing_time)
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            self.stats['total_errors'] += 1

    async def _process_parallel(self, queued_msg: QueuedMessage, wait_time: float):
        while len(self.processing_tasks) >= self.max_concurrent:
            await asyncio.sleep(0.05)
        task = asyncio.create_task(self._process_task(queued_msg, wait_time))
        self.processing_tasks.add(task)
        task.add_done_callback(self.processing_tasks.discard)

    async def _process_task(self, queued_msg: QueuedMessage, wait_time: float):
        start_time = time.time()
        try:
            await self.message_processor(queued_msg.message_data)
            processing_time = time.time() - start_time
            self.stats['total_processed'] += 1
            self._update_stats(wait_time, processing_time)
        except Exception as e:
            logger.error(f"Error processing message (parallel): {e}", exc_info=True)
            self.stats['total_errors'] += 1

    def _update_stats(self, wait_time: float, processing_time: float):
        n = max(1, self.stats['total_processed'])
        self.stats['avg_wait_time'] = (
            (self.stats['avg_wait_time'] * (n - 1) + wait_time) / n
        )
        self.stats['avg_processing_time'] = (
            (self.stats['avg_processing_time'] * (n - 1) + processing_time) / n
        )

    def get_stats(self) -> dict:
        return {
            **self.stats,
            'queue_size': self.queue.qsize(),
            'is_running': self.is_running,
            'active_tasks': len(self.processing_tasks),
        }

    async def clear_queue(self):
        count = 0
        # ล้างคิว compat
        while not self._compat_queue.empty():
            try:
                self._compat_queue.get_nowait()
                self._compat_queue.task_done()
                count += 1
            except asyncio.QueueEmpty:
                break
        # ล้างคิว optimized
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
                count += 1
            except asyncio.QueueEmpty:
                break
        logger.info(f"Cleared {count} messages from queues")
        return count


# Backward-compatible alias to the global queue manager used elsewhere
scheduler = queue_manager