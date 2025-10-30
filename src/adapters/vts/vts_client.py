"""
VTube Studio Client (Fixed .closed check)
"""
import asyncio
import websockets
import json
import logging
import os
import time
from typing import Optional, Dict
import numpy as np

logger = logging.getLogger(__name__)

class VTSClient:
    def __init__(self, host: str = "localhost", port: int = 8001, plugin_name: str = "AI_VTuber"):
        self.host = host
        self.port = port
        self.plugin_name = plugin_name
        self.ws = None
        self.auth_token = None
        self.is_authenticated = False
        # Rate limiting และ delta-filter สำหรับการส่งพารามิเตอร์
        self._last_send_ts = 0.0
        # ลดการส่งค่าเริ่มต้นลง (80ms ≈ 12.5 FPS) เพื่อเสถียรภาพ
        self._min_send_interval_sec = float(os.getenv("VTS_SEND_MIN_INTERVAL_MS", "80")) / 1000.0
        self._last_params: Dict[str, float] = {}
        # ยก threshold ให้สูงขึ้นเพื่อลดการส่งซ้ำ
        self._epsilon_map: Dict[str, float] = {
            "EyeOpenLeft": 0.10,
            "EyeOpenRight": 0.10,
            "FacePositionX": 0.30,
            "FacePositionY": 0.30,
            "FaceAngleX": 1.5,
            "FaceAngleY": 1.5,
            "FaceAngleZ": 1.5,
        }
        # ตัวแปรสำหรับ adaptive backoff และ suppression
        self._backoff_factor = 1.0
        self._suppress_until_ts = 0.0
        
        logger.info(f"VTSClient: {host}:{port}")

    def _is_connected(self) -> bool:
        """✅ ตรวจสอบว่าเชื่อมต่ออยู่หรือไม่"""
        if not self.ws:
            return False
        
        # ลองใช้ method ต่างๆ ตาม version
        if hasattr(self.ws, 'closed'):
            return not self.ws.closed
        elif hasattr(self.ws, 'close_code'):
            return self.ws.close_code is None
        else:
            # สมมติว่าเชื่อมต่ออยู่
            return True

    async def connect(self):
        """เชื่อมต่อ VTube Studio"""
        try:
            uri = f"ws://{self.host}:{self.port}"
            logger.info(f"📡 กำลังเชื่อมต่อ VTS: {uri}")
            
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    uri,
                    ping_interval=10,
                    ping_timeout=60,
                ),
                timeout=5.0
            )
            
            logger.info("✅ WebSocket connected")
            # หน่วงให้ฝั่ง VTS พร้อมหลัง reconnect
            await asyncio.sleep(0.5)
            # รีเซ็ตสถานะ backoff/suppress และค่าเดิม
            self._backoff_factor = 1.0
            self._suppress_until_ts = 0.0
            self._last_params.clear()
            self._last_send_ts = 0.0
            
            # Authenticate
            await self._authenticate()
            
            if self.is_authenticated:
                logger.info("✅ VTS เชื่อมต่อและ authenticate สำเร็จ")
            else:
                logger.warning("⚠️ VTS เชื่อมต่อแต่ authenticate ไม่สำเร็จ")
            
        except asyncio.TimeoutError:
            logger.error("❌ VTS connection timeout")
            self.ws = None
        except ConnectionRefusedError:
            logger.error("❌ VTS ปิดอยู่ หรือ port ผิด")
            self.ws = None
        except Exception as e:
            logger.error(f"❌ VTS connection error: {e}")
            self.ws = None

    async def _authenticate(self):
        """ขอ authentication token"""
        try:
            # 1. Request auth token
            auth_request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "auth_request",
                "messageType": "AuthenticationTokenRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": "AI_VTuber_Team"
                }
            }
            
            await self.ws.send(json.dumps(auth_request))
            response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            data = json.loads(response)
            
            if "data" in data and "authenticationToken" in data["data"]:
                self.auth_token = data["data"]["authenticationToken"]
                logger.info("✅ ได้ auth token แล้ว")
            else:
                logger.error("❌ ไม่ได้ auth token")
                return
            
            # 2. Authenticate with token
            auth_msg = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "auth",
                "messageType": "AuthenticationRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": "AI_VTuber_Team",
                    "authenticationToken": self.auth_token
                }
            }
            
            await self.ws.send(json.dumps(auth_msg))
            response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            data = json.loads(response)
            
            if data.get("data", {}).get("authenticated"):
                self.is_authenticated = True
                logger.info("✅ Authenticated")
            else:
                logger.error("❌ Authentication failed")
            
        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")

    async def disconnect(self):
        """ตัดการเชื่อมต่อ"""
        if self._is_connected():
            await self.ws.close()
            logger.info("🔌 VTS disconnected")
        self.ws = None

    async def inject_parameter(self, param_name: str, value: float):
        """ส่งค่าพารามิเตอร์ไปยัง VTS"""
        if not self._is_connected() or not self.is_authenticated:
            return
        
        try:
            msg = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "inject_param",
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "parameterValues": [
                        {
                            "id": param_name,
                            "value": float(value)
                        }
                    ]
                }
            }
            
            await self.ws.send(json.dumps(msg))
            
        except Exception as e:
            logger.error(f"Inject parameter error: {e}")
            # พยายาม reconnect แบบรวดเร็วเมื่อพบปัญหา keepalive/ping timeout
            try:
                await self.disconnect()
                await self.connect()
            except Exception as re:
                logger.error(f"Reconnect failed: {re}")

    async def inject_parameters_bulk(self, params: Dict[str, float]):
        """ส่งค่าพารามิเตอร์หลายตัวแบบ batch เพื่อลดจำนวนข้อความที่ส่ง"""
        if not self._is_connected() or not self.is_authenticated:
            return

        try:
            now = time.monotonic()
            # หยุดส่งชั่วคราวถ้าเพิ่งเกิด timeout
            if now < self._suppress_until_ts:
                return
            # หากส่งถี่เกินไปให้ข้ามเฟรมนี้ เพื่อลดภาระส่ง
            effective_interval = self._min_send_interval_sec * self._backoff_factor
            if (now - self._last_send_ts) < effective_interval:
                return

            # กรองเฉพาะค่าที่เปลี่ยนเกิน threshold เพื่อหลีกเลี่ยงการส่งซ้ำโดยไม่จำเป็น
            filtered_values = []
            for name, value in params.items():
                last = self._last_params.get(name)
                eps = self._epsilon_map.get(name, 0.5)
                if last is None or abs(float(value) - float(last)) >= eps:
                    filtered_values.append({"id": name, "value": float(value)})
                    self._last_params[name] = float(value)

            # หากไม่มีค่าที่เปลี่ยนจริง ๆ ก็ไม่ต้องส่ง
            if not filtered_values:
                return

            payload = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "inject_params_batch",
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "parameterValues": filtered_values
                }
            }

            await self.ws.send(json.dumps(payload))
            self._last_send_ts = now

        except Exception as e:
            logger.error(f"Inject parameters bulk error: {e}")
            # เพิ่ม backoff และกด suppression ชั่วคราวเพื่อให้ VTS ฟื้นตัว
            self._backoff_factor = min(self._backoff_factor * 1.5, 4.0)
            self._suppress_until_ts = time.monotonic() + 1.0
            await asyncio.sleep(0.5)
            try:
                await self.disconnect()
                await self.connect()
            except Exception as re:
                logger.error(f"Reconnect failed: {re}")

    async def trigger_hotkey(self, hotkey_id: str):
        """Trigger hotkey"""
        if not self._is_connected() or not self.is_authenticated:
            return
        
        try:
            msg = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "trigger_hotkey",
                "messageType": "HotkeyTriggerRequest",
                "data": {
                    "hotkeyID": hotkey_id
                }
            }
            
            await self.ws.send(json.dumps(msg))
            logger.info(f"💫 Triggered hotkey: {hotkey_id}")
            
        except Exception as e:
            logger.error(f"Trigger hotkey error: {e}")

    async def lipsync_bytes(self, audio_bytes: bytes):
        """
        ลิปซิงก์จาก audio bytes
        """
        if not self._is_connected() or not self.is_authenticated:
            logger.warning("VTS ไม่ได้เชื่อมต่อ - ข้ามลิปซิงก์")
            return
        
        try:
            import io
            import wave
            
            # อ่าน WAV header
            wav_io = io.BytesIO(audio_bytes)
            with wave.open(wav_io, 'rb') as wav:
                sample_rate = wav.getframerate()
                n_frames = wav.getnframes()
                audio_data = wav.readframes(n_frames)
                duration = n_frames / sample_rate
            
            logger.info(f"🎤 Lipsync: {duration:.2f}s, {sample_rate}Hz")
            
            # จำลองลิปซิงก์แบบง่าย (sine wave)
            steps = int(duration * 20)  # 20 FPS
            for i in range(steps):
                t = i / 20.0
                
                # Mouth open based on sine wave
                mouth_value = abs(np.sin(t * 10.0)) * 0.8
                
                await self.inject_parameter("MouthOpen", mouth_value)
                await asyncio.sleep(0.05)
            
            # ปิดปาก
            await self.inject_parameter("MouthOpen", 0.0)
            
            logger.info("✅ Lipsync เสร็จสิ้น")
            
        except Exception as e:
            logger.error(f"Lipsync error: {e}", exc_info=True)