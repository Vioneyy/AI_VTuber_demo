"""
VTube Studio WebSocket Client - Optimized for Hiyori_A Model
ใช้ built-in parameters ของ VTS แทนการสร้างเอง
"""
import asyncio
import json
import random
import logging
from typing import Optional, Dict, Any, List
import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class VTSClient:
    """
    VTube Studio WebSocket Client สำหรับโมเดล Hiyori_A
    ใช้ built-in parameters ของ VTS (FaceAngleX, FaceAngleY, EyeOpenLeft, ฯลฯ)
    """
    
    def __init__(
        self,
        plugin_name: str = "AI VTuber Demo",
        plugin_developer: str = "VIoneyy",
        host: str = "127.0.0.1",
        port: int = 8001,
        config = None
    ):
        self.plugin_name = plugin_name
        self.plugin_developer = plugin_developer
        self.host = host
        self.port = port
        self.ws_url = f"ws://{host}:{port}"
        self.config = config
        
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.auth_token: Optional[str] = None
        self.authenticated = False
        self.message_id = 0
        
        # Task สำหรับการเคลื่อนไหว
        self.motion_task: Optional[asyncio.Task] = None
        self.motion_enabled = False
        
        # ใช้ built-in parameters ของ VTS (รองรับโมเดลส่วนใหญ้ฯ)
        self.builtin_params = [
            "FaceAngleX",      # หมุนหัวซ้าย-ขวา
            "FaceAngleY",      # เงยหน้า-ก้มหน้า
            "FaceAngleZ",      # เอียงหัว
            "FacePositionX",   # เลื่อนหน้าซ้าย-ขวา
            "FacePositionY",   # เลื่อนหน้าบน-ล่าง
            "EyeLeftX",        # ตาซ้ายมองซ้าย-ขวา
            "EyeLeftY",        # ตาซ้ายมองบน-ล่าง
            "EyeRightX",       # ตาขวามองซ้าย-ขวา
            "EyeRightY",       # ตาขวามองบน-ล่าง
            "EyeOpenLeft",     # ลืมตาซ้าย
            "EyeOpenRight",    # ลืมตาขวา
            "MouthSmile",      # ยิ้ม
            "MouthOpen",       # อ้าปาก
            "BodyAngleX",      # หมุนตัวซ้าย-ขวา
            "BodyAngleY",      # โน้มตัวหน้า-หลัง
            "BodyAngleZ",      # เอียงตัว
        ]
        
        # การตั้งค่าการเคลื่อนไหว (อ่านจาก config)
        self.motion_intensity = 0.6
        self.blink_frequency = 0.4
        self.head_range = 12
        self.eye_range = 0.6
        self.body_range = 3
        self.motion_min_interval = 2.0
        self.motion_max_interval = 5.0
        self.blink_duration = 0.15
        
        if config:
            self.motion_intensity = getattr(config, "VTS_MOTION_INTENSITY", 0.6)
            self.blink_frequency = getattr(config, "VTS_BLINK_FREQUENCY", 0.4)
            self.head_range = getattr(config, "VTS_HEAD_MOVEMENT_RANGE", 12)
            self.eye_range = getattr(config, "VTS_EYE_MOVEMENT_RANGE", 0.6)
            self.body_range = getattr(config, "VTS_BODY_SWAY_RANGE", 3)
            self.motion_min_interval = getattr(config, "VTS_MOTION_MIN_INTERVAL", 2.0)
            self.motion_max_interval = getattr(config, "VTS_MOTION_MAX_INTERVAL", 5.0)
            self.blink_duration = getattr(config, "VTS_BLINK_DURATION", 0.15)
        
        # ตัวแปรสำหรับเก็บข้อมูลโมเดล
        self.current_model = None
        self.available_hotkeys = []
        self.available_parameters = []
        
        # speaking & mood state
        self.speaking = False
        self.speech_amplitude = 0.0
        self.speech_amplitude_target = 0.0
        self.speech_open_scale = 0.9
        self.mood = "neutral"  # thinking | happy | sad | neutral
        self._last_emote_ts = 0.0
        self._emote_cooldown_sec = 12.0
        self._emote_prob = {"thinking": 0.35, "happy": 0.35, "sad": 0.35}
        # keepalive task
        self._keepalive_task = None
    async def connect(self, max_retries: int = 3) -> bool:
        """เชื่อมต่อกับ VTube Studio"""
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"[VTS] เชื่อมต่อกับ {self.ws_url} (ครั้งที่ {attempt}/{max_retries})")
                
                self.ws = await websockets.connect(self.ws_url)
                
                if not await self._authenticate():
                    logger.error(f"[VTS] Token request failed (attempt {attempt}/{max_retries})")
                    if attempt < max_retries:
                        await asyncio.sleep(2)
                        continue
                    return False
                
                # ดึงข้อมูลโมเดล
                await self._get_current_model()
                
                # ดึงรายการ parameters ที่มี
                await self._get_available_parameters()
                
                # ดึงรายการ hotkeys
                await self._get_available_hotkeys()
                
                # สร้าง custom parameters ที่จำเป็น
                await self._create_custom_parameters()
                
                # ขออนุญาต permissions ที่จำเป็น
                await self._request_permissions()
                
                # start keepalive loop to prevent server closing idle connection
                try:
                    if self._keepalive_task is None or self._keepalive_task.done():
                        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
                except Exception as e:
                    logger.warning(f"[VTS] ไม่สามารถเริ่ม keepalive task: {e}")
                
                logger.info(f"✅ Connected to VTS at {self.ws_url}")
                return True
                
            except Exception as e:
                logger.error(f"[VTS] เชื่อมต่อล้มเหลว (ครั้งที่ {attempt}/{max_retries}): {e}")
                if self.ws:
                    await self.ws.close()
                    self.ws = None
                if attempt < max_retries:
                    await asyncio.sleep(2)
        
        logger.error("[VTS] Connect failed: Authentication token unavailable")
        return False
    
    async def _authenticate(self) -> bool:
        """ขอ authentication token และ authenticate"""
        try:
            # 1. ขอ token
            auth_token_request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": str(self._get_message_id()),
                "messageType": "AuthenticationTokenRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": self.plugin_developer
                }
            }
            
            await self.ws.send(json.dumps(auth_token_request))
            response = json.loads(await self.ws.recv())
            
            if response.get("messageType") == "AuthenticationTokenResponse":
                self.auth_token = response["data"]["authenticationToken"]
                logger.info(f"[VTS] ได้รับ token: {self.auth_token[:20]}...")
            else:
                logger.error(f"[VTS] Token request failed: {response}")
                return False
            
            # 2. Authenticate
            auth_request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": str(self._get_message_id()),
                "messageType": "AuthenticationRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": self.plugin_developer,
                    "authenticationToken": self.auth_token
                }
            }
            
            await self.ws.send(json.dumps(auth_request))
            auth_response = json.loads(await self.ws.recv())
            
            if auth_response.get("messageType") == "AuthenticationResponse":
                self.authenticated = auth_response["data"]["authenticated"]
                if self.authenticated:
                    logger.info("✅ [VTS] Authentication สำเร็จ!")
                    return True
                else:
                    logger.error("[VTS] Authentication ถูกปฏิเสธ - กรุณา Allow plugin ใน VTS")
            
            return False
            
        except Exception as e:
            logger.error(f"[VTS] Authentication error: {e}")
            return False
    
    async def _get_current_model(self):
        """ดึงข้อมูลโมเดลปัจจุบัน"""
        if not self.authenticated:
            return
        
        try:
            request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": str(self._get_message_id()),
                "messageType": "CurrentModelRequest"
            }
            
            await self.ws.send(json.dumps(request))
            response = json.loads(await self.ws.recv())
            
            if response.get("messageType") == "CurrentModelResponse":
                self.current_model = response["data"]
                model_name = self.current_model.get("modelName", "Unknown")
                logger.info(f"[VTS] 🎭 โมเดลปัจจุบัน: {model_name}")
                
                if "hiyori" in model_name.lower():
                    logger.info("[VTS] ✅ ตรวจพบโมเดล Hiyori - ใช้การตั้งค่าที่เหมาะสม")
            
        except Exception as e:
            logger.error(f"[VTS] ไม่สามารถดึงข้อมูลโมเดล: {e}")
    
    async def _get_available_parameters(self):
        """ดึงรายการ parameters ที่มีในโมเดล"""
        if not self.authenticated:
            return
        
        try:
            request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": str(self._get_message_id()),
                "messageType": "InputParameterListRequest"
            }
            
            await self.ws.send(json.dumps(request))
            response = json.loads(await self.ws.recv())
            
            if response.get("messageType") == "InputParameterListResponse":
                data = response["data"]
                all_params = data.get("defaultParameters", [])
                custom_params = data.get("customParameters", [])
                
                # รวม default และ custom parameters
                self.available_parameters = [p["name"] for p in all_params + custom_params]
                
                logger.info(f"[VTS] พบ {len(all_params)} default parameters และ {len(custom_params)} custom parameters")
                logger.info(f"[VTS] รวม {len(self.available_parameters)} parameters ทั้งหมด")
                
                # แสดง custom parameters ที่พบ
                if custom_params:
                    custom_names = [p["name"] for p in custom_params]
                    logger.info(f"[VTS] Custom parameters: {', '.join(custom_names)}")
                
                # ตรวจสอบว่า parameters ที่ต้องการมีหรือไม่
                missing = [p for p in self.builtin_params if p not in self.available_parameters]
                if missing:
                    logger.warning(f"[VTS] ⚠️ Parameters ที่ไม่มี: {', '.join(missing[:5])}")
            
        except Exception as e:
            logger.error(f"[VTS] ไม่สามารถดึงรายการ parameters: {e}")
    
    async def _get_available_hotkeys(self):
        """ดึงรายการ hotkeys ที่มีในโมเดล"""
        if not self.authenticated:
            return
        
        try:
            request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": str(self._get_message_id()),
                "messageType": "HotkeysInCurrentModelRequest"
            }
            
            await self.ws.send(json.dumps(request))
            response = json.loads(await self.ws.recv())
            
            if response.get("messageType") == "HotkeysInCurrentModelResponse":
                self.available_hotkeys = response["data"]["availableHotkeys"]
                logger.info(f"[VTS] 🎯 พบ {len(self.available_hotkeys)} hotkeys")
                
                # แสดงรายการ hotkeys ที่มี
                for hk in self.available_hotkeys:
                    logger.debug(f"  - {hk['name']} (Type: {hk['type']})")
            
        except Exception as e:
            logger.error(f"[VTS] ไม่สามารถดึงรายการ hotkeys: {e}")
    
    async def _create_custom_parameters(self):
        """สร้าง custom parameters ที่จำเป็นสำหรับ AI VTuber"""
        try:
            # รายการ custom parameters ที่เราต้องการสร้าง
            custom_params = [
                {
                    "parameterName": "AIVTuber_Mood_Happy",
                    "explanation": "AI VTuber happiness level (0.0 to 1.0)",
                    "min": 0.0,
                    "max": 1.0,
                    "defaultValue": 0.0
                },
                {
                    "parameterName": "AIVTuber_Mood_Sad", 
                    "explanation": "AI VTuber sadness level (0.0 to 1.0)",
                    "min": 0.0,
                    "max": 1.0,
                    "defaultValue": 0.0
                },
                {
                    "parameterName": "AIVTuber_Mood_Thinking",
                    "explanation": "AI VTuber thinking level (0.0 to 1.0)", 
                    "min": 0.0,
                    "max": 1.0,
                    "defaultValue": 0.0
                },
                {
                    "parameterName": "AIVTuber_Speaking",
                    "explanation": "AI VTuber speaking indicator (0.0 to 1.0)",
                    "min": 0.0,
                    "max": 1.0,
                    "defaultValue": 0.0
                },
                {
                    "parameterName": "AIVTuber_Energy",
                    "explanation": "AI VTuber energy level (0.0 to 1.0)",
                    "min": 0.0,
                    "max": 1.0,
                    "defaultValue": 0.5
                }
            ]
            
            for param in custom_params:
                request = {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0", 
                    "requestID": str(self._get_message_id()),
                    "messageType": "ParameterCreationRequest",
                    "data": param
                }
                
                await self.ws.send(json.dumps(request))
                response = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=2.0))
                
                if response.get("messageType") == "ParameterCreationResponse":
                    logger.info(f"✅ [VTS] สร้าง custom parameter: {param['parameterName']}")
                elif response.get("messageType") == "APIError":
                    error_msg = response.get("data", {}).get("message", "Unknown error")
                    if "already exists" in error_msg.lower():
                        logger.debug(f"[VTS] Parameter {param['parameterName']} มีอยู่แล้ว")
                    else:
                        logger.warning(f"⚠️ [VTS] ไม่สามารถสร้าง parameter {param['parameterName']}: {error_msg}")
                        
        except Exception as e:
            logger.error(f"[VTS] Error creating custom parameters: {e}")
    
    async def _request_permissions(self):
        """แจ้งเตือนเกี่ยวกับ permissions ที่ต้องอนุญาตผ่าน UI"""
        try:
            logger.info("📋 [VTS] กำลังตรวจสอบ permissions...")
            
            # แจ้งให้ผู้ใช้ทราบเกี่ยวกับ permissions ที่ต้องอนุญาตด้วยตนเอง
            logger.warning("⚠️ [VTS] สำคัญ: กรุณาตรวจสอบและอนุญาต permissions ต่อไปนี้ใน VTube Studio:")
            logger.warning("   1. เปิด VTube Studio > Settings > Plugins")
            logger.warning("   2. คลิกที่ 'AI VTuber Demo' plugin")
            logger.warning("   3. เปิดใช้งาน 'Load custom images' (Load arbitrary image data as item)")
            logger.warning("   4. คลิก 'Done' เพื่อบันทึกการตั้งค่า")
            logger.warning("   5. หากยังไม่ได้ผล ให้ลองปิด-เปิด VTube Studio ใหม่")
            
            # ตรวจสอบว่า plugin ได้รับการอนุญาตแล้วหรือไม่
            try:
                # ลองส่งคำขอทดสอบเพื่อดูว่า permissions ทำงานหรือไม่
                test_request = {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": str(self._get_message_id()),
                    "messageType": "APIStateRequest"
                }
                
                await self.ws.send(json.dumps(test_request))
                response = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=2.0))
                
                if response.get("messageType") == "APIStateResponse":
                    logger.info("✅ [VTS] Plugin connection ทำงานปกติ")
                    logger.info("💡 [VTS] หาก custom parameters ปรากฏใน VTS แล้ว แสดงว่าการตั้งค่าสำเร็จ")
                    logger.info("💡 [VTS] สำหรับ 'Load custom images' ต้องอนุญาตผ่าน UI ของ VTS เท่านั้น")
                
            except asyncio.TimeoutError:
                logger.warning("⚠️ [VTS] การตรวจสอบ API state timeout")
            except Exception as e:
                logger.warning(f"⚠️ [VTS] ไม่สามารถตรวจสอบ API state: {e}")
                
        except Exception as e:
            logger.error(f"[VTS] Error checking permissions: {e}")
    
    async def set_parameter_value(self, parameter_name: str, value: float, weight: float = 1.0):
        """ตั้งค่า parameter"""
        if not self.authenticated or not self.ws or getattr(self.ws, "closed", True):
            return
        
        # ตรวจสอบว่า parameter มีอยู่จริง
        if parameter_name not in self.available_parameters:
            return
        
        try:
            request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": str(self._get_message_id()),
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "parameterValues": [
                        {
                            "id": parameter_name,
                            "value": value * self.motion_intensity,  # ปรับตาม intensity
                            "weight": weight
                        }
                    ]
                }
            }
            
            await self.ws.send(json.dumps(request))
        except ConnectionClosed as e:
            logger.warning(f"[VTS] Connection closed while setting {parameter_name}: {e}")
            self.authenticated = False
            self.ws = None
        except Exception as e:
            logger.error(f"[VTS] Error setting {parameter_name}: {e}")
    
    async def trigger_hotkey(self, hotkey_identifier: str):
        """กด hotkey"""
        if not self.authenticated or not self.ws:
            logger.warning(f"[VTS] ไม่สามารถกด hotkey '{hotkey_identifier}': ไม่ได้เชื่อมต่อ")
            return
        
        # ตรวจสอบสถานะ websocket อย่างปลอดภัย
        try:
            if hasattr(self.ws, 'closed') and self.ws.closed:
                logger.warning(f"[VTS] ไม่สามารถกด hotkey '{hotkey_identifier}': websocket ปิดแล้ว")
                return
        except Exception:
            # หาก websocket ไม่มี attribute closed หรือมีปัญหา ให้ลองส่งต่อไป
            pass
        
        try:
            request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": str(self._get_message_id()),
                "messageType": "HotkeyTriggerRequest",
                "data": {
                    "hotkeyID": hotkey_identifier
                }
            }
            
            await self.ws.send(json.dumps(request))
            response = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=1.0))
            
            if response.get("messageType") == "HotkeyTriggerResponse":
                logger.info(f"✅ [VTS] กด hotkey: {hotkey_identifier}")
            elif response.get("messageType") == "APIError":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                logger.warning(f"⚠️ [VTS] ไม่สามารถกด hotkey '{hotkey_identifier}': {error_msg}")
            
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ [VTS] Timeout กด hotkey: {hotkey_identifier}")
        except ConnectionClosed as e:
            logger.warning(f"[VTS] Connection closed while triggering hotkey '{hotkey_identifier}': {e}")
            self.authenticated = False
            self.ws = None
        except Exception as e:
            logger.error(f"❌ [VTS] Error: {e}")

    async def list_model_hotkeys(self) -> List[Dict[str, Any]]:
        if not self.available_hotkeys:
            await self._get_available_hotkeys()
        return self.available_hotkeys

    async def trigger_hotkey_by_name(self, name: str):
        if not self.available_hotkeys:
            await self._get_available_hotkeys()
        target = None
        name_norm = name.strip().lower()
        for hk in self.available_hotkeys:
            n = str(hk.get("name") or hk.get("hotkeyName") or "").strip().lower()
            if n == name_norm:
                target = hk
                break
        if not target:
            logger.warning(f"[VTS] ไม่พบ hotkey ตามชื่อ: {name}")
            return
        identifier = target.get("hotkeyID") or target.get("id") or target.get("identifier")
        if identifier:
            await self.trigger_hotkey(str(identifier))
        else:
            logger.warning(f"[VTS] hotkey '{name}' ไม่มีรหัส ID ให้ทริกเกอร์")

    def set_context_mood(self, mood: str):
        m = (mood or "").strip().lower()
        if m in {"thinking", "happy", "sad", "neutral"}:
            self.mood = m
        else:
            self.mood = "neutral"

    async def maybe_trigger_context_emote(self):
        import time
        now = time.time()
        if now - self._last_emote_ts < self._emote_cooldown_sec:
            return
        p = self._emote_prob.get(self.mood, 0.0)
        if p and random.random() < p:
            await self.trigger_hotkey_by_name(self.mood)
            self._last_emote_ts = now

    def set_speaking(self, is_speaking: bool):
        self.speaking = bool(is_speaking)
        if not self.speaking:
            self.speech_amplitude_target = 0.0

    def update_speech_amplitude(self, level: float):
        lv = max(0.0, min(1.0, float(level)))
        self.speech_amplitude_target = lv

    async def start_idle_loop(self):
        await self.start_random_motion()

    async def stop_idle_loop(self):
        await self.stop_random_motion()
    
    async def start_random_motion(self):
        """เริ่มการเคลื่อนไหวแบบสุ่ม"""
        if self.motion_enabled:
            logger.warning("[VTS] Random motion กำลังทำงานอยู่แล้ว")
            return
        
        if not self.authenticated or not self.ws or getattr(self.ws, "closed", True):
            logger.warning("[VTS] ไม่ได้เชื่อมต่อ/ยังไม่ authenticate จึงไม่เริ่ม random motion")
            return
        
        self.motion_enabled = True
        self.motion_task = asyncio.create_task(self._random_motion_loop())
        logger.info("✅ [VTS] 🎬 เริ่มการเคลื่อนไหวแบบสุ่ม (Hiyori_A Mode)")
    
    async def stop_random_motion(self):
        """หยุดการเคลื่อนไหวแบบสุ่ม"""
        self.motion_enabled = False
        
        if self.motion_task:
            self.motion_task.cancel()
            try:
                await self.motion_task
            except asyncio.CancelledError:
                pass
            self.motion_task = None
        
        # รีเซ็ตค่า parameters กลับเป็น 0
        await self._reset_all_parameters()
        
        logger.info("🛑 [VTS] หยุดการเคลื่อนไหวแบบสุ่ม")

    async def _reset_all_parameters(self):
        """รีเซ็ต parameters ทั้งหมดกลับเป็นค่าปกติ"""
        reset_params = {
            "FaceAngleX": 0, "FaceAngleY": 0, "FaceAngleZ": 0,
            "FacePositionX": 0, "FacePositionY": 0,
            "EyeLeftX": 0, "EyeLeftY": 0,
            "EyeRightX": 0, "EyeRightY": 0,
            "EyeOpenLeft": 1, "EyeOpenRight": 1,
            "MouthSmile": 0, "MouthOpen": 0,
            "BodyAngleX": 0, "BodyAngleY": 0, "BodyAngleZ": 0
        }
        
        for param, value in reset_params.items():
            await self.set_parameter_value(param, value)
    
    async def _random_motion_loop(self):
        """Loop การขยับแบบสุ่ม + ปรับตามบริบท + ขยับปากตามเสียง"""
        logger.info("[VTS] 🎬 เริ่ม random motion loop (Context-aware + Speech mouth)")
        try:
            while self.motion_enabled and self.authenticated and self.ws and not getattr(self.ws, "closed", True):
                # ปรับค่า MouthOpen จากระดับเสียง (smooth)
                if self.speaking:
                    self.speech_amplitude += (self.speech_amplitude_target - self.speech_amplitude) * 0.5
                else:
                    self.speech_amplitude += (0.0 - self.speech_amplitude) * 0.2
                mouth_open = max(0.0, min(1.0, self.speech_amplitude * self.speech_open_scale))
                await self.set_parameter_value("MouthOpen", mouth_open)
                
                # 1) หันหัว
                if random.random() < 0.7:
                    angle_x = random.uniform(-self.head_range, self.head_range)
                    angle_y = random.uniform(-self.head_range * 0.7, self.head_range * 0.7)
                    angle_z = random.uniform(-self.head_range * 0.5, self.head_range * 0.5)
                    await self.set_parameter_value("FaceAngleX", angle_x)
                    await self.set_parameter_value("FaceAngleY", angle_y)
                    await self.set_parameter_value("FaceAngleZ", angle_z)
                
                # 2) มองซ้ายขวาบนล่าง
                if random.random() < 0.85:
                    eye_x = random.uniform(-self.eye_range, self.eye_range)
                    eye_y = random.uniform(-self.eye_range * 0.8, self.eye_range * 0.8)
                    await self.set_parameter_value("EyeLeftX", eye_x)
                    await self.set_parameter_value("EyeLeftY", eye_y)
                    await self.set_parameter_value("EyeRightX", eye_x)
                    await self.set_parameter_value("EyeRightY", eye_y)
                
                # 3) กระพริบตา
                if random.random() < self.blink_frequency:
                    await self.set_parameter_value("EyeOpenLeft", 0)
                    await self.set_parameter_value("EyeOpenRight", 0)
                    await asyncio.sleep(self.blink_duration)
                    await self.set_parameter_value("EyeOpenLeft", 1)
                    await self.set_parameter_value("EyeOpenRight", 1)
                
                # 4) micro-expressions ตามอารมณ์
                if self.mood == "happy" and random.random() < 0.20:
                    smile_value = random.uniform(0.4, 0.8)
                    await self.set_parameter_value("MouthSmile", smile_value)
                    await asyncio.sleep(random.uniform(0.5, 1.2))
                    await self.set_parameter_value("MouthSmile", 0)
                elif self.mood == "sad" and random.random() < 0.15:
                    angle_y = random.uniform(-self.head_range * 0.5, 0)
                    await self.set_parameter_value("FaceAngleY", angle_y)
                elif self.mood == "thinking" and random.random() < 0.18:
                    eye_x = random.uniform(0.2, 0.6)
                    eye_y = random.uniform(0.1, 0.4)
                    await self.set_parameter_value("EyeLeftX", eye_x)
                    await self.set_parameter_value("EyeRightX", eye_x)
                    await self.set_parameter_value("EyeLeftY", eye_y)
                    await self.set_parameter_value("EyeRightY", eye_y)
                else:
                    if random.random() < 0.25:
                        smile_value = random.uniform(0.3, 0.7)
                        await self.set_parameter_value("MouthSmile", smile_value)
                        await asyncio.sleep(random.uniform(0.8, 2.0))
                        await self.set_parameter_value("MouthSmile", 0)
                
                # 5) แกว่งตัว
                if random.random() < 0.35:
                    body_x = random.uniform(-self.body_range, self.body_range)
                    body_y = random.uniform(-self.body_range * 0.5, self.body_range * 0.5)
                    await self.set_parameter_value("BodyAngleX", body_x)
                    await self.set_parameter_value("BodyAngleY", body_y)
                
                # พิจารณากด emote hotkey ตามอารมณ์แบบสุ่มและมี cooldown
                await self.maybe_trigger_context_emote()
                
                # หน่วงเวลาระหว่างการเคลื่อนไหว
                wait_time = random.uniform(self.motion_min_interval, self.motion_max_interval)
                await asyncio.sleep(wait_time)
        except asyncio.CancelledError:
            logger.info("[VTS] Random motion loop ถูกยกเลิก")
        except ConnectionClosed as e:
            logger.warning(f"[VTS] Connection closed inside motion loop: {e}")
            self.authenticated = False
            self.ws = None
        except Exception as e:
            logger.error(f"[VTS] Random motion error: {e}", exc_info=True)

    def _get_message_id(self) -> int:
        """สร้าง message ID ที่ไม่ซ้ำกัน"""
        self.message_id += 1
        return self.message_id
    
    async def _keepalive_loop(self):
        """ส่ง ping เป็นระยะเพื่อรักษาการเชื่อมต่อ"""
        try:
            while self.ws and hasattr(self.ws, 'closed') and not self.ws.closed:
                try:
                    # ส่ง API Statistics request เป็น keepalive
                    keepalive_request = {
                        "apiName": "VTubeStudioPublicAPI",
                        "apiVersion": "1.0",
                        "requestID": str(self._get_message_id()),
                        "messageType": "APIStateRequest"
                    }
                    
                    await self.ws.send(json.dumps(keepalive_request))
                    response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                    
                    # ไม่จำเป็นต้องประมวลผล response เพียงแค่ส่งเพื่อรักษาการเชื่อมต่อ
                    
                except asyncio.TimeoutError:
                    logger.warning("[VTS] Keepalive timeout")
                    break
                except ConnectionClosed:
                    logger.info("[VTS] Connection closed during keepalive")
                    break
                except Exception as e:
                    logger.warning(f"[VTS] Keepalive error: {e}")
                    break
                
                # รอ 30 วินาทีก่อนส่ง keepalive ครั้งต่อไป
                await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            logger.debug("[VTS] Keepalive task cancelled")
        except Exception as e:
            logger.error(f"[VTS] Keepalive loop error: {e}")

    async def disconnect(self):
        """ตัดการเชื่อมต่อ"""
        logger.info("[VTS] กำลังตัดการเชื่อมต่อ...")
        
        await self.stop_random_motion()
        
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
        
        self.authenticated = False
        logger.info("✅ [VTS] ตัดการเชื่อมต่อสำเร็จ")
        try:
            if self._keepalive_task:
                try:
                    self._keepalive_task.cancel()
                except Exception:
                    pass
                self._keepalive_task = None
        except Exception:
            pass


