"""
ระบบควบคุม VTube Studio - Fixed Jittering & Lip Sync
แก้ไข:
1. ลดการกระตุก (jittering) ด้วย delta threshold + rate limiting
2. ปรับ lip sync ให้ตรงคำและเป็นธรรมชาติ
3. แก้ไขการ transition idle ให้ราบรื่น
"""

import asyncio
import websockets
import json
import random
import time
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)

class AnimationState(Enum):
    """สถานะการเคลื่อนไหว"""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"

class SmoothValue:
    """คลาสสำหรับทำให้ค่าเคลื่อนไหวนุ่มนวล"""
    def __init__(
        self,
        initial_value: float = 0.0,
        smooth_factor: float = 0.15,
        max_delta: float = 0.08,
        snap_epsilon: float = 0.002,  # ✅ เพิ่มจาก 0.001 → 0.002 เพื่อลด jitter
    ):
        self.current = initial_value
        self.target = initial_value
        self.smooth_factor = smooth_factor
        self.max_delta = max_delta
        self.snap_epsilon = snap_epsilon
    
    def set_target(self, value: float):
        self.target = value
    
    def update(self) -> float:
        diff = self.target - self.current
        
        # ✅ Snap เร็วขึ้นเพื่อลด oscillation
        if abs(diff) < self.snap_epsilon:
            self.current = self.target
            return self.current
        
        delta = diff * self.smooth_factor
        
        # ✅ จำกัด delta
        if self.max_delta is not None:
            delta = max(-self.max_delta, min(self.max_delta, delta))
        
        self.current += delta
        return self.current

