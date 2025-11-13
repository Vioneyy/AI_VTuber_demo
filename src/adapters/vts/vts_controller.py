"""
Wrapper ของ VTubeStudioController ให้เข้ากับ main.py
ตำแหน่ง: src/adapters/vts/vts_controller.py
"""

from typing import Optional
from .vtube_controller import VTubeStudioController, AnimationState
from core.config import config


class VTSController:
    """Wrapper สำหรับ VTubeStudioController"""
    
    def __init__(self, plugin_name: Optional[str] = None, model_name: Optional[str] = None):
        # Sync config
        if plugin_name:
            config.vtube.plugin_name = plugin_name
        if model_name:
            config.vtube.model_name = model_name
        
        self._controller = VTubeStudioController()
    
    async def connect(self) -> bool:
        """เชื่อมต่อ VTS"""
        return await self._controller.connect()
    
    async def update_idle_motion(self):
        """อัพเดท idle motion"""
        await self._controller.update_idle_motion()
    
    async def set_talking(self, talking: bool):
        """ตั้งสถานะกำลังพูด"""
        await self._controller.set_talking(talking)
    
    async def start_speaking(self, text: str):
        """เริ่มพูด"""
        await self._controller.start_speaking(text)
    
    async def stop_speaking(self):
        """หยุดพูด"""
        await self._controller.stop_speaking()
    
    async def start_lip_sync_from_file(self, audio_file_path: str):
        """เริ่ม lip sync จากไฟล์"""
        await self._controller.start_lip_sync_from_file(audio_file_path)

    async def set_parameter_value(self, param_name: str, value: float, immediate: bool = True):
        """ตั้งค่า parameter ของโมเดล VTS (เช่น MouthOpen/MouthForm)"""
        await self._controller.set_parameter_value(param_name, value, immediate)
    
    async def disconnect(self):
        """ตัดการเชื่อมต่อ"""
        await self._controller.disconnect()
    
    async def execute_motion_command(self, motion_cmd):
        """ส่งคำสั่ง motion"""
        await self._controller.execute_motion_command(motion_cmd)