async def test_vts_hiyori():
    """ทดสอบการเชื่อมต่อกับโมเดล Hiyori_A"""
    client = VTSClient()
    
    try:
        if await client.connect():
            print("\n✅ เชื่อมต่อสำเร็จ!")
            print(f"📋 โมเดล: {client.current_model.get('modelName', 'Unknown')}")
            print(f"🎯 Hotkeys: {len(client.available_hotkeys)} อัน")
            print(f"⚙️  Parameters: {len(client.available_parameters)} อัน")
            
            # แสดง hotkeys ที่มี
            print("\n📝 Hotkeys ที่พบ:")
            for hk in client.available_hotkeys[:10]:
                print(f"  - {hk['name']} ({hk['type']})")
            
            # เริ่มการเคลื่อนไหว
            await client.start_random_motion()
            
            # รอ 30 วินาที
            print("\n⏰ กำลังทดสอบการเคลื่อนไหว... (30 วินาที)")
            print("   ดูที่โมเดลว่าขยับหรือไม่")
            await asyncio.sleep(30)
            
            await client.disconnect()
            print("\n✅ ทดสอบสำเร็จ!")
        else:
            print("\n❌ เชื่อมต่อล้มเหลว")
            print("💡 ตรวจสอบ:")
            print("   1. VTube Studio เปิดอยู่หรือไม่")
            print("   2. กด Allow plugin เมื่อมี popup ขึ้นมา")
    
    except KeyboardInterrupt:
        print("\n⚠️ ถูกยกเลิกโดยผู้ใช้")
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(test_vts_hiyori())

    # (removed remaining duplicate global methods)