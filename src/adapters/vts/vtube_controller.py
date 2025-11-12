"""
ระบบควบคุม VTube Studio พร้อม Smooth Animation (Version 4 + Debug)
ตำแหน่ง: src/adapters/vts/vtube_controller.py
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

import sys
sys.path.append('../..')
from core.config import config
from personality.jeed_persona import Emotion, JeedPersona

# ใช้ logger แทนการ print
logger = logging.getLogger(__name__)

class AnimationState(Enum):
    """สถานะการเคลื่อนไหว"""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"

class SmoothValue:
    """คลาสสำหรับทำให้ค่าเคลื่อนไหวนุ่มนวล"""
    def __init__(self, initial_value: float = 0.0, smooth_factor: float = 0.15):
        self.current = initial_value
        self.target = initial_value
        self.smooth_factor = smooth_factor
    
    def set_target(self, value: float):
        self.target = value
    
    def update(self) -> float:
        diff = self.target - self.current
        self.current += diff * self.smooth_factor
        return self.current

class VTubeStudioController:
    """ควบคุม VTube Studio ผ่าน WebSocket"""
    
    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.authenticated = False
        self.auth_token: Optional[str] = config.vtube.plugin_token
        self.model_loaded = False
        self.model_id = None
        self.animation_task: Optional[asyncio.Task] = None
        self.state = AnimationState.IDLE
        self.running = False
        
        # Available parameters (ดึงจาก VTS)
        self.available_parameters: Dict[str, Dict] = {}
        
        # Smooth values
        smooth_factor = config.vtube.smooth_factor
        self.smooth_values = {
            'FaceAngleX': SmoothValue(0, smooth_factor),
            'FaceAngleY': SmoothValue(0, smooth_factor),
            'FaceAngleZ': SmoothValue(0, smooth_factor),
            'FacePositionX': SmoothValue(0, smooth_factor),
            'FacePositionY': SmoothValue(0, smooth_factor),
            'EyeLeftX': SmoothValue(0, smooth_factor),
            'EyeLeftY': SmoothValue(0, smooth_factor),
            'EyeRightX': SmoothValue(0, smooth_factor),
            'EyeRightY': SmoothValue(0, smooth_factor),
            'MouthOpen': SmoothValue(0, smooth_factor * 2),
        }
        
        # Movement parameters
        self.movement_intensity = 0.8
        self.movement_speed = 1.0
        self.current_emotion = Emotion.NEUTRAL
        self.intensity_variation = 0.3
        
        # Timers
        self.last_movement_change = time.time()
        self.last_eye_movement = time.time()
        self.last_intensity_change = time.time()
        self.movement_duration = random.uniform(1.5, 3.0)
        self.eye_movement_duration = random.uniform(0.8, 2.0)
        self.current_intensity_multiplier = 1.0
        
        # Lip sync state
        self._lip_sync_task: Optional[asyncio.Task] = None
        self._lip_sync_running: bool = False
        
        # ✅ Debug: นับจำนวน parameter sends
        self._param_send_count = 0
        self._last_param_time = time.time()

        # ✅ ควบคุมการ reconnect ไม่ให้ถี่เกินไป
        self._reconnecting: bool = False
        self._last_reconnect_attempt_ts: float = 0.0
        self._reconnect_min_interval: float = 2.0  # อย่างน้อย 2 วินาทีต่อครั้ง
        self._reconnect_fail_count: int = 0
    
    async def connect(self) -> bool:
        """เชื่อมต่อกับ VTube Studio"""
        try:
            logger.info("📡 กำลังเชื่อมต่อ VTube Studio...")
            
            # ✅ แก้: เพิ่ม ping_interval และ close_timeout เพื่อไม่ให้หลุด
            self.ws = await websockets.connect(
                config.vtube.websocket_url,
                ping_interval=10,  # ส่ง ping ทุก 10 วินาที (เดิม 20)
                ping_timeout=30,   # รอ pong 30 วินาที (เดิม 10)
                close_timeout=5    # รอปิด 5 วินาที
            )
            logger.info("✅ WebSocket เชื่อมต่อสำเร็จ")
            
            # Authentication
            await self._authenticate()
            
            # ดึงข้อมูลโมเดลปัจจุบัน
            await self._get_current_model()
            
            if not self.model_loaded:
                logger.warning("⚠️ ไม่พบโมเดลที่โหลดอยู่ กรุณาเปิดโมเดลใน VTube Studio")
                return False
            
            # ดึงรายการ parameters ที่มี
            await self._get_available_parameters()
            
            # เริ่ม animation loop (เฉพาะครั้งแรกเท่านั้น)
            if not self.running or not self.animation_task or self.animation_task.done():
                self.running = True
                self.animation_task = asyncio.create_task(self._animation_loop())
            
            logger.info("✅ VTube Studio พร้อมใช้งาน")
            
            # ✅ Debug: รอ 1 วินาที แล้วเช็คว่า loop เริ่มแล้ว
            await asyncio.sleep(1)
            if self.animation_task and not self.animation_task.done():
                logger.info("✅ Animation loop started successfully")
            else:
                logger.error("❌ Animation loop failed to start!")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ เชื่อมต่อ VTS ล้มเหลว: {e}", exc_info=True)
            return False

    async def _ensure_ws(self) -> bool:
        """ตรวจสอบและเชื่อมต่อใหม่แบบปลอดภัย พร้อม backoff ป้องกัน reconnect ถี่"""
        try:
            if self.ws and getattr(self.ws, 'state', None) and self.ws.state.name == 'OPEN':
                return True

            now = time.time()
            # ถ้ากำลัง reconnect อยู่ หรือเพิ่ง reconnect ไปเมื่อไม่นาน ให้ข้าม
            if self._reconnecting or (now - self._last_reconnect_attempt_ts) < self._reconnect_min_interval:
                return False

            self._reconnecting = True
            self._last_reconnect_attempt_ts = now
            logger.debug("🔁 WebSocket not open, attempting safe reconnect…")

            self.ws = await websockets.connect(
                config.vtube.websocket_url,
                ping_interval=20,   # ผ่อนปรนขึ้นเพื่อลด false timeout
                ping_timeout=40,
                close_timeout=5
            )
            await self._authenticate()
            await self._get_current_model()
            if not self.model_loaded:
                logger.warning("⚠️ ไม่พบโมเดลหลัง reconnect")
                self._reconnecting = False
                self._reconnect_fail_count += 1
                return False
            await self._get_available_parameters()
            logger.info("✅ Reconnected VTS WebSocket (no new animation loop)")
            self._reconnecting = False
            self._reconnect_fail_count = 0
            return True
        except Exception as e:
            self._reconnecting = False
            self._reconnect_fail_count += 1
            logger.error(f"❌ Safe reconnect failed: {e}")
            return False
    
    async def _authenticate(self):
        """ขอ authentication"""
        try:
            if self.auth_token:
                # ใช้ token ที่มี
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
                # ขอ token ใหม่
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
                # ลองอีกครั้งด้วย token ใหม่
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
                
                # แสดง parameters ที่สำคัญ
                important = ['FaceAngleX', 'FaceAngleY', 'FaceAngleZ', 'MouthOpen']
                available_important = [p for p in important if p in self.available_parameters]
                if available_important:
                    logger.info(f"✅ Parameters ที่มี: {', '.join(available_important)}")
                else:
                    logger.warning("⚠️ ไม่พบ parameters มาตรฐาน")
                    
        except Exception as e:
            logger.error(f"❌ Get Parameters Error: {e}")

    async def _send_parameters(self, parameters: Dict[str, float]):
        """ส่งค่าพารามิเตอร์ไปยัง VTS (แก้ไข: เช็ค connection ก่อนส่ง)"""
        if not self.authenticated or not self.model_loaded or not self.ws:
            return
        
        # ✅ แก้: เช็คว่า websocket ยังเปิดอยู่หรือไม่
        try:
            # ใช้ safe reconnect พร้อม backoff ไม่ยิงถี่ทุกเฟรม
            if self.ws.state.name != 'OPEN':
                ok = await self._ensure_ws()
                if not ok:
                    # ข้ามการส่งในเฟรมนี้
                    return
        except Exception:
            # ถ้าเช็ค state ไม่ได้ ให้ลองส่งไปเลย
            pass
        
        try:
            valid_params = []
            for param_name, value in parameters.items():
                if param_name in self.available_parameters:
                    param_info = self.available_parameters[param_name]
                    clamped_value = max(param_info['min'], min(param_info['max'], value))
                    valid_params.append({
                        "id": param_name,
                        "value": clamped_value
                    })
            
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
            
            # ✅ แก้: ใช้ wait_for กับ timeout สั้น
            try:
                await asyncio.wait_for(
                    self.ws.send(json.dumps(request)),
                    timeout=0.5
                )
            except asyncio.TimeoutError:
                logger.debug("⚠️ Send timeout (ignored)")
                return
            
            # ✅ Debug: นับจำนวนครั้งที่ส่ง
            self._param_send_count += 1
            current_time = time.time()
            if current_time - self._last_param_time >= 5.0:
                logger.debug(f"📊 Parameters sent: {self._param_send_count} times in 5s")
                self._param_send_count = 0
                self._last_param_time = current_time
                
        except Exception as e:
            # ✅ แก้: ไม่ log error ถ้ากำลังปิดระบบ
            if self.running:
                logger.error(f"❌ Send params error: {e}")
    
    def _generate_random_movement(self) -> Dict[str, float]:
        """สร้างจุดเป้าหมายแบบสุ่ม"""
        intensity_mult = self.current_intensity_multiplier
        base_intensity = random.uniform(0.6, 1.0)
        final_intensity = base_intensity * self.movement_intensity * intensity_mult
        
        # สร้างค่าเป้าหมาย
        movements = {
            'FaceAngleX': random.uniform(-12, 12) * final_intensity,
            'FaceAngleY': random.uniform(-20, 20) * final_intensity,
            'FaceAngleZ': random.uniform(-10, 10) * final_intensity,
            'FacePositionX': random.uniform(-5, 5) * final_intensity * 0.5,
            'FacePositionY': 0,
            'EyeLeftX': random.uniform(-1, 1),
            'EyeLeftY': random.uniform(-0.7, 0.7),
            'EyeRightX': random.uniform(-1, 1),
            'EyeRightY': random.uniform(-0.7, 0.7)
        }
        
        return movements
    
    async def _animation_loop(self):
        """Loop หลักสำหรับอัพเดทการเคลื่อนไหว"""
        logger.info("🎬 เริ่ม Animation Loop")
        
        loop_count = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                # ✅ Debug: แสดงสถานะทุก 100 iterations (~5 วินาที)
                if loop_count % 100 == 0:
                    logger.debug(f"🔄 Animation loop alive (iteration: {loop_count}, "
                               f"state: {self.state.value}, "
                               f"lip_sync: {self._lip_sync_running})")
                
                # สุ่มความแรงทุก 3-5 วินาที (ข้ามเมื่อ idle และปิด idle motion)
                if not (self.state == AnimationState.IDLE and not config.vtube.idle_motion_enabled):
                    if current_time - self.last_intensity_change >= random.uniform(3, 5):
                        self.current_intensity_multiplier = random.uniform(
                            1.0 - self.intensity_variation,
                            1.0 + self.intensity_variation
                        )
                        self.last_intensity_change = current_time
                
                # เปลี่ยนท่า (ข้ามเมื่อ idle และปิด idle motion)
                if not (self.state == AnimationState.IDLE and not config.vtube.idle_motion_enabled):
                    if current_time - self.last_movement_change >= self.movement_duration:
                        targets = self._generate_random_movement()
                        
                        # อัพเดทเป้าหมาย
                        for param_name, target_value in targets.items():
                            if param_name in self.smooth_values:
                                self.smooth_values[param_name].set_target(target_value)
                        
                        self.last_movement_change = current_time
                        self.movement_duration = random.uniform(1.5, 3.0) / self.movement_speed
                
                # เคลื่อนไหวตา (ข้ามเมื่อ idle และปิด idle motion)
                if not (self.state == AnimationState.IDLE and not config.vtube.idle_motion_enabled):
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
                
                # รอ 50ms (20 FPS)
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
        """✅ แก้ไข: Lip sync ที่เคลื่อนไหวเหมือนคนพูดจริง"""
        if not self.authenticated or not self.model_loaded:
            logger.warning("⚠️ VTS not ready for lip sync")
            return
        if 'MouthOpen' not in self.available_parameters:
            logger.warning("⚠️ MouthOpen parameter not available")
            return

        logger.info(f"🎤 Starting lip sync: {audio_file_path}")

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
                
                # ✅ แก้: ลด chunk size เพื่อให้ตอบสนองเร็วขึ้น
                chunk_size = max(1, int(sample_rate * 0.01))  # 10ms (เดิม 20ms)
                
                ema = 0.0
                # ✅ ปรับให้ปิดปากเร็วขึ้นและเปิดเร็วพอ
                attack = 0.8    # เปิดปากเร็ว
                release = 0.6   # ปิดปากเร็วขึ้น (เดิม 0.2)

                # ✅ เพิ่มตัวตรวจจับช่วงเงียบ เพื่อปิดปากทันทีเมื่อเงียบสั้นๆ (normalize เป็น 0..1)
                silence_threshold = 0.03   # RMS (normalized) ที่ถือว่าเงียบ
                silence_chunks_needed = 4  # 4 ชิ้นเสียง ~ 40ms
                silence_chunks = 0

                # ✅ จังหวะหยุดคล้ายพยางค์ เพื่อให้ดูเหมือนพูดจริง
                since_last_pause = 0.0
                next_pause_interval = random.uniform(0.12, 0.18)  # วินาที

                frame_count = 0
                last_mouth_value = 0.0

                for i in range(0, len(audio), chunk_size):
                    if not self._lip_sync_running:
                        break
                        
                    chunk = audio[i:i+chunk_size].astype(np.float32)
                    if chunk.size == 0:
                        continue
                        
                    # ✅ คำนวณ volume ที่แม่นยำขึ้น (normalize int16 → 0..1)
                    norm = chunk / 32767.0
                    rms = float(np.sqrt(np.mean(norm ** 2)))
                    volume = min(rms * 3.0, 1.0)
                    
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

                    # ✅ ปรับค่าให้เปิดปากมากขึ้น และมีความหลากหลาย
                    base_mouth = ema * 2.0
                    
                    # ✅ เพิ่ม variation ตามพยัญชนะ/สระ
                    if base_mouth > 0.3:
                        # เพิ่มการสั่นเล็กน้อย
                        variation = random.uniform(0.9, 1.15)
                        mouth_open = base_mouth * variation
                    else:
                        mouth_open = base_mouth

                    # ✅ หากเงียบเพียงพอ ให้ปิดปากทันที (กันอ้าค้าง)
                    if silence_chunks >= silence_chunks_needed:
                        mouth_open = 0.0
                        ema = max(0.0, ema * 0.5)  # เร่งการปิดด้วยการลด EMA
                    
                    mouth_open = max(0.0, min(1.0, mouth_open))
                    
                    # ✅ จังหวะหยุดสั้นๆ คล้ายพยางค์
                    since_last_pause += (chunk_size / sample_rate)
                    if since_last_pause >= next_pause_interval and mouth_open > 0.35:
                        mouth_open = max(0.0, mouth_open - 0.15)
                        since_last_pause = 0.0
                        next_pause_interval = random.uniform(0.12, 0.18)

                    # ✅ ป้องกันการค้างที่ค่าเดิม
                    if abs(mouth_open - last_mouth_value) > 0.02:
                        # ส่งผ่านระบบ smooth + batch เพื่อลดการกระตุก (ไม่ส่งทันที)
                        await self.set_parameter_value('MouthOpen', mouth_open, immediate=False)
                        last_mouth_value = mouth_open
                        
                        # ✅ MouthForm สำหรับรูปปาก
                        if 'MouthForm' in self.available_parameters:
                            # สุ่มรูปปากตามความกว้าง
                            if mouth_open > 0.6:
                                mouth_form = random.uniform(0.6, 0.8)  # ปากกว้าง (อา)
                            elif mouth_open > 0.3:
                                mouth_form = random.uniform(0.3, 0.5)  # ปากกลาง
                            else:
                                mouth_form = 0.0  # ปากปิด
                            await self.set_parameter_value('MouthForm', mouth_form, immediate=False)
                    
                    frame_count += 1
                    await asyncio.sleep(chunk_size / sample_rate)
                
                logger.info("✅ Lip sync completed")
                
            except Exception as e:
                logger.error(f"❌ Lip sync error: {e}", exc_info=True)
            finally:
                self._lip_sync_running = False
                
                # ✅ แก้: ปิดปากแบบค่อยๆ (ดูเป็นธรรมชาติ)
                try:
                    for val in [0.4, 0.2, 0.0]:
                        await self.set_parameter_value('MouthOpen', val, immediate=False)
                        if 'MouthForm' in self.available_parameters:
                            await self.set_parameter_value('MouthForm', 0.0, immediate=False)
                        await asyncio.sleep(0.05)
                    logger.info("👄 Mouth closed")
                except Exception:
                    pass

        # ยกเลิกงานเดิมถ้ามี แล้วสร้างใหม่
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

            # ส่งทันทีเฉพาะเมื่อจำเป็น และแน่ใจว่า ws พร้อม
            if immediate and self.authenticated and self.model_loaded:
                ok = await self._ensure_ws()
                if not ok or not self.ws:
                    logger.debug("⚠️ Cannot send param: WebSocket not ready")
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
        except Exception as e:
            logger.debug(f"Set param error: {e}")
    
    def set_emotion(self, emotion: Emotion, intensity: float):
        """ตั้งค่าอารมณ์"""
        self.current_emotion = emotion
        params = JeedPersona.get_movement_params(emotion, intensity)
        self.movement_speed = params["movement_speed"]
        self.movement_intensity = params["movement_intensity"]
        logger.debug(f"🎭 Emotion set: {emotion.value} (intensity: {intensity:.2f})")
    
    async def start_speaking(self, text: str):
        """เริ่มพูด - lip sync"""
        logger.info(f"🗣️ Start speaking: {text[:50]}...")
        self.state = AnimationState.SPEAKING
        emotion, intensity = JeedPersona.analyze_emotion(text)
        self.set_emotion(emotion, intensity)
    
    async def stop_speaking(self):
        """หยุดพูด"""
        logger.info("🛑 Stop speaking")
        self.state = AnimationState.IDLE
        self._lip_sync_running = False
        if self._lip_sync_task and not self._lip_sync_task.done():
            try:
                self._lip_sync_task.cancel()
                await self._lip_sync_task
            except asyncio.CancelledError:
                pass
        if 'MouthOpen' in self.smooth_values:
            self.smooth_values['MouthOpen'].set_target(0.0)
    
    async def set_state(self, state: AnimationState):
        """เปลี่ยนสถานะ"""
        logger.debug(f"🎮 State change: {self.state.value} → {state.value}")
        self.state = state
        if state == AnimationState.THINKING:
            self.movement_intensity = 0.4
        else:
            self.movement_intensity = 0.8
        
        # ✅ เมื่อกลับสู่ idle ให้รีเฟรชตัวตั้งเวลา
        if state == AnimationState.IDLE:
            self.last_movement_change = 0.0
            self.movement_duration = random.uniform(1.0, 2.0) / self.movement_speed
            self.last_eye_movement = 0.0
            logger.debug("🔄 Timers reset for idle motion")
    
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
        """คิดอยู่ - หัวเงย ตาลง นิ่งๆ"""
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
        """ตื่นเต้น - ยัน หัวเยื้อง เปะๆ"""
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
        """งงๆ - หัวเจียง ตากระพริบ"""
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
        """ยิ้ม - หัวแกว่ง"""
        import numpy as np
        intensity = motion_cmd.intensity.value
        elapsed = 0.0
        while elapsed < motion_cmd.duration:
            angle_y = 10.0 * intensity * abs(float(np.sin(elapsed * 2 * np.pi / 1.0)))
            self.smooth_values['FaceAngleY'].set_target(angle_y)
            await asyncio.sleep(0.1)
            elapsed += 0.1
        await self._motion_idle()

    async def _motion_sad(self, motion_cmd):
        """เศร้า - หัวลง ตาลง"""
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
        """โกรธ - หัวเงย บิด"""
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