"""
VTS Motion Controller - Neuro-sama Style

Also provides a minimal VTSHumanMotionController stub so that
vts_client and test scripts can import it without errors.
This stub does not perform real WebSocket calls; it exposes
the expected interface for compatibility.
"""
import asyncio
import random
import math
import time
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class _DummyWS:
    def __init__(self):
        self.closed = False

class VTSHumanMotionController:
    """
    Minimal stub to satisfy imports and orchestrator expectations.
    Provides connect/authenticate/disconnect, parameter mapping,
    and simple set_parameters interface. No real VTS API calls.
    """
    def __init__(
        self,
        plugin_name: str = "AI VTuber",
        plugin_developer: str = "AI VTuber",
        host: str = "127.0.0.1",
        port: int = 8001,
    ) -> None:
        self.plugin_name = plugin_name
        self.plugin_developer = plugin_developer
        self.host = host
        self.port = port
        self.ws: Optional[_DummyWS] = None
        self.authenticated: bool = False
        self.param_map: Dict[str, str] = {}
        self.enable_mic: bool = False
        # State used by motion/lipsync
        self.speech_target: float = 0.0
        self.speaking: bool = False

    async def connect(self):
        # Simulate a connected websocket
        self.ws = _DummyWS()
        logger.info("✅ VTSHumanMotionController: connected (stub)")

    async def authenticate(self) -> bool:
        # Simulate successful authentication
        self.authenticated = True
        logger.info("✅ VTSHumanMotionController: authenticated (stub)")
        return True

    async def disconnect(self):
        if self.ws:
            self.ws.closed = True
        self.ws = None
        self.authenticated = False
        logger.info("⏹️ VTSHumanMotionController: disconnected (stub)")

    async def _resolve_param_map(self):
        # Map common parameter names to themselves for simplicity
        names = [
            "MouthOpen", "MouthSmile",
            "FaceAngleX", "FaceAngleY", "FaceAngleZ",
            "FacePositionX", "FacePositionY",
            "EyeOpenLeft", "EyeOpenRight",
        ]
        self.param_map = {n: n for n in names}
        logger.info("🔧 Resolved %d parameters (stub)", len(self.param_map))

    async def set_parameters(self, values: Dict[str, float], weight: float = 1.0):
        # No-op; log for visibility
        try:
            logger.debug("[VTS Stub] set_parameters: %s (w=%.2f)", values, weight)
        except Exception:
            pass

    async def trigger_hotkey(self, name: str):
        # No-op; log only
        logger.debug("[VTS Stub] trigger_hotkey: %s", name)

    async def run(self):
        """Background loop placeholder for human-like motion (stub)."""
        try:
            while self.ws and not self.ws.closed:
                # Just keep alive; real motion loop is implemented in MotionController
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

