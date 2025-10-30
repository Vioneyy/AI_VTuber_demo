"""
VTube Studio Client (tuned thresholds + resilient)
"""
import asyncio
import websockets
import json
import logging
import os
import time
from typing import Optional, Dict
import math
import os as _os

logger = logging.getLogger(__name__)

class VTSClient:
    def __init__(self, host: str = "localhost", port: int = 8001, plugin_name: str = "AI_VTuber", plugin_developer: Optional[str] = None, config: Optional[object] = None):
        self.host = host
        self.port = port
        # allow override from env to match VTS authorization
        self.plugin_name = os.getenv("VTS_PLUGIN_NAME", plugin_name)
        self.plugin_dev = plugin_developer or os.getenv("VTS_PLUGIN_DEV", "AI_VTuber_Team")
        self.config = config
        self.ws = None
        self.auth_token = None
        self.is_authenticated = False
        self._auth_task = None
        self._watchdog_task = None
        self._next_auth_try_ts = 0.0
        self._last_send_ts = 0.0
        self._min_send_interval_sec = float(os.getenv("VTS_SEND_MIN_INTERVAL_MS", "60")) / 1000.0
        # Heartbeat เพื่อกัน motion หยุดเมื่อการเปลี่ยนแปลงต่ำกว่า epsilon ต่อเนื่อง
        self._heartbeat_interval_sec = float(os.getenv("VTS_HEARTBEAT_SEC", "1.0"))
        self._heartbeat_delta = float(os.getenv("VTS_HEARTBEAT_DELTA", "0.03"))
        self._hb_toggle = 1.0
        # Force-send เมื่อพารามิเตอร์ค้างนานแม้เปลี่ยนแปลงน้อยกว่า epsilon
        self._stale_sec = float(os.getenv("VTS_PARAM_STALE_SEC", "0.6"))
        self._last_params: Dict[str, float] = {}
        self._last_param_ts: Dict[str, float] = {}
        # ใช้พารามิเตอร์ที่ระบบส่งจริงเพื่อ heartbeat กัน motion หยุดนิ่ง
        _alive_raw = os.getenv("VTS_ALIVE_PARAMS", "FaceAngleZ,FaceAngleX,FaceAngleY,FacePositionX,ParamEyeLSmile,ParamEyeRSmile")
        self._alive_params = [p.strip() for p in _alive_raw.split(",") if p.strip()]
        # error handling tunables to avoid long pauses
        self._error_suppress_sec = float(os.getenv("VTS_ERROR_SUPPRESS_SEC", "0.2"))
        self._backoff_max = float(os.getenv("VTS_BACKOFF_MAX", "2.0"))
        self._auth_retry_interval_sec = float(os.getenv("VTS_AUTH_RETRY_SEC", "4.0"))
        self._auth_timeout_sec = float(os.getenv("VTS_AUTH_TIMEOUT_SEC", "10.0"))
        self._last_auth_attempt_ts = 0.0
        # ป้องกันการ recv ซ้อนจากการ authenticate พร้อมกันหลาย coroutine
        self._auth_lock = asyncio.Lock()
        self._epsilon_map: Dict[str, float] = {
            "EyeOpenLeft": 0.03,
            "EyeOpenRight": 0.03,
            "FacePositionX": 0.025,
            "FacePositionY": 0.025,
            # ลด threshold ของมุมเพื่อให้การอัปเดตไม่หยุดนิ่ง
            "FaceAngleX": 0.05,
            "FaceAngleY": 0.05,
            "FaceAngleZ": 0.05,
            "MouthSmile": 0.01,
            "ParamEyeLSmile": 0.015,
            "ParamEyeRSmile": 0.015,
            "MouthOpen": 0.015,
        }
        self._backoff_factor = 1.0
        self._suppress_until_ts = 0.0
        # cache for main/demo integration
        self.available_parameters = []
        self.available_hotkeys = []
        # motion controller (lazy)
        self._motion_controller = None
        logger.info(f"VTSClient: {host}:{port}")

    def _is_connected(self) -> bool:
        if not self.ws:
            return False
        if hasattr(self.ws, 'closed'):
            try:
                return not self.ws.closed
            except Exception:
                return False
        elif hasattr(self.ws, 'close_code'):
            return self.ws.close_code is None
        else:
            return True

    async def connect(self):
        try:
            uri = f"ws://{self.host}:{self.port}"
            logger.info(f"📡 Connecting to VTS: {uri}")
            self.ws = await asyncio.wait_for(websockets.connect(uri, ping_interval=10, ping_timeout=60), timeout=6.0)
            logger.info("✅ WebSocket connected")
            await asyncio.sleep(0.4)
            self._backoff_factor = 1.0
            self._suppress_until_ts = 0.0
            self._last_params.clear()
            self._last_send_ts = 0.0
            await self._authenticate()
            if self.is_authenticated:
                logger.info("✅ VTS authenticated")
            else:
                logger.warning("⚠️ VTS connected but not authenticated")
                # เริ่มลูป retry การยืนยันตัวตนจนกว่าจะสำเร็จ
                if not self._auth_task:
                    self._auth_task = asyncio.create_task(self._auth_loop())
            # เริ่ม watchdog เพื่อตรวจจับการหยุดนิ่งและส่ง heartbeat/รีเชื่อมต่อ
            if not self._watchdog_task:
                self._watchdog_task = asyncio.create_task(self._watchdog())
            return True
        except Exception as e:
            logger.error(f"❌ VTS connect error: {e}")
            self.ws = None
            return False

    async def _authenticate(self):
        try:
            self._last_auth_attempt_ts = time.monotonic()
            auth_request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "auth_request",
                "messageType": "AuthenticationTokenRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": self.plugin_dev
                }
            }
            async with self._auth_lock:
                await self.ws.send(json.dumps(auth_request))
                response = await asyncio.wait_for(self.ws.recv(), timeout=self._auth_timeout_sec)
            data = json.loads(response)
            if "data" in data and "authenticationToken" in data["data"]:
                self.auth_token = data["data"]["authenticationToken"]
                logger.info("✅ got auth token")
            else:
                logger.error("❌ no auth token")
                return
            auth_msg = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "auth",
                "messageType": "AuthenticationRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": self.plugin_dev,
                    "authenticationToken": self.auth_token
                }
            }
            async with self._auth_lock:
                await self.ws.send(json.dumps(auth_msg))
                response = await asyncio.wait_for(self.ws.recv(), timeout=self._auth_timeout_sec)
            data = json.loads(response)
            if data.get("data", {}).get("authenticated"):
                self.is_authenticated = True
            else:
                logger.error("❌ Authentication failed")
        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")

    async def _auth_loop(self):
        try:
            while self._is_connected() and not self.is_authenticated:
                try:
                    await self._authenticate()
                    if self.is_authenticated:
                        logger.info("✅ VTS authenticated (retry loop)")
                        break
                except Exception as re:
                    logger.debug(f"Auth loop error: {re}")
                await asyncio.sleep(self._auth_retry_interval_sec)
        finally:
            self._auth_task = None

    async def disconnect(self):
        if self._is_connected():
            try:
                await self.ws.close()
                logger.info("🔌 VTS disconnected")
            except Exception as e:
                logger.debug(f"Error closing websocket: {e}")
        self.ws = None
        self.is_authenticated = False
        # stop auth retry task if running
        try:
            if self._auth_task:
                self._auth_task.cancel()
        except Exception:
            pass
        try:
            if self._watchdog_task:
                self._watchdog_task.cancel()
        except Exception:
            pass

    async def verify_connection(self):
        """Populate basic caches used by demo; returns True if connected.
        In minimal form, this just sets known parameter names; VTS API calls
        can be added if needed.
        """
        ok = self._is_connected() and self.is_authenticated
        # minimal, non-blocking defaults
        self.available_parameters = [
            "FaceAngleX", "FaceAngleY", "FaceAngleZ",
            "BodyAngleX", "BodyAngleY",
            "EyeOpenLeft", "EyeCloseLeft", "EyeOpenRight", "EyeCloseRight",
            "ParamEyeLSmile", "ParamEyeRSmile",
            "BrowLY", "BrowLF", "BrowRY", "BrowRF",
            "MouthForm", "MouthOpen", "MouthX",
        ]
        self.available_hotkeys = []
        return ok

    async def inject_parameter(self, param_name: str, value: float):
        # ถ้ายังไม่ connected หรือยังไม่ authenticated ให้พยายามยืนยันตัวตนแบบ throttle
        if not self._is_connected():
            return
        if not self.is_authenticated:
            now = time.monotonic()
            if now >= self._next_auth_try_ts:
                self._next_auth_try_ts = now + self._auth_retry_interval_sec
                try:
                    await self._authenticate()
                    if not self.is_authenticated and not self._auth_task:
                        self._auth_task = asyncio.create_task(self._auth_loop())
                except Exception:
                    pass
            return
        # เคารพ suppress window เมื่อเกิด error ล่าสุด
        if time.monotonic() < self._suppress_until_ts:
            return
        try:
            msg = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": f"inject_{param_name}_{int(time.time()*1000)}",
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "parameterValues": [{"id": param_name, "value": float(value)}]
                }
            }
            await self.ws.send(json.dumps(msg))
            v = float(value)
            now = time.monotonic()
            self._last_params[param_name] = v
            self._last_param_ts[param_name] = now
            self._last_send_ts = now
        except Exception as e:
            logger.error(f"Inject parameter error: {e}")
            # เพิ่ม backoff และกดพักการส่งชั่วคราว จากนั้นรีเชื่อมต่อ
            self._backoff_factor = min(self._backoff_factor * 1.3, self._backoff_max)
            self._suppress_until_ts = time.monotonic() + self._error_suppress_sec
            await asyncio.sleep(0.3)
            try:
                await self.disconnect()
                await self.connect()
            except Exception as re:
                logger.error(f"Reconnect failed: {re}")

    async def set_parameter_value(self, param_name: str, value: float):
        """Compatibility wrapper used by demo; delegates to inject_parameter."""
        await self.inject_parameter(param_name, value)

    async def _watchdog(self):
        """เฝ้าระวังการหยุดนิ่ง/สูญเสียการยืนยันตัวตน ขยับด้วย heartbeat เมื่อไม่มีการส่ง
        และรีลองยืนยันตัวตนตามช่วงเวลา"""
        try:
            while self._is_connected():
                now = time.monotonic()
                # ถ้าหยุดส่งนาน ให้ส่ง heartbeat หลายพารามิเตอร์เพื่อกระตุ้น VTS
                if self.is_authenticated and (now - self._last_send_ts) > (self._heartbeat_interval_sec * 2.0):
                    try:
                        await self.inject_parameters_bulk({})
                    except Exception:
                        pass
                # ถ้าหลุด auth ให้พยายามยืนยันใหม่แบบ throttle
                if not self.is_authenticated and now >= self._next_auth_try_ts:
                    self._next_auth_try_ts = now + self._auth_retry_interval_sec
                    try:
                        await self._authenticate()
                    except Exception:
                        pass
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    async def inject_parameters_bulk(self, params: Dict[str, float]):
        if not self._is_connected():
            return
        # ถ้ายังไม่ authenticated ให้พยายามยืนยันตัวตนแบบ throttle และออก
        if not self.is_authenticated:
            now = time.monotonic()
            if now >= self._next_auth_try_ts:
                self._next_auth_try_ts = now + self._auth_retry_interval_sec
                try:
                    if not self._auth_task:
                        self._auth_task = asyncio.create_task(self._auth_loop())
                except Exception:
                    pass
            return
        try:
            now = time.monotonic()
            if now < self._suppress_until_ts:
                return
            # สร้าง filtered_values ก่อน แล้วค่อยตัดสินใจ rate-limit สำหรับการส่งปกติ
            filtered_values = []
            for name, value in params.items():
                last = self._last_params.get(name)
                eps = self._epsilon_map.get(name, 0.02)
                delta_ok = (last is None) or (abs(float(value) - float(last)) >= eps)
                stale_ok = (now - self._last_param_ts.get(name, 0.0)) >= self._stale_sec
                if delta_ok or stale_ok:
                    v = float(value)
                    filtered_values.append({"id": name, "value": v})
                    self._last_params[name] = v
                    self._last_param_ts[name] = now
            # หากไม่มีค่าที่ผ่าน threshold ต่อเนื่อง ให้ส่ง heartbeat หลายพารามิเตอร์เพื่อกันการหยุดนิ่ง
            if not filtered_values:
                # bypass rate-limit: ใช้ heartbeat_interval แทน effective_interval
                if (now - self._last_send_ts) >= self._heartbeat_interval_sec:
                    values = []
                    alive = self._alive_params or ["FaceAngleZ"]
                    for idx, name in enumerate(alive):
                        base = float(params.get(name, self._last_params.get(name, 0.0)))
                        val = base
                        # ใส่ dithering ที่พารามิเตอร์ตัวแรกเพื่อกระตุ้น VTS เสมอ
                        if idx == 0:
                            val = base + (self._hb_toggle * self._heartbeat_delta)
                            if name.startswith("FaceAngle"):
                                val = max(-30.0, min(30.0, val))
                            else:
                                val = max(0.0, min(1.0, val))
                        values.append({"id": name, "value": float(val)})
                        self._last_params[name] = float(val)
                        self._last_param_ts[name] = now

                    payload = {
                        "apiName": "VTubeStudioPublicAPI",
                        "apiVersion": "1.0",
                        "requestID": f"inject_params_heartbeat_{int(time.time()*1000)}",
                        "messageType": "InjectParameterDataRequest",
                        "data": {"parameterValues": values}
                    }
                    await self.ws.send(json.dumps(payload))
                    self._hb_toggle *= -1.0
                    self._last_send_ts = now
                return
            # ปกติ: เคารพ effective rate-limit
            effective_interval = self._min_send_interval_sec * self._backoff_factor
            if (now - self._last_send_ts) < effective_interval:
                return
            payload = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": f"inject_params_batch_{int(time.time()*1000)}",
                "messageType": "InjectParameterDataRequest",
                "data": {"parameterValues": filtered_values}
            }
            await self.ws.send(json.dumps(payload))
            self._last_send_ts = now
        except Exception as e:
            logger.error(f"Inject parameters bulk error: {e}", exc_info=True)
            self._backoff_factor = min(self._backoff_factor * 1.3, self._backoff_max)
            self._suppress_until_ts = time.monotonic() + self._error_suppress_sec
            await asyncio.sleep(0.3)
            try:
                await self.disconnect()
                await self.connect()
            except Exception as re:
                logger.error(f"Reconnect failed: {re}", exc_info=True)

    async def trigger_hotkey(self, hotkey_id: str):
        if not self._is_connected() or not self.is_authenticated:
            return
        try:
            msg = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": f"trigger_hotkey_{int(time.time()*1000)}",
                "messageType": "HotkeyTriggerRequest",
                "data": {"hotkeyID": hotkey_id}
            }
            await self.ws.send(json.dumps(msg))
            logger.info(f"💫 Triggered hotkey: {hotkey_id}")
        except Exception as e:
            logger.error(f"Trigger hotkey error: {e}", exc_info=True)

    async def trigger_hotkey_by_name(self, name: str):
        """Convenience wrapper: map common emotion names to known hotkey IDs."""
        mapping = {
            "happy": "happy_trigger",
            "sad": "sad_trigger",
            "angry": "angry_trigger",
            "surprised": "surprised_trigger",
            "thinking": "thinking_trigger",
        }
        hk = mapping.get((name or "").lower(), name)
        try:
            await self.trigger_hotkey(hk)
        except Exception:
            pass

    async def compute_mouth_envelope(self, audio_bytes: bytes):
        """
        Enhanced mouth envelope computation with improved word-level accuracy
        คืนค่า (mouth_series: List[float], interval_sec: float)
        """
        try:
            import io, wave
            import numpy as np
            from scipy import signal
            
            wav_io = io.BytesIO(audio_bytes)
            with wave.open(wav_io, 'rb') as wav:
                sample_rate = wav.getframerate()
                n_frames = wav.getnframes()
                n_channels = wav.getnchannels()
                sampwidth = wav.getsampwidth()
                raw = wav.readframes(n_frames)

            # dtype/scale
            if sampwidth == 2:
                dtype = np.int16
                scale = 32768.0
            elif sampwidth == 1:
                dtype = np.uint8
                scale = 255.0
            elif sampwidth == 4:
                dtype = np.int32
                scale = 2147483648.0
            else:
                dtype = np.int16
                scale = 32768.0

            audio = np.frombuffer(raw, dtype=dtype)
            if n_channels > 1:
                audio = audio.reshape(-1, n_channels).mean(axis=1)
            audio = audio.astype(np.float32) / float(scale)

            # Enhanced analysis for better word-level sync
            min_interval = max(0.02, self._min_send_interval_sec)  # Higher resolution
            target_fps = max(30, int(1.0 / min_interval))  # Increased FPS for accuracy
            window_size = max(1, int(sample_rate / target_fps))
            hop_size = window_size // 2  # 50% overlap for smoother transitions

            # Multi-band analysis for better speech detection
            # High-pass filter to emphasize speech frequencies
            try:
                nyquist = sample_rate / 2
                high_cutoff = 300 / nyquist  # Remove low-frequency noise
                b, a = signal.butter(2, high_cutoff, btype='high')
                audio_filtered = signal.filtfilt(b, a, audio)
            except:
                audio_filtered = audio  # Fallback if scipy not available

            # Compute RMS with overlap for smoother envelope
            rms = []
            for i in range(0, len(audio_filtered) - window_size + 1, hop_size):
                chunk = audio_filtered[i:i+window_size]
                if len(chunk) == 0:
                    continue
                
                # Enhanced RMS calculation with spectral centroid weighting
                rms_val = float(np.sqrt(np.mean(np.square(chunk))))
                
                # Add spectral emphasis for consonants and vowels
                if len(chunk) > 1:
                    # Simple spectral centroid approximation
                    diff_energy = float(np.mean(np.abs(np.diff(chunk))))
                    spectral_weight = 1.0 + min(0.3, diff_energy * 10)
                    rms_val *= spectral_weight
                
                rms.append(rms_val)
            
            if not rms:
                return [], min_interval
                
            rms = np.array(rms, dtype=np.float32)
            
            # Improved normalization with dynamic range compression
            peak = float(np.percentile(rms, 95)) or 1e-6  # Use 95th percentile for better dynamics
            noise_floor = float(np.percentile(rms, 10)) or 1e-8
            
            # Dynamic range compression
            compressed_rms = np.log1p(rms / max(noise_floor, 1e-8)) / np.log1p(peak / max(noise_floor, 1e-8))
            env = np.clip(compressed_rms, 0.0, 1.0)

            # Multi-stage smoothing for natural mouth movement
            # Stage 1: Fast response for attack
            alpha_fast = 0.6
            smooth_fast = np.zeros_like(env)
            s_fast = 0.0
            for i, v in enumerate(env):
                s_fast = (1.0 - alpha_fast) * s_fast + alpha_fast * v
                smooth_fast[i] = s_fast

            # Stage 2: Slower response for decay
            alpha_slow = 0.2
            smooth_slow = np.zeros_like(env)
            s_slow = 0.0
            for i, v in enumerate(smooth_fast):
                s_slow = (1.0 - alpha_slow) * s_slow + alpha_slow * v
                smooth_slow[i] = s_slow

            # Combine fast attack with slow decay for natural speech
            smooth = np.maximum(smooth_fast * 0.7, smooth_slow * 0.3)

            # Enhanced mouth mapping with phoneme-aware scaling
            base = 0.02  # Smaller base for more closed mouth at rest
            gain = 0.9   # Higher gain for more expressive movement
            
            # Add micro-variations for more natural movement
            micro_noise = np.random.normal(0, 0.01, len(smooth))
            smooth += micro_noise
            
            mouth_series = np.clip(base + gain * smooth, 0.0, 1.0)
            
            # Ensure minimum mouth movement duration for visibility
            min_open_duration = int(0.05 / min_interval)  # 50ms minimum
            for i in range(len(mouth_series) - min_open_duration):
                if mouth_series[i] > 0.3:  # If mouth is significantly open
                    # Ensure it stays open for minimum duration
                    for j in range(i, min(i + min_open_duration, len(mouth_series))):
                        mouth_series[j] = max(mouth_series[j], mouth_series[i] * 0.8)
            
            logger.info(f"🎤 Enhanced lip-sync: {len(mouth_series)} samples @ {min_interval:.3f}s, range: {mouth_series.min():.3f}-{mouth_series.max():.3f}")
            return [float(x) for x in mouth_series], float(min_interval)
            
        except ImportError:
            # Fallback to original method if scipy not available
            logger.warning("scipy not available, using basic lip-sync method")
            return await self._compute_mouth_envelope_basic(audio_bytes)
        except Exception as e:
            logger.error(f"compute_mouth_envelope error: {e}", exc_info=True)
            return [], float(max(0.03, self._min_send_interval_sec))

    async def _compute_mouth_envelope_basic(self, audio_bytes: bytes):
        """Basic fallback method for mouth envelope computation"""
        try:
            import io, wave
            import numpy as np
            wav_io = io.BytesIO(audio_bytes)
            with wave.open(wav_io, 'rb') as wav:
                sample_rate = wav.getframerate()
                n_frames = wav.getnframes()
                n_channels = wav.getnchannels()
                sampwidth = wav.getsampwidth()
                raw = wav.readframes(n_frames)

            # dtype/scale
            if sampwidth == 2:
                dtype = np.int16
                scale = 32768.0
            elif sampwidth == 1:
                dtype = np.uint8
                scale = 255.0
            elif sampwidth == 4:
                dtype = np.int32
                scale = 2147483648.0
            else:
                dtype = np.int16
                scale = 32768.0

            audio = np.frombuffer(raw, dtype=dtype)
            if n_channels > 1:
                audio = audio.reshape(-1, n_channels).mean(axis=1)
            audio = audio.astype(np.float32) / float(scale)

            min_interval = max(0.03, self._min_send_interval_sec)
            target_fps = max(15, int(1.0 / min_interval))
            window_size = max(1, int(sample_rate / target_fps))

            rms = []
            for i in range(0, len(audio), window_size):
                chunk = audio[i:i+window_size]
                if len(chunk) == 0:
                    continue
                val = float(np.sqrt(np.mean(np.square(chunk))))
                rms.append(val)
            if not rms:
                return [], min_interval
            rms = np.array(rms, dtype=np.float32)
            peak = float(np.percentile(rms, 98)) or 1e-6
            env = np.clip(rms / max(peak, 1e-6), 0.0, 1.0)

            alpha = 0.35
            smooth = np.zeros_like(env)
            s = 0.0
            for i, v in enumerate(env):
                s = (1.0 - alpha) * s + alpha * v
                smooth[i] = s

            base = 0.05
            gain = 0.85
            mouth_series = np.clip(base + gain * smooth, 0.0, 1.0)
            return [float(x) for x in mouth_series], float(min_interval)
        except Exception as e:
            logger.error(f"basic mouth envelope error: {e}", exc_info=True)
            return [], float(max(0.03, self._min_send_interval_sec))

    async def lipsync_bytes(self, audio_bytes: bytes):
        # ใช้ property ไม่เรียกเป็นเมธอด; คงค่า mouth ตามพลังเสียงจริง (RMS) และส่งแบบ bulk
        if not self._is_connected() or not self.is_authenticated:
            logger.warning("VTS not connected - skip lipsync")
            return
        try:
            import io, wave, struct
            import numpy as np
            wav_io = io.BytesIO(audio_bytes)
            with wave.open(wav_io, 'rb') as wav:
                sample_rate = wav.getframerate()
                n_frames = wav.getnframes()
                n_channels = wav.getnchannels()
                sampwidth = wav.getsampwidth()
                raw = wav.readframes(n_frames)
            duration = n_frames / float(sample_rate)
            logger.info(f"🎤 Lipsync: {duration:.2f}s, {sample_rate}Hz, ch={n_channels}, sw={sampwidth}")

            # แปลงเป็น numpy และรวมเป็นมอโนเพื่อคำนวณ RMS
            if sampwidth == 2:
                dtype = np.int16
                scale = 32768.0
            elif sampwidth == 1:
                dtype = np.uint8
                scale = 255.0
            elif sampwidth == 4:
                dtype = np.int32
                scale = 2147483648.0
            else:
                dtype = np.int16
                scale = 32768.0

            audio = np.frombuffer(raw, dtype=dtype)
            if n_channels > 1:
                audio = audio.reshape(-1, n_channels).mean(axis=1)
            audio = audio.astype(np.float32) / float(scale)

            # ใช้เฟรมตาม min send interval เพื่อไม่ชนกับ rate-limit ของ VTS
            min_interval = max(0.03, self._min_send_interval_sec)
            target_fps = max(15, int(1.0 / min_interval))  # อย่างน้อย 15Hz
            window_size = max(1, int(sample_rate / target_fps))

            # สร้าง envelope แบบ RMS ต่อหน้าต่าง และทำ smoothing
            rms = []
            for i in range(0, len(audio), window_size):
                chunk = audio[i:i+window_size]
                if len(chunk) == 0:
                    continue
                val = float(np.sqrt(np.mean(np.square(chunk))))
                rms.append(val)
            if not rms:
                return
            rms = np.array(rms, dtype=np.float32)
            # normalize และจำกัดช่วง [0,1]
            peak = float(np.percentile(rms, 98)) or 1e-6
            env = np.clip(rms / max(peak, 1e-6), 0.0, 1.0)
            # smoothing EMA
            alpha = 0.35
            smooth = np.zeros_like(env)
            s = 0.0
            for i, v in enumerate(env):
                s = (1.0 - alpha) * s + alpha * v
                smooth[i] = s

            # map เป็นค่า mouth open โดยมี base และเพดาน
            base = 0.05
            gain = 0.85
            mouth_series = np.clip(base + gain * smooth, 0.0, 1.0)

            # ส่งเป็น bulk ทีละเฟรมด้วย min interval
            for mv in mouth_series:
                await self.inject_parameters_bulk({"MouthOpen": float(mv)})
                await asyncio.sleep(min_interval)
            # ปิดปากกลับสู่ base อย่างนุ่มนวล
            await self.inject_parameters_bulk({"MouthOpen": float(base)})
            logger.info("✅ Lipsync finished")
        except Exception as e:
            logger.error(f"Lipsync error: {e}", exc_info=True)

    # -------------------- Random Motion (Neuro-inspired) Helpers --------------------
    def _ensure_motion_controller(self):
        if self._motion_controller is not None:
            return
        try:
            from .motion_controller import create_motion_controller
        except Exception:
            try:
                from src.adapters.vts.motion_controller import create_motion_controller
            except Exception as e:
                logger.error(f"MotionController import failed: {e}", exc_info=True)
                return
        # Use provided config if it's dict-like; else fall back to environment
        env_like = {}
        try:
            if isinstance(self.config, dict):
                env_like = self.config
            else:
                # expose env vars for controller tuning
                env_like = _os.environ
        except Exception:
            env_like = _os.environ
        try:
            self._motion_controller = create_motion_controller(self, env_like)
            logger.info("✅ MotionController ready (lazy-init)")
        except Exception as e:
            logger.error(f"MotionController creation failed: {e}", exc_info=True)
            self._motion_controller = None

    async def start_neuro_random_events(self):
        """Start continuous random motion using MotionController."""
        if not self._is_connected():
            logger.warning("VTS not connected; cannot start random events")
            return
        self._ensure_motion_controller()
        if not self._motion_controller:
            logger.warning("MotionController unavailable")
            return
        try:
            await self._motion_controller.start()
            logger.info("🎬 Neuro-random events started")
        except Exception as e:
            logger.error(f"start_neuro_random_events error: {e}", exc_info=True)

    async def stop_neuro_random_events(self):
        """Stop random motion."""
        if not self._motion_controller:
            return
        try:
            await self._motion_controller.stop()
            logger.info("🛑 Neuro-random events stopped")
        except Exception as e:
            logger.error(f"stop_neuro_random_events error: {e}", exc_info=True)

    async def play_neuro_random_events(self, duration_sec: float = 20.0):
        """Play random motion for a fixed duration, then stop."""
        try:
            await self.start_neuro_random_events()
            d = float(duration_sec or 0.0)
            if d > 0:
                await asyncio.sleep(d)
            await self.stop_neuro_random_events()
        except Exception as e:
            logger.error(f"play_neuro_random_events error: {e}", exc_info=True)

    async def play_neuro_clip_preset(self, duration_sec: float = 20.0):
        """Scripted preset placeholder: delegate to random events for now."""
        await self.play_neuro_random_events(duration_sec=duration_sec)

    # -------------------- Style Profile Stub --------------------
    def apply_style_profile_from_config(self):
        """Optional helper for main.py; currently a no-op with safe logging."""
        try:
            # Future: apply style presets to epsilon, smoothing, etc.
            logger.info("🎨 Style profile applied (stub)")
        except Exception:
            pass
