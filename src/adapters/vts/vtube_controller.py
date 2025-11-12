"""
ระบบควบคุม VTube Studio พร้อม Smooth Animation (แก้ให้โมเดลขยับได้จริง)
ตำแหน่ง: src/adapters/vts/vtube_controller.py
"""

import asyncio
import websockets
import json
import random
import time
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

import sys
sys.path.append('../..')
from core.config import config
from personality.jeed_persona import Emotion, JeedPersona

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
    
    async def connect(self) -> bool:
        """เชื่อมต่อกับ VTube Studio"""
        try:
            print("📡 กำลังเชื่อมต่อ VTube Studio...")
            
            self.ws = await websockets.connect(
                config.vtube.websocket_url,
                ping_interval=20,
                ping_timeout=10
            )
            print("✅ WebSocket เชื่อมต่อสำเร็จ")
            
            # Authentication
            await self._authenticate()
            
            # ดึงข้อมูลโมเดลปัจจุบัน
            await self._get_current_model()
            
            if not self.model_loaded:
                print("⚠️ ไม่พบโมเดลที่โหลดอยู่ กรุณาเปิดโมเดลใน VTube Studio")
                return False
            
            # ดึงรายการ parameters ที่มี
            await self._get_available_parameters()
            
            # เริ่ม animation loop
            self.running = True
            self.animation_task = asyncio.create_task(self._animation_loop())
            
            print("✅ VTube Studio พร้อมใช้งาน")
            return True
            
        except Exception as e:
            print(f"❌ เชื่อมต่อ VTS ล้มเหลว: {e}")
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
                print(f"💾 บันทึก token นี้ใน .env:")
                print(f"VTS_PLUGIN_TOKEN={self.auth_token}")
                # ลองอีกครั้งด้วย token ใหม่
                await self._authenticate()
                
            elif response.get("data", {}).get("authenticated"):
                self.authenticated = True
                print("✅ VTS Authentication สำเร็จ")
            else:
                print(f"⚠️ Authentication ล้มเหลว: {response}")
                
        except Exception as e:
            print(f"❌ Authentication Error: {e}")
    
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
                print(f"✅ พบโมเดล: {model_name}")
            else:
                print("⚠️ ไม่พบโมเดลที่โหลดอยู่")
                
        except Exception as e:
            print(f"❌ Get Model Error: {e}")
    
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
                
                print(f"📋 พบ {len(self.available_parameters)} parameters")
                
                # แสดง parameters ที่สำคัญ
                important = ['FaceAngleX', 'FaceAngleY', 'FaceAngleZ', 'MouthOpen']
                available_important = [p for p in important if p in self.available_parameters]
                if available_important:
                    print(f"✅ Parameters ที่มี: {', '.join(available_important)}")
                else:
                    print("⚠️ ไม่พบ parameters มาตรฐาน")
                    
        except Exception as e:
            print(f"❌ Get Parameters Error: {e}")
    
    def _generate_random_movement(self) -> Dict[str, float]:
        """สร้างจุดเป้าหมายแบบสุ่ม"""
        intensity_mult = self.current_intensity_multiplier
        base_intensity = random.uniform(0.6, 1.0)
        final_intensity = base_intensity * self.movement_intensity * intensity_mult
        
        # สร้างค่าเป้าหมาย
        movements = {
            'FaceAngleX': random.uniform(-12, 12) * final_intensity,  # Pitch (เงย-ก้ม)
            'FaceAngleY': random.uniform(-20, 20) * final_intensity,  # Yaw (ซ้าย-ขวา)
            'FaceAngleZ': random.uniform(-10, 10) * final_intensity,  # Roll (เอียง)
            'FacePositionX': random.uniform(-5, 5) * final_intensity * 0.5,
            'FacePositionY': 0,  # ไม่ขยับขึ้นลง
            'EyeLeftX': random.uniform(-1, 1),
            'EyeLeftY': random.uniform(-0.7, 0.7),
            'EyeRightX': random.uniform(-1, 1),
            'EyeRightY': random.uniform(-0.7, 0.7),
            'MouthOpen': 0.0
        }
        
        return movements
    
    async def _animation_loop(self):
        """Loop หลักสำหรับอัพเดทการเคลื่อนไหว"""
        print("🎬 เริ่ม Animation Loop")
        
        while self.running:
            try:
                current_time = time.time()
                
                # สุ่มความแรงทุก 3-5 วินาที
                if current_time - self.last_intensity_change >= random.uniform(3, 5):
                    self.current_intensity_multiplier = random.uniform(
                        1.0 - self.intensity_variation,
                        1.0 + self.intensity_variation
                    )
                    self.last_intensity_change = current_time
                
                # เปลี่ยนท่า
                if current_time - self.last_movement_change >= self.movement_duration:
                    targets = self._generate_random_movement()
                    
                    # อัพเดทเป้าหมาย
                    for param_name, target_value in targets.items():
                        if param_name in self.smooth_values:
                            self.smooth_values[param_name].set_target(target_value)
                    
                    self.last_movement_change = current_time
                    self.movement_duration = random.uniform(1.5, 3.0) / self.movement_speed
                
                # เคลื่อนไหวตา (แยกจากตัว)
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
                
                # รอ 50ms (20 FPS)
                await asyncio.sleep(config.vtube.idle_update_rate)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.running:
                    print(f"⚠️ Animation error: {e}")
                await asyncio.sleep(1)
        
        print("🛑 Animation Loop หยุดทำงาน")

    async def start_lip_sync_from_file(self, audio_file_path: str):
        """Lip sync โดยไม่ block (ปรับ: ใช้ wait_for + timeout)"""
        if not self.authenticated or not self.model_loaded:
            return
        if 'MouthOpen' not in self.available_parameters:
            return

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
                chunk_size = max(1, int(sample_rate * 0.02))
                ema = 0.0
                attack = 0.5
                release = 0.1

                for i in range(0, len(audio), chunk_size):
                    if not self._lip_sync_running:
                        break
                    chunk = audio[i:i+chunk_size].astype(np.float32)
                    if chunk.size == 0:
                        continue
                    rms = float(np.sqrt(np.mean(chunk ** 2)))
                    volume = min(rms / 2500.0, 1.0)
                    if volume > ema:
                        ema = attack * volume + (1 - attack) * ema
                    else:
                        ema = release * volume + (1 - release) * ema

                    mouth_open = max(0.0, min(1.0, ema * 1.4))
                    # ✅ ใช้ wait_for + timeout เพื่อไม่ block
                    try:
                        await asyncio.wait_for(
                            self.set_parameter_value('MouthOpen', mouth_open, immediate=True),
                            timeout=0.1
                        )
                        if 'MouthForm' in self.available_parameters:
                            mouth_form = 0.5 if mouth_open > 0.3 else 0.0
                            await asyncio.wait_for(
                                self.set_parameter_value('MouthForm', mouth_form, immediate=False),
                                timeout=0.1
                            )
                    except asyncio.TimeoutError:
                        pass
                    except Exception:
                        pass
                    await asyncio.sleep(chunk_size / sample_rate)
            except Exception:
                # เงียบไว้เพื่อหลีกเลี่ยง spam ระหว่างเล่นเสียง
                pass
            finally:
                self._lip_sync_running = False
                try:
                    await self.set_parameter_value('MouthOpen', 0.0, immediate=True)
                except Exception:
                    pass

        # ยกเลิกงานเดิมถ้ามี แล้วสร้างใหม่
        if self._lip_sync_task and not self._lip_sync_task.done():
            self._lip_sync_running = False
            try:
                self._lip_sync_task.cancel()
            except Exception:
                pass
        self._lip_sync_task = asyncio.create_task(_run())
    
    async def _send_parameters(self, parameters: Dict[str, float]):
        """ส่งค่าพารามิเตอร์ไปยัง VTS (ปรับ: ไม่ block)"""
        if not self.authenticated or not self.model_loaded or not self.ws:
            return
        
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
            
            # ✅ ส่งด้วย timeout สั้นเพื่อไม่ block
            try:
                await asyncio.wait_for(self.ws.send(json.dumps(request)), timeout=0.5)
            except asyncio.TimeoutError:
                # non-critical: ข้ามเพื่อไม่บล็อก loop
                pass
            except Exception:
                pass
        except Exception:
            # เงียบไว้เพื่อหลีกเลี่ยง spam
            pass

    async def set_parameter_value(self, param_name: str, value: float, immediate: bool = True):
        """ตั้งค่าพารามิเตอร์เดี่ยว (เช่น MouthOpen) จากแหล่งภายนอก
        - Clamp ตาม min/max ของโมเดล
        - อัพเดท smooth target เพื่อให้เคลื่อนไหวนุ่มนวล
        - ถ้า immediate=True จะส่ง InjectParameterDataRequest ทันที
        """
        try:
            if param_name not in self.available_parameters:
                return
            info = self.available_parameters[param_name]
            clamped = max(info['min'], min(info['max'], value))
            # อัพเดทค่าเป้าหมายสำหรับ smoothing
            if param_name in self.smooth_values:
                self.smooth_values[param_name].set_target(clamped)

            if immediate and self.authenticated and self.model_loaded and self.ws:
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
        except Exception:
            # เงียบไว้เพื่อหลีกเลี่ยง spam ระหว่างเล่นเสียง
            pass
    
    def set_emotion(self, emotion: Emotion, intensity: float):
        """ตั้งค่าอารมณ์"""
        self.current_emotion = emotion
        params = JeedPersona.get_movement_params(emotion, intensity)
        self.movement_speed = params["movement_speed"]
        self.movement_intensity = params["movement_intensity"]
    
    async def start_speaking(self, text: str):
        """เริ่มพูด - lip sync"""
        self.state = AnimationState.SPEAKING
        emotion, intensity = JeedPersona.analyze_emotion(text)
        self.set_emotion(emotion, intensity)
        
        word_count = JeedPersona.count_words(text)
        duration = word_count * 0.35
        asyncio.create_task(self._lip_sync(duration))
    
    async def _lip_sync(self, duration: float):
        """จำลอง lip sync"""
        if 'MouthOpen' not in self.smooth_values:
            return
        
        steps = int(duration / 0.05)
        for i in range(steps):
            if not self.running:
                break
            mouth_open = random.uniform(0.3, 0.7)
            self.smooth_values['MouthOpen'].set_target(mouth_open)
            await asyncio.sleep(0.05)
        
        self.smooth_values['MouthOpen'].set_target(0.0)
        self.state = AnimationState.IDLE
    
    async def stop_speaking(self):
        """หยุดพูด"""
        self.state = AnimationState.IDLE
        # หยุด lip sync ที่กำลังทำงานอยู่ด้วย
        self._lip_sync_running = False
        if self._lip_sync_task and not self._lip_sync_task.done():
            try:
                self._lip_sync_task.cancel()
            except Exception:
                pass
        if 'MouthOpen' in self.smooth_values:
            self.smooth_values['MouthOpen'].set_target(0.0)
    
    async def set_state(self, state: AnimationState):
        """เปลี่ยนสถานะ"""
        self.state = state
        if state == AnimationState.THINKING:
            self.movement_intensity = 0.4
        else:
            self.movement_intensity = 0.8
    
    async def disconnect(self):
        """ตัดการเชื่อมต่อ"""
        print("🛑 กำลังตัดการเชื่อมต่อ VTS...")
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
        
        print("👋 ตัดการเชื่อมต่อ VTS เรียบร้อย")

# Global controller
vtube_controller = VTubeStudioController()