class VTubeStudioController:
    """ควบคุม VTube Studio ผ่าน WebSocket"""
    
    def __init__(self):
        # ✅ อ่าน config จาก core.config
        from core.config import config
        
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.authenticated = False
        self.auth_token: Optional[str] = config.vtube.plugin_token
        self.model_loaded = False
        self.model_id = None
        self.animation_task: Optional[asyncio.Task] = None
        self.state = AnimationState.IDLE
        self.running = False
        
        # Available parameters
        self.available_parameters: Dict[str, Dict] = {}
        
        # ✅ Smooth values with improved settings
        smooth_factor = config.vtube.smooth_factor
        self.smooth_values = {
            'FaceAngleX': SmoothValue(0, smooth_factor, 0.06),
            'FaceAngleY': SmoothValue(0, smooth_factor, 0.06),
            'FaceAngleZ': SmoothValue(0, smooth_factor, 0.06),
            'FacePositionX': SmoothValue(0, smooth_factor, 0.04),
            'FacePositionY': SmoothValue(0, smooth_factor, 0.04),
            'EyeLeftX': SmoothValue(0, smooth_factor, 0.08),
            'EyeLeftY': SmoothValue(0, smooth_factor, 0.08),
            'EyeRightX': SmoothValue(0, smooth_factor, 0.08),
            'EyeRightY': SmoothValue(0, smooth_factor, 0.08),
            'MouthOpen': SmoothValue(0, smooth_factor * 1.5, 0.15),  # ✅ เร็วขึ้นสำหรับปาก
        }
        
        # Movement parameters
        self.movement_intensity = 0.8
        self.movement_speed = 1.0
        self.intensity_variation = 0.3
        
        # Timers
        self.last_movement_change = time.time()
        self.last_eye_movement = time.time()
        self.movement_duration = random.uniform(1.5, 3.0)
        self.eye_movement_duration = random.uniform(0.8, 2.0)
        
        # Lip sync state
        self._lip_sync_task: Optional[asyncio.Task] = None
        self._lip_sync_running: bool = False
        
        # ✅ จำกัดอัตราการส่ง parameter
        self._last_send_ts: float = 0.0
        self._min_send_interval: float = 0.040  # 40ms (25 FPS)
        self._last_sent_values: Dict[str, float] = {}
        self._send_threshold: float = 0.005  # ✅ ส่งเฉพาะเมื่อเปลี่ยนแปลง > 0.5%
        
        # ✅ Reconnect management
        self._reconnecting: bool = False
        self._last_reconnect_ts: float = 0.0
        self._reconnect_min_interval: float = 5.0
    
    async def connect(self) -> bool:
        """เชื่อมต่อกับ VTube Studio"""
        try:
            from core.config import config
            
            logger.info("📡 กำลังเชื่อมต่อ VTube Studio...")
            
            self.ws = await websockets.connect(
                config.vtube.websocket_url,
                ping_interval=30,
                ping_timeout=60,
                close_timeout=5
            )
            logger.info("✅ WebSocket เชื่อมต่อสำเร็จ")
            
            await self._authenticate()
            await self._get_current_model()
            
            if not self.model_loaded:
                logger.warning("⚠️ ไม่พบโมเดลที่โหลดอยู่")
                return False
            
            await self._get_available_parameters()
            
            # ✅ เริ่ม animation loop
            if not self.running or not self.animation_task or self.animation_task.done():
                self.running = True
                self.animation_task = asyncio.create_task(self._animation_loop())
            
            logger.info("✅ VTube Studio พร้อมใช้งาน")
            return True
            
        except Exception as e:
            logger.error(f"❌ เชื่อมต่อ VTS ล้มเหลว: {e}", exc_info=True)
            return False

    async def _ensure_ws(self) -> bool:
        """ตรวจสอบและเชื่อมต่อใหม่แบบปลอดภัย"""
        try:
            if self.ws and getattr(self.ws, 'open', False):
                return True

            now = time.time()
            if self._reconnecting or (now - self._last_reconnect_ts) < self._reconnect_min_interval:
                return False

            self._reconnecting = True
            self._last_reconnect_ts = now
            
            if self.ws:
                try:
                    await self.ws.close()
                except:
                    pass
                self.ws = None

            from core.config import config
            self.ws = await websockets.connect(
                config.vtube.websocket_url,
                ping_interval=30,
                ping_timeout=60,
                close_timeout=5
            )
            
            await self._authenticate()
            await self._get_current_model()
            
            if not self.model_loaded:
                self._reconnecting = False
                return False
                
            await self._get_available_parameters()
            
            logger.info("✅ Reconnected VTS WebSocket")
            self._reconnecting = False
            return True
            
        except Exception as e:
            self._reconnecting = False
            logger.debug(f"Reconnect failed: {e}")
            return False
    
    async def _authenticate(self):
        """ขอ authentication"""
        try:
            from core.config import config
            
            if self.auth_token:
                auth_data = {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": "auth",
                    "messageType": "AuthenticationRequest",
                    "data": {
                        "pluginName": config.vtube.plugin_name,
                        "pluginDeveloper": "vioneyy",
                        "authenticationToken": self.auth_token
                    }
                }
            else:
                auth_data = {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": "auth_token_request",
                    "messageType": "AuthenticationTokenRequest",
                    "data": {
                        "pluginName": config.vtube.plugin_name,
                        "pluginDeveloper": "vioneyy"
                    }
                }
            
            await self.ws.send(json.dumps(auth_data))
            response = json.loads(await self.ws.recv())
            
            if "authenticationToken" in response.get("data", {}):
                self.auth_token = response["data"]["authenticationToken"]
                logger.info(f"💾 บันทึก token นี้ใน .env:")
                logger.info(f"VTS_PLUGIN_TOKEN={self.auth_token}")
                await self._authenticate()
                
            elif response.get("data", {}).get("authenticated"):
                self.authenticated = True
                logger.info("✅ VTS Authentication สำเร็จ")
            else:
                logger.warning(f"⚠️ Authentication ล้มเหลว: {response}")
                
        except Exception as e:
            logger.error(f"❌ Authentication Error: {e}")
    
    async def _get_current_model(self):
        """ดึงข้อมูลโมเดลปัจจุบัน"""
        try:
            request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "get_model",
                "messageType": "CurrentModelRequest"
            }
            
            await self.ws.send(json.dumps(request))
            response = json.loads(await self.ws.recv())
            
            if response.get("data", {}).get("modelLoaded"):
                self.model_loaded = True
                self.model_id = response["data"]["modelID"]
                model_name = response["data"]["modelName"]
                logger.info(f"✅ พบโมเดล: {model_name}")
            else:
                logger.warning("⚠️ ไม่พบโมเดลที่โหลดอยู่")
                
        except Exception as e:
            logger.error(f"❌ Get Model Error: {e}")
    
    async def _get_available_parameters(self):
        """ดึงรายการ parameters ที่โมเดลมี"""
        try:
            request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "get_params",
                "messageType": "InputParameterListRequest"
            }
            
            await self.ws.send(json.dumps(request))
            response = json.loads(await self.ws.recv())
            
            if response.get("data", {}).get("defaultParameters"):
                for param in response["data"]["defaultParameters"]:
                    param_name = param["name"]
                    self.available_parameters[param_name] = {
                        "min": param["min"],
                        "max": param["max"],
                        "value": param["value"]
                    }
                
                logger.info(f"📋 พบ {len(self.available_parameters)} parameters")
                
                important = ['FaceAngleX', 'FaceAngleY', 'FaceAngleZ', 'MouthOpen']
                available_important = [p for p in important if p in self.available_parameters]
                if available_important:
                    logger.info(f"✅ Parameters ที่มี: {', '.join(available_important)}")
                    
        except Exception as e:
            logger.error(f"❌ Get Parameters Error: {e}")

    async def _send_parameters(self, parameters: Dict[str, float]):
        """ส่งค่าพารามิเตอร์ไปยัง VTS (ปรับปรุง - ลด jitter)"""
        if not self.authenticated or not self.model_loaded or not self.ws:
            return

        try:
            if self.ws.state.name != 'OPEN':
                ok = await self._ensure_ws()
                if not ok:
                    return
        except Exception:
            pass

        # ✅ Rate limiting - ส่งไม่เกิน 25 FPS (40ms interval)
        now = time.time()
        if (now - self._last_send_ts) < self._min_send_interval:
            return

        try:
            valid_params = []
            
            # ✅ Delta guard - ส่งเฉพาะที่เปลี่ยนแปลงมากพอ
            for param_name, value in parameters.items():
                if param_name not in self.available_parameters:
                    continue
                    
                param_info = self.available_parameters[param_name]
                clamped_value = max(param_info['min'], min(param_info['max'], value))
                
                last_val = self._last_sent_values.get(param_name, None)
                
                # ✅ ส่งเฉพาะเมื่อเปลี่ยนแปลง > threshold
                if last_val is None or abs(clamped_value - last_val) >= self._send_threshold:
                    valid_params.append({
                        "id": param_name,
                        "value": clamped_value
                    })
                    self._last_sent_values[param_name] = clamped_value

            if not valid_params:
                return
            
            request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "inject_params",
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "parameterValues": valid_params
                }
            }
            
            await asyncio.wait_for(
                self.ws.send(json.dumps(request)),
                timeout=0.5
            )
            
            self._last_send_ts = now
                
        except asyncio.TimeoutError:
            logger.debug("⚠️ Send timeout (ignored)")
        except Exception as e:
            if self.running:
                logger.error(f"❌ Send params error: {e}")
    
    def _generate_random_movement(self) -> Dict[str, float]:
        """สร้างจุดเป้าหมายแบบสุ่ม"""
        from core.config import config
        
        intensity = random.uniform(0.6, 1.0) * self.movement_intensity
        
        angle_min, angle_max = config.vtube.head_rotation_range
        movements = {
            'FaceAngleX': random.uniform(angle_min, angle_max) * intensity,
            'FaceAngleY': random.uniform(angle_min, angle_max) * intensity,
            'FaceAngleZ': random.uniform(angle_min, angle_max) * intensity,
            'FacePositionX': random.uniform(-5, 5) * intensity * 0.5,
            'FacePositionY': 0,
            'EyeLeftX': random.uniform(-1, 1),
            'EyeLeftY': random.uniform(-0.7, 0.7),
            'EyeRightX': random.uniform(-1, 1),
            'EyeRightY': random.uniform(-0.7, 0.7)
        }
        
        return movements
    
    async def _animation_loop(self):
        """Loop หลักสำหรับอัพเดทการเคลื่อนไหว"""
        from core.config import config
        
        logger.info("🎬 เริ่ม Animation Loop")
        
        loop_count = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                if loop_count % 100 == 0:
                    logger.debug(f"🔄 Animation loop alive (iteration: {loop_count}, state: {self.state.value})")
                
                # ✅ เปลี่ยนท่า (ไม่รบกวนขณะ speaking)
                if self.state != AnimationState.SPEAKING:
                    if current_time - self.last_movement_change >= self.movement_duration:
                        targets = self._generate_random_movement()
                        
                        for param_name, target_value in targets.items():
                            if param_name in self.smooth_values:
                                self.smooth_values[param_name].set_target(target_value)
                        
                        self.last_movement_change = current_time
                        self.movement_duration = random.uniform(1.5, 3.0) / self.movement_speed
                
                # ✅ เคลื่อนไหวตา (ไม่รบกวนขณะ speaking)
                if self.state != AnimationState.SPEAKING:
                    if current_time - self.last_eye_movement >= self.eye_movement_duration:
                        eye_x = random.uniform(-1, 1)
                        eye_y = random.uniform(-0.7, 0.7)
                        
                        self.smooth_values['EyeLeftX'].set_target(eye_x)
                        self.smooth_values['EyeLeftY'].set_target(eye_y)
                        self.smooth_values['EyeRightX'].set_target(eye_x)
                        self.smooth_values['EyeRightY'].set_target(eye_y)
                        
                        self.last_eye_movement = current_time
                        self.eye_movement_duration = random.uniform(0.8, 2.0)
                
                # อัพเดทค่าทั้งหมด
                current_values = {}
                for param_name, smooth_value in self.smooth_values.items():
                    current_values[param_name] = smooth_value.update()
                
                # ส่งไป VTS
                await self._send_parameters(current_values)
                
                loop_count += 1
                
                # ✅ รอ 50ms (20 FPS)
                await asyncio.sleep(config.vtube.idle_update_rate)
                
            except asyncio.CancelledError:
                logger.info("🛑 Animation Loop cancelled")
                break
            except Exception as e:
                if self.running:
                    logger.error(f"⚠️ Animation error: {e}", exc_info=True)
                await asyncio.sleep(1)
        
        logger.info("🛑 Animation Loop หยุดทำงาน")

    async def start_lip_sync_from_file(self, audio_file_path: str):
        """✅ Lip sync ที่ปรับปรุงให้ตรงคำและเป็นธรรมชาติ"""
        if not self.authenticated or not self.model_loaded:
            logger.warning("⚠️ VTS not ready for lip sync")
            return
        if 'MouthOpen' not in self.available_parameters:
            logger.warning("⚠️ MouthOpen parameter not available")
            return

        logger.info(f"🎤 Starting improved lip sync: {audio_file_path}")

        async def _run():
            import wave
            import numpy as np
            try:
                self._lip_sync_running = True
                
                with wave.open(audio_file_path, 'rb') as wav:
                    sample_rate = wav.getframerate()
                    n_frames = wav.getnframes()
                    audio_bytes = wav.readframes(n_frames)
                    
                audio = np.frombuffer(audio_bytes, dtype=np.int16)
                
                # ✅ ปรับ chunk size ให้ใหญ่ขึ้น (15ms) เพื่อจับพยางค์ได้ดีขึ้น
                chunk_ms = 15  # เพิ่มจาก 10ms → 15ms
                chunk_size = max(1, int(sample_rate * (chunk_ms / 1000.0)))
                
                ema = 0.0
                # ✅ ปรับ attack/release ให้เร็วและตอบสนองดีขึ้น
                attack = 0.85
                release = 0.70  # เร็วขึ้นเพื่อปิดปากทัน
                
                # ✅ Silence detection
                silence_threshold = 0.02  # เพิ่มจาก 0.015
                silence_chunks_needed = 3  # ลดจาก 4
                silence_chunks = 0

                # ✅ Hysteresis gate
                open_th = 0.20  # ลดจาก 0.22
                close_th = 0.10  # ลดจาก 0.12
                min_open_ms = 50  # ลดจาก 60
                min_close_ms = 30  # ลดจาก 40
                mouth_is_open = False
                time_since_open_ms = 0
                time_since_close_ms = 0

                # ✅ Dynamic noise floor
                pre_samples = max(chunk_size, int(sample_rate * 0.2))
                pre = audio[:pre_samples].astype(np.float32)
                baseline_energy = 0.0
                if pre.size > 0:
                    norm_pre = pre / 32767.0
                    win_pre = np.hanning(norm_pre.size)
                    spec_pre = np.fft.rfft(norm_pre * win_pre)
                    freqs_pre = np.fft.rfftfreq(norm_pre.size, d=1.0 / sample_rate)
                    band_pre = (freqs_pre >= 300) & (freqs_pre <= 3400)
                    band_energy_pre = np.sqrt(np.mean(np.abs(spec_pre[band_pre]) ** 2)) if np.any(band_pre) else 0.0
                    rms_pre = float(np.sqrt(np.mean(norm_pre ** 2)))
                    baseline_energy = 0.7 * band_energy_pre + 0.3 * rms_pre

                # ✅ จังหวะหยุด (พยางค์)
                since_last_pause = 0.0
                pause_min = 0.10  # ลดจาก 0.12
                pause_max = 0.16  # ลดจาก 0.18
                next_pause_interval = random.uniform(pause_min, pause_max)

                last_mouth_value = 0.0

                for i in range(0, len(audio), chunk_size):
                    if not self._lip_sync_running:
                        break
                        
                    chunk = audio[i:i+chunk_size].astype(np.float32)
                    if chunk.size == 0:
                        continue
                        
                    # ✅ คำนวณ volume แม่นยำ (speech band 300-3400 Hz)
                    norm = chunk / 32767.0
                    win = np.hanning(norm.size)
                    spec = np.fft.rfft(norm * win)
                    freqs = np.fft.rfftfreq(norm.size, d=1.0 / sample_rate)
                    band = (freqs >= 300) & (freqs <= 3400)
                    band_energy = np.sqrt(np.mean(np.abs(spec[band]) ** 2)) if np.any(band) else 0.0
                    rms = float(np.sqrt(np.mean(norm ** 2)))
                    energy_raw = 0.7 * band_energy + 0.3 * rms
                    energy = max(0.0, energy_raw - baseline_energy * 1.1)
                    volume = min(energy * 2.2, 1.0)  # เพิ่ม gain เล็กน้อย
                    
                    # ✅ นับช่วงเงียบ
                    if rms < silence_threshold:
                        silence_chunks += 1
                    else:
                        silence_chunks = 0
                    
                    # Smoothing
                    if volume > ema:
                        ema = attack * volume + (1 - attack) * ema
                    else:
                        ema = release * volume + (1 - release) * ema

                    # ✅ Hysteresis gating
                    if mouth_is_open:
                        time_since_open_ms += chunk_ms
                        if ema < close_th and time_since_open_ms >= min_open_ms:
                            mouth_is_open = False
                            time_since_close_ms = 0
                    else:
                        time_since_close_ms += chunk_ms
                        if ema > open_th and time_since_close_ms >= min_close_ms:
                            mouth_is_open = True
                            time_since_open_ms = 0

                    base_mouth = ema
                    if mouth_is_open:
                        if base_mouth > 0.4:
                            variation = random.uniform(0.97, 1.06)
                            mouth_open = base_mouth * variation
                        else:
                            mouth_open = base_mouth
                    else:
                        mouth_open = 0.0

                    # ✅ ปิดปากทันทีเมื่อเงียบ
                    if silence_chunks >= silence_chunks_needed:
                        mouth_open = 0.0
                        ema = max(0.0, ema * 0.5)
                        mouth_is_open = False
                        time_since_close_ms = 0
                    
                    mouth_open = max(0.0, min(1.0, mouth_open))
                    
                    # ✅ จังหวะหยุด (พยางค์)
                    since_last_pause += (chunk_size / sample_rate)
                    if since_last_pause >= next_pause_interval and mouth_open > 0.30:
                        mouth_open = max(0.0, mouth_open - 0.12)
                        since_last_pause = 0.0
                        next_pause_interval = random.uniform(pause_min, pause_max)

                    # ✅ ส่งเฉพาะเมื่อเปลี่ยนแปลงมากพอ
                    if abs(mouth_open - last_mouth_value) > 0.015:  # ลด threshold
                        await self.set_parameter_value('MouthOpen', mouth_open, immediate=False)
                        last_mouth_value = mouth_open
                        
                        # MouthForm
                        if 'MouthForm' in self.available_parameters:
                            await self.set_parameter_value('MouthForm', 0.0, immediate=False)
                        await asyncio.sleep(0.05)
                    logger.info("👄 Mouth closed")
                except Exception:
                    pass

        # ยกเลิกงานเดิมถ้ามี
        if self._lip_sync_task and not self._lip_sync_task.done():
            self._lip_sync_running = False
            self._lip_sync_task.cancel()
            try:
                await self._lip_sync_task
            except asyncio.CancelledError:
                pass
        
        self._lip_sync_task = asyncio.create_task(_run())

    async def set_parameter_value(self, param_name: str, value: float, immediate: bool = True):
        """ตั้งค่าพารามิเตอร์เดี่ยว"""
        try:
            if param_name not in self.available_parameters:
                return
            info = self.available_parameters[param_name]
            clamped = max(info['min'], min(info['max'], value))
            
            # อัพเดท smooth target
            if param_name in self.smooth_values:
                self.smooth_values[param_name].set_target(clamped)

            # ส่งทันทีเฉพาะเมื่อจำเป็น
            if immediate and self.authenticated and self.model_loaded:
                now = time.time()
                if (now - self._last_send_ts) < self._min_send_interval:
                    return
                ok = await self._ensure_ws()
                if not ok or not self.ws:
                    return
                req = {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": "inject_param_single",
                    "messageType": "InjectParameterDataRequest",
                    "data": {
                        "parameterValues": [{"id": param_name, "value": clamped}]
                    }
                }
                await self.ws.send(json.dumps(req))
                self._last_send_ts = now
                self._last_sent_values[param_name] = clamped
        except Exception as e:
            logger.debug(f"Set param error: {e}")
    
    async def start_speaking(self, text: str):
        """เริ่มพูด"""
        logger.info(f"🗣️ Start speaking: {text[:50]}...")
        self.state = AnimationState.SPEAKING
    
    async def stop_speaking(self):
        """✅ หยุดพูด - ปรับปรุงให้ transition กลับ idle นุ่มนวล"""
        logger.info("🛑 Stop speaking")
        self._lip_sync_running = False
        
        # ยกเลิก lip sync task
        if self._lip_sync_task and not self._lip_sync_task.done():
            try:
                self._lip_sync_task.cancel()
                await self._lip_sync_task
            except asyncio.CancelledError:
                pass
        
        # ✅ ปิดปากอย่างนุ่มนวล
        if 'MouthOpen' in self.smooth_values:
            try:
                # Gradual close (4 steps)
                for val in [0.3, 0.15, 0.05, 0.0]:
                    self.smooth_values['MouthOpen'].set_target(val)
                    await asyncio.sleep(0.03)
            except Exception:
                pass
        
        # ✅ เปลี่ยนสถานะกลับ idle
        self.state = AnimationState.IDLE
        
        # ✅ รีเซ็ต movement timers เพื่อเริ่ม idle motion ทันที
        self.last_movement_change = 0.0
        self.last_eye_movement = 0.0
        self.movement_duration = random.uniform(1.0, 2.0)
        self.eye_movement_duration = random.uniform(0.5, 1.0)
        
        logger.info("✅ Transitioned back to IDLE")
    
    async def set_state(self, state: AnimationState):
        """เปลี่ยนสถานะ"""
        logger.debug(f"🎮 State change: {self.state.value} → {state.value}")
        self.state = state
        
        if state == AnimationState.THINKING:
            self.movement_intensity = 0.4
        else:
            self.movement_intensity = 0.8
        
        # ✅ รีเซ็ต timers เมื่อกลับ idle
        if state == AnimationState.IDLE:
            self.last_movement_change = 0.0
            self.movement_duration = random.uniform(1.0, 2.0)
            self.last_eye_movement = 0.0
            logger.debug("🔄 Timers reset for idle motion")
    
    async def set_talking(self, talking: bool):
        """ตั้งสถานะกำลังพูด"""
        if talking:
            await self.set_state(AnimationState.SPEAKING)
        else:
            await self.stop_speaking()
    
    async def update_idle_motion(self):
        """✅ อัพเดท idle motion - ปรับปรุงให้กลับมาเคลื่อนไหวทันที"""
        logger.info("🔄 Updating idle motion")
        await self.set_state(AnimationState.IDLE)
        
        # ✅ สุ่มท่าใหม่ทันที
        targets = self._generate_random_movement()
        for param_name, target_value in targets.items():
            if param_name in self.smooth_values:
                self.smooth_values[param_name].set_target(target_value)
        
        logger.info("✅ Idle motion updated")
    
    async def disconnect(self):
        """ตัดการเชื่อมต่อ"""
        logger.info("🛑 กำลังตัดการเชื่อมต่อ VTS...")
        self.running = False
        
        if self.animation_task:
            self.animation_task.cancel()
            try:
                await self.animation_task
            except asyncio.CancelledError:
                pass
        
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        
        logger.info("👋 ตัดการเชื่อมต่อ VTS เรียบร้อย")

    async def execute_motion_command(self, motion_cmd):
        """ทำการขยับตามคำสั่ง motion"""
        from core.motion_commands import MotionType

        if not self.authenticated or not self.model_loaded:
            logger.warning("⚠️ VTS not ready for motion")
            return

        logger.info(f"🎭 Executing motion: {motion_cmd.motion_type.value}")

        try:
            if motion_cmd.motion_type == MotionType.THINKING:
                await self._motion_thinking(motion_cmd)
            elif motion_cmd.motion_type == MotionType.EXCITED:
                await self._motion_excited(motion_cmd)
            elif motion_cmd.motion_type == MotionType.CONFUSED:
                await self._motion_confused(motion_cmd)
            elif motion_cmd.motion_type == MotionType.HAPPY:
                await self._motion_happy(motion_cmd)
            elif motion_cmd.motion_type == MotionType.SAD:
                await self._motion_sad(motion_cmd)
            elif motion_cmd.motion_type == MotionType.ANGRY:
                await self._motion_angry(motion_cmd)
            else:
                await self._motion_idle()
        except Exception as e:
            logger.error(f"❌ Motion execution error: {e}")

    async def _motion_thinking(self, motion_cmd):
        """คิดอยู่"""
        intensity = motion_cmd.intensity.value
        targets = {
            'FaceAngleX': 5.0 * intensity,
            'FaceAngleY': 0.0,
            'FaceAngleZ': 0.0,
            'EyeLeftY': -0.3 * intensity,
            'EyeRightY': -0.3 * intensity,
        }
        for param_name, target_value in targets.items():
            if param_name in self.smooth_values:
                self.smooth_values[param_name].set_target(target_value)
        await asyncio.sleep(motion_cmd.duration)
        await self._motion_idle()

    async def _motion_excited(self, motion_cmd):
        """ตื่นเต้น"""
        intensity = motion_cmd.intensity.value
        targets = {
            'FaceAngleX': -8.0 * intensity,
            'FaceAngleY': float(random.choice([-15, 15])) * intensity,
            'FaceAngleZ': float(random.choice([-8, 8])) * intensity,
            'EyeLeftX': float(random.uniform(-1, 1)),
            'EyeLeftY': float(random.uniform(-0.5, 0.5)),
            'EyeRightX': float(random.uniform(-1, 1)),
            'EyeRightY': float(random.uniform(-0.5, 0.5)),
        }
        for param_name, target_value in targets.items():
            if param_name in self.smooth_values:
                self.smooth_values[param_name].set_target(target_value)
        
        elapsed = 0.0
        while elapsed < motion_cmd.duration:
            if motion_cmd.micro_twitch_enabled and elapsed % 0.5 < 0.25:
                twitch = self._generate_random_micro_twitch()
                for key in twitch:
                    if key in self.smooth_values:
                        current_target = self.smooth_values[key].target
                        self.smooth_values[key].set_target(current_target + twitch[key] * 0.3)
            await asyncio.sleep(0.05)
            elapsed += 0.05
        await self._motion_idle()

    def _generate_random_micro_twitch(self) -> Dict[str, float]:
        """สุ่มการขยับเล็ก ๆ"""
        return {
            'FaceAngleX': random.uniform(-2, 2),
            'FaceAngleY': random.uniform(-3, 3),
            'FaceAngleZ': random.uniform(-2, 2),
        }

    async def _motion_confused(self, motion_cmd):
        """งงๆ"""
        intensity = motion_cmd.intensity.value
        targets = {
            'FaceAngleX': float(random.uniform(-3, 3)),
            'FaceAngleY': 15.0 * intensity,
            'FaceAngleZ': 8.0 * intensity,
            'EyeLeftX': -0.5,
            'EyeLeftY': 0.2,
            'EyeRightX': 0.5,
            'EyeRightY': -0.2,
        }
        for param_name, target_value in targets.items():
            if param_name in self.smooth_values:
                self.smooth_values[param_name].set_target(target_value)
        
        elapsed = 0.0
        while elapsed < motion_cmd.duration:
            if elapsed % 0.3 < 0.15:
                self.smooth_values['EyeLeftY'].set_target(-0.5)
                self.smooth_values['EyeRightY'].set_target(-0.5)
            else:
                self.smooth_values['EyeLeftY'].set_target(0.2)
                self.smooth_values['EyeRightY'].set_target(-0.2)
            await asyncio.sleep(0.05)
            elapsed += 0.05
        await self._motion_idle()

    async def _motion_happy(self, motion_cmd):
        """ยิ้ม"""
        intensity = motion_cmd.intensity.value
        elapsed = 0.0
        while elapsed < motion_cmd.duration:
            angle_y = 10.0 * intensity * abs(float(np.sin(elapsed * 2 * np.pi / 1.0)))
            self.smooth_values['FaceAngleY'].set_target(angle_y)
            await asyncio.sleep(0.1)
            elapsed += 0.1
        await self._motion_idle()

    async def _motion_sad(self, motion_cmd):
        """เศร้า"""
        intensity = motion_cmd.intensity.value
        targets = {
            'FaceAngleX': 10.0 * intensity,
            'FaceAngleY': 0.0,
            'FaceAngleZ': 0.0,
            'EyeLeftY': -0.5 * intensity,
            'EyeRightY': -0.5 * intensity,
        }
        for param_name, target_value in targets.items():
            if param_name in self.smooth_values:
                self.smooth_values[param_name].set_target(target_value)
        await asyncio.sleep(motion_cmd.duration)
        await self._motion_idle()

    async def _motion_angry(self, motion_cmd):
        """โกรธ"""
        intensity = motion_cmd.intensity.value
        targets = {
            'FaceAngleX': -10.0 * intensity,
            'FaceAngleY': 0.0,
            'FaceAngleZ': float(random.choice([-1, 1])) * 5.0 * intensity,
        }
        for param_name, target_value in targets.items():
            if param_name in self.smooth_values:
                self.smooth_values[param_name].set_target(target_value)
        await asyncio.sleep(motion_cmd.duration)
        await self._motion_idle()

    async def _motion_idle(self):
        """กลับเป็น idle"""
        targets = self._generate_random_movement()
        for param_name, target_value in targets.items():
            if param_name in self.smooth_values:
                self.smooth_values[param_name].set_target(target_value)

# Global controller
vtube_controller = VTubeStudioController()
                            if mouth_open > 0.6:
                                mouth_form = random.uniform(0.6, 0.8)
                            elif mouth_open > 0.3:
                                mouth_form = random.uniform(0.3, 0.5)
                            else:
                                mouth_form = 0.0
                            await self.set_parameter_value('MouthForm', mouth_form, immediate=False)
                    
                    await asyncio.sleep(chunk_size / sample_rate)
                
                logger.info("✅ Lip sync completed")
                
            except Exception as e:
                logger.error(f"❌ Lip sync error: {e}", exc_info=True)
            finally:
                self._lip_sync_running = False
                
                # ✅ ปิดปากอย่างนุ่มนวล
                try:
                    for val in [0.4, 0.2, 0.0]:
                        await self.set_parameter_value('MouthOpen', val, immediate=False)
                        if 'MouthForm' in self.available_parameters: