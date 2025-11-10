"""
Wrapper ของ VTubeStudioController ให้เข้ากับ main.py
ให้คลาสชื่อ VTSController ที่รับ plugin_name / model_name และมีเมธอด
- connect()
- update_idle_motion()
- set_talking(flag)
- disconnect()
"""

from typing import Optional

from .vtube_controller import VTubeStudioController, AnimationState
from core.config import config


class VTSController:
    def __init__(self, plugin_name: Optional[str] = None, model_name: Optional[str] = None):
        # sync config ถ้ามีค่าใหม่จาก main
        if plugin_name:
            config.vtube.plugin_name = plugin_name
        if model_name:
            config.vtube.model_name = model_name

        self._controller = VTubeStudioController()

    async def connect(self) -> bool:
        return await self._controller.connect()

    async def update_idle_motion(self):
        # ให้สถานะเป็น idle อย่างต่อเนื่อง
        await self._controller.set_state(AnimationState.IDLE)

    async def set_talking(self, talking: bool):
        # map การพูดไปยัง state SPEAKING หรือกลับไป IDLE
        await self._controller.set_state(AnimationState.SPEAKING if talking else AnimationState.IDLE)

    async def start_speaking(self, text: str):
        """เริ่มพูด พร้อมกระตุ้น lip sync ตามข้อความ"""
        await self._controller.start_speaking(text)

    async def stop_speaking(self):
        """หยุดพูด และปิดการขยับปาก"""
        await self._controller.stop_speaking()

    async def disconnect(self):
        await self._controller.disconnect()