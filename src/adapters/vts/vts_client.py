from __future__ import annotations
import asyncio
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
        self._idle_task: Optional[asyncio.Task] = None
        self._blink_task: Optional[asyncio.Task] = None
        self._breathing_task: Optional[asyncio.Task] = None
        self._random_smile_task: Optional[asyncio.Task] = None
        self._last_send_ts: float = 0.0
        self._min_send_interval: float = 1.0 / float(getattr(self.settings, "VTS_INJECT_MAX_FPS", 30.0))
        # แมปชื่อพารามิเตอร์ทั่วไป -> ชื่อพารามิเตอร์จริงในโมเดล
        self._param_map: Dict[str, str] = {}

    async def connect(self):
        # ใช้ websockets ถ้ามี และทำ auth ตามสเปก VTS
        if not websockets:
            print("websockets library not available")
            return
        uri = f"ws://{self.settings.VTS_HOST}:{self.settings.VTS_PORT}"
        try:
            self._ws = await websockets.connect(uri, ping_interval=15, ping_timeout=10, max_queue=32)
            print(f"Connected to VTS at {uri}")

            # ทำ Authentication: ขอ token ถ้ายังไม่มี แล้ว authenticate
            plugin_name = getattr(self.settings, "VTS_PLUGIN_NAME", "AI VTuber Demo")
            plugin_dev = "AI VTuber Demo"

            token = getattr(self.settings, "VTS_PLUGIN_TOKEN", None)
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
                    await self._ws.send(json.dumps(token_req))
                    resp = await asyncio.wait_for(self._ws.recv(), timeout=8.0)
                    print(f"[VTS] Token response: {resp}")
                    try:
                        j = json.loads(resp)
                        token = j.get("data", {}).get("authenticationToken") or None
                    except Exception:
                        pass
                except Exception as e:
                    print(f"[VTS] Token request failed: {e}")

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
                await self._ws.send(json.dumps(payload))
                try:
                    resp = await asyncio.wait_for(self._ws.recv(), timeout=4.0)
                    print(f"[VTS] Auth response: {resp}")
                    # หลัง auth สำเร็จ สร้าง custom parameters และแมปชื่อพารามิเตอร์กับโมเดล
                    try:
                        await self._ensure_custom_parameters()
                        await self._build_param_mapping()
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception as e:
                print(f"VTS auth send failed: {e}")
        except Exception as e:
            print(f"Connect VTS failed: {e}")
            self._ws = None

    async def set_expression(self, expression: str, active: bool = True):
        # เปิด/ปิด expression ตามชื่อ
        print(f"[VTS] set_expression: {expression} -> {'ON' if active else 'OFF'}")
        if not self._ws:
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
            await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] set_expression failed: {e}")

    async def set_parameter(self, name: str, value: float):
        # ปรับค่า parameter เดี่ยว เช่น ExpressionIntensity/MouthOpen
        print(f"[VTS] set_parameter: {name}={value}")
        if not self._ws:
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
            await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] set_parameter failed: {e}")

    async def _build_param_mapping(self):
        """ดึงรายชื่อพารามิเตอร์ของโมเดลจาก VTS และสร้าง mapping อัตโนมัติ."""
        if not self._ws:
            return
        try:
            req = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "messageType": "RequestParameterList",
                "requestID": "param-list",
                "data": {}
            }
            await self._ws.send(json.dumps(req))
            resp = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            names: list[str] = []
            try:
                j = json.loads(resp)
                params = j.get("data", {}).get("parameters", [])
                names = [str(p.get("name", "")) for p in params]
            except Exception:
                names = []
            lower = [n.lower() for n in names]
            def find_one(candidates: list[str]) -> Optional[str]:
                for cand in candidates:
                    cand_l = cand.lower()
                    for i, n in enumerate(lower):
                        if cand_l in n:
                            return names[i]
                return None
            # สร้าง mapping สำหรับคีย์ที่โค้ดใช้
            mapping: Dict[str, str] = {}
            # มุมร่างกาย
            mapping["BodyAngleX"] = find_one(["anglex", "paramanglex"]) or mapping.get("BodyAngleX", "ParamAngleX")
            mapping["BodyAngleY"] = find_one(["angley", "paramangley"]) or mapping.get("BodyAngleY", "ParamAngleY")
            mapping["BodyAngleZ"] = find_one(["anglez", "paramanglez"]) or mapping.get("BodyAngleZ", "ParamAngleZ")
            # ตาเปิด
            mapping["EyeLeftOpen"] = find_one(["eyelopen", "eyelopen_l", "eyelopenleft", "parameyelopen_l"]) or find_one(["eyelopenl"]) or mapping.get("EyeLeftOpen", "ParamEyeLOpen")
            mapping["EyeRightOpen"] = find_one(["eyelopen", "eyelopen_r", "eyelopenright", "parameyelopen_r"]) or find_one(["eyelopenr"]) or mapping.get("EyeRightOpen", "ParamEyeROpen")
            # ปาก
            mapping["MouthOpen"] = find_one(["mouthopeny", "mouthopen", "parammouthopen"]) or mapping.get("MouthOpen", "ParamMouthOpenY")
            mapping["MouthSmile"] = find_one(["mouthsmile", "mouthform"]) or mapping.get("MouthSmile", "ParamMouthSmile")
            self._param_map = mapping
            print(f"[VTS] Param mapping: {self._param_map}")
        except Exception as e:
            print(f"[VTS] build_param_mapping failed: {e}")

    async def inject_parameters(self, values: Dict[str, float], weight: Optional[float] = None):
        # ส่งค่า parameter หลายตัวพร้อมกัน (Idle motion / เคลื่อนไหวตามเสียง)
        if not self._ws:
            return
        # Throttle to limit send rate
        now = asyncio.get_event_loop().time()
        dt = now - self._last_send_ts
        if dt < self._min_send_interval:
            await asyncio.sleep(self._min_send_interval - dt)
        self._last_send_ts = asyncio.get_event_loop().time()
        # Clamp values with per-parameter ranges
        w = float(weight if weight is not None else getattr(self.settings, "IDLE_MOTION_SENSITIVITY", 1.0))
        data_values = []
        for k, v in values.items():
            # แมปชื่อที่ส่งให้เป็นชื่อที่โมเดลมี ถ้ามี
            mapped_name = self._param_map.get(k, k)
            kl = mapped_name.lower()
            # กำหนดช่วงค่า
            if "angle" in kl:
                vmin, vmax = -1.0, 1.0
            elif "smile" in kl:
                vmin, vmax = -1.0, 1.0
            else:
                vmin, vmax = 0.0, 1.0
            try:
                safe_v = max(vmin, min(vmax, float(v)))
            except Exception:
                safe_v = vmin
            data_values.append({"name": mapped_name, "value": float(safe_v), "weight": float(w)})
        msg = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "messageType": "InjectParameterDataRequest",
            "requestID": "inject-parameters",
            "data": {
                "parameterValues": data_values
            }
        }
        try:
            await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] inject_parameters failed: {e}")
            try:
                await self._reconnect()
            except Exception:
                pass

    async def trigger_hotkey_by_name(self, name: str):
        if not self._ws:
            return
        try:
            msg = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "messageType": "HotkeyTriggerRequest",
                "requestID": "trigger_hotkey",
                "data": {
                    "hotkeyName": name
                }
            }
            await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] trigger_hotkey failed: {e}")
            try:
                await self._reconnect()
            except Exception:
                pass

    async def trigger_hotkey(self, hotkey_name: str):
        """ทริกเกอร์ hotkey โดยใช้ชื่อ hotkey จาก settings"""
        try:
            # แมป hotkey name กับ settings
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
        # การเคลื่อนไหวแบบสุ่มสมบูรณ์ ไม่มีแพทเทิน
        if self._idle_task and not self._idle_task.done():
            return

        async def _runner():
            amp = float(getattr(self.settings, "IDLE_MOTION_AMPLITUDE", 0.4))
            base_interval = float(getattr(self.settings, "IDLE_MOTION_INTERVAL", 2.0))
            while True:
                try:
                    # สุ่มทุกอย่าง: ทิศทาง, ความแรง, ระยะเวลา
                    x_pos = random.uniform(-amp, amp)
                    y_pos = random.uniform(-amp * 0.3, amp * 0.3)  # เพิ่มแกน Y เล็กน้อย
                    
                    # สุ่มความแรงการฉีด
                    weight = random.uniform(0.5, 1.5)
                    
                    vals = {
                        "BodyAngleY": x_pos,
                        "BodyAngleX": y_pos,
                    }
                    await self.inject_parameters(vals, weight=weight)
                    
                    # สุ่มช่วงเวลารอแบบไม่มีแพทเทิน
                    random_interval = random.uniform(base_interval * 0.3, base_interval * 2.5)
                except Exception:
                    random_interval = base_interval
                await asyncio.sleep(random_interval)
        self._idle_task = asyncio.create_task(_runner())

    async def start_blinking(self):
        # กระพริบตาแบบสุ่มสมบูรณ์ ไม่มีแพทเทิน
        if self._blink_task and not self._blink_task.done():
            return

        async def _runner():
            min_i = float(getattr(self.settings, "BLINK_MIN_INTERVAL", 3.0))
            max_i = float(getattr(self.settings, "BLINK_MAX_INTERVAL", 6.0))
            close_ms = int(getattr(self.settings, "BLINK_CLOSE_MS", 120))
            dbl_prob = float(getattr(self.settings, "BLINK_DOUBLE_PROB", 0.2))
            while True:
                try:
                    # สุ่มช่วงเวลาแบบไม่มีแพทเทิน (อาจนานมาก หรือเร็วมาก)
                    if random.random() < 0.1:  # 10% โอกาสช่วงแปลก ๆ
                        interval = random.uniform(0.5, 15.0)
                    else:
                        interval = random.uniform(min_i, max_i)
                    
                    await asyncio.sleep(interval)
                    
                    # สุ่มความเร็วการหลับตา
                    close_time = random.uniform(close_ms * 0.5, close_ms * 2.0) / 1000.0
                    
                    # ปิดตา
                    await self.inject_parameters({"EyeLeftOpen": 0.0, "EyeRightOpen": 0.0}, weight=1.0)
                    await asyncio.sleep(close_time)
                    # เปิดตา
                    await self.inject_parameters({"EyeLeftOpen": 1.0, "EyeRightOpen": 1.0}, weight=1.0)
                    
                    # สุ่มกระพริบซ้อน (อาจ 2-4 ครั้ง)
                    if random.random() < dbl_prob:
                        extra_blinks = random.randint(1, 3)
                        for _ in range(extra_blinks):
                            await asyncio.sleep(random.uniform(0.05, 0.2))
                            await self.inject_parameters({"EyeLeftOpen": 0.0, "EyeRightOpen": 0.0}, weight=1.0)
                            await asyncio.sleep(random.uniform(close_time * 0.5, close_time))
                            await self.inject_parameters({"EyeLeftOpen": 1.0, "EyeRightOpen": 1.0}, weight=1.0)
                except Exception:
                    pass
        self._blink_task = asyncio.create_task(_runner())

    async def start_breathing(self):
        # การหายใจแบบสุ่มสมบูรณ์ ไม่มีจังหวะ
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
                    # สุ่มช่วงเวลารอแบบไม่มีแพทเทิน
                    if random.random() < 0.15:  # 15% โอกาสหายใจแปลก ๆ
                        interval = random.uniform(0.8, 20.0)
                    else:
                        interval = random.uniform(min_i, max_i)
                    
                    await asyncio.sleep(interval)
                    
                    # สุ่มความแรงและระยะเวลาหายใจ
                    intensity = random.uniform(min_int, max_int)
                    duration = random.uniform(min_dur, max_dur)
                    
                    # สุ่มรูปแบบการหายใจ (หายใจเข้า-ออก หรือแค่เข้า หรือแค่ออก)
                    breath_type = random.choice(["in_out", "in_only", "out_only", "irregular"])
                    
                    if breath_type == "in_out":
                        # หายใจเข้า
                        await self.inject_parameters({"BodyAngleZ": intensity}, weight=0.8)
                        await asyncio.sleep(duration * 0.4)
                        # หายใจออก
                        await self.inject_parameters({"BodyAngleZ": -intensity * 0.3}, weight=0.6)
                        await asyncio.sleep(duration * 0.6)
                        # กลับปกติ
                        await self.inject_parameters({"BodyAngleZ": 0.0}, weight=0.5)
                    elif breath_type == "irregular":
                        # หายใจไม่เป็นจังหวะ
                        steps = random.randint(3, 7)
                        for i in range(steps):
                            val = random.uniform(-intensity, intensity)
                            weight = random.uniform(0.3, 1.0)
                            await self.inject_parameters({"BodyAngleZ": val}, weight=weight)
                            await asyncio.sleep(duration / steps * random.uniform(0.5, 2.0))
                        await self.inject_parameters({"BodyAngleZ": 0.0}, weight=0.5)
                    else:
                        # หายใจเข้าหรือย่างเดียว
                        val = intensity if breath_type == "in_only" else -intensity * 0.5
                        await self.inject_parameters({"BodyAngleZ": val}, weight=0.7)
                        await asyncio.sleep(duration)
                        await self.inject_parameters({"BodyAngleZ": 0.0}, weight=0.5)
                        
                except Exception:
                    pass
        self._breathing_task = asyncio.create_task(_runner())

    async def start_random_smile(self):
        # ยิ้มมุมปากแบบสุ่มสมบูรณ์ ไม่มีแพทเทิน
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
                    # สุ่มช่วงเวลาแบบไม่มีแพทเทิน (อาจยิ้มบ่อยมาก หรือนานมาก)
                    if random.random() < 0.2:  # 20% โอกาสยิ้มแปลก ๆ
                        interval = random.uniform(5.0, 120.0)
                    else:
                        interval = random.uniform(min_i, max_i)
                    
                    await asyncio.sleep(interval)
                    
                    # สุ่มรูปแบบการยิ้ม
                    smile_type = random.choice([
                        "gentle", "wide", "smirk", "half_smile", 
                        "gradual", "quick_flash", "sustained"
                    ])
                    
                    intensity = random.uniform(min_int, max_int)
                    duration = random.uniform(min_dur, max_dur)
                    
                    if smile_type == "gradual":
                        # ยิ้มค่อย ๆ เพิ่มขึ้น
                        steps = random.randint(5, 12)
                        for i in range(steps):
                            current_intensity = intensity * (i + 1) / steps
                            await self.inject_parameters({"MouthSmile": current_intensity}, weight=0.6)
                            await asyncio.sleep(duration * 0.3 / steps)
                        
                        # คงยิ้มไว้
                        await asyncio.sleep(duration * 0.4)
                        
                        # ค่อย ๆ หาย
                        for i in range(steps):
                            current_intensity = intensity * (steps - i) / steps
                            await self.inject_parameters({"MouthSmile": current_intensity}, weight=0.6)
                            await asyncio.sleep(duration * 0.3 / steps)
                            
                    elif smile_type == "quick_flash":
                        # ยิ้มแปบเดียว
                        await self.inject_parameters({"MouthSmile": intensity * 1.2}, weight=0.8)
                        await asyncio.sleep(random.uniform(0.3, 0.8))
                        await self.inject_parameters({"MouthSmile": 0.0}, weight=0.6)
                        
                    elif smile_type == "sustained":
                        # ยิ้มนาน ๆ แบบไม่เปลี่ยน
                        await self.inject_parameters({"MouthSmile": intensity}, weight=0.7)
                        await asyncio.sleep(duration * random.uniform(1.5, 3.0))
                        await self.inject_parameters({"MouthSmile": 0.0}, weight=0.5)
                        
                    else:
                        # ยิ้มปกติแต่สุ่มความแรง
                        final_intensity = intensity * random.uniform(0.7, 1.3)
                        await self.inject_parameters({"MouthSmile": final_intensity}, weight=0.7)
                        await asyncio.sleep(duration)
                        
                        # ค่อย ๆ หาย
                        fade_steps = random.randint(3, 8)
                        for i in range(fade_steps):
                            current = final_intensity * (fade_steps - i) / fade_steps
                            await self.inject_parameters({"MouthSmile": current}, weight=0.5)
                            await asyncio.sleep(fade_time / fade_steps)
                    
                    # รีเซ็ตให้แน่ใจ
                    await self.inject_parameters({"MouthSmile": 0.0}, weight=0.4)
                    
                except Exception:
                    pass
        self._random_smile_task = asyncio.create_task(_runner())

    def _emotion_trigger_prob(self, emotion_key: str) -> float:
        k = str(emotion_key).lower()
        
        # สุ่มความน่าจะเป็นแบบไม่มีแพทเทิน
        base_prob = float(getattr(self.settings, "EMOTION_TRIGGER_PROBABILITY", 0.3))
        
        # เพิ่มความสุ่มให้แต่ละอีโมท
        random_factor = random.uniform(0.5, 2.0)  # สุ่มตัวคูณ
        
        # บางครั้งอาจไม่ทริกเกอร์เลย หรือทริกเกอร์แน่นอน
        if random.random() < 0.1:  # 10% โอกาสพิเศษ
            return random.choice([0.0, 1.0])  # ไม่ทริกเกอร์หรือทริกเกอร์แน่นอน
        
        # สุ่มความน่าจะเป็นตามอีโมท
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

    async def apply_emotion(self, emotion_key: str, intensity: float = 1.0):
        # สุ่มว่าจะทริกเกอร์หรือไม่
        trigger_prob = self._emotion_trigger_prob(emotion_key)
        
        # เพิ่มความสุ่มในการตัดสินใจ
        random_threshold = random.uniform(0.0, 1.0)
        
        if random_threshold > trigger_prob:
            # ไม่ทริกเกอร์ แต่อาจมีการแสดงออกเล็กน้อย
            if random.random() < 0.3:  # 30% โอกาสแสดงออกเล็กน้อย
                subtle_actions = ["MouthSmile", "EyeLeftOpen", "EyeRightOpen"]
                action = random.choice(subtle_actions)
                subtle_intensity = random.uniform(0.1, 0.3)
                await self.inject_parameters({action: subtle_intensity}, weight=0.3)
                await asyncio.sleep(random.uniform(0.5, 2.0))
                await self.inject_parameters({action: 0.0}, weight=0.2)
            return
        
        # ทริกเกอร์อีโมท
        emotion_lower = emotion_key.lower()
        hotkey_name = None
        
        # สุ่มการเลือก hotkey
        if emotion_lower in ["happy", "joy", "excited"]:
            # บางครั้งอาจไม่ยิ้ม แต่แสดงออกกับอื่น
            if random.random() < 0.8:
                hotkey_name = "Happy"
            else:
                # แสดงออกกับอื่นแทน
                await self.inject_parameters({"EyeLeftOpen": 0.8, "EyeRightOpen": 0.8}, weight=0.6)
                await asyncio.sleep(random.uniform(1.0, 3.0))
                await self.inject_parameters({"EyeLeftOpen": 1.0, "EyeRightOpen": 1.0}, weight=0.4)
                return
                
        elif emotion_lower in ["sad", "disappointed", "upset"]:
            # สุ่มระหว่าง Sad หรือกลับเป็น Neutral
            if random.random() < 0.6:
                hotkey_name = "Sad" if random.random() < 0.7 else "Neutral"
            else:
                # แสดงออกแบบเศร้าเล็กน้อย
                await self.inject_parameters({"MouthSmile": -0.2}, weight=0.5)
                await asyncio.sleep(random.uniform(2.0, 5.0))
                await self.inject_parameters({"MouthSmile": 0.0}, weight=0.3)
                return
                
        elif emotion_lower in ["angry", "frustrated", "annoyed"]:
            hotkey_name = "Angry" if random.random() < 0.8 else "Neutral"
            
        elif emotion_lower in ["surprised", "shocked", "amazed"]:
            hotkey_name = "Surprised" if random.random() < 0.9 else "Happy"
            
        else:
            # อีโมทอื่น ๆ สุ่มเลือก
            possible_emotions = ["Neutral", "Happy", "Surprised"]
            hotkey_name = random.choice(possible_emotions)
        
        # ทริกเกอร์ hotkey ถ้ามี
        if hotkey_name:
            # สุ่มความแรงและระยะเวลา
            random_intensity = intensity * random.uniform(0.7, 1.3)
            await self.trigger_hotkey(hotkey_name)
            
            # บางครั้งอาจเพิ่มการแสดงออกเสริม
            if random.random() < 0.4:  # 40% โอกาส
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
                    # รีเซ็ต
                    reset_params = {k: 0.0 for k in extra_params.keys()}
                    await self.inject_parameters(reset_params, weight=0.3)

    async def lipsync_wav(self, wav_path: str, param_name: Optional[str] = None):
        """อ่านไฟล์ WAV และอัปเดตพารามิเตอร์ปากแบบเรียลไทม์ตามแอมพลิจูด
        - แบ่งเสียงเป็นช่วง ๆ (เช่น 30ms) คำนวณ RMS แล้วแมปเป็นค่าปาก 0..1
        - ใช้ InjectParameterDataRequest เพื่อให้ลื่นไหล
        """
        if not self._ws:
            return
        import wave, struct, math
        try:
            p_name = param_name or getattr(self.settings, "LIPSYNC_PARAM", "MouthOpen")
            frame_ms = float(getattr(self.settings, "LIPSYNC_FRAME_MS", 30.0))
            with wave.open(wav_path, 'rb') as w:
                n_channels = w.getnchannels()
                sampwidth = w.getsampwidth()  # bytes per sample
                framerate = w.getframerate()
                nframes = w.getnframes()
                # อ่านทีละบล็อกตาม frame_ms
                block_size = max(1, int(framerate * (frame_ms/1000.0)))
                fmt = {1:'b', 2:'h', 4:'i'}.get(sampwidth, 'h')  # สมมติ 16-bit เป็นหลัก
                max_val = float({1:127, 2:32767, 4:2147483647}.get(sampwidth, 32767))
                idx = 0
                while idx < nframes:
                    to_read = min(block_size, nframes - idx)
                    raw = w.readframes(to_read)
                    # แปลงเป็นตัวอย่าง
                    count = to_read * n_channels
                    samples = struct.unpack('<' + fmt*count, raw)
                    # หากหลายช่อง เฉลี่ยเป็นโมโน
                    if n_channels > 1:
                        # เฉลี่ยทีละ n_channels
                        mono = []
                        for i in range(0, len(samples), n_channels):
                            s = sum(samples[i:i+n_channels]) / n_channels
                            mono.append(s)
                        samples = mono
                    # คำนวณ RMS
                    if not samples:
                        rms = 0.0
                    else:
                        acc = 0.0
                        for s in samples:
                            acc += (float(s)/max_val)**2
                        rms = math.sqrt(acc/len(samples))
                    # แมปเป็นค่าปาก 0..1 พร้อมโค้งแรงตามไดนามิก
                    # เพิ่มคอมเพรสชันเล็กน้อยให้เปิดปากไม่สั่นเกินไป
                    mouth = min(1.0, max(0.0, rms*1.8))
                    # ส่งค่าไป VTS
                    try:
                        await self.inject_parameters({p_name: mouth}, weight=0.8)
                    except Exception:
                        pass
                    # รอให้ตรงกับช่วงเวลา
                    await asyncio.sleep(frame_ms/1000.0)
                    idx += to_read
            # รีเซ็ตปากปิดหลังจบ
            try:
                await self.inject_parameters({p_name: 0.0}, weight=0.5)
            except Exception:
                pass
        except Exception as e:
            print(f"[VTS] lipsync_wav failed: {e}")

    async def lipsync_bytes(self, wav_bytes: bytes, param_name: Optional[str] = None):
        """ลิปซิงก์จาก WAV bytes ในหน่วยความจำ ไม่ต้องเขียนไฟล์"""
        if not self._ws:
            return
        import wave, struct, math, io
        try:
            p_name = param_name or getattr(self.settings, "LIPSYNC_PARAM", "MouthOpen")
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

    async def _reconnect(self):
        backoff_ms = int(getattr(self.settings, "VTS_RECONNECT_BACKOFF_MS", 500))
        try:
            if self._ws:
                try:
                    await self._ws.close()
                except Exception:
                    pass
            await asyncio.sleep(backoff_ms / 1000.0)
            await self.connect()
        except Exception as e:
            print(f"[VTS] reconnect failed: {e}")

    async def _ensure_custom_parameters(self):
        """Create required custom parameters if missing.
        Names used by our motions/lipsync: BodyAngleX/Y/Z, EyeLeftOpen, EyeRightOpen, MouthOpen, MouthSmile.
        """
        if not self._ws:
            return
        try:
            required = [
                ("BodyAngleX", -1.0, 1.0, 0.0),
                ("BodyAngleY", -1.0, 1.0, 0.0),
                ("BodyAngleZ", -1.0, 1.0, 0.0),
                ("EyeLeftOpen", 0.0, 1.0, 1.0),
                ("EyeRightOpen", 0.0, 1.0, 1.0),
                ("MouthOpen", 0.0, 1.0, 0.0),
                ("MouthSmile", 0.0, 1.0, 0.0),
            ]
            for name, vmin, vmax, default in required:
                try:
                    msg = {
                        "apiName": "VTubeStudioPublicAPI",
                        "apiVersion": "1.0",
                        "messageType": "ParameterCreationRequest",
                        "requestID": f"create-{name}",
                        "data": {
                            "parameterName": name,
                            "explanation": "AI VTuber Demo",
                            "min": float(vmin),
                            "max": float(vmax),
                            "defaultValue": float(default),
                            "forceOverwrite": False
                        }
                    }
                    await self._ws.send(json.dumps(msg))
                    # Best-effort: ignore response; VTS may return error if already exists
                    try:
                        await asyncio.wait_for(self._ws.recv(), timeout=2.0)
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception as e:
            print(f"[VTS] ensure_custom_parameters failed: {e}")