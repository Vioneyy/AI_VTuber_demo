"""
VTS Motion Controller - Neuro-sama Style
✨ การเคลื่อนไหวแบบสุ่ม มีชีวิตชีวา ไม่ซ้ำซาก
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
        self.motion_task = None
        self.should_stop = False
        
        # State
        self.current_head_x = 0.0
        self.current_head_y = 0.0
        self.current_head_z = 0.0
        self.current_body_x = 0.0
        self.current_body_y = 0.0
        
        # Timers
        self.breath_time = 0.0
        self.blink_timer = time.time()
        self.action_timer = time.time()
        self.next_action_time = time.time()
        self.current_action: Optional[MotionAction] = None
        self.action_progress = 0.0
        # จดจำท่าล่าสุดเพื่อหลีกเลี่ยงการซ้ำติดกัน
        from collections import deque
        self._recent_actions = deque(maxlen=3)

        # รอยยิ้ม: ฐาน + ramp แบบค่อยๆ เพิ่มและลดเป็นช่วง ๆ
        self.smile_base = 0.35
        self.smile_value = self.smile_base
        self.smile_target = self.smile_base
        self.smile_peak = 0.85
        self.smile_speed_up = 1.2   # หน่วยต่อวินาที
        self.smile_speed_down = 0.8 # หน่วยต่อวินาที
        self.next_smile_time = time.time() + random.uniform(8.0, 14.0)
        self.smile_hold_until = 0.0
        
        # Config
        # เพิ่มความสมูทเริ่มต้นให้สูงขึ้น ลดอาการสั่น
        self.smoothing = float(config.get("smoothing", 0.96))
        self.intensity = float(config.get("intensity", 1.0))
        # อัตราอัพเดท (dt) ค่าเริ่มต้น 0.05 (~20 FPS) เพื่อความเสถียร
        self.update_dt = float(config.get("update_dt", 0.05))
        # การหายใจ (รองรับ override จาก .env ผ่าน config)
        self.breath_speed = float(config.get("VTS_BREATH_SPEED", 0.8))
        self.breath_intensity = float(config.get("VTS_BREATH_INTENSITY", 0.3))
        self.breath_value = 0.0
        # การควบคุมความถี่การสุ่มท่าทาง
        self.action_duration_scale = float(config.get("action_duration_scale", 1.15))
        self.action_rest_min_sec = float(config.get("action_rest_min_sec", 0.6))
        self.action_rest_max_sec = float(config.get("action_rest_max_sec", 1.2))
        self.idle_hold_prob = float(config.get("idle_hold_prob", 0.35))
        
        # ✨ สร้างชุดท่าทางแบบ Neuro-sama
        self.action_pool = self._create_action_pool()
        # ปรับ duration ให้ยาวขึ้นเพื่อให้สุ่มท่าถี่น้อยลง
        for a in self.action_pool:
            a.duration = max(0.2, a.duration * self.action_duration_scale)
        # กลุ่ม idle สำหรับ bias
        self.idle_actions = [a for a in self.action_pool if a.name.startswith("idle_") or "idle" in a.name]
        
        logger.info(f"✅ Neuro Motion: {len(self.action_pool)} actions, intensity={self.intensity}, duration_scale={self.action_duration_scale}")

        # เตรียมแผนที่ชื่อพารามิเตอร์ (จะรีเฟรชอีกครั้งตอน start หลัง verify_connection)
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
        }

    def _create_action_pool(self) -> List[MotionAction]:
        """
        สร้างชุดท่าทางต่างๆ แบบ Neuro-sama
        🎭 มีท่าพิเศษเยอะๆ ไม่ซ้ำซาก
        """
        actions = []
        
        # === 1. Head Tilts (เอียงหัว) ===
        actions.extend([
            MotionAction("tilt_right", 1.5, head_z=0.8, intensity=0.8),
            MotionAction("tilt_left", 1.5, head_z=-0.8, intensity=0.8),
            MotionAction("tilt_right_strong", 1.2, head_z=1.2, head_y=0.3, intensity=1.2),
            MotionAction("tilt_left_strong", 1.2, head_z=-1.2, head_y=-0.3, intensity=1.2),
        ])
        
        # === 2. Head Nods (พยักหน้า/ส่ายหน้า) ===
        actions.extend([
            MotionAction("nod_yes", 1.0, head_y=0.6, intensity=0.9),
            MotionAction("nod_no", 1.2, head_x=0.8, intensity=0.9),
            MotionAction("nod_confused", 1.5, head_x=0.5, head_z=0.4, intensity=0.7),
        ])
        
        # === 3. Look Around (มองไปรอบๆ) ===
        actions.extend([
            MotionAction("look_right", 1.8, head_x=1.0, head_y=0.2, intensity=1.0),
            MotionAction("look_left", 1.8, head_x=-1.0, head_y=0.2, intensity=1.0),
            MotionAction("look_up", 1.5, head_y=0.8, intensity=0.8),
            MotionAction("look_down", 1.5, head_y=-0.5, intensity=0.6),
            MotionAction("look_up_right", 2.0, head_x=0.7, head_y=0.6, intensity=0.9),
            MotionAction("look_up_left", 2.0, head_x=-0.7, head_y=0.6, intensity=0.9),
        ])
        
        # === 4. Thinking Poses (ท่าคิด) ===
        actions.extend([
            MotionAction("thinking_right", 2.5, head_x=0.5, head_z=0.3, head_y=-0.2, intensity=0.7),
            MotionAction("thinking_left", 2.5, head_x=-0.5, head_z=-0.3, head_y=-0.2, intensity=0.7),
            MotionAction("thinking_up", 2.0, head_y=0.4, head_z=0.2, intensity=0.6),
        ])
        
        # === 5. Surprised/Excited (ตกใจ/ตื่นเต้น) ===
        actions.extend([
            MotionAction("surprised", 0.8, head_y=0.5, body_y=0.3, intensity=1.5),
            MotionAction("excited_bounce", 1.0, head_y=0.4, body_y=0.5, intensity=1.8),
            MotionAction("shocked", 0.6, head_x=0.3, head_y=0.4, intensity=1.6),
        ])
        
        # === 6. Curious (สงสัย/อยากรู้) ===
        actions.extend([
            MotionAction("curious_tilt", 2.0, head_z=0.6, head_x=0.3, intensity=0.8),
            MotionAction("curious_lean", 2.2, head_x=0.4, body_x=0.3, intensity=0.9),
            MotionAction("peek_right", 1.5, head_x=0.8, body_x=0.4, intensity=1.0),
            MotionAction("peek_left", 1.5, head_x=-0.8, body_x=-0.4, intensity=1.0),
        ])
        
        # === 7. Playful (ขี้เล่น) ===
        actions.extend([
            MotionAction("playful_wiggle", 1.2, head_z=0.5, body_x=0.2, intensity=1.1),
            MotionAction("cheeky_smile", 1.5, head_z=0.4, head_y=0.2, intensity=0.9),
            MotionAction("teasing", 1.8, head_x=0.5, head_z=-0.3, intensity=1.0),
        ])
        
        # === 8. Confident (มั่นใจ) ===
        actions.extend([
            MotionAction("confident_up", 2.0, head_y=0.3, body_y=0.2, intensity=0.8),
            MotionAction("proud", 2.5, head_y=0.4, head_z=0.1, intensity=0.9),
        ])
        
        # === 9. Shy/Embarrassed (อาย) ===
        actions.extend([
            MotionAction("shy_down", 2.0, head_y=-0.4, head_z=0.2, intensity=0.6),
            MotionAction("embarrassed", 1.8, head_x=0.3, head_y=-0.3, head_z=0.4, intensity=0.7),
        ])
        
        # === 10. Idle Variations (ท่าพักธรรมดา แต่หลากหลาย) ===
        actions.extend([
            MotionAction("idle_center", 3.0, head_x=0.0, head_y=0.0, head_z=0.0, intensity=0.5),
            MotionAction("idle_slight_right", 2.5, head_x=0.2, head_z=0.1, intensity=0.5),
            MotionAction("idle_slight_left", 2.5, head_x=-0.2, head_z=-0.1, intensity=0.5),
            MotionAction("idle_relaxed", 3.5, head_y=-0.1, head_z=0.05, intensity=0.4),
        ])
        
        # === 11. Special Actions (ท่าพิเศษ) ===
        actions.extend([
            MotionAction("head_shake_fast", 0.8, head_x=0.9, intensity=1.8),
            MotionAction("big_nod", 1.0, head_y=0.8, intensity=1.5),
            MotionAction("lean_forward", 2.0, head_y=-0.3, body_y=-0.2, intensity=1.0),
            MotionAction("lean_back", 2.0, head_y=0.3, body_y=0.2, intensity=1.0),
        ])

        # === 12. Slow Pans & Arcs (เคลื่อนช้า เนียน) ===
        actions.extend([
            MotionAction("pan_left_slow", 2.6, head_x=-0.6, head_y=0.1, intensity=0.7),
            MotionAction("pan_right_slow", 2.6, head_x=0.6, head_y=0.1, intensity=0.7),
            MotionAction("arc_up_left", 2.4, head_x=-0.4, head_y=0.5, intensity=0.7),
            MotionAction("arc_up_right", 2.4, head_x=0.4, head_y=0.5, intensity=0.7),
            MotionAction("arc_down_left", 2.4, head_x=-0.4, head_y=-0.4, intensity=0.6),
            MotionAction("arc_down_right", 2.4, head_x=0.4, head_y=-0.4, intensity=0.6),
        ])

        # === 13. Figure Eight & Circles (รูปเลขแปด/วงกลม) ===
        actions.extend([
            MotionAction("figure8_small", 3.0, head_x=0.5, head_y=0.4, intensity=0.6),
            MotionAction("figure8_wide", 3.4, head_x=0.7, head_y=0.5, intensity=0.7),
            MotionAction("head_circle_cw", 3.2, head_x=0.5, head_y=0.5, intensity=0.6),
            MotionAction("head_circle_ccw", 3.2, head_x=-0.5, head_y=0.5, intensity=0.6),
        ])

        # === 14. Sways & Bounces (แกว่ง/ย่อ) ===
        actions.extend([
            MotionAction("sway_x_soft", 2.4, head_x=0.6, intensity=0.7),
            MotionAction("sway_y_soft", 2.4, head_y=0.6, intensity=0.7),
            MotionAction("sway_z_soft", 2.4, head_z=0.6, intensity=0.7),
            MotionAction("bounce_soft", 2.0, head_y=0.4, body_y=0.4, intensity=0.6),
        ])

        # === 15. Diagonal Tilts & Looks (เอียงแนวทแยง) ===
        actions.extend([
            MotionAction("tilt_look_up_left", 2.2, head_x=-0.5, head_y=0.4, head_z=0.4, intensity=0.7),
            MotionAction("tilt_look_up_right", 2.2, head_x=0.5, head_y=0.4, head_z=-0.4, intensity=0.7),
            MotionAction("tilt_look_down_left", 2.2, head_x=-0.4, head_y=-0.4, head_z=0.4, intensity=0.6),
            MotionAction("tilt_look_down_right", 2.2, head_x=0.4, head_y=-0.4, head_z=-0.4, intensity=0.6),
        ])

        # === 16. Idle Holds (ท่าพักยาวๆ เบามาก) ===
        actions.extend([
            MotionAction("idle_hold_soft", 3.8, head_x=0.1, head_y=0.05, intensity=0.4),
            MotionAction("idle_hold_focus", 3.6, head_x=0.1, head_y=0.1, intensity=0.45),
        ])
        
        return actions

    async def start(self):
        """เริ่ม motion loop"""
        if self.motion_task and not self.motion_task.done():
            logger.warning("Motion loop กำลังทำงานอยู่แล้ว")
            return
        
        # รีโซลฟ์ชื่อพารามิเตอร์อีกครั้ง หลัง verify_connection เพื่อให้ตรงกับโมเดลจริง
        try:
            self._param_names = {
                # Angles
                "AngleX": self.vts.resolve_param_name("FaceAngleX", "ParamAngleX", "AngleX"),
                "AngleY": self.vts.resolve_param_name("FaceAngleY", "ParamAngleY", "AngleY"),
                "AngleZ": self.vts.resolve_param_name("FaceAngleZ", "ParamAngleZ", "AngleZ"),
                # Positions
                "PosX": self.vts.resolve_param_name("FacePositionX", "ParamPositionX", "PositionX", "ParamPosX", "PosX"),
                "PosY": self.vts.resolve_param_name("FacePositionY", "ParamPositionY", "PositionY", "ParamPosY", "PosY"),
                # Mouth/Eye
                "MouthSmile": self.vts.resolve_param_name("MouthSmile", "ParamMouthSmile", "Smile"),
                "EyeSmileL": self.vts.resolve_param_name("ParamEyeLSmile", "EyeSmileLeft", "ParamEyeSmileLeft"),
                "EyeSmileR": self.vts.resolve_param_name("ParamEyeRSmile", "EyeSmileRight", "ParamEyeSmileRight"),
                "EyeOpenL": self.vts.resolve_param_name("EyeOpenLeft", "ParamEyeOpenLeft", "EyeOpenL", "ParamEyeOpenL"),
                "EyeOpenR": self.vts.resolve_param_name("EyeOpenRight", "ParamEyeOpenRight", "EyeOpenR", "ParamEyeOpenR"),
            }
        except Exception:
            pass

        self.should_stop = False
        self.motion_task = asyncio.create_task(self._motion_loop())
        logger.info("🎬 Neuro Motion เริ่มทำงาน")
        # บังคับให้ยิ้มทันทีด้วย hotkey หากมี
        try:
            if self.vts._is_connected():
                ok = await self.vts.trigger_hotkey_by_name(["smile", "happy", "ยิ้ม"])  # สนับสนุนชื่อไทยด้วย
                if ok:
                    logger.info("😊 บังคับยิ้มผ่าน Hotkey แล้ว")
        except Exception:
            pass

    async def stop(self):
        """หยุด motion loop"""
        self.should_stop = True
        if self.motion_task:
            try:
                await asyncio.wait_for(self.motion_task, timeout=2.0)
            except:
                pass
            self.motion_task = None
        logger.info("⏹️ Motion loop หยุดแล้ว")

    def set_speaking(self, speaking: bool):
        self.is_speaking = speaking

    def set_generating(self, generating: bool):
        self.is_generating = generating

    async def _motion_loop(self):
        """
        Main motion loop - Neuro-sama Style
        ✨ สุ่มท่าทางใหม่ทุกครั้ง ไม่ซ้ำซาก
        """
        logger.info("🎭 Neuro Motion Loop เริ่มต้น")
        
        while not self.should_stop:
            try:
                if not self.vts._is_connected():
                    await asyncio.sleep(1.0)
                    continue
                
                dt = self.update_dt  # ~30 FPS
                self.breath_time += dt
                
        # === เลือกท่าทางใหม่ด้วยช่วงพัก ===
                if self.current_action is not None and self.action_progress >= 1.0:
                    self.current_action = None
                    self.action_progress = 0.0
                    self.next_action_time = time.time() + random.uniform(self.action_rest_min_sec, self.action_rest_max_sec)

                if self.current_action is None and time.time() >= self.next_action_time:
                    if random.random() < self.idle_hold_prob and self.idle_actions:
                        self.current_action = random.choice(self.idle_actions)
                        self.action_progress = 0.0
                        self.action_timer = time.time()
                    else:
                        self._pick_random_action()
                
                # === อัพเดทการเคลื่อนไหว ===
                await self._update_action(dt)
                
                # === Breathing + Blinking (ทำตลอด) ===
                await self._update_breathing()
                await self._update_blinking()
                await self._update_smile()

                # ส่งพารามิเตอร์ทุกเฟรม เพื่อให้การหายใจ/ยิ้มต่อเนื่องแม้ช่วงพักท่า
                await self._apply_parameters()
                
                await asyncio.sleep(dt)
                
            except Exception as e:
                logger.error(f"Motion error: {e}")
                await asyncio.sleep(0.5)
        
        logger.info("🛑 Motion loop หยุด")

    def _pick_random_action(self):
        """
        สุ่มเลือกท่าทางใหม่
        🎲 มีน้ำหนักตามสถานะ (speaking, generating, idle)
        """
        # กำหนดน้ำหนักตามสถานะ
        if self.is_speaking:
            # ตอนพูด: ชอบท่าที่มีพลังมากกว่า
            weights = [
                (a, a.intensity * 1.5) if a.intensity > 1.0 else (a, a.intensity * 0.5)
                for a in self.action_pool
            ]
        elif self.is_generating:
            # ตอนเจนเสียง: ชอบท่าคิด/idle
            weights = [
                (a, 2.0) if "thinking" in a.name or "idle" in a.name else (a, 0.5)
                for a in self.action_pool
            ]
        else:
            # ปกติ: สุ่มทุกท่า
            weights = [(a, 1.0) for a in self.action_pool]
        
        # สุ่มเลือก
        actions, probs = zip(*weights)
        total = sum(probs)
        normalized_probs = [p / total for p in probs]
        
        # หลีกเลี่ยงท่าที่ซ้ำกับล่าสุด
        for _ in range(10):
            candidate = random.choices(actions, weights=normalized_probs)[0]
            if not any(candidate.name == a.name for a in self._recent_actions):
                self.current_action = candidate
                break
        else:
            # หากสุ่มไม่ผ่านเงื่อนไข ให้เลือกตามเดิม
            self.current_action = random.choices(actions, weights=normalized_probs)[0]

        self.action_progress = 0.0
        self.action_timer = time.time()
        self._recent_actions.append(self.current_action)
        
        logger.debug(f"🎭 Action: {self.current_action.name} ({self.current_action.duration}s)")

    async def _update_action(self, dt: float):
        """
        อัพเดทท่าทางปัจจุบัน
        """
        if not self.current_action:
            return
        
        # คำนวณ progress (0.0 → 1.0)
        self.action_progress += dt / self.current_action.duration
        self.action_progress = min(self.action_progress, 1.0)
        
        # Easing function (ทำให้การเคลื่อนไหวนุ่มนวล)
        t = self.action_progress
        
        # Ease in-out cubic
        if t < 0.5:
            eased = 4 * t * t * t
        else:
            eased = 1 - pow(-2 * t + 2, 3) / 2
        
        # คำนวณ target position
        action = self.current_action
        intensity_multiplier = action.intensity * self.intensity
        
        target_head_x = action.head_x * eased * intensity_multiplier
        target_head_y = action.head_y * eased * intensity_multiplier
        target_head_z = action.head_z * eased * intensity_multiplier
        target_body_x = action.body_x * eased * intensity_multiplier
        target_body_y = action.body_y * eased * intensity_multiplier
        
        # เพิ่ม subtle noise (ลดลงเพื่อความนิ่ง)
        noise_factor = 0.01
        target_head_x += math.sin(self.breath_time * 3.7) * noise_factor
        target_head_y += math.cos(self.breath_time * 2.9) * noise_factor
        target_head_z += math.sin(self.breath_time * 4.1) * noise_factor
        
        # Smooth interpolation
        alpha = 1.0 - self.smoothing
        
        self.current_head_x += (target_head_x - self.current_head_x) * alpha
        self.current_head_y += (target_head_y - self.current_head_y) * alpha
        self.current_head_z += (target_head_z - self.current_head_z) * alpha
        self.current_body_x += (target_body_x - self.current_body_x) * alpha
        self.current_body_y += (target_body_y - self.current_body_y) * alpha
        
        # ส่งไปยัง VTS
        await self._apply_parameters()

    async def _apply_parameters(self):
        """ส่งค่าพารามิเตอร์ไปยัง VTS"""
        try:
            if not self.vts._is_connected():
                return
            # รวมค่า breathing เข้าไปใน FacePositionY เพื่อลดการส่งซ้ำ
            body_y_with_breath = self.current_body_y + (self.breath_value * 0.5)

            params = {
                self._param_names["AngleX"]: self.current_head_x * 30.0,
                self._param_names["AngleY"]: self.current_head_y * 30.0,
                self._param_names["AngleZ"]: self.current_head_z * 30.0,
                self._param_names["PosX"]: self.current_body_x * 10.0,
                self._param_names["PosY"]: body_y_with_breath * 5.0,
            }

            # รอยยิ้ม: ฐาน + ไมโครเวฟ + ramp
            micro = (math.sin(self.breath_time * 0.7) + math.sin(self.breath_time * 0.37 + 1.1)) * 0.05
            mouth_smile = max(0.0, min(1.0, self.smile_value + micro))
            eye_smile = max(0.0, min(1.0, 0.25 + mouth_smile * 0.25 + math.sin(self.breath_time * 0.5) * 0.06))

            params.update({
                self._param_names["MouthSmile"]: mouth_smile,
                self._param_names["EyeSmileL"]: eye_smile,
                self._param_names["EyeSmileR"]: eye_smile,
            })

            # ส่งแบบ batch เพียงครั้งเดียวในแต่ละ tick
            await self.vts.inject_parameters_bulk(params)
                
        except:
            pass

    async def _update_smile(self):
        """อัพเดทรอยยิ้มให้มีช่วงยิ้มกว้างขึ้นแบบค่อยๆ เพิ่ม/ลด"""
        dt = self.update_dt
        now = time.time()

        # ทริกเกอร์รอบใหม่เป็นช่วง ๆ โดยสุ่มระหว่าง 8–14 วินาที
        if now >= self.next_smile_time and now >= self.smile_hold_until:
            self.smile_target = self.smile_peak
            # ถือรอยยิ้มกว้างไว้ช่วงสั้น ๆ หลัง ramp ถึงเป้าหมาย
            self.smile_hold_until = 0.0  # จะตั้งหลังถึงเป้าหมาย
        
        # เคลื่อนค่าไปยังเป้าหมายแบบนุ่มนวล
        if self.smile_target > self.smile_value:
            self.smile_value += self.smile_speed_up * dt
            if self.smile_value >= self.smile_target:
                self.smile_value = self.smile_target
                # ถือไว้ 0.7–1.2 วินาที แล้วค่อยลดลง
                self.smile_hold_until = now + random.uniform(0.7, 1.2)
                self.smile_target = self.smile_base
                self.next_smile_time = now + random.uniform(8.0, 14.0)
        else:
            self.smile_value -= self.smile_speed_down * dt
            if self.smile_value < self.smile_base:
                self.smile_value = self.smile_base

    async def _update_breathing(self):
        """Breathing Animation"""
        try:
            if not self.vts._is_connected():
                return
            # คำนวณค่า breathing แล้วเก็บไว้ให้ _apply_parameters รวมไปด้วย
            self.breath_value = (math.sin(self.breath_time * self.breath_speed) + 1.0) * 0.5
            self.breath_value *= self.breath_intensity
            
        except:
            pass

    async def _update_blinking(self):
        """Blinking - ปรับความถี่ตามอารมณ์"""
        try:
            if not self.vts._is_connected():
                return
            
            now = time.time()
            
            # ปรับความถี่การกระพริบตามสถานะ
            if self.is_speaking or self.is_generating:
                blink_min = 1.5
                blink_max = 4.0
            else:
                blink_min = 2.0
                blink_max = 6.0
            
            blink_duration = 0.15
            next_blink = self.blink_timer + random.uniform(blink_min, blink_max)
            
            if now >= next_blink:
                # ปิดตาแบบ batch
                await self.vts.inject_parameters_bulk({
                    self._param_names["EyeOpenL"]: 0.0,
                    self._param_names["EyeOpenR"]: 0.0,
                })
                await asyncio.sleep(blink_duration)
                # เปิดตาแบบ batch
                await self.vts.inject_parameters_bulk({
                    self._param_names["EyeOpenL"]: 1.0,
                    self._param_names["EyeOpenR"]: 1.0,
                })
                
                self.blink_timer = time.time()
                
        except:
            pass

    async def trigger_emotion(self, emotion: str):
        """Trigger hotkey emotion"""
        try:
            if not self.vts._is_connected():
                return
            
            hotkey_map = {
                "happy": "happy_trigger",
                "sad": "sad_trigger",
                "angry": "angry_trigger",
                "surprised": "surprised_trigger",
                "thinking": "thinking_trigger"
            }
            
            hotkey = hotkey_map.get(emotion.lower())
            if hotkey:
                await self.vts.trigger_hotkey(hotkey)
                logger.info(f"💫 Emotion: {emotion}")
        except Exception as e:
            logger.error(f"Emotion error: {e}")


def create_motion_controller(vts_client, env_config: dict):
    """สร้าง Motion Controller"""
    config = {
        # เพิ่มค่าเริ่มต้นให้สมูทมากขึ้น เพื่อลดอาการวาป/สั่น
        "smoothing": env_config.get("VTS_MOVEMENT_SMOOTHING", "0.96"),
        "intensity": env_config.get("VTS_MOTION_INTENSITY", "1.0"),
        # รองรับการตั้งค่าเฟรมเรตจาก .env เพื่อลดภาระการส่งพารามิเตอร์
        "update_dt": env_config.get("VTS_UPDATE_DT", None),
        # ส่งค่าเกี่ยวกับการหายใจมาไว้ใน config ด้วย
        "VTS_BREATH_SPEED": env_config.get("VTS_BREATH_SPEED", "0.8"),
        "VTS_BREATH_INTENSITY": env_config.get("VTS_BREATH_INTENSITY", "0.3"),
        # คุมความถี่และความสมูทของการสุ่มท่า
        "action_duration_scale": env_config.get("VTS_ACTION_DURATION_SCALE", "1.15"),
        "action_rest_min_sec": env_config.get("VTS_ACTION_REST_MIN_SEC", "0.6"),
        "action_rest_max_sec": env_config.get("VTS_ACTION_REST_MAX_SEC", "1.2"),
        "idle_hold_prob": env_config.get("VTS_IDLE_HOLD_PROB", "0.35"),
    }
    # หากไม่ได้ตั้งค่า update_dt ให้ลบทิ้งเพื่อใช้ค่าเริ่มต้น 0.033
    if config["update_dt"] is None:
        del config["update_dt"]
    return MotionController(vts_client, config)