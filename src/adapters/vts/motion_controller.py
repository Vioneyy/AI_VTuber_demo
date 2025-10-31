"""
motion_controller.py - VTube Studio Motion Controller
ระบบควบคุมการขยับของโมเดล พร้อม Anti-Freeze + Smile
"""

import asyncio
import os
import websockets
import json
import random
import time
import math
from typing import Optional, Dict, Tuple, List
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EmotionType(Enum):
    """ประเภทอารมณ์"""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    EXCITED = "excited"
    ANGRY = "angry"
    CONFUSED = "confused"
    THINKING = "thinking"


class PerlinNoise:
    """Perlin Noise สำหรับการขยับที่ smooth"""
    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        self.permutation = list(range(256))
        random.shuffle(self.permutation)
        self.permutation *= 2
    
    def fade(self, t: float) -> float:
        return t * t * t * (t * (t * 6 - 15) + 10)
    
    def lerp(self, t: float, a: float, b: float) -> float:
        return a + t * (b - a)
    
    def grad(self, hash: int, x: float, y: float) -> float:
        h = hash & 3
        u = x if h < 2 else y
        v = y if h < 2 else x
        return (u if (h & 1) == 0 else -u) + (v if (h & 2) == 0 else -v)
    
    def noise(self, x: float, y: float) -> float:
        X = int(x) & 255
        Y = int(y) & 255
        x -= int(x)
        y -= int(y)
        u = self.fade(x)
        v = self.fade(y)
        
        a = self.permutation[X] + Y
        aa = self.permutation[a]
        ab = self.permutation[a + 1]
        b = self.permutation[X + 1] + Y
        ba = self.permutation[b]
        bb = self.permutation[b + 1]
        
        return self.lerp(v,
            self.lerp(u, self.grad(self.permutation[aa], x, y),
                         self.grad(self.permutation[ba], x - 1, y)),
            self.lerp(u, self.grad(self.permutation[ab], x, y - 1),
                         self.grad(self.permutation[bb], x - 1, y - 1)))


