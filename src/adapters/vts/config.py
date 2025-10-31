"""
config.py - VTube Studio Configuration
การตั้งค่าระบบ VTS ทั้งหมด
"""

import os
from dataclasses import dataclass, field
from typing import Tuple, Optional


@dataclass
class VTSConnectionConfig:
    """การตั้งค่าการเชื่อมต่อ VTS"""
    host: str = "localhost"
    port: int = 8001
    plugin_name: str = "AI_VTuber_Motion"
    plugin_developer: str = "Vioneyy"
    connection_timeout: float = 10.0
    max_reconnect_attempts: int = 5


@dataclass
class MotionSystemConfig:
    """การตั้งค่าระบบการขยับ"""
    update_rate: float = 60.0
    angle_x_range: Tuple[float, float] = (-15.0, 15.0)
    angle_y_range: Tuple[float, float] = (-8.0, 8.0)
    angle_z_range: Tuple[float, float] = (-10.0, 10.0)
    movement_speed: float = 0.5
    motion_timeout: float = 2.0


@dataclass
class LipSyncConfig:
    """การตั้งค่า Lip Sync"""
    enable: bool = True
    mode: str = "file"  # "stream", "file", "text"
    sample_rate: int = 48000
    volume_threshold: float = 0.01
    volume_multiplier: float = 3.0


@dataclass
class SystemConfig:
    """การตั้งค่าระบบทั้งหมด"""
    connection: VTSConnectionConfig = field(default_factory=VTSConnectionConfig)
    motion: MotionSystemConfig = field(default_factory=MotionSystemConfig)
    lipsync: LipSyncConfig = field(default_factory=LipSyncConfig)
    
    @classmethod
    def from_env(cls):
        """สร้าง config จาก .env"""
        config = cls()
        config.connection.host = os.getenv('VTS_HOST', 'localhost')
        config.connection.port = int(os.getenv('VTS_PORT', '8001'))
        return config


DEFAULT_CONFIG = SystemConfig()