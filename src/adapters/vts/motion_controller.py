"""
VTS Human-Like Motion Controller
Connects to VTube Studio via WebSocket, maps parameters, and drives
natural motion with Perlin noise, micro-movements, breathing, blinking,
and speaking-responsive head bob. Supports optional microphone input.
"""

import asyncio
import json
import math
import random
import time
import os
from typing import Dict, Optional

try:
    from noise import pnoise1  # type: ignore
except Exception:
    def pnoise1(x: float, repeat: int = 1024):  # type: ignore
        return math.sin(x)

try:
    import sounddevice as sd  # type: ignore
except Exception:
    sd = None  # type: ignore

import websockets
from websockets.exceptions import ConnectionClosed


API_NAME = "VTubeStudioPublicAPI"
API_VERSION = "1.0"


class VTSHumanMotionController:
    def __init__(
        self,
        plugin_name: str = "AI VTuber Human Motion",
        plugin_developer: str = "TraeAI",
        host: str = os.getenv("VTS_HOST", "127.0.0.1"),
        port: int = int(os.getenv("VTS_PORT", "8001")),
    ):
        self.plugin_name = plugin_name
        self.plugin_developer = plugin_developer
        self.host = host
        self.port = port
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.authenticated = False
        self._msg_id = 0
        self.current_model_id: Optional[str] = None
        self.param_map: Dict[str, Optional[str]] = {
            "FaceAngleX": None,
            "FaceAngleY": None,
            "FaceAngleZ": None,
            "FacePositionX": None,
            "FacePositionY": None,
            "MouthSmile": None,
            "EyeOpenLeft": None,
            "EyeOpenRight": None,
            "MouthOpen": None,
        }

        # Helpers to read .env
        def _envf(key: str, default: str) -> float:
            try:
                return float(os.getenv(key, default))
            except Exception:
                return float(default)
        def _envb(key: str, default: str) -> bool:
            try:
                return str(os.getenv(key, default)).strip().lower() in {"1","true","yes","on"}
            except Exception:
                return str(default).strip().lower() in {"1","true","yes","on"}

        # Smoothing/damping (EMA). Higher alpha → faster response to target
        self.smoothing_alpha = _envf("MOTION_DAMPING_ALPHA", "0.92")

        # Slew-rate limits to prevent sudden jumps (warp)
        self.slew_angle_deg_per_sec = _envf("MOTION_SLEW_ANGLE_DEG_PER_SEC", "50.0")
        self.slew_pos_per_sec = _envf("MOTION_SLEW_POS_PER_SEC", "0.30")

        # Motion amplitude ranges
        self.range_angle_x = _envf("MOTION_RANGE_FACEANGLE_X", "20.0")
        self.range_angle_y = _envf("MOTION_RANGE_FACEANGLE_Y", "15.0")
        self.range_angle_z = _envf("MOTION_RANGE_FACEANGLE_Z", "10.0")
        self.range_pos_xy_min = _envf("MOTION_RANGE_FACEPOS_MIN", "0.05")
        self.range_pos_xy_max = _envf("MOTION_RANGE_FACEPOS_MAX", "0.10")

        # Base Perlin noise parameters
        self.noise_params = {
            "yaw": {"freq": 0.28, "amp": 1.0, "phase": random.uniform(0, 1000)},
            "pitch": {"freq": 0.24, "amp": 1.0, "phase": random.uniform(0, 1000)},
            "roll": {"freq": 0.26, "amp": 1.0, "phase": random.uniform(0, 1000)},
            "posx": {"freq": 0.22, "amp": 1.0, "phase": random.uniform(0, 1000)},
            "posy": {"freq": 0.20, "amp": 1.0, "phase": random.uniform(0, 1000)},
        }
        self._next_noise_shuffle_ts = 0.0

        # Continuous jitter settings
        self.jitter_freq_hz = _envf("MOTION_JITTER_FREQ_HZ", "1.2")
        self.jitter_amp_deg = _envf("MOTION_JITTER_AMP_DEG", "0.2")
        self.jitter_amp_pos = _envf("MOTION_JITTER_AMP_POS", "0.006")
        self._jitter_phase = {
            "x": random.uniform(0, 1000),
            "y": random.uniform(0, 1000),
            "z": random.uniform(0, 1000),
            "px": random.uniform(0, 1000),
            "py": random.uniform(0, 1000),
        }

        # Smile baseline and overlays
        self.smile_base_min = _envf("SMILE_BASE_MIN", "0.80")
        self.smile_base_max = _envf("SMILE_BASE_MAX", "1.00")
        self.smile_overlay_until = 0.0
        self.smile_overlay_value: Optional[float] = None

        # Blink state
        self.next_blink_ts = 0.0
        self.blink_duration = _envf("BLINK_DURATION", "0.30")
        self.blink_cluster_rem = 0

        # Speaking state
        self.speaking = False
        self.speech_amp = 0.0
        self.speech_target = 0.0
        self.speech_open_scale = 0.9

        # EMA/RL state
        self.prev: Dict[str, float] = {}
        self.out_prev: Dict[str, float] = {}

        # Jitter, breathing
        self.jitter_deg = _envf("MOTION_JITTER_DEG", "0.4")
        self.jitter_pos = _envf("MOTION_JITTER_POS", "0.01")
        self.breathe_freq = _envf("BREATH_FREQ_HZ", "0.15")
        self.breathe_amp = _envf("BREATH_AMP", "0.03")

        # Mood
        self.mood = "neutral"
        self._last_emote_ts = 0.0
        self._emote_cooldown_sec = 12.0
        self._emote_prob = {"thinking": 0.35, "happy": 0.35, "sad": 0.35}

        # Microphone reactive motion toggle
        self.enable_mic = _envb("ENABLE_MIC", "true")
        self._mic_stream = None

        # Stabilized face position amplitude drifting
        self.pos_amp_x = random.uniform(self.range_pos_xy_min, self.range_pos_xy_max)
        self.pos_amp_y = random.uniform(self.range_pos_xy_min, self.range_pos_xy_max)
        self.pos_amp_target_x = self.pos_amp_x
        self.pos_amp_target_y = self.pos_amp_y
        self._next_pos_amp_shuffle_ts = 0.0

        # Motion style and waypoint state
        self.motion_style = os.getenv("MOTION_STYLE", "waypoint").strip().lower()
        self.waypoint_min_sec = _envf("WAYPOINT_MIN_SEC", "2.5")
        self.waypoint_max_sec = _envf("WAYPOINT_MAX_SEC", "5.0")
        self._next_waypoint_ts = 0.0
        self._waypoint = {"ax": 0.0, "ay": 0.0, "az": 0.0, "px": 0.0, "py": 0.0}

        # Humanized idle micro-movement state
        self._micro_timer = 0.0
        self._micro_delay = random.uniform(3.0, 7.0)
        self._micro_intensity = 0.0
        self._micro_target_intensity = 0.0
        self._micro_mode = "idle"

    def _get_message_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def connect(self):
        url = f"ws://{self.host}:{self.port}"
        self.ws = await websockets.connect(url, ping_interval=15, ping_timeout=10)

    async def disconnect(self):
        try:
            if self.ws is not None:
                await self.ws.close()
        except Exception:
            pass
        finally:
            self.ws = None
            self.authenticated = False

    async def _request(self, message_type: str, data: Dict) -> Dict:
        req = {
            "apiName": API_NAME,
            "apiVersion": API_VERSION,
            "requestID": str(self._get_message_id()),
            "messageType": message_type,
            "data": data,
        }
        await self.ws.send(json.dumps(req))
        # Allow more time; VTS may take a few seconds to respond
        raw = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
        return json.loads(raw)

    async def authenticate(self) -> bool:
        token_resp = await self._request("AuthenticationTokenRequest", {
            "pluginName": self.plugin_name,
            "pluginDeveloper": self.plugin_developer,
        })
        token = token_resp.get("data", {}).get("authenticationToken")
        if not token:
            print("⚠️ No authentication token returned. Please allow the plugin in VTS.")
            return False

        auth_resp = await self._request("AuthenticationRequest", {
            "pluginName": self.plugin_name,
            "pluginDeveloper": self.plugin_developer,
            "authenticationToken": token,
        })
        ok = auth_resp.get("data", {}).get("authenticated")
        self.authenticated = bool(ok)
        print("✅ Authenticated with VTS" if ok else "❌ Authentication failed")
        return self.authenticated

    async def _get_current_model(self) -> Optional[str]:
        try:
            resp = await self._request("CurrentModelRequest", {})
            mid = resp.get("data", {}).get("modelID") or resp.get("data", {}).get("modelId")
            self.current_model_id = mid
            return mid
        except Exception:
            return None

    async def _get_live2d_parameters(self) -> Dict[str, Dict]:
        try:
            resp = await self._request("InputParameterListRequest", {})
            data = resp.get("data", {})
            defaults = data.get("defaultParameters", [])
            customs = data.get("customParameters", [])
            out = {}
            for p in defaults + customs:
                name = p.get("name") or p.get("id")
                if name:
                    out[str(name)] = p
            return out
        except Exception:
            return {}

    def _pick(self, available: Dict[str, Dict], candidates):
        aset = {k.lower(): k for k in available.keys()}
        for c in candidates:
            if c.lower() in aset:
                return aset[c.lower()]
        lc = list(aset.keys())
        for c in candidates:
            cl = c.lower()
            for k in lc:
                if cl in k:
                    return aset[k]
        return None

    async def _resolve_param_map(self):
        await self._get_current_model()
        params = await self._get_live2d_parameters()
        if not params:
            print("⚠️ Could not fetch model parameters. Motion updates may not apply.")
            return
        self.param_map["FaceAngleX"] = self._pick(params, ["FaceAngleX", "ParamAngleX", "AngleX"])  # yaw
        self.param_map["FaceAngleY"] = self._pick(params, ["FaceAngleY", "ParamAngleY", "AngleY"])  # pitch
        self.param_map["FaceAngleZ"] = self._pick(params, ["FaceAngleZ", "ParamAngleZ", "AngleZ"])  # roll
        self.param_map["FacePositionX"] = self._pick(params, ["FacePositionX", "ParamPositionX", "PositionX", "HeadX", "FaceX"])
        self.param_map["FacePositionY"] = self._pick(params, ["FacePositionY", "ParamPositionY", "PositionY", "HeadY", "FaceY"])
        self.param_map["MouthSmile"] = self._pick(params, ["MouthSmile", "ParamMouthSmile"])
        self.param_map["EyeOpenLeft"] = self._pick(params, ["EyeOpenLeft", "ParamEyeOpenLeft", "ParamEyeLOpen"])
        self.param_map["EyeOpenRight"] = self._pick(params, ["EyeOpenRight", "ParamEyeOpenRight", "ParamEyeROpen"])
        self.param_map["MouthOpen"] = self._pick(params, ["MouthOpen", "ParamMouthOpenY", "ParamMouthOpen"])
        print("🧭 Parameter mapping (generic -> model):")
        for k, v in self.param_map.items():
            print(f"  - {k} -> {v if v else 'N/A (skipped)'}")

    async def set_parameters(self, values: Dict[str, float], weight: float = 1.0):
        if not self.ws or not self.authenticated:
            return
        payload = {
            "apiName": API_NAME,
            "apiVersion": API_VERSION,
            "requestID": str(self._get_message_id()),
            "messageType": "InjectParameterDataRequest",
            "data": {
                "parameterValues": [
                    {"id": k, "value": float(v), "weight": float(weight)}
                    for k, v in values.items()
                ]
            }
        }
        try:
            await self.ws.send(json.dumps(payload))
            try:
                await asyncio.wait_for(self.ws.recv(), timeout=0.5)
            except Exception:
                pass
        except ConnectionClosed:
            self.authenticated = False
            self.ws = None

    def _shuffle_noise(self):
        def rnd_freq(base: float, jitter: float = 0.12):
            return max(0.05, base + random.uniform(-jitter, jitter))
        for key in self.noise_params.keys():
            self.noise_params[key]["freq"] = rnd_freq(self.noise_params[key]["freq"])
            self.noise_params[key]["amp"] = random.uniform(0.90, 1.10)
            self.noise_params[key]["phase"] = random.uniform(0, 1000)
        self._next_noise_shuffle_ts = time.time() + random.uniform(2.0, 5.0)

    def _perlin(self, t: float, key: str) -> float:
        p = self.noise_params[key]
        return float(pnoise1(t * p["freq"] + p["phase"]) * 2.0 * p["amp"])  # [-1, 1]

    def _ema(self, name: str, target: float) -> float:
        prev = self.prev.get(name, target)
        val = prev + (target - prev) * self.smoothing_alpha
        self.prev[name] = val
        return val

    def _rate_limit(self, name: str, target: float, dt: float, rate_per_sec: float) -> float:
        prev = self.out_prev.get(name, target)
        max_delta = rate_per_sec * max(0.0, dt)
        delta = target - prev
        if delta > max_delta:
            val = prev + max_delta
        elif delta < -max_delta:
            val = prev - max_delta
        else:
            val = target
        self.out_prev[name] = val
        return val

    def _clamp(self, x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))

    def _compute_blink(self, now: float) -> Optional[float]:
        blink_min = float(os.getenv("BLINK_MIN_SEC", "1.2"))
        blink_max = float(os.getenv("BLINK_MAX_SEC", "3.5"))
        if self.next_blink_ts == 0.0:
            self.next_blink_ts = now + random.uniform(blink_min, blink_max)
            return None
        if now >= self.next_blink_ts:
            self.next_blink_ts = 0.0
            self.blink_cluster_rem = random.choice([0, 1]) if random.random() < 0.12 else 0
            return 0.0
        return None

    def _update_speech(self):
        self.speech_amp += (self.speech_target - self.speech_amp) * 0.5

    def _poll_mic(self):
        if not self.enable_mic or sd is None:
            self.speech_target = 0.0
            return
        try:
            if self._mic_stream is None:
                self._mic_stream = sd.InputStream(channels=1, samplerate=16000, blocksize=1024)
                self._mic_stream.start()
            frames, _ = self._mic_stream.read(256)
            if frames is not None:
                arr = frames.flatten()
                rms = float((arr ** 2).mean() ** 0.5)
                lvl = max(0.0, min(1.0, rms * 20.0))
                self.speech_target = lvl
                self.speaking = lvl > 0.08
        except Exception:
            self.speech_target = 0.0
            self.speaking = False

    def _apply_smile(self, now: float) -> float:
        base = self.smile_base_min + random.random() * (self.smile_base_max - self.smile_base_min)
        if self.smile_overlay_value is not None and now < self.smile_overlay_until:
            return self._clamp(float(self.smile_overlay_value), 0.4, 1.2)
        return self._clamp(base, 0.4, 1.2)

    def set_mood(self, mood: str):
        m = (mood or "").strip().lower()
        self.mood = m if m in {"neutral", "happy", "sad", "thinking"} else "neutral"
        dur = random.uniform(2.0, 5.0)
        if self.mood == "happy":
            self.smile_overlay_value = 1.0 + random.uniform(0.0, 0.2)
            self.smile_overlay_until = time.time() + dur
        elif self.mood == "sad":
            self.smile_overlay_value = 0.4 + random.uniform(0.0, 0.2)
            self.smile_overlay_until = time.time() + dur
        else:
            self.smile_overlay_value = None
            self.smile_overlay_until = 0.0

    def _maybe_auto_emote(self, now: float):
        if now - self._last_emote_ts < self._emote_cooldown_sec:
            return
        p = self._emote_prob.get(self.mood, 0.0)
        if p and random.random() < p:
            self.set_mood(self.mood)
            self._last_emote_ts = now

    def _update_micro_motion(self, now: float, dt: float):
        """เพิ่มการขยับเล็กๆ แบบมนุษย์ เช่น ขยับหัว กะพริบตา เอียงตัวเล็กน้อย"""
        if now >= self._micro_timer:
            self._micro_timer = now + random.uniform(2.5, 6.0)
            # สลับโหมดระหว่าง idle, look_around, head_tilt
            self._micro_mode = random.choice(["idle", "look_around", "head_tilt"])
            self._micro_target_intensity = random.uniform(0.2, 1.0)

        # ค่อยๆ เคลื่อนไปยัง intensity เป้าหมาย
        self._micro_intensity += (self._micro_target_intensity - self._micro_intensity) * 0.05

        # ผลลัพธ์มุมเอียงเล็กๆ
        offset_x, offset_y, offset_z = 0.0, 0.0, 0.0
        if self._micro_mode == "look_around":
            offset_x = math.sin(now * 0.6) * 2.5 * self._micro_intensity
            offset_y = math.sin(now * 0.4) * 1.5 * self._micro_intensity
        elif self._micro_mode == "head_tilt":
            offset_z = math.sin(now * 0.8) * 1.2 * self._micro_intensity

        return offset_x, offset_y, offset_z

    async def run(self):
        await self.connect()
        ok = await self.authenticate()
        if not ok:
            print("❌ Unable to authenticate. Exiting.")
            return

        await self._resolve_param_map()

        start = time.time()
        last_time = start
        try:
            hz = float(os.getenv("MOTION_UPDATE_HZ", "60"))
        except Exception:
            hz = 60.0
        hz = max(24.0, min(120.0, hz))
        tick = 1.0 / hz
        self._shuffle_noise()
        blink_in_progress_until = 0.0
        blink_start_ts = 0.0

        while True:
            now = time.time()
            t = now - start
            dt = now - last_time
            last_time = now

            if now >= self._next_noise_shuffle_ts:
                self._shuffle_noise()

            self._poll_mic()
            self._update_speech()
            speak_gain = 1.0 + 0.8 * self.speech_amp

            yaw = self._perlin(t, "yaw")
            pitch = self._perlin(t, "pitch")
            roll = self._perlin(t, "roll")

            # ผสมการเคลื่อนไหวเล็กๆ แบบมนุษย์
            micro_x, micro_y, micro_z = self._update_micro_motion(now, dt)
            yaw += micro_x * 0.05
            pitch += micro_y * 0.05
            roll += micro_z * 0.05

            # Continuous jitter (Perlin-based) for micro-movements
            jx = float(pnoise1(t * self.jitter_freq_hz + self._jitter_phase["x"]) * self.jitter_amp_deg)
            jy = float(pnoise1(t * self.jitter_freq_hz + self._jitter_phase["y"]) * self.jitter_amp_deg)
            jz = float(pnoise1(t * self.jitter_freq_hz + self._jitter_phase["z"]) * self.jitter_amp_deg)

            context_energy = 1.0
            if self.mood == "happy":
                context_energy = 1.2
            elif self.mood == "sad":
                context_energy = 0.8
            elif self.mood == "thinking":
                context_energy = 0.9

            head_tilt_intensity = max(0.6, min(1.6, context_energy * speak_gain))

            if self.motion_style == "waypoint":
                if self._next_waypoint_ts == 0.0 or now >= self._next_waypoint_ts:
                    self._waypoint["ax"] = random.uniform(-self.range_angle_x, self.range_angle_x)
                    self._waypoint["ay"] = random.uniform(-self.range_angle_y * 0.8 * head_tilt_intensity, self.range_angle_y * 0.8 * head_tilt_intensity)
                    self._waypoint["az"] = random.uniform(-self.range_angle_z * 0.8 * head_tilt_intensity, self.range_angle_z * 0.8 * head_tilt_intensity)
                    self._waypoint["px"] = random.uniform(-self.range_pos_xy_max, self.range_pos_xy_max)
                    self._waypoint["py"] = random.uniform(-self.range_pos_xy_max, self.range_pos_xy_max)
                    self._next_waypoint_ts = now + random.uniform(self.waypoint_min_sec, self.waypoint_max_sec)

                target_ax = self._clamp(self._waypoint["ax"] + jx, -self.range_angle_x, self.range_angle_x)
                target_ay = self._clamp(self._waypoint["ay"] + jy, -self.range_angle_y, self.range_angle_y)
                target_az = self._clamp(self._waypoint["az"] + jz, -self.range_angle_z, self.range_angle_z)
            else:
                target_ax = self._clamp(yaw * self.range_angle_x + jx, -self.range_angle_x, self.range_angle_x)
                target_ay = self._clamp((pitch * self.range_angle_y * 0.8 * head_tilt_intensity) + jy, -self.range_angle_y, self.range_angle_y)
                target_az = self._clamp((roll * self.range_angle_z * 0.8 * head_tilt_intensity) + jz, -self.range_angle_z, self.range_angle_z)

            head_bob = 0.0
            if self.speaking:
                # ขยับหัวเบาๆ แบบตามจังหวะพูด (ไม่เกิน 4 องศา)
                head_bob = math.sin(t * (2.0 + self.speech_amp * 2.0)) * (1.5 + self.speech_amp * 2.0)
                target_ax = self._clamp(target_ax + head_bob * 0.5, -self.range_angle_x, self.range_angle_x)
                # ยิ้มเล็กน้อยระหว่างพูด
                if random.random() < 0.05:
                    self.smile_overlay_value = 1.05
                    self.smile_overlay_until = now + 0.5

            posx_noise = self._perlin(t, "posx")
            posy_noise = self._perlin(t, "posy")

            if self._next_pos_amp_shuffle_ts == 0.0 or now >= self._next_pos_amp_shuffle_ts:
                self.pos_amp_target_x = random.uniform(self.range_pos_xy_min, self.range_pos_xy_max)
                self.pos_amp_target_y = random.uniform(self.range_pos_xy_min, self.range_pos_xy_max)
                self._next_pos_amp_shuffle_ts = now + random.uniform(3.0, 6.0)

            amp_rate = 0.06
            self.pos_amp_x = self._clamp(self.pos_amp_x + max(-amp_rate * dt, min(amp_rate * dt, self.pos_amp_target_x - self.pos_amp_x)), self.range_pos_xy_min, self.range_pos_xy_max)
            self.pos_amp_y = self._clamp(self.pos_amp_y + max(-amp_rate * dt, min(amp_rate * dt, self.pos_amp_target_y - self.pos_amp_y)), self.range_pos_xy_min, self.range_pos_xy_max)
            breathing = self.breathe_amp * math.sin(t * 2.0 * math.pi * self.breathe_freq)
            jpx = float(pnoise1(t * (self.jitter_freq_hz * 1.2) + self._jitter_phase["px"]) * self.jitter_amp_pos)
            jpy = float(pnoise1(t * (self.jitter_freq_hz * 1.1) + self._jitter_phase["py"]) * self.jitter_amp_pos)

            if self.motion_style == "waypoint":
                target_px = self._clamp(self._waypoint["px"] + jpx, -self.range_pos_xy_max, self.range_pos_xy_max)
                target_py = self._clamp(self._waypoint["py"] + breathing + jpy, -self.range_pos_xy_max, self.range_pos_xy_max)
            else:
                target_px = self._clamp(posx_noise * self.pos_amp_x + jpx, -self.range_pos_xy_max, self.range_pos_xy_max)
                target_py = self._clamp(posy_noise * self.pos_amp_y + breathing + jpy, -self.range_pos_xy_max, self.range_pos_xy_max)

            ax_l = self._rate_limit("FaceAngleX", target_ax, dt, self.slew_angle_deg_per_sec)
            ay_l = self._rate_limit("FaceAngleY", target_ay, dt, self.slew_angle_deg_per_sec)
            az_l = self._rate_limit("FaceAngleZ", target_az, dt, self.slew_angle_deg_per_sec)
            px_l = self._rate_limit("FacePositionX", target_px, dt, self.slew_pos_per_sec)
            py_l = self._rate_limit("FacePositionY", target_py, dt, self.slew_pos_per_sec)

            ax = self._ema("FaceAngleX", ax_l)
            ay = self._ema("FaceAngleY", ay_l)
            az = self._ema("FaceAngleZ", az_l)
            px = self._ema("FacePositionX", px_l)
            py = self._ema("FacePositionY", py_l)

            self._maybe_auto_emote(now)
            smile = self._apply_smile(now)
            smile += 0.06 if self.speaking else 0.0
            smile = self._clamp(smile, 0.4, 1.2)

            eye_open = 1.0
            if blink_in_progress_until > 0.0:
                if now < blink_in_progress_until:
                    dur = max(0.05, blink_in_progress_until - blink_start_ts)
                    phase = self._clamp((now - blink_start_ts) / dur, 0.0, 1.0)
                    eye_open = self._clamp(1.0 - 4.0 * phase * (1.0 - phase), 0.0, 1.0)
                else:
                    if self.blink_cluster_rem > 0:
                        self.blink_cluster_rem -= 1
                        self.next_blink_ts = now + random.uniform(0.20, 0.40)
                    else:
                        self.next_blink_ts = now + random.uniform(1.0, 3.0)
                    blink_in_progress_until = 0.0
                    blink_start_ts = 0.0
            else:
                if self._compute_blink(now) == 0.0:
                    blink_start_ts = now
                    blink_in_progress_until = now + self.blink_duration * (1.0 + random.uniform(0.0, 0.3))

            mouth_open = self._clamp(self.speech_amp * self.speech_open_scale, 0.0, 1.0)

            updates = {}
            if self.param_map.get("FaceAngleX"): updates[self.param_map["FaceAngleX"]] = ax
            if self.param_map.get("FaceAngleY"): updates[self.param_map["FaceAngleY"]] = ay
            if self.param_map.get("FaceAngleZ"): updates[self.param_map["FaceAngleZ"]] = az
            if self.param_map.get("FacePositionX"): updates[self.param_map["FacePositionX"]] = px
            if self.param_map.get("FacePositionY"): updates[self.param_map["FacePositionY"]] = py
            if self.param_map.get("MouthSmile"): updates[self.param_map["MouthSmile"]] = smile
            if self.param_map.get("EyeOpenLeft"): updates[self.param_map["EyeOpenLeft"]] = eye_open
            if self.param_map.get("EyeOpenRight"): updates[self.param_map["EyeOpenRight"]] = eye_open
            if self.speaking and self.param_map.get("MouthOpen"):
                updates[self.param_map["MouthOpen"]] = mouth_open

            if updates:
                await self.set_parameters(updates, weight=1.0)

            await asyncio.sleep(tick)


async def run_motion():
    ctrl = VTSHumanMotionController()
    await ctrl.run()


if __name__ == "__main__":
    try:
        asyncio.run(run_motion())
    except KeyboardInterrupt:
        print("🛑 Shutdown by user")