class MotionController:
    def __init__(self, vts_client, config: dict):
        self.vts = vts_client
        self.config = config
        
        self.is_speaking = False
        self.is_generating = False
        self.motion_task = None
        self.should_stop = False
        
        self.time_offset = 0.0
        self.breath_time = 0.0
        self.blink_timer = time.time()
        
        self.current_head_x = 0.0
        self.current_head_y = 0.0
        self.current_head_z = 0.0
        self.target_head_x = 0.0
        self.target_head_y = 0.0
        self.target_head_z = 0.0
        
        self.current_body_x = 0.0
        self.current_body_y = 0.0
        self.target_body_x = 0.0
        self.target_body_y = 0.0
        
        self.smoothing = float(config.get("smoothing", 0.85))
        self.intensity = float(config.get("intensity", 0.4))
        self.idle_intensity = float(config.get("idle_head_intensity", 0.15))
        self.idle_breath = float(config.get("idle_breath_intensity", 0.25))
        
        logger.info(f"✅ Motion Controller: smooth={self.smoothing}, intensity={self.intensity}")

    async def start(self):
        """เริ่ม motion loop"""
        if self.motion_task and not self.motion_task.done():
            logger.warning("Motion loop กำลังทำงานอยู่แล้ว")
            return
        
        self.should_stop = False
        self.motion_task = asyncio.create_task(self._motion_loop())
        logger.info("🎬 Motion loop เริ่มทำงาน")

    async def stop(self):
        """หยุด motion loop"""
        self.should_stop = True
        if self.motion_task:
            try:
                await asyncio.wait_for(self.motion_task, timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Motion loop timeout")
            self.motion_task = None
        logger.info("⏹️ Motion loop หยุดแล้ว")

    def set_speaking(self, speaking: bool):
        """ตั้งสถานะกำลังพูด"""
        self.is_speaking = speaking
        if speaking:
            logger.debug("🗣️ เริ่มพูด")
        else:
            logger.debug("🤐 พูดเสร็จ")

    def set_generating(self, generating: bool):
        """ตั้งสถานะกำลังเจนเสียง"""
        self.is_generating = generating
        if generating:
            logger.debug("⚙️ กำลังเจนเสียง - เริ่ม idle animation")
        else:
            logger.debug("✅ เจนเสียงเสร็จ")

    async def _motion_loop(self):
        """
        Main motion loop
        """
        logger.info("🎭 Motion loop เริ่มต้น")
        
        while not self.should_stop:
            try:
                dt = 0.05
                
                self.time_offset += dt * 0.5
                self.breath_time += dt
                
                if self.is_generating:
                    await self._update_idle_animation(dt)
                elif not self.is_speaking:
                    await self._update_natural_movement(dt)
                else:
                    await self._update_speaking_animation(dt)
                
                await self._update_breathing()
                await self._update_blinking()
                
                await asyncio.sleep(dt)
                
            except Exception as e:
                logger.error(f"Motion loop error: {e}", exc_info=True)
                await asyncio.sleep(0.1)
        
        logger.info("🛑 Motion loop หยุด")

    async def _update_idle_animation(self, dt: float):
        """Idle Animation: เคลื่อนไหวเบาๆ ตอนกำลังเจนเสียง"""
        idle_wave = math.sin(self.time_offset * 0.8) * self.idle_intensity
        
        self.target_head_x = idle_wave * 0.5
        self.target_head_y = math.cos(self.time_offset * 0.6) * self.idle_intensity * 0.3
        self.target_head_z = idle_wave * 0.3
        
        self.target_body_x = math.sin(self.time_offset * 0.5) * self.idle_intensity * 0.4
        
        await self._smooth_update(dt)

    async def _update_natural_movement(self, dt: float):
        """Natural Movement: เคลื่อนไหวแบบธรรมชาติ"""
        noise_x = math.sin(self.time_offset * 1.2) * math.cos(self.time_offset * 0.7)
        noise_y = math.cos(self.time_offset * 0.9) * math.sin(self.time_offset * 1.1)
        noise_z = math.sin(self.time_offset * 0.8) * math.cos(self.time_offset * 1.3)
        
        self.target_head_x = noise_x * self.intensity * 0.6
        self.target_head_y = noise_y * self.intensity * 0.4
        self.target_head_z = noise_z * self.intensity * 0.5
        
        self.target_body_x = math.sin(self.time_offset * 0.6) * self.intensity * 0.3
        self.target_body_y = math.cos(self.time_offset * 0.5) * self.intensity * 0.2
        
        if random.random() < 0.01:
            self.target_head_x += random.uniform(-0.1, 0.1)
            self.target_head_y += random.uniform(-0.05, 0.05)
        
        await self._smooth_update(dt)

    async def _update_speaking_animation(self, dt: float):
        """Speaking Animation: เคลื่อนไหวตอนพูด"""
        bob_intensity = 0.4
        talk_speed = 2.0
        
        bob_x = math.sin(self.time_offset * talk_speed) * bob_intensity
        bob_y = abs(math.cos(self.time_offset * talk_speed * 0.8)) * bob_intensity * 0.5
        
        self.target_head_x = bob_x * 0.3
        self.target_head_y = bob_y * 0.2
        self.target_head_z = math.sin(self.time_offset * talk_speed * 0.6) * 0.15
        
        await self._smooth_update(dt)

    async def _smooth_update(self, dt: float):
        """Smooth Interpolation"""
        alpha = 1.0 - self.smoothing
        
        self.current_head_x += (self.target_head_x - self.current_head_x) * alpha
        self.current_head_y += (self.target_head_y - self.current_head_y) * alpha
        self.current_head_z += (self.target_head_z - self.current_head_z) * alpha
        
        self.current_body_x += (self.target_body_x - self.current_body_x) * alpha
        self.current_body_y += (self.target_body_y - self.current_body_y) * alpha
        
        await self._apply_parameters()

    async def _apply_parameters(self):
        """ส่งค่าพารามิเตอร์ไปยัง VTS"""
        try:
            params = {
                "FaceAngleX": self.current_head_x * 30.0,
                "FaceAngleY": self.current_head_y * 30.0,
                "FaceAngleZ": self.current_head_z * 30.0,
                "FacePositionX": self.current_body_x * 10.0,
                "FacePositionY": self.current_body_y * 5.0,
            }
            
            for param_name, value in params.items():
                await self.vts.inject_parameter(param_name, value)
                
        except Exception as e:
            logger.error(f"Apply parameters error: {e}")

    async def _update_breathing(self):
        """Breathing Animation"""
        try:
            breath_speed = float(self.config.get("breath_speed", 0.8))
            
            if self.is_generating:
                breath_intensity = self.idle_breath
            else:
                breath_intensity = float(self.config.get("breath_intensity", 0.3))
            
            breath_value = (math.sin(self.breath_time * breath_speed) + 1.0) * 0.5
            breath_value *= breath_intensity
            
            await self.vts.inject_parameter("FacePositionY", breath_value * 2.0)
            
        except Exception as e:
            logger.error(f"Breathing error: {e}")

    async def _update_blinking(self):
        """Blinking"""
        try:
            now = time.time()
            blink_min = float(self.config.get("blink_interval_min", 2.0))
            blink_max = float(self.config.get("blink_interval_max", 6.0))
            blink_duration = float(self.config.get("blink_duration", 0.15))
            
            next_blink = self.blink_timer + random.uniform(blink_min, blink_max)
            
            if now >= next_blink:
                await self.vts.inject_parameter("EyeOpenLeft", 0.0)
                await self.vts.inject_parameter("EyeOpenRight", 0.0)
                await asyncio.sleep(blink_duration)
                await self.vts.inject_parameter("EyeOpenLeft", 1.0)
                await self.vts.inject_parameter("EyeOpenRight", 1.0)
                
                self.blink_timer = time.time()
                
        except Exception as e:
            logger.error(f"Blinking error: {e}")

    async def trigger_emotion(self, emotion: str):
        """Trigger hotkey emotion"""
        try:
            hotkey_map = {
                "happy": "happy_trigger",
                "sad": "sad_trigger",
                "angry": "angry_trigger",
                "surprised": "surprised_trigger",
                "thinking": "thinking_trigger"
            }
            
            hotkey = hotkey_map.get(emotion.lower())
            if hotkey and self.vts.ws:
                await self.vts.trigger_hotkey(hotkey)
                logger.info(f"💫 Triggered emotion: {emotion}")
        except Exception as e:
            logger.error(f"Emotion trigger error: {e}")


def create_motion_controller(vts_client, env_config: dict):
    """สร้าง Motion Controller จาก config"""
    config = {
        "smoothing": env_config.get("VTS_MOVEMENT_SMOOTHING", "0.85"),
        "intensity": env_config.get("VTS_MOTION_INTENSITY", "0.4"),
        "idle_head_intensity": env_config.get("VTS_IDLE_HEAD_INTENSITY", "0.15"),
        "idle_breath_intensity": env_config.get("VTS_IDLE_BREATH_INTENSITY", "0.25"),
        "breath_speed": env_config.get("VTS_BREATH_SPEED", "0.8"),
        "breath_intensity": env_config.get("VTS_BREATH_INTENSITY", "0.3"),
        "blink_interval_min": env_config.get("VTS_BLINK_INTERVAL_MIN", "2.0"),
        "blink_interval_max": env_config.get("VTS_BLINK_INTERVAL_MAX", "6.0"),
        "blink_duration": env_config.get("VTS_BLINK_DURATION", "0.15"),
    }
    
    return MotionController(vts_client, config)

async def run_motion():
    """Entry point used by scripts/vts_human_motion.py (stub)."""
    try:
        from .vts_client import VTSClient
    except Exception:
        # Fallback import if relative fails
        from src.adapters.vts.vts_client import VTSClient

    client = VTSClient()
    await client.connect()
    # Create a default motion controller and start it
    ctrl = create_motion_controller(client, {})
    await ctrl.start()
    # Keep running until interrupted
    await asyncio.Event().wait()