"""
ระบบควบคุม VTube Studio พร้อม Smooth Animation
ตำแหน่ง: src/adapters/vts/vtube_controller.py (สร้างโฟลเดอร์ vts/ ใหม่)
"""

import asyncio
import websockets
import json
import random
import math
import time
from typing import Dict, Optional
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

@dataclass
class MovementTarget:
    """เป้าหมายการเคลื่อนไหว"""
    head_x: float = 0.0
    head_y: float = 0.0
    body_x: float = 0.0
    body_y: float = 0.0
    eye_x: float = 0.0
    eye_y: float = 0.0
    mouth_open: float = 0.0

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
    
    def is_near_target(self, threshold: float = 0.01) -> bool:
        return abs(self.target - self.current) < threshold

class VTubeStudioController:
    """ควบคุม VTube Studio ผ่าน WebSocket"""
    
    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.authenticated = False
        self.auth_token: Optional[str] = config.vtube.plugin_token
        self.model_loaded = False
        self.animation_task: Optional[asyncio.Task] = None
        self.state = AnimationState.IDLE
        self.running = False
        
        # Smooth values
        self.smooth_head_x = SmoothValue(0, config.vtube.smooth_factor)
        self.smooth_head_y = SmoothValue(0, config.vtube.smooth_factor)
        self.smooth_body_x = SmoothValue(0, config.vtube.smooth_factor)
        self.smooth_body_y = SmoothValue(0, config.vtube.smooth_factor)
        self.smooth_eye_x = SmoothValue(0, config.vtube.smooth_factor)
        self.smooth_eye_y = SmoothValue(0, config.vtube.smooth_factor)
        self.smooth_mouth = SmoothValue(0, config.vtube.smooth_factor * 2)
        
        # Movement parameters
        self.movement_intensity = 0.5
        self.movement_speed = 1.0
        self.current_emotion = Emotion.NEUTRAL
        self.expression = "smile"
        
        # Timers
        self.last_movement_change = time.time()
        self.last_eye_movement = time.time()
        self.movement_duration = random.uniform(2, 4)
        self.eye_movement_duration = random.uniform(1, 3)
    
    async def connect(self) -> bool:
        """เชื่อมต่อกับ VTube Studio"""
        try:
            self.ws = await websockets.connect(
                config.vtube.websocket_url,
                ping_interval=20,
                ping_timeout=10
            )
            print("✅ เชื่อมต่อ VTube Studio")
            
            await self._authenticate()
            # ตรวจว่าโมเดลถูกโหลดแล้วหรือยัง และพยายามโหลดตามชื่อหากระบุไว้
            await self._ensure_model_loaded()
            # สร้าง custom parameters ที่จำเป็นถ้ายังไม่มี
            await self._ensure_custom_parameters()
            
            self.running = True
            self.animation_task = asyncio.create_task(self._animation_loop())
            
            return True
        except Exception as e:
            print(f"❌ เชื่อมต่อ VTS ล้มเหลว: {e}")
            return False
    
    async def _authenticate(self):
        """ขอ authentication"""
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
            print(f"💾 Save this token to .env: VTS_PLUGIN_TOKEN={self.auth_token}")
            await self._authenticate()
        elif response.get("data", {}).get("authenticated"):
            self.authenticated = True
            print("✅ VTS Authentication สำเร็จ")
    
    async def _ensure_model_loaded(self):
        """ตรวจสอบและทำให้แน่ใจว่า VTS มีโมเดลโหลดอยู่"""
        try:
            # เช็คโมเดลปัจจุบัน
            current_req = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "current_model",
                "messageType": "CurrentModelRequest",
                "data": {}
            }
            await self.ws.send(json.dumps(current_req))
            current_res = json.loads(await self.ws.recv())
            if current_res.get("data", {}).get("modelLoaded"):
                self.model_loaded = True
                model_name = current_res.get("data", {}).get("modelName", "")
                print(f"✅ พบโมเดลที่โหลดอยู่: {model_name}")
                return

            # ถ้าไม่มีโมเดล ให้พยายามโหลดตามชื่อใน config โดยค้นหา ID ก่อน
            if getattr(config.vtube, "model_name", None):
                list_req = {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": "list_models",
                    "messageType": "AvailableModelsRequest",
                    "data": {}
                }
                await self.ws.send(json.dumps(list_req))
                list_res = json.loads(await self.ws.recv())
                models = list_res.get("data", {}).get("availableModels", [])
                target_id = None
                for m in models:
                    if m.get("modelName") == config.vtube.model_name:
                        target_id = m.get("modelID")
                        break
                if target_id:
                    load_req = {
                        "apiName": "VTubeStudioPublicAPI",
                        "apiVersion": "1.0",
                        "requestID": "load_model",
                        "messageType": "ModelLoadRequest",
                        "data": {"modelID": target_id}
                    }
                    await self.ws.send(json.dumps(load_req))
                    load_res = json.loads(await self.ws.recv())
                    if load_res.get("data", {}).get("modelLoaded"):
                        self.model_loaded = True
                        print(f"✅ โหลดโมเดล {config.vtube.model_name}")
                        return
            print("⚠️ ไม่มีโมเดลที่โหลดอยู่ใน VTS (โปรดโหลดโมเดลในแอป)")
        except Exception as e:
            print(f"⚠️ ตรวจสอบ/โหลดโมเดลล้มเหลว: {e}")

    async def _ensure_custom_parameters(self):
        """สร้าง custom parameters ที่ใช้โดยระบบ หากยังไม่มี"""
        try:
            list_req = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "list_custom_params",
                "messageType": "AvailableCustomParametersRequest",
                "data": {}
            }
            await self.ws.send(json.dumps(list_req))
            list_res = json.loads(await self.ws.recv())
            existing = {p.get("name") for p in list_res.get("data", {}).get("customParameters", [])}

            needed = [
                "AIVTuber_Mood_Happy",
                "AIVTuber_Mood_Sad",
                "AIVTuber_Mood_Thinking",
                "AIVTuber_Speaking",
                "AIVTuber_Energy",
            ]

            for name in needed:
                if name in existing:
                    continue
                create_req = {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": f"create_{name}",
                    "messageType": "CreateCustomParameterRequest",
                    "data": {
                        "parameterName": name,
                        "explanation": "Parameter created by AI VTuber Demo",
                        "min": 0.0,
                        "max": 1.0,
                        "defaultValue": 0.0,
                        "deleteWhenPluginDisconnects": True
                    }
                }
                try:
                    await self.ws.send(json.dumps(create_req))
                    _ = json.loads(await self.ws.recv())
                    print(f"🧩 สร้าง custom parameter: {name}")
                except Exception as ce:
                    print(f"⚠️ สร้าง custom parameter ไม่สำเร็จ ({name}): {ce}")
        except Exception as e:
            print(f"⚠️ ตรวจสอบ custom parameters ล้มเหลว: {e}")
    
    def _generate_random_movement(self) -> MovementTarget:
        """สร้างจุดเป้าหมายแบบสุ่ม"""
        intensity = random.uniform(*config.vtube.movement_intensity)
        intensity *= self.movement_intensity
        
        head_x = random.uniform(*config.vtube.head_rotation_range) * intensity
        head_y = random.uniform(-10, 10) * intensity
        body_x = random.uniform(*config.vtube.body_rotation_range) * intensity * 0.6
        body_y = 0
        eye_x = random.uniform(-1, 1)
        eye_y = random.uniform(-0.5, 0.5)
        
        return MovementTarget(
            head_x=head_x, head_y=head_y,
            body_x=body_x, body_y=body_y,
            eye_x=eye_x, eye_y=eye_y,
            mouth_open=0.0
        )
    
    async def _animation_loop(self):
        """Loop หลักสำหรับอัพเดทการเคลื่อนไหว"""
        print("🎬 เริ่ม Animation Loop")
        
        while self.running:
            try:
                current_time = time.time()
                
                # เปลี่ยนท่า
                if current_time - self.last_movement_change >= self.movement_duration:
                    target = self._generate_random_movement()
                    self.smooth_head_x.set_target(target.head_x)
                    self.smooth_head_y.set_target(target.head_y)
                    self.smooth_body_x.set_target(target.body_x)
                    self.smooth_body_y.set_target(target.body_y)
                    self.last_movement_change = current_time
                    self.movement_duration = random.uniform(2, 4) / self.movement_speed
                
                # เคลื่อนไหวตา
                if current_time - self.last_eye_movement >= self.eye_movement_duration:
                    eye_target = self._generate_random_movement()
                    self.smooth_eye_x.set_target(eye_target.eye_x)
                    self.smooth_eye_y.set_target(eye_target.eye_y)
                    self.last_eye_movement = current_time
                    self.eye_movement_duration = random.uniform(*config.vtube.eye_movement_speed)
                
                # อัพเดทค่า
                head_x = self.smooth_head_x.update()
                head_y = self.smooth_head_y.update()
                body_x = self.smooth_body_x.update()
                body_y = self.smooth_body_y.update()
                eye_x = self.smooth_eye_x.update()
                eye_y = self.smooth_eye_y.update()
                mouth = self.smooth_mouth.update()
                
                # ส่งไป VTS
                await self._send_parameters({
                    "FaceAngleX": head_y,
                    "FaceAngleY": head_x,
                    "FaceAngleZ": body_x,
                    "FacePositionX": body_x * 0.5,
                    "EyeLeftX": eye_x,
                    "EyeLeftY": eye_y,
                    "EyeRightX": eye_x,
                    "EyeRightY": eye_y,
                    "MouthOpen": mouth
                })
                
                await asyncio.sleep(config.vtube.idle_update_rate)
            except Exception as e:
                print(f"⚠️ Animation error: {e}")
                await asyncio.sleep(1)
    
    async def _send_parameters(self, parameters: Dict[str, float]):
        """ส่งค่าพารามิเตอร์"""
        if not self.authenticated or not self.model_loaded:
            return
        
        parameter_values = [
            {"id": name, "value": value}
            for name, value in parameters.items()
        ]
        
        request = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "set_params",
            "messageType": "InjectParameterDataRequest",
            "data": {"parameterValues": parameter_values}
        }
        
        try:
            await self.ws.send(json.dumps(request))
        except:
            pass
    
    def set_emotion(self, emotion: Emotion, intensity: float):
        """ตั้งค่าอารมณ์"""
        self.current_emotion = emotion
        params = JeedPersona.get_movement_params(emotion, intensity)
        self.movement_speed = params["movement_speed"]
        self.movement_intensity = params["movement_intensity"]
        self.expression = params["expression"]
    
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
        steps = int(duration / 0.05)
        for i in range(steps):
            mouth_open = random.uniform(0.3, 0.7)
            self.smooth_mouth.set_target(mouth_open)
            await asyncio.sleep(0.05)
        self.smooth_mouth.set_target(0.0)
        self.state = AnimationState.IDLE
    
    async def stop_speaking(self):
        """หยุดพูด"""
        self.state = AnimationState.IDLE
        self.smooth_mouth.set_target(0.0)
    
    async def set_state(self, state: AnimationState):
        """เปลี่ยนสถานะ"""
        self.state = state
        if state == AnimationState.THINKING:
            self.movement_intensity = 0.3
        else:
            self.movement_intensity = 0.5
    
    async def disconnect(self):
        """ตัดการเชื่อมต่อ"""
        self.running = False
        if self.animation_task:
            self.animation_task.cancel()
        if self.ws:
            await self.ws.close()
        print("👋 ตัดการเชื่อมต่อ VTS")

# Global controller
vtube_controller = VTubeStudioController()