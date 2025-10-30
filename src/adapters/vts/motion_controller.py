"""
VTS Motion Controller - Neuro-sama Style (Improved)
✨ การเคลื่อนไหวแบบต่อเนื่องและมีชีวิตชีวาเหมือน Neuro-sama
"""
import asyncio
import random
import math
import time
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class MotionAction:
    """การกระทำการเคลื่อนไหวหนึ่งอัน"""
    name: str
    duration: float
    head_x: float = 0.0
    head_y: float = 0.0
    head_z: float = 0.0
    body_x: float = 0.0
    body_y: float = 0.0
    intensity: float = 1.0

class MotionController:
    def __init__(self, vts_client, config: dict):
        self.vts = vts_client
        self.config = config
        
        self.is_speaking = False
        self.is_generating = False
        self.is_lipsyncing = False
        self.motion_task = None
        self.should_stop = False
        
        # State - เพิ่มระบบ interpolation ที่ดีขึ้น
        self.current_head_x = 0.0
        self.current_head_y = 0.0
        self.current_head_z = 0.0
        self.current_body_x = 0.0
        self.current_body_y = 0.0
        
        self.target_head_x = 0.0
        self.target_head_y = 0.0
        self.target_head_z = 0.0
        self.target_body_x = 0.0
        self.target_body_y = 0.0
        
        # Timers
        self.breath_time = 0.0
        self.blink_timer = time.time()
        self.idle_timer = time.time()
        self.current_action: Optional[MotionAction] = None
        self.action_progress = 0.0
        
        # จดจำท่าล่าสุดเพื่อหลีกเลี่ยงการซ้ำติดกัน
        from collections import deque
        self._recent_actions = deque(maxlen=2)  # ลดลงเพื่อให้เปลี่ยนท่าบ่อยขึ้น

        # รอยยิ้ม: ระบบใหม่ที่เห็นชัดเจนกว่า
        self.smile_base = 0.4
        self.smile_value = self.smile_base
        self.smile_target = self.smile_base
        self.smile_peak = 0.9
        self.smile_transition_speed = 0.4
        self.next_smile_change = time.time() + random.uniform(3.0, 8.0)  # บ่อยขึ้น
        
        # Config - ปรับค่าให้เคลื่อนไหวบ่อยขึ้น
        self.smoothing = float(config.get("smoothing", 0.7))  # ลด smoothing เพื่อให้ขยับบ่อยขึ้น
        self.intensity = float(config.get("intensity", 1.0))
        self.update_dt = float(config.get("update_dt", 0.033))
        
        # Breathing - เพิ่มความเข้มข้น
        self.breath_speed = float(config.get("VTS_BREATH_SPEED", 0.6))
        self.breath_intensity = float(config.get("VTS_BREATH_INTENSITY", 0.4))
        self.breath_value = 0.0
        
        # การควบคุมความถี่การสุ่มท่าทาง - ลดเวลาพักให้น้อยลง
        self.action_duration_scale = float(config.get("action_duration_scale", 0.8))
        self.min_action_duration = float(config.get("min_action_duration", 0.8))
        self.max_action_duration = float(config.get("max_action_duration", 2.0))
        
        # ✨ สร้างชุดท่าทางแบบ Neuro-sama - ลดความซับซ้อนแต่เพิ่มความถี่
        self.action_pool = self._create_simplified_action_pool()
        
        logger.info(f"✅ Neuro Motion: {len(self.action_pool)} actions, intensity={self.intensity}")

        # เตรียมแผนที่ชื่อพารามิเตอร์
        self._param_names = {
            "AngleX": "FaceAngleX",
            "AngleY": "FaceAngleY", 
            "AngleZ": "FaceAngleZ",
            "PosX": "FacePositionX",
            "PosY": "FacePositionY",
            "MouthSmile": "MouthSmile",
            "EyeSmileL": "ParamEyeLSmile",
            "EyeSmileR": "ParamEyeRSmile",
            "EyeOpenL": "EyeOpenLeft",
            "EyeOpenR": "EyeOpenRight",
            "MouthOpen": "MouthOpen"
        }

    def _create_simplified_action_pool(self) -> List[MotionAction]:
        """
        สร้างชุดท่าทางแบบง่ายแต่เคลื่อนไหวบ่อยเหมือน Neuro-sama
        """
        actions = []
        
        # === Basic Idle Movements (ท่าพื้นฐานที่ขยับเล็กน้อยตลอดเวลา) ===
        actions.extend([
            MotionAction("micro_wiggle", 1.2, head_x=0.1, head_z=0.05, intensity=0.3),
            MotionAction("micro_nod", 1.0, head_y=0.1, intensity=0.3),
            MotionAction("micro_sway", 1.5, head_x=0.08, head_z=0.08, intensity=0.4),
            MotionAction("breath_bob", 1.8, head_y=0.05, body_y=0.1, intensity=0.3),
        ])
        
        # === Frequent Head Movements (ท่าเอียงหัวที่พบบ่อย) ===
        actions.extend([
            MotionAction("tilt_right", 1.5, head_z=0.3, intensity=0.6),
            MotionAction("tilt_left", 1.5, head_z=-0.3, intensity=0.6),
            MotionAction("tilt_curious", 1.8, head_z=0.2, head_y=0.1, intensity=0.5),
            MotionAction("nod_yes", 1.2, head_y=0.2, intensity=0.7),
            MotionAction("nod_no", 1.4, head_x=0.3, intensity=0.7),
        ])
        
        # === Looking Around (มองไปรอบๆ) ===
        actions.extend([
            MotionAction("look_right", 1.6, head_x=0.4, intensity=0.8),
            MotionAction("look_left", 1.6, head_x=-0.4, intensity=0.8),
            MotionAction("look_up", 1.3, head_y=0.3, intensity=0.6),
            MotionAction("look_down", 1.3, head_y=-0.2, intensity=0.5),
            MotionAction("look_around", 2.0, head_x=0.3, head_y=0.1, intensity=0.7),
        ])
        
        # === Expressive Movements (ท่าทางแสดงอารムณ์) ===
        actions.extend([
            MotionAction("thinking_tilt", 2.0, head_z=0.2, head_y=-0.1, intensity=0.6),
            MotionAction("curious_lean", 1.8, head_x=0.2, body_x=0.1, intensity=0.7),
            MotionAction("happy_bounce", 1.2, head_y=0.15, body_y=0.2, intensity=0.8),
        ])
        
        # === Body Sways (การเคลื่อนไหวร่างกาย) ===
        actions.extend([
            MotionAction("body_sway_right", 2.0, body_x=0.2, head_x=0.1, intensity=0.6),
            MotionAction("body_sway_left", 2.0, body_x=-0.2, head_x=-0.1, intensity=0.6),
            MotionAction("body_lean_forward", 1.5, body_y=-0.1, head_y=-0.05, intensity=0.5),
            MotionAction("body_lean_back", 1.5, body_y=0.1, head_y=0.05, intensity=0.5),
        ])
        
        return actions

    async def start(self):
        """เริ่ม motion loop"""
        if self.motion_task and not self.motion_task.done():
            logger.warning("Motion loop กำลังทำงานอยู่แล้ว")
            return
        
        # รีโซลฟ์ชื่อพารามิเตอร์
        try:
            self._param_names = {
                "AngleX": self.vts.resolve_param_name("FaceAngleX", "ParamAngleX", "AngleX"),
                "AngleY": self.vts.resolve_param_name("FaceAngleY", "ParamAngleY", "AngleY"),
                "AngleZ": self.vts.resolve_param_name("FaceAngleZ", "ParamAngleZ", "AngleZ"),
                "PosX": self.vts.resolve_param_name("FacePositionX", "ParamPositionX", "PositionX", "ParamPosX", "PosX"),
                "PosY": self.vts.resolve_param_name("FacePositionY", "ParamPositionY", "PositionY", "ParamPosY", "PosY"),
                "MouthSmile": self.vts.resolve_param_name("MouthSmile", "ParamMouthSmile", "Smile"),
                "EyeSmileL": self.vts.resolve_param_name("ParamEyeLSmile", "EyeSmileLeft", "ParamEyeSmileLeft"),
                "EyeSmileR": self.vts.resolve_param_name("ParamEyeRSmile", "EyeSmileRight", "ParamEyeSmileRight"),
                "EyeOpenL": self.vts.resolve_param_name("EyeOpenLeft", "ParamEyeOpenLeft", "EyeOpenL", "ParamEyeOpenL"),
                "EyeOpenR": self.vts.resolve_param_name("EyeOpenRight", "ParamEyeOpenRight", "EyeOpenR", "ParamEyeOpenR"),
                "MouthOpen": self.vts.resolve_param_name("MouthOpen", "ParamMouthOpen", "MouthOpenY"),
            }
        except Exception as e:
            logger.warning(f"ไม่สามารถ resolve parameter names: {e}")

        self.should_stop = False
        self.motion_task = asyncio.create_task(self._motion_loop())
        logger.info("🎬 Neuro Motion เริ่มทำงาน")

    async def stop(self):
        """หยุด motion loop"""
        self.should_stop = True
        if self.motion_task:
            try:
                self.motion_task.cancel()
                await asyncio.wait_for(self.motion_task, timeout=2.0)
            except:
                pass
            self.motion_task = None
        logger.info("⏹️ Motion loop หยุดแล้ว")

    def set_speaking(self, speaking: bool):
        """ตั้งสถานะการพูด"""
        self.is_speaking = speaking
        if speaking:
            logger.info("🎤 สถานะ: กำลังพูด")
        else:
            logger.info("🔇 สถานะ: หยุดพูด")

    def set_generating(self, generating: bool):
        self.is_generating = generating

    def set_lipsyncing(self, lipsyncing: bool):
        """ตั้งสถานะลิปซิงก์ เพื่อหลีกเลี่ยงการฉีด MouthOpen ซ้ำซ้อนจาก motion"""
        self.is_lipsyncing = lipsyncing

    async def _motion_loop(self):
        """
        Main motion loop - Neuro-sama Style ที่ขยับตลอดเวลา
        """
        logger.info("🎭 Neuro Motion Loop เริ่มต้น")
        
        # เริ่มท่าแรกทันที
        self._pick_random_action()
        
        while not self.should_stop:
            try:
                current_time = time.time()
                dt = self.update_dt
                
                if not self.vts._is_connected():
                    await asyncio.sleep(1.0)
                    continue
                
                self.breath_time += dt
                
                # === เปลี่ยนท่าทางใหม่เมื่อท่าเดิมจบ ===
                if self.current_action is not None and self.action_progress >= 1.0:
                    self._pick_random_action()
                
                # === อัพเดทการเคลื่อนไหว ===
                await self._update_action(dt)
                
                # === ระบบพื้นฐาน ===
                await self._update_breathing()
                await self._update_blinking()
                await self._update_smile()
                await self._update_idle_movement()

                # ส่งพารามิเตอร์
                await self._apply_parameters()
                
                await asyncio.sleep(dt)
                
            except Exception as e:
                logger.error(f"Motion error: {e}", exc_info=True)
                await asyncio.sleep(0.5)
        
        logger.info("🛑 Motion loop หยุด")

    def _pick_random_action(self):
        """สุ่มเลือกท่าทางใหม่"""
        # หลีกเลี่ยงท่าที่ซ้ำกับล่าสุด
        available_actions = [a for a in self.action_pool 
                           if not any(a.name == recent.name for recent in self._recent_actions)]
        
        if not available_actions:
            available_actions = self.action_pool
        
        self.current_action = random.choice(available_actions)
        
        # ปรับระยะเวลาตามสถานะ
        if self.is_speaking:
            base_duration = random.uniform(self.min_action_duration * 0.7, self.max_action_duration * 0.8)
        else:
            base_duration = random.uniform(self.min_action_duration, self.max_action_duration)
        
        self.current_action.duration = base_duration * self.action_duration_scale
        self.action_progress = 0.0
        
        # ตั้งค่า target positions
        action = self.current_action
        intensity_multiplier = action.intensity * self.intensity
        
        self.target_head_x = action.head_x * intensity_multiplier
        self.target_head_y = action.head_y * intensity_multiplier  
        self.target_head_z = action.head_z * intensity_multiplier
        self.target_body_x = action.body_x * intensity_multiplier
        self.target_body_y = action.body_y * intensity_multiplier
        
        self._recent_actions.append(self.current_action)
        
        logger.debug(f"🎭 Action: {self.current_action.name} ({self.current_action.duration:.1f}s)")

    async def _update_action(self, dt: float):
        """อัพเดทท่าทางปัจจุบัน"""
        if self.current_action:
            # คำนวณ progress
            self.action_progress += dt / self.current_action.duration
            self.action_progress = min(self.action_progress, 1.0)
            
            # Easing function สำหรับการเคลื่อนไหวที่สมูท
            t = self.action_progress
            if t < 0.5:
                eased = 2 * t * t
            else:
                eased = -1 + (4 - 2 * t) * t
            
            # คำนวณ target position ตาม easing
            action = self.current_action
            intensity_multiplier = action.intensity * self.intensity
            
            target_head_x = action.head_x * eased * intensity_multiplier
            target_head_y = action.head_y * eased * intensity_multiplier
            target_head_z = action.head_z * eased * intensity_multiplier
            target_body_x = action.body_x * eased * intensity_multiplier
            target_body_y = action.body_y * eased * intensity_multiplier
            
            # Smooth interpolation ไปยัง target
            alpha = 0.15
            
            self.current_head_x += (target_head_x - self.current_head_x) * alpha
            self.current_head_y += (target_head_y - self.current_head_y) * alpha
            self.current_head_z += (target_head_z - self.current_head_z) * alpha
            self.current_body_x += (target_body_x - self.current_body_x) * alpha
            self.current_body_y += (target_body_y - self.current_body_y) * alpha
        else:
            # ถ้าไม่มี action ปัจจุบัน ให้ค่อยๆ คืนสู่ตำแหน่งกลาง
            self.target_head_x = 0.0
            self.target_head_y = 0.0
            self.target_head_z = 0.0
            self.target_body_x = 0.0
            self.target_body_y = 0.0
            
            alpha = 0.1
            self.current_head_x += (self.target_head_x - self.current_head_x) * alpha
            self.current_head_y += (self.target_head_y - self.current_head_y) * alpha
            self.current_head_z += (self.target_head_z - self.current_head_z) * alpha
            self.current_body_x += (self.target_body_x - self.current_body_x) * alpha
            self.current_body_y += (self.target_body_y - self.current_body_y) * alpha

    async def _update_idle_movement(self):
        """การเคลื่อนไหวเล็กน้อยระหว่างเปลี่ยนท่า"""
        # เพิ่มการเคลื่อนไหวแบบสุ่มเล็กน้อยตลอดเวลา
        micro_movement = math.sin(self.breath_time * 2.0) * 0.02
        self.current_head_x += micro_movement * 0.1
        self.current_head_y += math.cos(self.breath_time * 1.7) * 0.015
        self.current_head_z += math.sin(self.breath_time * 2.3) * 0.01

    async def _apply_parameters(self):
        """ส่งค่าพารามิเตอร์ไปยัง VTS"""
        try:
            if not self.vts._is_connected():
                return

            # รวมค่า breathing
            body_y_with_breath = self.current_body_y + (self.breath_value * 0.3)

            params = {
                self._param_names["AngleX"]: self.current_head_x * 30.0,
                self._param_names["AngleY"]: self.current_head_y * 30.0,
                self._param_names["AngleZ"]: self.current_head_z * 30.0,
                self._param_names["PosX"]: self.current_body_x * 10.0,
                self._param_names["PosY"]: body_y_with_breath * 5.0,
            }

            # รอยยิ้ม + เสียงพูด (ถ้ากำลังพูด)
            micro_smile = (math.sin(self.breath_time * 0.5) + math.cos(self.breath_time * 0.3)) * 0.05
            base_smile = self.smile_value
            
            # หากกำลังพูด และไม่มีลิปซิงก์ ให้เพิ่ม animation ปากพื้นฐาน
            if self.is_speaking and not self.is_lipsyncing:
                mouth_move = abs(math.sin(self.breath_time * 6.0)) * 0.3
                # ใช้พารามิเตอร์ปากสำหรับลิปซิงก์
                params[self._param_names["MouthOpen"]] = mouth_move
                # ยิ้มมากขึ้นขณะพูด
                base_smile += 0.2
            
            mouth_smile = max(0.0, min(1.0, base_smile + micro_smile))
            eye_smile = max(0.0, min(1.0, 0.3 + mouth_smile * 0.4))

            params.update({
                self._param_names["MouthSmile"]: mouth_smile,
                self._param_names["EyeSmileL"]: eye_smile,
                self._param_names["EyeSmileR"]: eye_smile,
            })

            # ส่งแบบ batch
            await self.vts.inject_parameters_bulk(params)
                
        except Exception as e:
            logger.error(f"Apply parameters error: {e}")

    async def _update_smile(self):
        """อัพเดทรอยยิ้ม - บ่อยและเห็นชัดเจนกว่า"""
        current_time = time.time()
        
        # เปลี่ยนเป้าหมายรอยยิ้มบ่อยขึ้น
        if current_time >= self.next_smile_change:
            if self.smile_target == self.smile_base:
                # สุ่มว่าจะยิ้มกว้างหรือไม่ (50% โอกาส)
                if random.random() < 0.5:
                    self.smile_target = random.uniform(self.smile_peak * 0.7, self.smile_peak)
                else:
                    self.smile_target = random.uniform(self.smile_base, self.smile_peak * 0.5)
            else:
                # คืนสู่ค่าฐาน
                self.smile_target = self.smile_base
            
            # สุ่มเวลาถัดไป (บ่อยขึ้น)
            self.next_smile_change = current_time + random.uniform(2.0, 6.0)
        
        # ค่อยๆ เปลี่ยนค่า
        if self.smile_target > self.smile_value:
            self.smile_value += self.smile_transition_speed * self.update_dt
            if self.smile_value >= self.smile_target:
                self.smile_value = self.smile_target
        elif self.smile_target < self.smile_value:
            self.smile_value -= self.smile_transition_speed * self.update_dt
            if self.smile_value <= self.smile_target:
                self.smile_value = self.smile_target

    async def _update_breathing(self):
        """Breathing Animation - แบบเห็นชัดเจน"""
        self.breath_value = (math.sin(self.breath_time * self.breath_speed) + 1.0) * 0.5
        self.breath_value *= self.breath_intensity

    async def _update_blinking(self):
        """Blinking - ความถี่ตามธรรมชาติ"""
        try:
            if not self.vts._is_connected():
                return
            
            current_time = time.time()
            
            # ความถี่การกระพริบตามธรรมชาติ (บ่อยขึ้น)
            blink_interval = random.uniform(1.5, 4.0)
            
            if current_time - self.blink_timer >= blink_interval:
                # ปิดตา
                await self.vts.inject_parameters_bulk({
                    self._param_names["EyeOpenL"]: 0.0,
                    self._param_names["EyeOpenR"]: 0.0,
                })
                
                await asyncio.sleep(0.08)  # กระพริบเร็ว
                
                # เปิดตา
                await self.vts.inject_parameters_bulk({
                    self._param_names["EyeOpenL"]: 1.0,
                    self._param_names["EyeOpenR"]: 1.0,
                })
                
                self.blink_timer = current_time
                
        except Exception as e:
            logger.error(f"Blinking error: {e}")

    async def trigger_emotion(self, emotion: str):
        """Trigger emotion hotkey"""
        try:
            if not self.vts._is_connected():
                return
            
            hotkey_map = {
                "happy": ["happy", "smile", "ยิ้ม"],
                "sad": ["sad", "เศร้า"], 
                "angry": ["angry", "โกรธ"],
                "surprised": ["surprised", "ตกใจ"],
                "thinking": ["thinking", "คิด"]
            }
            
            if emotion.lower() in hotkey_map:
                await self.vts.trigger_hotkey_by_name(hotkey_map[emotion.lower()])
                logger.info(f"💫 Emotion: {emotion}")
        except Exception as e:
            logger.error(f"Emotion error: {e}")


def create_motion_controller(vts_client, env_config: dict):
    """สร้าง Motion Controller ใหม่"""
    config = {
        "smoothing": env_config.get("VTS_MOVEMENT_SMOOTHING", "0.7"),
        "intensity": env_config.get("VTS_MOTION_INTENSITY", "1.0"),
        "update_dt": env_config.get("VTS_UPDATE_DT", "0.033"),
        "VTS_BREATH_SPEED": env_config.get("VTS_BREATH_SPEED", "0.6"),
        "VTS_BREATH_INTENSITY": env_config.get("VTS_BREATH_INTENSITY", "0.4"),
        "action_duration_scale": env_config.get("VTS_ACTION_DURATION_SCALE", "0.8"),
        "min_action_duration": env_config.get("VTS_MIN_ACTION_DURATION", "0.8"),
        "max_action_duration": env_config.get("VTS_MAX_ACTION_DURATION", "2.0"),
    }
    return MotionController(vts_client, config)