class VTSMotionController:
    """ตัวควบคุมการขยับของ VTube Studio"""
    
    def __init__(self, host: str = "localhost", port: int = 8001):
        self.host = host
        self.port = port
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.authenticated = False
        self.plugin_name = "AI_VTuber_Motion_Controller"
        self.plugin_developer = "Vioneyy"
        self.auth_token: Optional[str] = None
        
        # Motion state
        self.current_emotion = EmotionType.HAPPY  # เริ่มต้นด้วยยิ้ม
        self.motion_active = True
        
        # Perlin noise
        self.noise_x = PerlinNoise(seed=random.randint(0, 10000))
        self.noise_y = PerlinNoise(seed=random.randint(0, 10000))
        self.noise_z = PerlinNoise(seed=random.randint(0, 10000))
        
        # Time tracking
        self.time_offset = 0.0
        self.last_update = time.time()
        
        # Positions
        self.current_pos = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.target_pos = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.next_target_change = time.time() + random.uniform(2.0, 5.0)
        
        # Smile system (ใหม่)
        self.current_smile = 1.0  # เริ่มต้นยิ้มเต็มที่
        self.target_smile = 1.0
        self.base_smile = 0.7  # รอยยิ้มพื้นฐาน (ยิ้มตลอดเวลา)
        
        # Anti-freeze (ปรับค่าให้ดีขึ้น)
        self.last_motion_update = time.time()
        self.motion_timeout = 10.0  # เพิ่มจาก 2.0 เป็น 10.0 วินาที
        self.motion_task: Optional[asyncio.Task] = None
        self.health_check_task: Optional[asyncio.Task] = None
        self.envelope_task: Optional[asyncio.Task] = None
        
        # Config
        self.angle_x_range = (-15.0, 15.0)
        self.angle_y_range = (-8.0, 8.0)
        self.angle_z_range = (-10.0, 10.0)
        try:
            self.update_rate = float(os.getenv("VTS_UPDATE_RATE", "30"))
        except Exception:
            self.update_rate = 30.0  # ลดจาก 60 เป็น 30 FPS เพื่อลด load
        
        # Send throttle (avoid VTS disconnect on flood)
        try:
            self.send_min_interval = max(0.0, float(os.getenv("VTS_SEND_MIN_INTERVAL_MS", "50")) / 1000.0)
        except Exception:
            self.send_min_interval = 0.05  # เพิ่มจาก 0.03 เป็น 0.05
        self._last_send_ts = 0.0
        
        # WebSocket settings
        self.ws_ping_interval = 20
        self.ws_ping_timeout = 30
        self.ws_close_timeout = 10
    
    async def connect(self) -> bool:
        """เชื่อมต่อกับ VTS พร้อม ping/pong settings"""
        try:
            logger.info(f"📡 เชื่อมต่อกับ VTS: {self.host}:{self.port}")
            
            # เพิ่ม ping/pong settings เพื่อรักษาการเชื่อมต่อ
            self.ws = await websockets.connect(
                f"ws://{self.host}:{self.port}",
                ping_interval=self.ws_ping_interval,
                ping_timeout=self.ws_ping_timeout,
                close_timeout=self.ws_close_timeout
            )
            
            logger.info("✅ เชื่อมต่อสำเร็จ!")
            return True
        except Exception as e:
            logger.error(f"❌ ไม่สามารถเชื่อมต่อได้: {e}")
            return False
    
    async def authenticate(self) -> bool:
        """ยืนยันตัวตนกับ VTS"""
        if not self.ws:
            return False
        
        try:
            # ขอ token
            auth_request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "AuthRequest",
                "messageType": "AuthenticationTokenRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": self.plugin_developer
                }
            }
            
            await self.ws.send(json.dumps(auth_request))
            response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            data = json.loads(response)
            
            if "data" in data and "authenticationToken" in data["data"]:
                self.auth_token = data["data"]["authenticationToken"]
            
            # Authenticate
            if self.auth_token:
                auth = {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": "Authenticate",
                    "messageType": "AuthenticationRequest",
                    "data": {
                        "pluginName": self.plugin_name,
                        "pluginDeveloper": self.plugin_developer,
                        "authenticationToken": self.auth_token
                    }
                }
                
                await self.ws.send(json.dumps(auth))
                response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                data = json.loads(response)
                
                if data.get("data", {}).get("authenticated", False):
                    self.authenticated = True
                    logger.info("✅ ยืนยันตัวตนสำเร็จ!")
                    return True
            
            return False
            
        except asyncio.TimeoutError:
            logger.error("❌ ยืนยันตัวตน timeout")
            return False
        except Exception as e:
            logger.error(f"❌ ยืนยันตัวตนล้มเหลว: {e}")
            return False
    
    async def set_parameter_value(self, parameter: str, value: float) -> bool:
        """ตั้งค่า parameter พร้อม throttling และอ่าน ack แบบเร็วเพื่อกันบัฟเฟอร์ล้น"""
        if not self.ws or not self.authenticated:
            return False
        
        try:
            # Global throttle to avoid flooding the VTS socket
            now = time.time()
            delta = now - self._last_send_ts
            if delta < self.send_min_interval:
                await asyncio.sleep(self.send_min_interval - delta)
            
            request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": f"SetParam_{parameter}_{int(time.time()*1000)}",
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "parameterValues": [
                        {
                            "id": parameter,
                            "value": value
                        }
                    ]
                }
            }
            
            await self.ws.send(json.dumps(request))
            self._last_send_ts = time.time()
            # Consume ack quickly if any; ignore timeouts to keep loop light
            try:
                _ = await asyncio.wait_for(self.ws.recv(), timeout=0.02)
            except asyncio.TimeoutError:
                pass
            return True
            
        except websockets.exceptions.ConnectionClosed as e:
            # ไม่ log บ่อยเกินไป เพื่อไม่ให้ spam
            if random.random() < 0.1:  # log แค่ 10%
                logger.debug(f"Connection closed ขณะส่ง {parameter}: {e}")
            try:
                self.authenticated = False
                self.ws = None
            except Exception:
                pass
            return False

    async def set_parameter_values(self, values: Dict[str, float], request_id: str = "SetParamsBatch") -> bool:
        """ส่งพารามิเตอร์หลายตัวแบบ batch เพื่อลดจำนวนข้อความและอ่าน ack แบบเร็ว"""
        if not self.ws or not self.authenticated:
            return False
        try:
            now = time.time()
            delta = now - self._last_send_ts
            if delta < self.send_min_interval:
                await asyncio.sleep(self.send_min_interval - delta)
            param_list = [{"id": k, "value": float(v)} for k, v in values.items()]
            request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": f"{request_id}_{int(time.time()*1000)}",
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "parameterValues": param_list
                }
            }
            await self.ws.send(json.dumps(request))
            self._last_send_ts = time.time()
            try:
                _ = await asyncio.wait_for(self.ws.recv(), timeout=0.02)
            except asyncio.TimeoutError:
                pass
            return True
        except websockets.exceptions.ConnectionClosed as e:
            if random.random() < 0.1:
                logger.debug(f"Connection closed ขณะส่ง batch: {e}")
            try:
                self.authenticated = False
                self.ws = None
            except Exception:
                pass
            return False
        except Exception as e:
            if random.random() < 0.1:
                logger.debug(f"ไม่สามารถส่ง batch: {e}")
            try:
                self.authenticated = False
                self.ws = None
            except Exception:
                pass
            return False
        except Exception as e:
            if random.random() < 0.1:  # log แค่ 10%
                logger.debug(f"ไม่สามารถส่ง {parameter}: {e}")
            try:
                self.authenticated = False
                self.ws = None
            except Exception:
                pass
            return False
    
    def calculate_smooth_position(self, current: float, target: float, delta: float) -> float:
        """คำนวณตำแหน่งแบบ smooth"""
        smoothing = 1.0 - math.exp(-5.0 * delta)
        return current + (target - current) * smoothing
    
    def generate_random_target(self, emotion: EmotionType) -> Dict[str, float]:
        """สร้างเป้าหมายแบบสุ่มตามอารมณ์"""
        intensity_map = {
            EmotionType.NEUTRAL: 0.5,
            EmotionType.HAPPY: 0.8,
            EmotionType.SAD: 0.3,
            EmotionType.EXCITED: 1.0,
            EmotionType.ANGRY: 0.7,
            EmotionType.CONFUSED: 0.6,
            EmotionType.THINKING: 0.4
        }
        
        intensity = intensity_map.get(emotion, 0.5)
        
        return {
            "x": random.uniform(self.angle_x_range[0] * intensity, self.angle_x_range[1] * intensity),
            "y": random.uniform(self.angle_y_range[0] * intensity, self.angle_y_range[1] * intensity),
            "z": random.uniform(self.angle_z_range[0] * intensity, self.angle_z_range[1] * intensity)
        }
    
    def get_smile_value(self, emotion: EmotionType) -> float:
        """คำนวณค่ายิ้มตามอารมณ์ (เพิ่ม base_smile เพื่อยิ้มตลอด)"""
        smile_intensity = {
            EmotionType.NEUTRAL: 0.2,
            EmotionType.HAPPY: 1.0,
            EmotionType.SAD: 0.0,
            EmotionType.EXCITED: 1.0,
            EmotionType.ANGRY: 0.0,
            EmotionType.CONFUSED: 0.3,
            EmotionType.THINKING: 0.4
        }
        
        intensity = smile_intensity.get(emotion, 0.5)
        # รวม base_smile เพื่อให้ยิ้มตลอดเวลา
        return max(self.base_smile, intensity)
    
    async def update_motion(self):
        """อัพเดทการขยับพร้อมรอยยิ้ม (ส่งแบบ batch ลดภาระ)"""
        try:
            current_time = time.time()
            delta_time = current_time - self.last_update
            self.last_update = current_time
            self.time_offset += delta_time
            
            # เปลี่ยนเป้าหมาย
            if current_time >= self.next_target_change:
                self.target_pos = self.generate_random_target(self.current_emotion)
                self.target_smile = self.get_smile_value(self.current_emotion)
                self.next_target_change = current_time + random.uniform(2.0, 5.0)
            
            # คำนวณตำแหน่ง
            self.current_pos["x"] = self.calculate_smooth_position(
                self.current_pos["x"], self.target_pos["x"], delta_time
            )
            self.current_pos["y"] = self.calculate_smooth_position(
                self.current_pos["y"], self.target_pos["y"], delta_time
            )
            self.current_pos["z"] = self.calculate_smooth_position(
                self.current_pos["z"], self.target_pos["z"], delta_time
            )
            
            # คำนวณรอยยิ้ม (smooth)
            self.current_smile = self.calculate_smooth_position(
                self.current_smile, self.target_smile, delta_time
            )
            
            # เพิ่ม Perlin noise
            noise_x = self.noise_x.noise(self.time_offset * 0.5, 0.0) * 0.3 * 5
            noise_y = self.noise_y.noise(self.time_offset * 0.3, 0.0) * 0.3 * 3
            noise_z = self.noise_z.noise(self.time_offset * 0.4, 0.0) * 0.3 * 4
            
            final_x = self.current_pos["x"] + noise_x
            final_y = self.current_pos["y"] + noise_y
            final_z = self.current_pos["z"] + noise_z
            
            # เตรียมค่าที่จะส่งแบบ batch
            params = {
                "FaceAngleX": final_x,
                "FaceAngleY": final_y,
                "FaceAngleZ": final_z,
                "MouthSmile": self.current_smile,
            }

            # ยิ้มให้กว้างที่สุดแต่ไม่อ้าปากเมื่อไม่ได้พูด
            speaking = bool(getattr(self, "_speaking", False))
            if not speaking:
                # บังคับให้ปากปิด และเพิ่มรอยยิ้มให้สูงเกือบเต็ม
                params["MouthOpen"] = 0.0
                params["MouthSmile"] = max(params.get("MouthSmile", 0.0), 0.98)
            
            # Eye movements
            if random.random() < 0.05:
                eye_x = random.uniform(-1.0, 1.0)
                eye_y = random.uniform(-1.0, 1.0)
                params.update({
                    "EyeLeftX": eye_x,
                    "EyeRightX": eye_x,
                    "EyeLeftY": eye_y,
                    "EyeRightY": eye_y,
                })
            
            # Blink
            if random.random() < 0.02:
                # ปิดตาใน batch นี้ก่อน
                blink_close = dict(params)
                blink_close.update({"EyeOpenLeft": 0.0, "EyeOpenRight": 0.0})
                await self.set_parameter_values(blink_close, request_id="BlinkClose")
                await asyncio.sleep(0.1)
                # เปิดตากลับ
                await self.set_parameter_values({"EyeOpenLeft": 1.0, "EyeOpenRight": 1.0}, request_id="BlinkOpen")
                self.last_motion_update = current_time
                return

            # ส่งแบบ batch ปกติ
            await self.set_parameter_values(params)
            
            self.last_motion_update = current_time
            
        except Exception as e:
            # ลด logging เพื่อไม่ spam
            if random.random() < 0.05:
                logger.debug(f"update_motion error: {e}")
    
    async def motion_loop(self):
        """Loop หลักสำหรับการขยับ"""
        logger.info("🎭 Motion loop เริ่มทำงาน")
        
        while self.motion_active:
            try:
                # รองรับหลายเวอร์ชันของ websockets
                ws_closed = False
                try:
                    ws_closed = bool(getattr(self.ws, 'closed', False))
                except Exception:
                    ws_closed = False
                
                if not self.ws or ws_closed or not self.authenticated:
                    logger.info("⚠️ WebSocket ขาด — reconnecting...")
                    ok = await self._reconnect()
                    if not ok:
                        await asyncio.sleep(5.0)  # รอนานขึ้นเมื่อ reconnect ล้มเหลว
                        continue
                
                await self.update_motion()
                await asyncio.sleep(1.0 / self.update_rate)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                if random.random() < 0.05:
                    logger.debug(f"motion_loop error: {e}")
                await asyncio.sleep(1.0)
    
    async def health_check_loop(self):
        """ตรวจสอบสุขภาพระบบ (ช้าลง) + ส่ง ping เป็น heartbeat"""
        logger.info("🐕 Health check เริ่มทำงาน")
        
        while self.motion_active:
            try:
                await asyncio.sleep(3.0)  # เช็คทุก 3 วินาที
                
                current_time = time.time()
                time_since_motion = current_time - self.last_motion_update
                
                # เพิ่ม threshold
                if time_since_motion > self.motion_timeout:
                    logger.warning(f"⚠️ ตรวจพบ freeze! ({time_since_motion:.1f}s)")
                    logger.info("🔄 กำลัง restart...")
                    
                    if self.motion_task and not self.motion_task.done():
                        self.motion_task.cancel()
                        try:
                            await self.motion_task
                        except asyncio.CancelledError:
                            pass
                    
                    self.last_motion_update = current_time
                    self.motion_task = asyncio.create_task(self.motion_loop())
                    logger.info("✅ Restart สำเร็จ")

                # พยายามส่ง ping เพื่อรักษาการเชื่อมต่อ
                try:
                    if self.ws:
                        await self.ws.ping()
                except Exception:
                    pass
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Health check error: {e}")
    
    async def start(self) -> bool:
        """เริ่มต้นระบบ"""
        logger.info("🚀 เริ่มต้น Motion Controller...")
        
        if not await self.connect():
            return False
        
        if not await self.authenticate():
            return False
        
        # ตั้งค่ารอยยิ้มเริ่มต้น
        self.current_smile = self.base_smile
        self.target_smile = self.get_smile_value(self.current_emotion)
        
        self.motion_active = True
        self.last_motion_update = time.time()
        self.motion_task = asyncio.create_task(self.motion_loop())
        self.health_check_task = asyncio.create_task(self.health_check_loop())
        
        logger.info("✅ Motion Controller พร้อมใช้งาน!")
        logger.info(f"😊 รอยยิ้มพื้นฐาน: {self.base_smile:.2f}")
        return True

    async def _reconnect(self) -> bool:
        """พยายาม reconnect + authenticate"""
        try:
            # Close previous if exists
            if self.ws:
                try:
                    await self.ws.close()
                except Exception:
                    pass
            self.ws = None
            self.authenticated = False
            
            # Connect
            connected = await self.connect()
            if not connected:
                return False
            
            authed = await self.authenticate()
            if authed:
                logger.info("✅ Reconnect สำเร็จ!")
            return bool(authed)
        except Exception as e:
            logger.debug(f"Reconnect error: {e}")
            return False
    
    async def stop(self):
        """หยุดการทำงาน"""
        logger.info("🛑 หยุด Motion Controller...")
        
        self.motion_active = False
        
        if self.motion_task:
            self.motion_task.cancel()
            try:
                await self.motion_task
            except asyncio.CancelledError:
                pass
        
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
        
        if self.envelope_task:
            self.envelope_task.cancel()
            try:
                await self.envelope_task
            except asyncio.CancelledError:
                pass
        
        if self.ws:
            await self.ws.close()
        
        logger.info("✅ หยุดเรียบร้อย")
    
    def set_emotion(self, emotion: EmotionType):
        """เปลี่ยนอารมณ์"""
        self.current_emotion = emotion
        self.target_pos = self.generate_random_target(emotion)
        self.target_smile = self.get_smile_value(emotion)
        logger.info(f"😊 เปลี่ยนอารมณ์: {emotion.value} (ยิ้ม: {self.target_smile:.2f})")


