"""
__init__.py - VTS Package
"""

from .config import SystemConfig, DEFAULT_CONFIG
from .motion_controller import VTSMotionController, EmotionType
from .lipsync_system import LipSyncController, SimpleLipSyncFromTTS
from .vts_integration import CompleteVTuberSystem
from .vts_client import VTSClient

__version__ = "1.0.0"

__all__ = [
    'SystemConfig',
    'DEFAULT_CONFIG',
    'VTSMotionController',
    'EmotionType',
    'LipSyncController',
    'SimpleLipSyncFromTTS',
    'CompleteVTuberSystem',
    'VTSClient'
]