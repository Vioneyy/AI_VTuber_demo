"""
VTube Studio Client (Enhanced)
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
        
        # Discovered parameter names
        self.available_parameters = []
        self.available_input_parameters = []
        self.available_hotkeys = []
        
        # Rate limiting
        self._last_send_ts = 0.0
        self._min_send_interval_sec = float(os.getenv("VTS_SEND_MIN_INTERVAL_MS", "30")) / 1000.0  # เร็วขึ้น
        self._last_params: Dict[str, float] = {}
        
        # Threshold สำหรับการส่งพารามิเตอร์
        self._epsilon_map: Dict[str, float] = {
            "EyeOpenLeft": 0.02,
            "EyeOpenRight": 0.02,
            "FacePositionX": 0.05,
            "FacePositionY": 0.05,
            "FaceAngleX": 0.1,
            "FaceAngleY": 0.1,
            "FaceAngleZ": 0.1,
            "MouthSmile": 0.01,
            "ParamEyeLSmile": 0.02,
            "ParamEyeRSmile": 0.02,
            # ลด epsilon ของปากเพื่อให้ตามเสียงได้ละเอียดขึ้น
            "MouthOpen": 0.02,
        }
        
        logger.info(f"VTSClient: {host}:{port}")

    def _is_connected(self) -> bool:
        """ตรวจสอบว่าเชื่อมต่ออยู่หรือไม่"""
        if not self.ws:
            return False
        
        try:
            if hasattr(self.ws, 'closed'):
                return not self.ws.closed
            elif hasattr(self.ws, 'close_code'):
                return self.ws.close_code is None
            else:
                return True
        except:
            return False

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
            await asyncio.sleep(0.5)
            
            # Authenticate
            await self._authenticate()
            
            if self.is_authenticated:
                logger.info("✅ VTS เชื่อมต่อและ authenticate สำเร็จ")
                await self.verify_connection()
                
                # ทดสอบส่งค่าพารามิเตอร์เบื้องต้น
                await self._send_test_parameters()
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

    async def _send_test_parameters(self):
        """ส่งค่าพารามิเตอร์ทดสอบเพื่อยืนยันการทำงาน"""
        try:
            # ส่งค่าพารามิเตอร์เริ่มต้นเพื่อให้เห็นการขยับ
            test_params = {
                self.resolve_param_name("FaceAngleX", "ParamAngleX", "AngleX"): 5.0,
                self.resolve_param_name("FaceAngleY", "ParamAngleY", "AngleY"): -2.0,
                self.resolve_param_name("MouthSmile", "ParamMouthSmile", "Smile"): 0.6,
            }
            await self.inject_parameters_bulk(test_params)
            logger.info("✅ ส่งค่าพารามิเตอร์ทดสอบแล้ว")
        except Exception as e:
            logger.warning(f"ไม่สามารถส่งค่าทดสอบ: {e}")

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

    async def verify_connection(self):
        """Fetch parameter lists and hotkeys"""
        if not self._is_connected() or not self.is_authenticated:
            return
            
        try:
            # Request input parameters
            msg_inputs = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "input_params",
                "messageType": "InputParameterListRequest",
                "data": {}
            }
            await self.ws.send(json.dumps(msg_inputs))
            resp_inputs = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            data_inputs = json.loads(resp_inputs)
            names_inputs = [p.get("name") or p.get("parameterName") or p.get("id") for p in data_inputs.get("data", {}).get("parameters", [])]
            self.available_input_parameters = [n for n in names_inputs if isinstance(n, str)]
        except Exception as e:
            logger.warning(f"ไม่สามารถดึง input parameters: {e}")
            self.available_input_parameters = []
            
        try:
            # Request model parameters
            msg_params = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "model_params",
                "messageType": "ParameterListRequest",
                "data": {}
            }
            await self.ws.send(json.dumps(msg_params))
            resp_params = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            data_params = json.loads(resp_params)
            names_params = [p.get("name") or p.get("parameterName") or p.get("id") for p in data_params.get("data", {}).get("parameters", [])]
            self.available_parameters = [n for n in names_params if isinstance(n, str)]
        except Exception as e:
            logger.warning(f"ไม่สามารถดึง model parameters: {e}")
            self.available_parameters = []
            
        logger.info(f"🎯 พารามิเตอร์ Input: {len(self.available_input_parameters)}, Model: {len(self.available_parameters)}")

    def resolve_param_name(self, *candidates: str) -> str:
        """Pick the first existing parameter"""
        sets = [set(self.available_input_parameters or []), set(self.available_parameters or [])]
        for name in candidates:
            for s in sets:
                if name in s:
                    return name
        return candidates[0] if candidates else ""

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
                "requestID": f"inject_{param_name}_{time.time()}",
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

    async def inject_parameters_bulk(self, params: Dict[str, float]):
        """ส่งค่าพารามิเตอร์หลายตัวแบบ batch"""
        if not self._is_connected() or not self.is_authenticated:
            return

        try:
            now = time.monotonic()
            
            # Rate limiting
            if (now - self._last_send_ts) < self._min_send_interval_sec:
                return

            # กรองเฉพาะค่าที่เปลี่ยนเกิน threshold
            filtered_values = []
            for name, value in params.items():
                last = self._last_params.get(name)
                eps = self._epsilon_map.get(name, 0.05)
                if last is None or abs(float(value) - float(last)) >= eps:
                    filtered_values.append({"id": name, "value": float(value)})
                    self._last_params[name] = float(value)

            if not filtered_values:
                return

            payload = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": f"inject_batch_{time.time()}",
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "parameterValues": filtered_values
                }
            }

            await self.ws.send(json.dumps(payload))
            self._last_send_ts = now

        except Exception as e:
            logger.error(f"Inject parameters bulk error: {e}")

    async def trigger_hotkey(self, hotkey_id: str):
        """Trigger hotkey"""
        if not self._is_connected() or not self.is_authenticated:
            return
        
        try:
            msg = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": f"hotkey_{time.time()}",
                "messageType": "HotkeyTriggerRequest",
                "data": {
                    "hotkeyID": hotkey_id
                }
            }
            
            await self.ws.send(json.dumps(msg))
            logger.info(f"💫 Triggered hotkey: {hotkey_id}")
            
        except Exception as e:
            logger.error(f"Trigger hotkey error: {e}")

    async def trigger_hotkey_by_name(self, substrings):
        """Trigger first hotkey whose name contains any of substrings"""
        if not self._is_connected() or not self.is_authenticated:
            return False
            
        try:
            if not self.available_hotkeys:
                await self.verify_connection()
                
            subs = [s.lower() for s in (substrings or [])]
            for hk in (self.available_hotkeys or []):
                name = (hk.get("name") or "").lower()
                if any(s in name for s in subs):
                    await self.trigger_hotkey(hk.get("hotkeyID"))
                    return True
                    
            logger.warning(f"ไม่พบ hotkey ที่มีคำว่า: {substrings}")
            return False
            
        except Exception as e:
            logger.error(f"Trigger hotkey by name error: {e}")
            return False

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
            import numpy as np
            
            # อ่าน WAV header เพื่อหาความยาว
            wav_io = io.BytesIO(audio_bytes)
            with wave.open(wav_io, 'rb') as wav:
                sample_rate = wav.getframerate()
                n_frames = wav.getnframes()
                sampwidth = wav.getsampwidth()
                n_channels = wav.getnchannels()
                frames = wav.readframes(n_frames)
                duration = n_frames / sample_rate
            
            logger.info(f"🎤 Lipsync: {duration:.2f}s, {sample_rate}Hz")
            
            # ใช้พารามิเตอร์ปาก
            mouth_param = self.resolve_param_name("MouthOpen", "ParamMouthOpen", "MouthOpenY")
            
            # แปลงเป็น mono float [-1,1]
            try:
                if sampwidth == 2:
                    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                elif sampwidth == 4:
                    # torchaudio มักบันทึกเป็น float32 PCM
                    data = np.frombuffer(frames, dtype=np.float32)
                    # เผื่อกรณีเป็น int32
                    if data.max() > 1.5 or data.min() < -1.5:
                        data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / (2**31)
                elif sampwidth == 1:
                    data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
                else:
                    # fallback
                    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                if n_channels and n_channels > 1:
                    try:
                        data = data.reshape(-1, n_channels).mean(axis=1)
                    except Exception:
                        # ถ้า reshape ไม่ได้ ให้เดาว่า interleaved และเฉลี่ยแบบ step
                        data = data[::n_channels]
                mono = np.clip(data, -1.0, 1.0)
            except Exception as e:
                logger.warning(f"วิเคราะห์ WAV ไม่สำเร็จ ใช้ลิปซิงก์แบบพื้นฐานแทน: {e}")
                mono = None

            # ถ้ามีสัญญาณ mono ให้ทำลิปซิงก์ตามพลังเสียง
            if mono is not None and len(mono) > sample_rate * 0.1:
                # ตั้งค่าเฟรมเรตของลิปซิงก์ให้สอดคล้องกับ rate limit
                target_fps = max(10, int(1.0 / max(self._min_send_interval_sec, 0.03)))
                hop = max(1, int(sample_rate / target_fps))
                window = max(hop, int(sample_rate * 0.03))  # ~30–50ms

                # คำนวณ RMS แบบสไลด์
                # ป้องกันค่า NaN
                mono = np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0)
                global_rms = float(np.sqrt(np.mean(mono**2)) + 1e-6)

                # เตรียม smoothing
                mouth = 0.0
                attack = 0.7
                release = 0.35

                # วิ่งทีละ hop ก้อน
                idx = 0
                while idx + window <= len(mono):
                    seg = mono[idx:idx+window]
                    rms = float(np.sqrt(np.mean(seg**2)))
                    # ทำ normalization เทียบกับ global RMS เพื่อให้เปิดปากตามสัมพัทธ์ของเสียง
                    rnorm = min(2.0, rms / global_rms)
                    target = max(0.0, min(1.0, 0.05 + 0.85 * (rnorm / 2.0)))
                    # smoothing attack/release
                    alpha = attack if target > mouth else release
                    mouth = mouth + (target - mouth) * alpha
                    # ส่งค่า
                    await self.inject_parameter(mouth_param, mouth)
                    # เคารพ rate limit
                    await asyncio.sleep(max(self._min_send_interval_sec, 0.03))
                    idx += hop

                # ปิดปากอย่างนุ่มนวลหลังจบ
                for _ in range(3):
                    mouth = mouth + (0.0 - mouth) * 0.5
                    await self.inject_parameter(mouth_param, mouth)
                    await asyncio.sleep(max(self._min_send_interval_sec, 0.03))
                await self.inject_parameter(mouth_param, 0.0)
            else:
                # Fallback: หากอ่าน audio ไม่ได้ ใช้ animation พื้นฐาน
                steps = int(duration * 15)  # 15 FPS
                for i in range(steps):
                    t = i / 15.0
                    base_move = abs(math.sin(t * 8.0 + random.uniform(-0.5, 0.5)))
                    mouth_value = base_move * 0.7
                    await self.inject_parameter(mouth_param, mouth_value)
                    await asyncio.sleep(0.067)
                await self.inject_parameter(mouth_param, 0.0)
            
            logger.info("✅ Lipsync เสร็จสิ้น")
            
        except Exception as e:
            logger.error(f"Lipsync error: {e}", exc_info=True)

# เพิ่ม import math ที่ขาดไป
import math