# -----------------------------
# Compatibility Wrapper & Factory
# -----------------------------

class CompatibleMotionController(VTSMotionController):
    """ตัวครอบเพื่อให้เข้ากับโค้ดเดิมของโปรเจกต์"""

    def __init__(self, host: str = "localhost", port: int = 8001, plugin_name: Optional[str] = None, plugin_developer: Optional[str] = None):
        super().__init__(host=host, port=port)
        if plugin_name:
            self.plugin_name = plugin_name
        if plugin_developer:
            self.plugin_developer = plugin_developer
        self._speaking = False
        self._generating = False

    def _mood_to_emotion(self, mood: str) -> EmotionType:
        m = (mood or "").strip().lower()
        mapping = {
            "neutral": EmotionType.NEUTRAL,
            "thinking": EmotionType.THINKING,
            "happy": EmotionType.HAPPY,
            "pleased": EmotionType.HAPPY,
            "friendly": EmotionType.HAPPY,
            "sad": EmotionType.SAD,
            "angry": EmotionType.ANGRY,
            "surprised": EmotionType.EXCITED,
            "excited": EmotionType.EXCITED,
            "confused": EmotionType.CONFUSED,
            "curious": EmotionType.THINKING,
        }
        return mapping.get(m, EmotionType.HAPPY)  # default เป็น HAPPY เพื่อยิ้ม

    def set_mood(self, mood: str, energy: float = 0.5, details: Optional[Dict] = None):
        """แมป mood เป็น EmotionType และตั้งค่าเป้าหมายการเคลื่อนไหว"""
        try:
            self.set_emotion(self._mood_to_emotion(mood))
        except Exception:
            pass

    async def trigger_emotion(self, mood: str):
        """ทริกเกอร์อีโมชันแบบรวดเร็ว"""
        try:
            self.set_emotion(self._mood_to_emotion(mood))
        except Exception:
            pass

    def set_speaking(self, value: bool):
        self._speaking = bool(value)

    def set_generating(self, value: bool):
        self._generating = bool(value)

    def set_mouth_envelope(self, series: List[float], interval_sec: float):
        """ฉีดค่า MouthOpen ตาม series ใน background task"""
        async def _run():
            try:
                for v in series:
                    try:
                        await self.set_parameter_value("MouthOpen", float(max(0.0, min(1.0, v))))
                    except Exception:
                        pass
                    await asyncio.sleep(max(0.01, float(interval_sec)))
                # ปิดปากเมื่อจบ
                try:
                    await self.set_parameter_value("MouthOpen", 0.0)
                except Exception:
                    pass
            except asyncio.CancelledError:
                # ปิดปากเมื่อถูกยกเลิก
                try:
                    await self.set_parameter_value("MouthOpen", 0.0)
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"mouth_envelope task error: {e}")

        if self.envelope_task and not self.envelope_task.done():
            self.envelope_task.cancel()
        self.envelope_task = asyncio.create_task(_run())


def create_motion_controller(vts_client, env: Dict[str, str] | None = None) -> CompatibleMotionController:
    """สร้าง CompatibleMotionController โดยอ่านค่าจาก VTSClient และ .env"""
    host = getattr(vts_client, "host", "localhost")
    port = int(getattr(vts_client, "port", 8001))
    plugin_name = None
    plugin_dev = None
    try:
        plugin_name = (env or {}).get("VTS_PLUGIN_NAME")
        plugin_dev = (env or {}).get("VTS_PLUGIN_DEVELOPER") or (env or {}).get("VTS_PLUGIN_DEV")
    except Exception:
        pass
    return CompatibleMotionController(host=host, port=port, plugin_name=plugin_name, plugin_developer=plugin_dev)