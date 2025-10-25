# --- BEGIN vts_client.py (patched) ---
from __future__ import annotations
import asyncio
from asyncio import Lock, Event
from typing import Dict, Any, Optional
import json
import random
import traceback

from adapters.vts import __init__ as _vts_pkg  # noqa: F401
from core.config import get_settings

try:
    import websockets  # type: ignore
    from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError, ConnectionClosed
except Exception:  # pragma: no cover
    websockets = None  # type: ignore

class VTSClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._ws = None
        self._ws_lock = Lock()
        self._recv_task: Optional[asyncio.Task] = None
        self._reconnect_lock = Lock()
        self._stop_event = Event()
        self._idle_task: Optional[asyncio.Task] = None
        self._blink_task: Optional[asyncio.Task] = None
        self._breathing_task: Optional[asyncio.Task] = None
        self._random_smile_task: Optional[asyncio.Task] = None
        self._last_send_ts: float = 0.0
        self._min_send_interval: float = 1.0 / float(getattr(self.settings, "VTS_INJECT_MAX_FPS", 30.0))
        self._param_map: Dict[str, str] = {}
        self._is_connected = False
        self._safe_hotkey_task: Optional[asyncio.Task] = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._pending_by_type: Dict[str, asyncio.Future] = {}

    def _ws_is_closed(self) -> bool:
        try:
            return not getattr(self._ws, "open", False)
        except Exception:
            return True

    async def connect(self):
        # Connect to VTS and start receiver loop. Safe to call multiple times.
        if not websockets:
            print("[VTS] websockets library not available")
            return

        if self._is_connected and self._ws and getattr(self._ws, "open", False):
            print("[VTS] Already connected")
            return

        uri = f"ws://{self.settings.VTS_HOST}:{self.settings.VTS_PORT}"
        try:
            if self._ws:
                try:
                    await self._ws.close()
                except Exception:
                    pass
            # ใช้ค่า ping จาก config เพื่อหลีกเลี่ยง timeout
            # Try setting Origin header to satisfy potential VTS checks
            self._ws = await websockets.connect(uri, ping_interval=None, max_queue=32, origin=f"http://{self.settings.VTS_HOST}")
            self._is_connected = True
            print(f"Connected to VTS at {uri}")

            # Start receiver FIRST so send_and_wait can resolve responses
            if not self._recv_task or self._recv_task.done():
                self._recv_task = asyncio.create_task(self._recv_loop())

            await self._authenticate()

            auto_setup = bool(getattr(self.settings, "VTS_AUTO_SETUP_PARAMETERS", False))
            if auto_setup:
                try:
                    await self._ensure_custom_parameters()
                except Exception:
                    pass
                try:
                    await self._build_param_mapping()
                except Exception:
                    pass

        except Exception as e:
            print(f"[VTS] Connect failed: {e}")
            self._is_connected = False
            try:
                if self._ws:
                    await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _send_json_and_wait(self, payload: Dict[str, Any], timeout: float = 5.0) -> Dict[str, Any]:
        if not self._ws:
            raise RuntimeError("WebSocket unavailable")
        req_id = payload.get("requestID") or payload.get("requestId")
        if not req_id:
            req_id = f"req-{random.randint(1000, 9999)}"
            payload["requestID"] = req_id
        msg_type = str(payload.get("messageType", ""))
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        if req_id:
            self._pending[req_id] = fut
        if msg_type:
            self._pending_by_type[msg_type] = fut
        async with self._ws_lock:
            await self._ws.send(json.dumps(payload))
        try:
            j = await asyncio.wait_for(fut, timeout=timeout)
            return j if isinstance(j, dict) else {}
        finally:
            if req_id:
                self._pending.pop(req_id, None)
            if msg_type:
                self._pending_by_type.pop(msg_type, None)

    async def _authenticate(self):
        # Separate authentication logic
        if not self._ws:
            return

        plugin_name = getattr(self.settings, "VTS_PLUGIN_NAME", "AI VTuber Demo")
        plugin_dev = getattr(self.settings, "VTS_PLUGIN_DEVELOPER", "AI VTuber Demo")
        token = getattr(self.settings, "VTS_PLUGIN_TOKEN", None)

        if not token:
            # Try to request token up to 3 times before giving up
            for attempt in range(3):
                try:
                    token_req = {
                        "apiName": "VTubeStudioPublicAPI",
                        "apiVersion": "1.0",
                        "messageType": "AuthenticationTokenRequest",
                        "requestID": "auth-token",
                        "data": {"pluginName": plugin_name, "pluginDeveloper": plugin_dev}
                    }
                    j = await self._send_json_and_wait(token_req, timeout=20.0)
                    token = j.get("data", {}).get("authenticationToken") or None
                    print(f"[VTS] Token response: {j.get('messageType')}")
                    if token:
                        break
                except Exception as e:
                    print(f"[VTS] Token request failed (attempt {attempt+1}/3): {e}")
                    await asyncio.sleep(0.5)
            if not token:
                raise RuntimeError("Authentication token unavailable")

        payload = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "messageType": "AuthenticationRequest",
            "requestID": "auth-1",
            "data": {"pluginName": plugin_name, "pluginDeveloper": plugin_dev, "authenticationToken": token}
        }
        try:
            j = await self._send_json_and_wait(payload, timeout=4.0)
            print(f"[VTS] Auth response: {json.dumps(j)}")
        except Exception as e:
            print(f"[VTS] auth send failed: {e}")

    async def _recv_loop(self):
        # Central dispatcher: continuously drain incoming messages and resolve pending futures
        try:
            while True:
                if not self._ws:
                    await asyncio.sleep(0.5)
                    continue
                if not getattr(self._ws, "open", False):
                    await asyncio.sleep(0.2)
                    continue
                try:
                    msg = await self._ws.recv()
                except (ConnectionClosedOK, ConnectionClosedError, ConnectionClosed) as e:
                    print(f"[VTS] Connection closed: {e}")
                    self._is_connected = False
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
                    asyncio.create_task(self._reconnect())
                    break
                except Exception as e:
                    print(f"[VTS] recv loop error: {e}")
                    traceback.print_exc()
                    self._is_connected = False
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
                    asyncio.create_task(self._reconnect())
                    break
                try:
                    j = json.loads(msg)
                except Exception:
                    j = {"raw": msg}
                req_id = j.get("requestID") or j.get("requestId") or None
                if req_id and req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        fut.set_result(j)
                else:
                    # Ignore unsolicited events for now
                    pass
        finally:
            self._is_connected = False

    async def _reconnect(self):
        # Reconnect with backoff, ensure only one reconnect runs at a time.
        async with self._reconnect_lock:
            max_attempts = int(getattr(self.settings, "VTS_RECONNECT_ATTEMPTS", 5))
            backoff_ms = int(getattr(self.settings, "VTS_RECONNECT_BACKOFF_MS", 500))
            attempt = 0
            while attempt < max_attempts and not self._is_connected:
                attempt += 1
                try:
                    print(f"[VTS] Reconnect attempt {attempt}/{max_attempts}")
                    await self.connect()
                    if self._is_connected:
                        print("[VTS] Reconnected successfully")
                        return
                except Exception as e:
                    print(f"[VTS] Reconnect failed attempt {attempt}: {e}")
                await asyncio.sleep(backoff_ms / 1000.0 * attempt)
            print("[VTS] Reconnect attempts exhausted")

    async def set_expression(self, expression: str, active: bool = True):
        print(f"[VTS] set_expression: {expression} -> {'ON' if active else 'OFF'}")
        if not self._is_connected or not self._ws:
            return
        msg = {"apiName": "VTubeStudioPublicAPI","apiVersion":"1.0","messageType":"SetExpressionStateRequest","requestID":f"expr-{expression}","data":{"expressionName": expression,"active": bool(active)}}
        try:
            async with self._ws_lock:
                await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] set_expression failed: {e}")
            asyncio.create_task(self._reconnect())

    async def set_parameter(self, name: str, value: float):
        if not self._is_connected or not self._ws:
            return
        msg = {"apiName":"VTubeStudioPublicAPI","apiVersion":"1.0","messageType":"SetParameterValueRequest","requestID":f"param-{name}","data":{"name": name,"value": float(value)}}
        try:
            async with self._ws_lock:
                await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] set_parameter failed: {e}")
            asyncio.create_task(self._reconnect())

    async def _build_param_mapping(self):
        if not self._is_connected or not self._ws:
            return
        try:
            req = {"apiName":"VTubeStudioPublicAPI","apiVersion":"1.0","messageType":"RequestParameterList","requestID":"param-list","data":{}}
            j = await self._send_json_and_wait(req, timeout=5.0)
            names: list[str] = []
            try:
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
            self._param_map = {
                "body_angle_x": find_one(["BodyAngleX", "AngleX", "Body X"] ) or "BodyAngleX",
                "body_angle_y": find_one(["BodyAngleY", "AngleY", "Body Y"] ) or "BodyAngleY",
                "body_angle_z": find_one(["BodyAngleZ", "AngleZ", "Body Z"] ) or "BodyAngleZ",
                "eye_left_open": find_one(["EyeLeftOpen", "EyeL", "LeftEyeOpen"]) or "EyeLeftOpen",
                "eye_right_open": find_one(["EyeRightOpen", "EyeR", "RightEyeOpen"]) or "EyeRightOpen",
                "mouth_open": find_one(["MouthOpen", "Mouth", "OpenMouth"]) or "MouthOpen",
                "mouth_smile": find_one(["MouthSmile", "Smile", "MouthCurve"]) or "MouthSmile",
            }
        except Exception as e:
            print(f"[VTS] build_param_mapping failed: {e}")
            traceback.print_exc()

    async def inject_parameters(self, values: Dict[str, float], weight: Optional[float] = None):
        if not self._is_connected or not self._ws:
            return
        now = asyncio.get_event_loop().time()
        dt = now - self._last_send_ts
        if dt < self._min_send_interval:
            await asyncio.sleep(self._min_send_interval - dt)
        self._last_send_ts = asyncio.get_event_loop().time()
        w = float(weight if weight is not None else getattr(self.settings, "IDLE_MOTION_SENSITIVITY", 1.0))
        data_values = []
        for k, v in values.items():
            mapped_name = self._param_map.get(k, k)
            kl = mapped_name.lower()
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
        msg = {"apiName":"VTubeStudioPublicAPI","apiVersion":"1.0","messageType":"InjectParameterDataRequest","requestID":"inject-parameters","data":{"parameterValues": data_values}}
        try:
            async with self._ws_lock:
                await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] inject_parameters failed: {e}")
            asyncio.create_task(self._reconnect())

    async def trigger_hotkey_by_name(self, name: str):
        if not self._is_connected or not self._ws:
            return
        try:
            msg = {"apiName":"VTubeStudioPublicAPI","apiVersion":"1.0","messageType":"HotkeyTriggerRequest","requestID":"trigger_hotkey","data":{"hotkeyName": name}}
            async with self._ws_lock:
                await self._ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[VTS] trigger_hotkey failed: {e}")
            asyncio.create_task(self._reconnect())

    async def trigger_hotkey(self, hotkey_name: str):
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
        if self._idle_task and not self._idle_task.done():
            return
        async def _runner():
            amp = float(getattr(self.settings, "IDLE_MOTION_AMPLITUDE", 0.4))
            base_interval = float(getattr(self.settings, "IDLE_MOTION_INTERVAL", 2.0))
            while not self._stop_event.is_set():
                try:
                    x_pos = random.uniform(-amp, amp)
                    y_pos = random.uniform(-amp * 0.3, amp * 0.3)
                    weight = random.uniform(0.5, 1.5)
                    vals = {"BodyAngleY": x_pos, "BodyAngleX": y_pos}
                    await self.inject_parameters(vals, weight=weight)
                    random_interval = random.uniform(base_interval * 0.3, base_interval * 2.5)
                except Exception:
                    random_interval = base_interval
                await asyncio.sleep(random_interval)
        self._idle_task = asyncio.create_task(_runner())

    async def start_blinking(self):
        if self._blink_task and not self._blink_task.done():
            return
        async def _runner():
            min_i = float(getattr(self.settings, "BLINK_MIN_INTERVAL", 3.0))
            max_i = float(getattr(self.settings, "BLINK_MAX_INTERVAL", 6.0))
            close_ms = int(getattr(self.settings, "BLINK_CLOSE_MS", 120))
            dbl_prob = float(getattr(self.settings, "BLINK_DOUBLE_PROB", 0.2))
            while not self._stop_event.is_set():
                try:
                    if random.random() < 0.1:
                        interval = random.uniform(0.5, 15.0)
                    else:
                        interval = random.uniform(min_i, max_i)
                    await asyncio.sleep(interval)
                    close_time = random.uniform(close_ms * 0.5, close_ms * 2.0) / 1000.0
                    await self.inject_parameters({"EyeLeftOpen": 0.0, "EyeRightOpen": 0.0}, weight=1.0)
                    await asyncio.sleep(close_time)
                    await self.inject_parameters({"EyeLeftOpen": 1.0, "EyeRightOpen": 1.0}, weight=1.0)
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
        if self._breathing_task and not self._breathing_task.done():
            return
        async def _runner():
            min_i = float(getattr(self.settings, "BREATHING_MIN_INTERVAL", 2.5))
            max_i = float(getattr(self.settings, "BREATHING_MAX_INTERVAL", 8.0))
            min_int = float(getattr(self.settings, "BREATHING_MIN_INTENSITY", 0.1))
            max_int = float(getattr(self.settings, "BREATHING_MAX_INTENSITY", 0.4))
            min_dur = float(getattr(self.settings, "BREATHING_MIN_DURATION", 1.2))
            max_dur = float(getattr(self.settings, "BREATHING_MAX_DURATION", 3.5))
            while not self._stop_event.is_set():
                try:
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
                except Exception:
                    pass
        self._breathing_task = asyncio.create_task(_runner())

    async def start_random_smile(self):
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
            while not self._stop_event.is_set():
                try:
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
                except Exception:
                    pass
        self._random_smile_task = asyncio.create_task(_runner())

    def _emotion_trigger_prob(self, emotion_key: str) -> float:
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

    async def apply_emotion(self, emotion_key: str, intensity: float = 1.0):
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
            random_intensity = intensity * random.uniform(0.7, 1.3)
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
        if not self._is_connected or not self._ws:
            return
        import wave, struct, math
        try:
            p_name = param_name or getattr(self.settings, "LIPSYNC_PARAM", "MouthOpen")
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
                        rms = (acc/len(samples))**0.5
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
            traceback.print_exc()

    async def lipsync_bytes(self, wav_bytes: bytes, param_name: Optional[str] = None):
        if not self._is_connected or not self._ws:
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
                        rms = (acc/len(samples))**0.5
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
            traceback.print_exc()

    async def _ensure_custom_parameters(self):
        if not self._is_connected or not self._ws:
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
                    async with self._ws_lock:
                        await self._ws.send(json.dumps(msg))
                        try:
                            await asyncio.wait_for(self._ws.recv(), timeout=2.0)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as e:
            print(f"[VTS] ensure_custom_parameters failed: {e}")
            traceback.print_exc()

    async def list_model_hotkeys(self):
        if not self._is_connected or not self._ws:
            return []
        try:
            req = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "messageType": "AvailableHotkeysRequest",
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

    async def start_safe_motion_hotkeys(self):
        if self._safe_hotkey_task and not self._safe_hotkey_task.done():
            return
        async def _runner():
            interval = float(getattr(self.settings, "SAFE_HOTKEY_INTERVAL", 6.0))
            weight = float(getattr(self.settings, "SAFE_HOTKEY_WEIGHT", 1.0))
            names_cfg = getattr(self.settings, "SAFE_HOTKEY_NAMES", None)
            chosen: list[str] = []
            try:
                available = await self.list_model_hotkeys()
                if isinstance(available, list) and available:
                    if names_cfg:
                        want = [n.strip() for n in str(names_cfg).split(",") if n.strip()]
                        lower_want = {w.lower() for w in want}
                        for hk in available:
                            name = str(hk.get("name", ""))
                            if not name:
                                continue
                            if not want or name.lower() in lower_want:
                                chosen.append(name)
                    else:
                        for hk in available[:5]:
                            name = str(hk.get("name", ""))
                            if name:
                                chosen.append(name)
            except Exception:
                pass
            if not chosen:
                # fallback to F1/F2/F3 names users reported
                chosen = ["Neutral", "Happy", "Sad"]
            idx = 0
            while not self._stop_event.is_set():
                try:
                    name = chosen[idx % len(chosen)]
                    await self.trigger_hotkey_by_name(name)
                except Exception:
                    pass
                await asyncio.sleep(interval)
                idx += 1
        self._safe_hotkey_task = asyncio.create_task(_runner())

    async def stop_all_motions(self):
        self._stop_event.set()
        for t in [self._idle_task, self._blink_task, self._breathing_task, self._random_smile_task, self._safe_hotkey_task]:
            try:
                if t and not t.done():
                    t.cancel()
            except Exception:
                pass
