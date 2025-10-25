from __future__ import annotations
import asyncio
from asyncio import Lock
from typing import Dict, Any, Optional
import json
import random

from adapters.vts import __init__ as _vts_pkg  # noqa: F401
from core.config import get_settings

try:
    import websockets  # type: ignore
except Exception:  # pragma: no cover
    websockets = None  # type: ignore


class VTSClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._ws = None
        self._ws_lock = Lock()  # เพิ่ม lock สำหรับป้องกัน concurrent access
        self._idle_task: Optional[asyncio.Task] = None
        self._blink_task: Optional[asyncio.Task] = None
        self._breathing_task: Optional[asyncio.Task] = None
        self._random_smile_task: Optional[asyncio.Task] = None
        self._auto_gaze_task: Optional[asyncio.Task] = None
        self._random_animations_task: Optional[asyncio.Task] = None
        self._micro_expr_task: Optional[asyncio.Task] = None
        self._last_send_ts: float = 0.0
        self._min_send_interval: float = 1.0 / float(getattr(self.settings, "VTS_INJECT_MAX_FPS", 30.0))
        self._param_map: Dict[str, str] = {}
        self._is_connected: bool = False
        self._reconnecting: bool = False
        
        # Speaking state tracking
        self._is_speaking: bool = False
        self._speaking_lock = Lock()

    async def connect(self):
        """Connect to VTS with proper session management"""
        # ป้องกันการ connect ซ้ำ
        if self._ws and not self._ws.closed and self._is_connected:
            print("[VTS] Already connected")
            return
        
        if not websockets:
            print("[VTS] websockets library not available")
            return
        
        uri = f"ws://{self.settings.VTS_HOST}:{self.settings.VTS_PORT}"
        
        try:
            # ปิด connection เก่าก่อน (ถ้ามี)
            if self._ws:
                try:
                    await self._ws.close()
                except:
                    pass
                self._ws = None
            
            self._is_connected = False
            
            # สร้าง connection ใหม่
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    uri, 
                    ping_interval=20,
                    ping_timeout=15,
                    max_queue=64,
                    close_timeout=10
                ),
                timeout=10.0
            )
            print(f"Connected to VTS at {uri}")

            # Authentication
            await self._authenticate()
            
            # Setup parameters
            await self._ensure_custom_parameters()
            await asyncio.sleep(0.5)  # รอให้ VTS ประมวลผล
            await self._build_param_mapping()
            
            self._is_connected = True
            
        except asyncio.TimeoutError:
            print(f"[VTS] Connection timeout to {uri}")
            self._ws = None
            self._is_connected = False
        except Exception as e:
            print(f"[VTS] Connect failed: {e}")
            self._ws = None
            self._is_connected = False

    async def _authenticate(self):
        """Separate authentication logic"""
        if not self._ws:
            return
        
        plugin_name = getattr(self.settings, "VTS_PLUGIN_NAME", "AI VTuber Demo")
        plugin_dev = "AI VTuber Demo"
        token = getattr(self.settings, "VTS_PLUGIN_TOKEN", None)
        
        # Request token if not exists
        if not token:
            try:
                token_req = {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "messageType": "AuthenticationTokenRequest",
                    "requestID": "auth-token",
                    "data": {
                        "pluginName": plugin_name,
                        "pluginDeveloper": plugin_dev
                    }
                }
                async with self._ws_lock:
                    await self._ws.send(json.dumps(token_req))
                    resp = await asyncio.wait_for(self._ws.recv(), timeout=8.0)
                
                j = json.loads(resp)
                token = j.get("data", {}).get("authenticationToken")
                if token:
                    print(f"[VTS] Got new token: {token[:20]}...")
            except Exception as e:
                print(f"[VTS] Token request failed: {e}")
                return
        
        # Authenticate
        payload = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "messageType": "AuthenticationRequest",
            "requestID": "auth-1",
            "data": {
                "pluginName": plugin_name,
                "pluginDeveloper": plugin_dev,
                "authenticationToken": token
            }
        }
        
        try:
            async with self._ws_lock:
                await self._ws.send(json.dumps(payload))
                resp = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            print(f"[VTS] Auth response: {resp}")
        except Exception as e:
            print(f"[VTS] Auth failed: {e}")

    async def set_expression(self, expression: str, active: bool = True):
        """เปิด/ปิด expression ตามชื่อ"""
        if not self._ws or self._ws.closed:
            return
        
        msg = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "messageType": "SetExpressionStateRequest",
            "requestID": f"expr-{expression}",
            "data": {
                "expressionName": expression,
                "active": bool(active)
            }
        }
        try:
            async with self._ws_lock:
                await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] set_expression failed: {e}")
            await self._handle_disconnect()

    async def set_parameter(self, name: str, value: float):
        """ปรับค่า parameter เดี่ยว"""
        if not self._ws or self._ws.closed:
            return
        
        msg = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "messageType": "SetParameterValueRequest",
            "requestID": f"param-{name}",
            "data": {
                "name": name,
                "value": float(value)
            }
        }
        try:
            async with self._ws_lock:
                await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] set_parameter failed: {e}")
            await self._handle_disconnect()

    async def _build_param_mapping(self):
        """ดึงรายชื่อพารามิเตอร์ของโมเดลจาก VTS และสร้าง mapping อัตโนมัติ"""
        if not self._ws or self._ws.closed:
            return
        
        try:
            req = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "messageType": "InputParameterListRequest",
                "requestID": "param-list",
                "data": {}
            }
            
            async with self._ws_lock:
                await self._ws.send(json.dumps(req))
                resp = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            
            names: list[str] = []
            try:
                j = json.loads(resp)
                params = j.get("data", {}).get("defaultParameters", [])
                if not params:
                    params = j.get("data", {}).get("customParameters", [])
                names = [str(p.get("name", "")) for p in params]
            except Exception:
                names = []
            
            if not names:
                print("[VTS] No parameters found, using defaults")
                # ใช้ค่าเริ่มต้นสำหรับโมเดล Hiyori
                self._param_map = {
                    "BodyAngleX": "ParamAngleX",
                    "BodyAngleY": "ParamAngleY",
                    "BodyAngleZ": "ParamAngleZ",
                    "EyeLeftOpen": "ParamEyeLOpen",
                    "EyeRightOpen": "ParamEyeROpen",
                    "MouthOpen": "ParamMouthOpenY",
                    "MouthSmile": "ParamMouthSmile"
                }
                print(f"[VTS] Using default param mapping: {self._param_map}")
                return
            
            lower = [n.lower() for n in names]
            
            def find_one(candidates: list[str]) -> Optional[str]:
                for cand in candidates:
                    cand_l = cand.lower()
                    for i, n in enumerate(lower):
                        if cand_l in n:
                            return names[i]
                return None
            
            # สร้าง mapping
            mapping: Dict[str, str] = {}
            
            # มุมร่างกาย
            mapping["BodyAngleX"] = find_one(["anglex", "paramanglex"]) or "ParamAngleX"
            mapping["BodyAngleY"] = find_one(["angley", "paramangley"]) or "ParamAngleY"
            mapping["BodyAngleZ"] = find_one(["anglez", "paramanglez"]) or "ParamAngleZ"
            
            # ตาเปิด
            mapping["EyeLeftOpen"] = find_one(["eyelopen", "eyelopen_l", "eyelopenleft", "parameyelopen"]) or "ParamEyeLOpen"
            mapping["EyeRightOpen"] = find_one(["eyeropen", "eyelopen_r", "eyelopenright", "parameyer open"]) or "ParamEyeROpen"
            
            # การมอง
            lookx = find_one(["eyeballx", "lookx", "parameyelookx", "eyex"])
            looky = find_one(["eyebally", "looky", "parameyelooky", "eyey"])
            if lookx:
                mapping["EyeLookX"] = lookx
            if looky:
                mapping["EyeLookY"] = looky
            
            # ปาก
            mapping["MouthOpen"] = find_one(["mouthopeny", "mouthopen", "parammouthopen"]) or "ParamMouthOpenY"
            mapping["MouthSmile"] = find_one(["mouthsmile", "mouthform"]) or "ParamMouthSmile"
            
            # รอยยิ้มและอื่นๆ
            eye_smile = find_one(["eyesmile", "parameyesmile"])
            if eye_smile:
                mapping["EyeSmile"] = eye_smile
            
            cheek = find_one(["cheek", "paramcheek"])
            if cheek:
                mapping["Cheek"] = cheek
            
            # คิ้ว
            for side in ["Left", "Right"]:
                for dir in ["Up", "Down"]:
                    key = f"Brow{side}{dir}"
                    param = find_one([f"brow{side.lower()}{dir.lower()}", f"parambrow{side.lower()}{dir.lower()}"])
                    if param:
                        mapping[key] = param
            
            self._param_map = mapping
            print(f"[VTS] Param mapping: {self._param_map}")
            
        except Exception as e:
            print(f"[VTS] build_param_mapping failed: {e}")
            # ใช้ค่าเริ่มต้น
            self._param_map = {
                "BodyAngleX": "ParamAngleX",
                "BodyAngleY": "ParamAngleY",
                "BodyAngleZ": "ParamAngleZ",
                "EyeLeftOpen": "ParamEyeLOpen",
                "EyeRightOpen": "ParamEyeROpen",
                "MouthOpen": "ParamMouthOpenY",
                "MouthSmile": "ParamMouthSmile"
            }

    async def inject_parameters(self, values: Dict[str, float], weight: Optional[float] = None):
        """ส่งค่า parameter หลายตัวพร้อมกัน"""
        if not self._ws or self._ws.closed:
            return
        
        # Throttle
        now = asyncio.get_event_loop().time()
        dt = now - self._last_send_ts
        if dt < self._min_send_interval:
            await asyncio.sleep(self._min_send_interval - dt)
        
        self._last_send_ts = asyncio.get_event_loop().time()
        
        # Build values
        w = float(weight if weight is not None else getattr(self.settings, "IDLE_MOTION_SENSITIVITY", 1.0))
        data_values = []
        
        for k, v in values.items():
            mapped_name = self._param_map.get(k, k)
            kl = mapped_name.lower()
            
            # กำหนดช่วงค่า
            if ("angle" in kl) or ("look" in kl):
                vmin, vmax = -30.0, 30.0
            elif "smile" in kl:
                vmin, vmax = -1.0, 1.0
            else:
                vmin, vmax = 0.0, 1.0
            
            try:
                safe_v = max(vmin, min(vmax, float(v)))
            except Exception:
                safe_v = vmin
            
            data_values.append({
                "id": mapped_name,
                "value": float(safe_v),
                "weight": float(w)
            })
        
        msg = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "messageType": "InjectParameterDataRequest",
            "requestID": "inject-params",
            "data": {
                "parameterValues": data_values,
                "faceFound": True,
                "mode": "set"
            }
        }
        
        try:
            async with self._ws_lock:
                await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] inject_parameters failed: {e}")
            await self._handle_disconnect()

    async def trigger_hotkey_by_name(self, name: str):
        """ทริกเกอร์ hotkey โดยใช้ชื่อ"""
        if not self._ws or self._ws.closed:
            return
        
        try:
            msg = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "messageType": "HotkeyTriggerRequest",
                "requestID": "trigger-hotkey",
                "data": {
                    "hotkeyID": name
                }
            }
            async with self._ws_lock:
                await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] trigger_hotkey failed: {e}")
            await self._handle_disconnect()

    async def trigger_hotkey(self, hotkey_name: str):
        """ทริกเกอร์ hotkey โดยใช้ชื่อ hotkey จาก settings"""
        try:
            hotkey_map = {
                "Happy": getattr(self.settings, "VTS_HK_HAPPY", "Happy"),
                "Sad": getattr(self.settings, "VTS_HK_SAD", "Sad"),
                "Angry": getattr(self.settings, "VTS_HK_ANGRY", "Angry"),
                "Surprised": getattr(self.settings, "VTS_HK_SURPRISED", "Surprised"),
                "Neutral": getattr(self.settings, "VTS_HK_NEUTRAL", "Neutral"),
                "Thinking": getattr(self.settings, "VTS_HK_THINKING", "Thinking"),
                "Calm": getattr(self.settings, "VTS_HK_CALM", "Calm"),
            }
            
            hotkey_id = hotkey_map.get(hotkey_name, hotkey_name)
            await self.trigger_hotkey_by_name(hotkey_id)
        except Exception as e:
            print(f"[VTS] trigger_hotkey '{hotkey_name}' failed: {e}")

    async def start_idle_motion(self):
        """การเคลื่อนไหวแบบสุ่มสมบูรณ์"""
        if self._idle_task and not self._idle_task.done():
            return

        async def _runner():
            amp = float(getattr(self.settings, "IDLE_MOTION_AMPLITUDE", 0.4))
            base_interval = float(getattr(self.settings, "IDLE_MOTION_INTERVAL", 2.0))
            
            while True:
                try:
                    if not self._is_connected or not self._ws or self._ws.closed:
                        await asyncio.sleep(1.0)
                        continue
                    
                    # ลดการเคลื่อนไหวขณะพูด
                    async with self._speaking_lock:
                        current_amp = amp * 0.2 if self._is_speaking else amp
                        current_interval = base_interval * 2.0 if self._is_speaking else base_interval
                    
                    x_pos = random.uniform(-current_amp, current_amp)
                    y_pos = random.uniform(-current_amp * 0.3, current_amp * 0.3)
                    weight = random.uniform(0.3, 0.8) if self._is_speaking else random.uniform(0.5, 1.5)
                    
                    vals = {
                        "BodyAngleY": x_pos,
                        "BodyAngleX": y_pos,
                    }
                    await self.inject_parameters(vals, weight=weight)
                    
                    random_interval = random.uniform(current_interval * 0.3, current_interval * 2.5)
                    await asyncio.sleep(random_interval)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"[VTS] idle_motion error: {e}")
                    await asyncio.sleep(base_interval)
        
        self._idle_task = asyncio.create_task(_runner())

    async def start_blinking(self):
        """กระพริบตาแบบสุ่มสมบูรณ์"""
        if self._blink_task and not self._blink_task.done():
            return

        async def _runner():
            min_i = float(getattr(self.settings, "BLINK_MIN_INTERVAL", 3.0))
            max_i = float(getattr(self.settings, "BLINK_MAX_INTERVAL", 6.0))
            close_ms = int(getattr(self.settings, "BLINK_CLOSE_MS", 120))
            dbl_prob = float(getattr(self.settings, "BLINK_DOUBLE_PROB", 0.2))
            
            while True:
                try:
                    if not self._is_connected or not self._ws or self._ws.closed:
                        await asyncio.sleep(1.0)
                        continue
                    
                    if random.random() < 0.1:
                        interval = random.uniform(0.5, 15.0)
                    else:
                        interval = random.uniform(min_i, max_i)
                    
                    await asyncio.sleep(interval)
                    
                    close_time = random.uniform(close_ms * 0.5, close_ms * 2.0) / 1000.0
                    
                    # ปิดตา
                    await self.inject_parameters({"EyeLeftOpen": 0.0, "EyeRightOpen": 0.0}, weight=1.0)
                    await asyncio.sleep(close_time)
                    # เปิดตา
                    await self.inject_parameters({"EyeLeftOpen": 1.0, "EyeRightOpen": 1.0}, weight=1.0)
                    
                    # กระพริบซ้อน
                    if random.random() < dbl_prob:
                        extra_blinks = random.randint(1, 3)
                        for _ in range(extra_blinks):
                            await asyncio.sleep(random.uniform(0.05, 0.2))
                            await self.inject_parameters({"EyeLeftOpen": 0.0, "EyeRightOpen": 0.0}, weight=1.0)
                            await asyncio.sleep(random.uniform(close_time * 0.5, close_time))
                            await self.inject_parameters({"EyeLeftOpen": 1.0, "EyeRightOpen": 1.0}, weight=1.0)
                            
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(min_i)
        
        self._blink_task = asyncio.create_task(_runner())

    async def start_breathing(self):
        """การหายใจแบบสุ่มสมบูรณ์"""
        if self._breathing_task and not self._breathing_task.done():
            return

        async def _runner():
            min_i = float(getattr(self.settings, "BREATHING_MIN_INTERVAL", 2.5))
            max_i = float(getattr(self.settings, "BREATHING_MAX_INTERVAL", 8.0))
            min_int = float(getattr(self.settings, "BREATHING_MIN_INTENSITY", 0.1))
            max_int = float(getattr(self.settings, "BREATHING_MAX_INTENSITY", 0.4))
            min_dur = float(getattr(self.settings, "BREATHING_MIN_DURATION", 1.2))
            max_dur = float(getattr(self.settings, "BREATHING_MAX_DURATION", 3.5))
            
            while True:
                try:
                    if not self._is_connected or not self._ws or self._ws.closed:
                        await asyncio.sleep(1.0)
                        continue
                    
                    if random.random() < 0.15:
                        interval = random.uniform(0.8, 20.0)
                    else:
                        interval = random.uniform(min_i, max_i)
                    
                    await asyncio.sleep(interval)
                    
                    intensity = random.uniform(min_int, max_int)
                    duration = random.uniform(min_dur, max_dur)
                    breath_type = random.choice(["in_out", "in_only", "out_only", "irregular"])
                    
                    if breath_type == "in_out":
                        await self.inject_parameters({"BodyAngleZ": intensity}, weight=0.8)
                        await asyncio.sleep(duration * 0.4)
                        await self.inject_parameters({"BodyAngleZ": -intensity * 0.3}, weight=0.6)
                        await asyncio.sleep(duration * 0.6)
                        await self.inject_parameters({"BodyAngleZ": 0.0}, weight=0.5)
                        
                    elif breath_type == "irregular":
                        steps = random.randint(3, 7)
                        for i in range(steps):
                            val = random.uniform(-intensity, intensity)
                            weight = random.uniform(0.3, 1.0)
                            await self.inject_parameters({"BodyAngleZ": val}, weight=weight)
                            await asyncio.sleep(duration / steps * random.uniform(0.5, 2.0))
                        await self.inject_parameters({"BodyAngleZ": 0.0}, weight=0.5)
                        
                    else:
                        val = intensity if breath_type == "in_only" else -intensity * 0.5
                        await self.inject_parameters({"BodyAngleZ": val}, weight=0.7)
                        await asyncio.sleep(duration)
                        await self.inject_parameters({"BodyAngleZ": 0.0}, weight=0.5)
                        
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(min_i)
        
        self._breathing_task = asyncio.create_task(_runner())

    async def start_random_smile(self):
        """ยิ้มมุมปากแบบสุ่มสมบูรณ์"""
        if self._random_smile_task and not self._random_smile_task.done():
            return

        async def _runner():
            min_i = float(getattr(self.settings, "RANDOM_SMILE_MIN_INTERVAL", 15.0))
            max_i = float(getattr(self.settings, "RANDOM_SMILE_MAX_INTERVAL", 45.0))
            min_int = float(getattr(self.settings, "RANDOM_SMILE_MIN_INTENSITY", 0.2))
            max_int = float(getattr(self.settings, "RANDOM_SMILE_MAX_INTENSITY", 0.6))
            min_dur = float(getattr(self.settings, "RANDOM_SMILE_MIN_DURATION", 2.0))
            max_dur = float(getattr(self.settings, "RANDOM_SMILE_MAX_DURATION", 8.0))
            fade_time = float(getattr(self.settings, "RANDOM_SMILE_FADE_TIME", 0.8))
            
            while True:
                try:
                    if not self._is_connected or not self._ws or self._ws.closed:
                        await asyncio.sleep(1.0)
                        continue
                    
                    if random.random() < 0.2:
                        interval = random.uniform(5.0, 120.0)
                    else:
                        interval = random.uniform(min_i, max_i)
                    
                    await asyncio.sleep(interval)
                    
                    smile_type = random.choice([
                        "gentle", "wide", "smirk", "half_smile", 
                        "gradual", "quick_flash", "sustained"
                    ])
                    
                    intensity = random.uniform(min_int, max_int)
                    duration = random.uniform(min_dur, max_dur)
                    
                    if smile_type == "gradual":
                        steps = random.randint(5, 12)
                        for i in range(steps):
                            current_intensity = intensity * (i + 1) / steps
                            await self.inject_parameters({"MouthSmile": current_intensity}, weight=0.6)
                            await asyncio.sleep(duration * 0.3 / steps)
                        
                        await asyncio.sleep(duration * 0.4)
                        
                        for i in range(steps):
                            current_intensity = intensity * (steps - i) / steps
                            await self.inject_parameters({"MouthSmile": current_intensity}, weight=0.6)
                            await asyncio.sleep(duration * 0.3 / steps)
                            
                    elif smile_type == "quick_flash":
                        await self.inject_parameters({"MouthSmile": intensity * 1.2}, weight=0.8)
                        await asyncio.sleep(random.uniform(0.3, 0.8))
                        await self.inject_parameters({"MouthSmile": 0.0}, weight=0.6)
                        
                    elif smile_type == "sustained":
                        await self.inject_parameters({"MouthSmile": intensity}, weight=0.7)
                        await asyncio.sleep(duration * random.uniform(1.5, 3.0))
                        await self.inject_parameters({"MouthSmile": 0.0}, weight=0.5)
                        
                    else:
                        final_intensity = intensity * random.uniform(0.7, 1.3)
                        await self.inject_parameters({"MouthSmile": final_intensity}, weight=0.7)
                        await asyncio.sleep(duration)
                        
                        fade_steps = random.randint(3, 8)
                        for i in range(fade_steps):
                            current = final_intensity * (fade_steps - i) / fade_steps
                            await self.inject_parameters({"MouthSmile": current}, weight=0.5)
                            await asyncio.sleep(fade_time / fade_steps)
                    
                    await self.inject_parameters({"MouthSmile": 0.0}, weight=0.4)
                    
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(min_i)
        
        self._random_smile_task = asyncio.create_task(_runner())

    async def start_auto_gaze(self):
        """มองซ้ายขวา/ขึ้นลงแบบสุ่ม"""
        if self._auto_gaze_task and not self._auto_gaze_task.done():
            return
            
        async def _runner():
            min_i = float(getattr(self.settings, "AUTO_GAZE_MIN_INTERVAL", 3.0))
            max_i = float(getattr(self.settings, "AUTO_GAZE_MAX_INTERVAL", 8.0))
            min_dur = float(getattr(self.settings, "AUTO_GAZE_MIN_DURATION", 0.6))
            max_dur = float(getattr(self.settings, "AUTO_GAZE_MAX_DURATION", 2.0))
            amp = float(getattr(self.settings, "AUTO_GAZE_AMPLITUDE", 0.7))
            
            while True:
                try:
                    if not self._is_connected or not self._ws or self._ws.closed:
                        await asyncio.sleep(1.0)
                        continue
                    
                    await asyncio.sleep(random.uniform(min_i, max_i))
                    
                    lx = self._param_map.get("EyeLookX")
                    ly = self._param_map.get("EyeLookY")
                    
                    if not lx and not ly:
                        await asyncio.sleep(5.0)
                        continue
                    
                    dur = random.uniform(min_dur, max_dur)
                    tx = random.uniform(-amp, amp) if lx else None
                    ty = random.uniform(-amp, amp) if ly else None
                    
                    steps = max(3, int(dur / 0.1))
                    for i in range(steps):
                        fx = (i + 1) / steps
                        vals = {}
                        if lx and tx is not None:
                            vals["EyeLookX"] = tx * fx
                        if ly and ty is not None:
                            vals["EyeLookY"] = ty * fx
                        await self.inject_parameters(vals, weight=0.6)
                        await asyncio.sleep(0.1)    
                    
                    await asyncio.sleep(random.uniform(0.1, 0.6))
                    
                    back_steps = random.randint(3, 8)
                    for i in range(back_steps):
                        fx = (back_steps - i) / back_steps
                        vals = {}
                        if lx and tx is not None:
                            vals["EyeLookX"] = tx * fx
                        if ly and ty is not None:
                            vals["EyeLookY"] = ty * fx
                        await self.inject_parameters(vals, weight=0.5)
                        await asyncio.sleep(0.1)
                    
                    vals = {}
                    if lx:
                        vals["EyeLookX"] = 0.0
                    if ly:
                        vals["EyeLookY"] = 0.0
                    await self.inject_parameters(vals, weight=0.5)
                    
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(min_i)
        
        self._auto_gaze_task = asyncio.create_task(_runner())

    async def start_random_animations(self):
        """เริ่มงานพื้นหลัง เล่นอนิเมชันตาม hotkeys ของโมเดลแบบสุ่ม"""
        if self._random_animations_task and not self._random_animations_task.done():
            return
        self._random_animations_task = asyncio.create_task(self._run_random_animations_loop())

    async def start_micro_expressions(self):
        """แสดง micro expressions แบบสุ่ม"""
        if self._micro_expr_task and not self._micro_expr_task.done():
            return
            
        async def _runner():
            min_i = float(getattr(self.settings, "MICRO_EXPR_MIN_INTERVAL", 5.0))
            max_i = float(getattr(self.settings, "MICRO_EXPR_MAX_INTERVAL", 18.0))
            
            while True:
                try:
                    if not self._is_connected or not self._ws or self._ws.closed:
                        await asyncio.sleep(1.0)
                        continue
                    
                    await asyncio.sleep(random.uniform(min_i, max_i))
                    
                    actions = []
                    if self._param_map.get("EyeSmile"):
                        actions.append("EyeSmile")
                    if self._param_map.get("Cheek"):
                        actions.append("Cheek")
                    
                    brow_candidates = ["BrowLeftUp", "BrowRightUp", "BrowLeftDown", "BrowRightDown"]
                    actions += [b for b in brow_candidates if self._param_map.get(b)]
                    
                    if not actions:
                        await asyncio.sleep(5.0)
                        continue
                    
                    k = random.randint(1, min(2, len(actions)))
                    chosen = random.sample(actions, k)
                    intensity = random.uniform(0.2, 0.7)
                    
                    vals = {name: intensity for name in chosen}
                    await self.inject_parameters(vals, weight=0.6)
                    await asyncio.sleep(random.uniform(0.5, 2.0))
                    
                    fade_steps = random.randint(3, 6)
                    for i in range(fade_steps):
                        fx = (fade_steps - i) / fade_steps
                        vals = {name: intensity * fx for name in chosen}
                        await self.inject_parameters(vals, weight=0.5)
                        await asyncio.sleep(random.uniform(0.1, 0.25))
                    
                    vals = {name: 0.0 for name in chosen}
                    await self.inject_parameters(vals, weight=0.4)
                    
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(min_i)
        
        self._micro_expr_task = asyncio.create_task(_runner())

    def _emotion_trigger_prob(self, emotion_key: str) -> float:
        """คำนวณความน่าจะเป็นของการทริกเกอร์อีโมท"""
        k = str(emotion_key).lower()
        base_prob = float(getattr(self.settings, "EMOTION_TRIGGER_PROBABILITY", 0.3))
        random_factor = random.uniform(0.5, 2.0)
        
        if random.random() < 0.1:
            return random.choice([0.0, 1.0])
        
        if k in ["happy", "joy", "excited"]:
            prob = base_prob * random_factor * random.uniform(0.8, 1.5)
        elif k in ["sad", "disappointed", "upset"]:
            prob = base_prob * random_factor * random.uniform(0.6, 1.2)
        elif k in ["angry", "frustrated", "annoyed"]:
            prob = base_prob * random_factor * random.uniform(0.7, 1.3)
        elif k in ["surprised", "shocked", "amazed"]:
            prob = base_prob * random_factor * random.uniform(0.9, 1.6)
        else:
            prob = base_prob * random_factor * random.uniform(0.5, 1.4)
        
        return min(1.0, max(0.0, prob))

    async def apply_emotion(self, emotion_config: Dict[str, Any]):
        """ใช้อีโมทกับโมเดล"""
        if not self._ws or self._ws.closed:
            return
        
        # ดึง emotion key จาก config
        emotion_key = emotion_config.get("_emotion_key", "neutral")
        intensity = float(emotion_config.get("intensity", 1.0))
        
        # ตรวจสอบว่าจะทริกเกอร์หรือไม่
        trigger_prob = self._emotion_trigger_prob(emotion_key)
        random_threshold = random.uniform(0.0, 1.0)
        
        if random_threshold > trigger_prob:
            if random.random() < 0.3:
                subtle_actions = ["MouthSmile", "EyeLeftOpen", "EyeRightOpen"]
                action = random.choice(subtle_actions)
                subtle_intensity = random.uniform(0.1, 0.3)
                await self.inject_parameters({action: subtle_intensity}, weight=0.3)
                await asyncio.sleep(random.uniform(0.5, 2.0))
                await self.inject_parameters({action: 0.0}, weight=0.2)
            return
        
        emotion_lower = emotion_key.lower()
        hotkey_name = None
        
        if emotion_lower in ["happy", "joy", "excited"]:
            if random.random() < 0.8:
                hotkey_name = "Happy"
            else:
                await self.inject_parameters({"EyeLeftOpen": 0.8, "EyeRightOpen": 0.8}, weight=0.6)
                await asyncio.sleep(random.uniform(1.0, 3.0))
                await self.inject_parameters({"EyeLeftOpen": 1.0, "EyeRightOpen": 1.0}, weight=0.4)
                return
                
        elif emotion_lower in ["sad", "disappointed", "upset"]:
            if random.random() < 0.6:
                hotkey_name = "Sad" if random.random() < 0.7 else "Neutral"
            else:
                await self.inject_parameters({"MouthSmile": -0.2}, weight=0.5)
                await asyncio.sleep(random.uniform(2.0, 5.0))
                await self.inject_parameters({"MouthSmile": 0.0}, weight=0.3)
                return
                
        elif emotion_lower in ["angry", "frustrated", "annoyed"]:
            hotkey_name = "Angry" if random.random() < 0.8 else "Neutral"
            
        elif emotion_lower in ["surprised", "shocked", "amazed"]:
            hotkey_name = "Surprised" if random.random() < 0.9 else "Happy"
            
        else:
            possible_emotions = ["Neutral", "Happy", "Surprised"]
            hotkey_name = random.choice(possible_emotions)
        
        if hotkey_name:
            await self.trigger_hotkey(hotkey_name)
            
            if random.random() < 0.4:
                await asyncio.sleep(random.uniform(0.5, 2.0))
                extra_params = {}
                
                if hotkey_name == "Happy":
                    extra_params["MouthSmile"] = random.uniform(0.2, 0.6)
                elif hotkey_name == "Surprised":
                    extra_params["EyeLeftOpen"] = random.uniform(1.2, 1.5)
                    extra_params["EyeRightOpen"] = random.uniform(1.2, 1.5)
                elif hotkey_name == "Sad":
                    extra_params["MouthSmile"] = random.uniform(-0.3, -0.1)
                
                if extra_params:
                    await self.inject_parameters(extra_params, weight=random.uniform(0.4, 0.8))
                    await asyncio.sleep(random.uniform(1.0, 4.0))
                    reset_params = {k: 0.0 for k in extra_params.keys()}
                    await self.inject_parameters(reset_params, weight=0.3)

    async def lipsync_wav(self, wav_path: str, param_name: Optional[str] = None):
        """อ่านไฟล์ WAV และอัปเดตพารามิเตอร์ปากแบบเรียลไทม์"""
        if not self._ws or self._ws.closed:
            return
        
        import wave, struct, math
        
        try:
            p_name = param_name or self._param_map.get("MouthOpen", "ParamMouthOpenY")
            frame_ms = float(getattr(self.settings, "LIPSYNC_FRAME_MS", 30.0))
            
            with wave.open(wav_path, 'rb') as w:
                n_channels = w.getnchannels()
                sampwidth = w.getsampwidth()
                framerate = w.getframerate()
                nframes = w.getnframes()
                
                block_size = max(1, int(framerate * (frame_ms/1000.0)))
                fmt = {1:'b', 2:'h', 4:'i'}.get(sampwidth, 'h')
                max_val = float({1:127, 2:32767, 4:2147483647}.get(sampwidth, 32767))
                
                idx = 0
                while idx < nframes:
                    if not self._is_connected or not self._ws or self._ws.closed:
                        break
                    
                    to_read = min(block_size, nframes - idx)
                    raw = w.readframes(to_read)
                    count = to_read * n_channels
                    samples = struct.unpack('<' + fmt*count, raw)
                    
                    if n_channels > 1:
                        mono = []
                        for i in range(0, len(samples), n_channels):
                            s = sum(samples[i:i+n_channels]) / n_channels
                            mono.append(s)
                        samples = mono
                    
                    if not samples:
                        rms = 0.0
                    else:
                        acc = 0.0
                        for s in samples:
                            acc += (float(s)/max_val)**2
                        rms = math.sqrt(acc/len(samples))
                    
                    mouth = min(1.0, max(0.0, rms*1.8))
                    
                    try:
                        await self.inject_parameters({p_name: mouth}, weight=0.8)
                    except Exception:
                        pass
                    
                    await asyncio.sleep(frame_ms/1000.0)
                    idx += to_read
            
            try:
                await self.inject_parameters({p_name: 0.0}, weight=0.5)
            except Exception:
                pass
                
        except Exception as e:
            print(f"[VTS] lipsync_wav failed: {e}")

    async def lipsync_bytes(self, wav_bytes: bytes, param_name: Optional[str] = None):
        """ลิปซิงก์จาก WAV bytes ในหน่วยความจำ"""
        if not self._ws or self._ws.closed:
            return
        
        import wave, struct, math, io
        
        # ตั้งสถานะการพูด
        async with self._speaking_lock:
            self._is_speaking = True
        
        try:
            p_name = param_name or self._param_map.get("MouthOpen", "ParamMouthOpenY")
            frame_ms = float(getattr(self.settings, "LIPSYNC_FRAME_MS", 30.0))
            
            with wave.open(io.BytesIO(wav_bytes), 'rb') as w:
                n_channels = w.getnchannels()
                sampwidth = w.getsampwidth()
                framerate = w.getframerate()
                nframes = w.getnframes()
                
                block_size = max(1, int(framerate * (frame_ms/1000.0)))
                fmt = {1:'b', 2:'h', 4:'i'}.get(sampwidth, 'h')
                max_val = float({1:127, 2:32767, 4:2147483647}.get(sampwidth, 32767))
                
                idx = 0
                while idx < nframes:
                    if not self._is_connected or not self._ws or self._ws.closed:
                        break
                    
                    to_read = min(block_size, nframes - idx)
                    raw = w.readframes(to_read)
                    count = to_read * n_channels
                    samples = struct.unpack('<' + fmt*count, raw)
                    
                    if n_channels > 1:
                        mono = []
                        for i in range(0, len(samples), n_channels):
                            s = sum(samples[i:i+n_channels]) / n_channels
                            mono.append(s)
                        samples = mono
                    
                    if not samples:
                        rms = 0.0
                    else:
                        acc = 0.0
                        for s in samples:
                            acc += (float(s)/max_val)**2
                        rms = math.sqrt(acc/len(samples))
                    
                    mouth = min(1.0, max(0.0, rms*1.8))
                    
                    try:
                        await self.inject_parameters({p_name: mouth}, weight=0.8)
                    except Exception:
                        pass
                    
                    await asyncio.sleep(frame_ms/1000.0)
                    idx += to_read
            
            try:
                await self.inject_parameters({p_name: 0.0}, weight=0.5)
            except Exception:
                pass
                
        except Exception as e:
            print(f"[VTS] lipsync_bytes failed: {e}")
        finally:
            # รีเซ็ตสถานะการพูด
            async with self._speaking_lock:
                self._is_speaking = False

    async def start_thinking_animation(self):
        """เริ่มอนิเมชันขณะกำลังคิด สำหรับตอนสร้างคำตอบยาวๆ"""
        try:
            # ใช้อนิเมชันที่เหมาะสมสำหรับการคิด
            thinking_animations = ["Think", "Thinking", "Idle", "Ponder", "Concentrate"]
            
            # ลองหาอนิเมชันที่มีอยู่
            hotkeys = await self._list_model_hotkeys()
            available_thinking = []
            
            for anim_name in thinking_animations:
                for hk in hotkeys:
                    if anim_name.lower() in str(hk.get("name", "")).lower():
                        available_thinking.append(hk.get("name"))
                        break
            
            if available_thinking:
                chosen = random.choice(available_thinking)
                print(f"[VTS] Starting thinking animation: {chosen}")
                await self.trigger_hotkey_by_name(chosen)
            else:
                # ถ้าไม่มีอนิเมชันเฉพาะ ใช้การเคลื่อนไหวเบาๆ
                vals = {
                    "BodyAngleY": random.uniform(-0.1, 0.1),
                    "BodyAngleX": random.uniform(-0.05, 0.05),
                }
                await self.inject_parameters(vals, weight=0.3)
                
        except Exception as e:
            print(f"[VTS] thinking animation failed: {e}")

    async def stop_thinking_animation(self):
        """หยุดอนิเมชันขณะคิด"""
        try:
            # รีเซ็ตท่าทางกลับเป็นปกติ
            vals = {
                "BodyAngleY": 0.0,
                "BodyAngleX": 0.0,
            }
            await self.inject_parameters(vals, weight=0.5)
        except Exception as e:
             print(f"[VTS] stop thinking animation failed: {e}")

    async def trigger_manual_emotion(self, emotion_type: str):
        """ทริกเกอร์อีโมทแบบ manual ที่ต้องกดใช้เอง
        
        Args:
            emotion_type: ประเภทอีโมท ('thinking', 'happy', 'sad', 'angry', 'surprised')
        """
        if not getattr(self.settings, "MANUAL_EMOTIONS_ENABLED", True):
            print("[VTS] Manual emotions are disabled")
            return
            
        try:
            manual_emotions = {
                'thinking': {
                    'expressions': ['Think', 'Thinking', 'Ponder', 'Concentrate'],
                    'params': {
                        'BodyAngleY': 0.1,
                        'BodyAngleX': -0.05,
                        'EyeLeftOpen': 0.7,
                        'EyeRightOpen': 0.7
                    },
                    'weight': 0.6
                },
                'happy': {
                    'expressions': ['Happy', 'Joy', 'Smile', 'Cheerful'],
                    'params': {
                        'ParamMouthForm': 1.0,
                        'ParamEyeForm': 0.8,
                        'BodyAngleY': 0.0,
                        'BodyAngleX': 0.0
                    },
                    'weight': 0.8
                },
                'sad': {
                    'expressions': ['Sad', 'Cry', 'Depressed', 'Melancholy'],
                    'params': {
                        'ParamMouthForm': -0.5,
                        'ParamEyeForm': -0.3,
                        'BodyAngleY': -0.1,
                        'BodyAngleX': 0.1
                    },
                    'weight': 0.7
                },
                'angry': {
                    'expressions': ['Angry', 'Mad', 'Furious', 'Annoyed'],
                    'params': {
                        'ParamEyeForm': -0.8,
                        'ParamBrowForm': -1.0,
                        'BodyAngleY': 0.0,
                        'BodyAngleX': -0.1
                    },
                    'weight': 0.9
                },
                'surprised': {
                    'expressions': ['Surprised', 'Shock', 'Amazed', 'Astonished'],
                    'params': {
                        'ParamEyeForm': 1.0,
                        'ParamMouthForm': 0.5,
                        'EyeLeftOpen': 1.0,
                        'EyeRightOpen': 1.0
                    },
                    'weight': 0.8
                }
            }
            
            if emotion_type not in manual_emotions:
                print(f"[VTS] Unknown manual emotion type: {emotion_type}")
                return
            
            emotion_config = manual_emotions[emotion_type]
            
            # ลองหา expression ที่ตรงกัน
            hotkeys = await self._list_model_hotkeys()
            found_expression = None
            
            for expr_name in emotion_config['expressions']:
                for hk in hotkeys:
                    if expr_name.lower() in str(hk.get("name", "")).lower():
                        found_expression = hk.get("name")
                        break
                if found_expression:
                    break
            
            # เล่น expression ถ้าเจอ
            if found_expression:
                print(f"[VTS] Manual emotion '{emotion_type}' -> trigger expression: {found_expression}")
                await self.trigger_hotkey_by_name(found_expression)
            
            # ตั้งค่าพารามิเตอร์
            if emotion_config['params']:
                print(f"[VTS] Manual emotion '{emotion_type}' -> setting parameters")
                await self.inject_parameters(
                    emotion_config['params'], 
                    weight=emotion_config['weight']
                )
            
            # Auto-reset หลังจากเวลาที่กำหนด
            if getattr(self.settings, "MANUAL_EMOTION_AUTO_RESET", True):
                duration = float(getattr(self.settings, "MANUAL_EMOTION_DURATION_SEC", 5.0))
                asyncio.create_task(self._auto_reset_emotion(duration))
                
        except Exception as e:
            print(f"[VTS] Manual emotion '{emotion_type}' failed: {e}")

    async def _auto_reset_emotion(self, delay_seconds: float):
        """รีเซ็ตอีโมทอัตโนมัติหลังจากเวลาที่กำหนด"""
        try:
            await asyncio.sleep(delay_seconds)
            await self.reset_manual_emotion()
        except Exception as e:
            print(f"[VTS] Auto reset emotion failed: {e}")

    async def reset_manual_emotion(self):
        """รีเซ็ตอีโมทกลับเป็นปกติ"""
        try:
            reset_params = {
                'ParamMouthForm': 0.0,
                'ParamEyeForm': 0.0,
                'ParamBrowForm': 0.0,
                'BodyAngleY': 0.0,
                'BodyAngleX': 0.0,
                'EyeLeftOpen': 1.0,
                'EyeRightOpen': 1.0
            }
            
            print("[VTS] Resetting manual emotion to neutral")
            await self.inject_parameters(reset_params, weight=0.5)
            
        except Exception as e:
            print(f"[VTS] Reset manual emotion failed: {e}")

    async def _handle_disconnect(self):
        """จัดการเมื่อการเชื่อมต่อขาด"""
        if self._reconnecting:
            return
        
        self._reconnecting = True
        self._is_connected = False
        
        print("[VTS] Connection lost, attempting to reconnect...")
        
        try:
            await self._reconnect()
        finally:
            self._reconnecting = False

    async def _reconnect(self):
        """เชื่อมต่อใหม่"""
        backoff_ms = int(getattr(self.settings, "VTS_RECONNECT_BACKOFF_MS", 1000))
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if self._ws:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
                
                await asyncio.sleep(backoff_ms / 1000.0)
                
                print(f"[VTS] Reconnect attempt {attempt + 1}/{max_retries}")
                await self.connect()
                
                if self._is_connected:
                    print("[VTS] Reconnected successfully")
                    return
                    
            except Exception as e:
                print(f"[VTS] Reconnect attempt {attempt + 1} failed: {e}")
                backoff_ms *= 2  # Exponential backoff
        
        print("[VTS] Failed to reconnect after all attempts")

    async def _ensure_custom_parameters(self):
        """สร้างพารามิเตอร์ที่จำเป็น"""
        if not self._ws or self._ws.closed:
            return
        
        # สำหรับ Hiyori ไม่จำเป็นต้องสร้างพารามิเตอร์เอง เพราะมีอยู่แล้ว
        # แต่ถ้าโมเดลอื่นไม่มี ให้สร้าง
        print("[VTS] Skipping custom parameter creation (using model defaults)")

    async def _run_random_animations_loop(self):
        """ลูปเล่นอนิเมชันแบบสุ่ม"""
        # รอให้เชื่อมต่อเสร็จก่อน
        await asyncio.sleep(2.0)
        
        hotkeys = await self._list_model_hotkeys()
        
        def is_animation(hk: dict) -> bool:
            t = str(hk.get("type", "")).lower()
            n = str(hk.get("name", "")).lower()
            return ("anim" in n) or ("animation" in t)
        
        anim_hotkeys = [hk for hk in hotkeys if is_animation(hk)]
        
        if not anim_hotkeys:
            common_guess = ["Animation1", "Animation2", "Anim", "IdleAnim", "Wave", "BlinkAnim"]
            anim_hotkeys = [{"name": x, "type": "Animation"} for x in common_guess]
        
        min_iv = float(getattr(self.settings, "ANIM_MIN_INTERVAL_SEC", 8.0))
        max_iv = float(getattr(self.settings, "ANIM_MAX_INTERVAL_SEC", 18.0))
        trigger_chance = float(getattr(self.settings, "ANIM_TRIGGER_CHANCE", 0.6))
        
        while True:
            try:
                if not self._is_connected or not self._ws or self._ws.closed:
                    await asyncio.sleep(5.0)
                    continue
                
                await asyncio.sleep(random.uniform(min_iv, max_iv))
                
                # ไม่เล่นอนิเมชันขณะพูด
                async with self._speaking_lock:
                    if self._is_speaking:
                        continue
                
                if random.random() > max(0.0, min(1.0, trigger_chance)):
                    continue
                
                if not anim_hotkeys:
                    continue
                
                hk = random.choice(anim_hotkeys)
                name = hk.get("name") or hk.get("hotkeyName")
                
                if not name:
                    continue
                
                print(f"[VTS] Random animation -> trigger hotkey: {name}")
                await self.trigger_hotkey_by_name(str(name))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[VTS] random animation loop error: {e}")
                await asyncio.sleep(5.0)

    async def _list_model_hotkeys(self) -> list[dict]:
        """ดึงรายชื่อ hotkeys ทั้งหมดของโมเดล"""
        if not self._ws or self._ws.closed:
            return []
        
        try:
            req = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "messageType": "HotkeysInCurrentModelRequest",
                "requestID": "hotkeys-list",
                "data": {}
            }
            
            async with self._ws_lock:
                await self._ws.send(json.dumps(req))
                resp = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            
            j = json.loads(resp)
            hotkeys = j.get("data", {}).get("availableHotkeys", [])
            return hotkeys if isinstance(hotkeys, list) else []
            
        except Exception as e:
            print(f"[VTS] list_model_hotkeys failed: {e}")
            return []