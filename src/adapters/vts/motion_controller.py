"""
VTS Motion Controller - Live & Smooth (Neuro-inspired)
- Smooth interpolation (cubic ease-in-out)
- Randomized non-looping actions with variable durations/rests
- Continuous gentle smile + eye-smile
- MouthOpen modulation while speaking (simple envelope)
- Robust to VTS reconnects (doesn't permanently stop)
"""

import asyncio
import random
import math
import time
import logging
import csv
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger(__name__)

@dataclass
class MotionAction:
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
        self.config = config or {}

        # Flags
        self.is_speaking = False
        self.is_generating = False
        self.motion_task: Optional[asyncio.Task] = None
        self.should_stop = False

        # Internal state
        self.current_head_x = 0.0
        self.current_head_y = 0.0
        self.current_head_z = 0.0
        self.current_body_x = 0.0
        self.current_body_y = 0.0
        self.current_mouth_open = 0.0

        # Mouth envelope (ลิปซิงค์รวมกับ motion ส่งครั้งเดียว)
        self._mouth_envelope: deque[float] = deque()
        self._mouth_sample_interval: float = 0.05
        self._mouth_next_time: float = time.time()
        # ระยะเวลาการเฟดปิดปากเมื่อหยุดพูด
        self._mouth_decay_sec: float = float(self.config.get("mouth_decay_sec", 0.18))

        # Timers/state
        self.breath_time = 0.0
        self.blink_timer = time.time() + random.uniform(0.5, 2.0)
        self.action_timer = time.time()
        self.next_action_time = time.time() + 0.5
        self.current_action: Optional[MotionAction] = None
        self.action_progress = 0.0
        self._recent_actions = deque(maxlen=4)

        # Configurable params (with tuned defaults for livelier motion)
        self.smoothing = float(config.get("smoothing", 0.92))
        self.base_dt = float(config.get("base_dt", 0.028))
        self.update_dt = float(config.get("update_dt", 0.028))
        self.intensity = float(config.get("intensity", 1.15))

        # Breathing
        self.breath_speed = float(config.get("VTS_BREATH_SPEED", 1.0))
        self.breath_intensity = float(config.get("VTS_BREATH_INTENSITY", 0.28))
        self.breath_value = 0.0

        # Action timing & randomness
        self.action_duration_scale = float(config.get("action_duration_scale", 1.10))
        self.action_rest_min_sec = float(config.get("action_rest_min_sec", 0.25))
        self.action_rest_max_sec = float(config.get("action_rest_max_sec", 0.65))
        self.idle_hold_prob = float(config.get("idle_hold_prob", 0.12))

        # Smile expression controls
        self.smile_base_min = float(config.get("SMILE_BASE_MIN", 0.86))
        self.smile_var_amp = float(config.get("SMILE_VAR_AMP", 0.015))
        self.smile_pulse_max = float(config.get("SMILE_PULSE_MAX", 0.25))

        # Random intensity ranges (per axis)
        self.rand_int_x_min = float(config.get("RAND_INT_X_MIN", 0.85))
        self.rand_int_x_max = float(config.get("RAND_INT_X_MAX", 1.25))
        self.rand_int_y_min = float(config.get("RAND_INT_Y_MIN", 0.85))
        self.rand_int_y_max = float(config.get("RAND_INT_Y_MAX", 1.25))
        self.rand_int_z_min = float(config.get("RAND_INT_Z_MIN", 0.85))
        self.rand_int_z_max = float(config.get("RAND_INT_Z_MAX", 1.25))
        self.rand_int_body_min = float(config.get("RAND_INT_BODY_MIN", 0.90))
        self.rand_int_body_max = float(config.get("RAND_INT_BODY_MAX", 1.35))

        # Random idle sway frequency ranges
        self.idle_freq_x_min = float(config.get("IDLE_FREQ_X_MIN", 0.55))
        self.idle_freq_x_max = float(config.get("IDLE_FREQ_X_MAX", 0.85))
        self.idle_freq_y_min = float(config.get("IDLE_FREQ_Y_MIN", 0.75))
        self.idle_freq_y_max = float(config.get("IDLE_FREQ_Y_MAX", 1.10))
        self.idle_freq_z_min = float(config.get("IDLE_FREQ_Z_MIN", 0.35))
        self.idle_freq_z_max = float(config.get("IDLE_FREQ_Z_MAX", 0.75))
        self._idle_freq_x = random.uniform(self.idle_freq_x_min, self.idle_freq_x_max)
        self._idle_freq_y = random.uniform(self.idle_freq_y_min, self.idle_freq_y_max)
        self._idle_freq_z = random.uniform(self.idle_freq_z_min, self.idle_freq_z_max)
        self._next_idle_freq_reset = time.time() + random.uniform(8.0, 18.0)

        # Enhanced stall recovery and continuous motion system
        self.stall_recovery_sec = float(config.get("MOTION_STALL_RECOVERY_SEC", 2.0))  # Faster recovery
        self._axis_mult = {"x": 1.0, "y": 1.0, "z": 1.0, "bx": 1.0, "by": 1.0}
        
        # Motion state tracking for seamless transitions
        self._motion_state = {
            "last_update": time.time(),
            "velocity_x": 0.0,
            "velocity_y": 0.0, 
            "velocity_z": 0.0,
            "target_x": 0.0,
            "target_y": 0.0,
            "target_z": 0.0,
            "transition_progress": 0.0,
            "is_transitioning": False
        }
        
        # Emergency motion system to prevent complete stops
        self._emergency_motion = {
            "enabled": True,
            "min_movement_threshold": 0.001,  # Minimum movement to detect stalls
            "stall_counter": 0,
            "max_stall_frames": 10,  # Max frames without movement before emergency
            "backup_actions": []  # Emergency actions when main system fails
        }
        
        # Continuous motion guarantees
        self._motion_continuity = {
            "last_significant_movement": time.time(),
            "movement_history": deque(maxlen=30),  # Track recent movements
            "min_idle_movement": 0.005,  # Minimum movement during idle
            "seamless_transition_time": 0.3  # Time for seamless transitions
        }

        # Periodic motion refresh
        self.motion_refresh_sec = float(config.get("MOTION_REFRESH_SEC", 25.0))  # More frequent refresh
        self._next_motion_refresh = time.time() + self.motion_refresh_sec

        # Mouth parameters for lip-sync-ish movement when speaking
        self.mouth_base = float(config.get("mouth_base", 0.06))
        self.mouth_peak = float(config.get("mouth_peak", 0.65))
        self.mouth_freq = float(config.get("mouth_freq", 8.0))

        # Smoothness Guard thresholds & state
        self.smooth_guard_enabled = bool(str(config.get("SMOOTHNESS_GUARD", "1")).lower() in ("1","true","yes"))
        self.max_delta_head = float(config.get("SMOOTH_MAX_DELTA_HEAD", 0.08))
        self.max_delta_body = float(config.get("SMOOTH_MAX_DELTA_BODY", 0.12))
        self.max_delta_mouth = float(config.get("SMOOTH_MAX_DELTA_MOUTH", 0.55))
        self._prev_state = {
            "head_x": 0.0,
            "head_y": 0.0,
            "head_z": 0.0,
            "body_x": 0.0,
            "body_y": 0.0,
            "mouth": 0.0,
        }

        # CSV logger for motion parameters
        self._csv_log_every_sec = float(config.get("MOTION_LOG_INTERVAL_SEC", 0.2))
        self._csv_next_log_time = time.time() + self._csv_log_every_sec
        raw_path = config.get("MOTION_LOG_FILE", str(Path("logs") / "motion_params.csv"))
        try:
            self._csv_path = Path(raw_path)
            self._csv_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            self._csv_path = Path("motion_params.csv")

        # Create action pool (keeps many variants)
        self.action_pool = self._create_action_pool()
        for a in self.action_pool:
            a.duration = max(0.25, a.duration * self.action_duration_scale)
        self.idle_actions = [a for a in self.action_pool if "idle" in a.name or a.name.startswith("idle_")]
        
        # Initialize emergency backup actions
        self._emergency_motion["backup_actions"] = self._create_emergency_actions()

        # Mood state (ปรับน้ำหนัก action และรอยยิ้มตามอารมณ์)
        self._mood: str = "happy"  # default: ถ้าไม่มีสถานการณ์ให้ยิ้มกว้างที่สุด
        self._mood_energy: float = 0.6

        logger.info(f"✅ Neuro Motion: {len(self.action_pool)} actions, intensity={self.intensity}, duration_scale={self.action_duration_scale}")

    def _create_action_pool(self) -> List[MotionAction]:
        actions: List[MotionAction] = [
            MotionAction("idle_center", 3.0, head_x=0.0, head_y=0.0, head_z=0.0, intensity=0.4),
            MotionAction("idle_slight_right", 2.6, head_x=0.22, head_y=0.0, head_z=0.08, intensity=0.45),
            MotionAction("idle_slight_left", 2.6, head_x=-0.22, head_y=0.0, head_z=-0.08, intensity=0.45),
            MotionAction("look_right", 1.6, head_x=0.95, head_y=0.0, intensity=0.9),
            MotionAction("look_left", 1.6, head_x=-0.95, head_y=0.0, intensity=0.9),
            # ลดมุมเอียงให้พอดี (≈15° เมื่อคูณสเกล 30)
            MotionAction("tilt_right", 1.4, head_z=0.5, intensity=0.8),
            MotionAction("tilt_left", 1.4, head_z=-0.5, intensity=0.8),
            # remove vertical nod; keep thinking without vertical component
            MotionAction("thinking", 2.2, head_x=0.35, head_y=0.0, head_z=0.2, intensity=0.7),
            MotionAction("playful_wiggle", 1.2, head_z=0.45, body_x=0.18, intensity=1.05),
            MotionAction("sway_x_soft", 2.4, head_x=0.6, intensity=0.65),
            MotionAction("pan_left_slow", 2.6, head_x=-0.6, head_y=0.0, intensity=0.6),
            MotionAction("pan_right_slow", 2.6, head_x=0.6, head_y=0.0, intensity=0.6),
            MotionAction("peek_right", 1.4, head_x=0.75, body_x=0.3, intensity=1.0),
            MotionAction("peek_left", 1.4, head_x=-0.75, body_x=-0.3, intensity=1.0),
            # remove bounce (vertical) and figure8 (has vertical)
        ]
        return actions

    def _create_emergency_actions(self) -> List[MotionAction]:
        """Create minimal emergency actions to prevent complete motion stops"""
        emergency_actions = [
            MotionAction("emergency_micro_sway", 0.8, head_x=0.02, head_z=0.015, intensity=0.3),
            MotionAction("emergency_gentle_turn", 1.2, head_x=0.03, head_y=0.02, intensity=0.4),
            MotionAction("emergency_subtle_tilt", 0.6, head_z=0.025, body_x=0.01, intensity=0.35),
            MotionAction("emergency_breath_sync", 1.0, head_x=0.015, body_x=0.008, intensity=0.25),
            MotionAction("emergency_minimal_nod", 0.7, head_x=0.02, intensity=0.3),
        ]
        return emergency_actions

    def _track_motion_continuity(self, dt: float):
        """Track motion continuity and detect potential stalls"""
        current_pos = (self.current_head_x, self.current_head_y, self.current_head_z)
        
        # Calculate movement magnitude
        if self._motion_continuity["movement_history"]:
            last_pos = self._motion_continuity["movement_history"][-1]
            movement = sum(abs(a - b) for a, b in zip(current_pos, last_pos))
        else:
            movement = 0.0
        
        # Add to movement history
        self._motion_continuity["movement_history"].append(current_pos)
        
        # Check for significant movement
        if movement > self._emergency_motion["min_movement_threshold"]:
            self._motion_continuity["last_significant_movement"] = time.time()
            self._emergency_motion["stall_counter"] = 0
        else:
            self._emergency_motion["stall_counter"] += 1
        
        # Emergency motion trigger
        if (self._emergency_motion["stall_counter"] >= self._emergency_motion["max_stall_frames"] and 
            self._emergency_motion["enabled"]):
            self._trigger_emergency_motion()
        
        return movement

    def _trigger_emergency_motion(self):
        """Trigger emergency motion to prevent complete stops"""
        if self._emergency_motion["backup_actions"] and not self.current_action:
            emergency_action = random.choice(self._emergency_motion["backup_actions"])
            # Create a copy with randomized parameters
            self.current_action = MotionAction(
                name=f"{emergency_action.name}_emergency",
                duration=emergency_action.duration * random.uniform(0.8, 1.3),
                head_x=emergency_action.head_x * random.uniform(0.7, 1.4),
                head_y=emergency_action.head_y * random.uniform(0.7, 1.4),
                head_z=emergency_action.head_z * random.uniform(0.7, 1.4),
                body_x=emergency_action.body_x * random.uniform(0.7, 1.4),
                body_y=emergency_action.body_y * random.uniform(0.7, 1.4),
                intensity=emergency_action.intensity * random.uniform(0.8, 1.2)
            )
            self.action_progress = 0.0
            self.action_timer = time.time()
            self._emergency_motion["stall_counter"] = 0
            logger.warning(f"🚨 Emergency motion triggered: {self.current_action.name}")

    def _ensure_minimum_idle_motion(self, dt: float):
        """Ensure minimum motion during idle periods"""
        if not self.current_action:
            # Add subtle continuous motion even during idle
            time_factor = time.time() * 0.3
            micro_x = math.sin(time_factor * 1.7) * self._motion_continuity["min_idle_movement"]
            micro_z = math.cos(time_factor * 2.3) * self._motion_continuity["min_idle_movement"] * 0.7
            
            # Apply micro-motion with smooth interpolation
            alpha = min(1.0, dt * 3.0)  # Gentle application
            self.current_head_x += micro_x * alpha
            self.current_head_z += micro_z * alpha

    async def start(self):
        if self.motion_task and not self.motion_task.done():
            logger.warning("Motion loop already running")
            return
        self.should_stop = False
        self.motion_task = asyncio.create_task(self._motion_loop())
        logger.info("🎬 Neuro Motion started")

    async def stop(self):
        self.should_stop = True
        if self.motion_task:
            try:
                await asyncio.wait_for(self.motion_task, timeout=2.0)
            except Exception:
                pass
            self.motion_task = None
        logger.info("⏹️ Motion loop stopped")

    def set_speaking(self, speaking: bool):
        if speaking and not self.is_speaking:
            self.speaking_since = time.time()
        self.is_speaking = speaking

    def set_generating(self, generating: bool):
        self.is_generating = generating

    def set_mouth_envelope(self, series: List[float], interval_sec: float):
        try:
            self._mouth_envelope.clear()
            for v in series:
                self._mouth_envelope.append(float(max(0.0, min(1.0, v))))
            self._mouth_sample_interval = max(0.02, float(interval_sec))
            self._mouth_next_time = time.time()
            self.set_speaking(True)
            logger.info(f"🎤 Mouth envelope loaded: {len(self._mouth_envelope)} samples @ {self._mouth_sample_interval:.3f}s")
        except Exception as e:
            logger.debug(f"set_mouth_envelope error: {e}")

    def _pick_random_action(self):
        """Enhanced action selection with comprehensive emotion and context awareness"""
        mood = (self._mood or "happy").lower()
        mood_details = getattr(self, '_mood_details', {})
        
        def comprehensive_mood_weight(a: MotionAction) -> float:
            base = a.intensity
            
            # State-based adjustments
            if self.is_speaking:
                base = max(0.5, a.intensity * 1.2)
                # Favor subtle movements while speaking
                if "idle" in a.name or "sway" in a.name:
                    base *= 1.3
            elif self.is_generating:
                base = 2.0 if "thinking" in a.name else 0.6
            
            # Primary mood adjustments
            if mood == "happy":
                if "idle" in a.name or "peek" in a.name or "sway" in a.name:
                    base *= 1.4
                if "pan" in a.name:
                    base *= 1.2
                if "playful" in a.name:
                    base *= 1.3
            elif mood == "pleased":
                # More expressive movements for compliments
                if "peek" in a.name or "sway" in a.name:
                    base *= 1.5
                if "tilt" in a.name:
                    base *= 1.2
            elif mood == "friendly":
                # Welcoming, open movements
                if "look" in a.name or "pan" in a.name:
                    base *= 1.3
                if "idle" in a.name:
                    base *= 1.2
            elif mood == "curious":
                # Inquisitive head movements
                if "look" in a.name or "tilt" in a.name:
                    base *= 1.4
                if "peek" in a.name:
                    base *= 1.3
            elif mood == "sad":
                if "pan_" in a.name or "idle" in a.name:
                    base *= 1.35
                if "playful" in a.name or "peek" in a.name:
                    base *= 0.5
            elif mood == "angry":
                if "tilt" in a.name or "look" in a.name:
                    base *= 1.4
                if "idle" in a.name:
                    base *= 0.7
                if "sway" in a.name:
                    base *= 0.6
            elif mood == "surprised":
                if "look" in a.name or "peek" in a.name:
                    base *= 1.5
                if "tilt" in a.name:
                    base *= 1.2
            elif mood == "thinking":
                if "thinking" in a.name:
                    base *= 2.0
                elif "idle" in a.name:
                    base *= 1.1
                else:
                    base *= 0.8
            
            # Context-based adjustments
            if mood_details.get("is_question"):
                if "look" in a.name or "tilt" in a.name:
                    base *= 1.2
            
            if mood_details.get("is_greeting"):
                if "pan" in a.name or "sway" in a.name:
                    base *= 1.3
            
            # Energy level adjustments
            energy = getattr(self, '_mood_energy', 0.6)
            if energy > 0.7:
                # High energy - favor more dynamic movements
                if "sway" in a.name or "pan" in a.name:
                    base *= 1.2
            elif energy < 0.4:
                # Low energy - favor subtle movements
                if "idle" in a.name:
                    base *= 1.3
                if "sway" in a.name or "pan" in a.name:
                    base *= 0.8
            
            return max(0.1, base)

        # Calculate weights for all actions
        weights = [(a, comprehensive_mood_weight(a)) for a in self.action_pool]
        actions, probs = zip(*weights)
        total = sum(probs)
        normalized = [p / total for p in probs]

        # Try to avoid recent actions for variety
        for _ in range(10):
            candidate = random.choices(actions, weights=normalized)[0]
            if not any(candidate.name == r.name for r in self._recent_actions):
                chosen = candidate
                break
        else:
            # If all recent, pick the best weighted option
            chosen = random.choices(actions, weights=normalized)[0]

        # Apply duration randomization with mood influence
        duration_variance = 0.15 if mood in ["thinking", "sad"] else 0.25
        dur_min = 1.0 - duration_variance
        dur_max = 1.0 + duration_variance
        dur = max(0.25, chosen.duration * random.uniform(dur_min, dur_max))
        
        chosen = MotionAction(chosen.name, dur, chosen.head_x, chosen.head_y, chosen.head_z, 
                             chosen.body_x, chosen.body_y, chosen.intensity)
        
        # Enhanced axis-specific random intensity multipliers with mood influence
        energy_mult = 0.8 + (getattr(self, '_mood_energy', 0.6) * 0.4)  # 0.8 to 1.2 range
        
        self._axis_mult = {
            "x": random.uniform(self.rand_int_x_min, self.rand_int_x_max) * energy_mult if abs(chosen.head_x) > 1e-3 else 1.0,
            "y": random.uniform(self.rand_int_y_min, self.rand_int_y_max) * energy_mult if abs(chosen.head_y) > 1e-3 else 1.0,
            "z": random.uniform(self.rand_int_z_min, self.rand_int_z_max) * energy_mult if abs(chosen.head_z) > 1e-3 else 1.0,
            "bx": random.uniform(self.rand_int_body_min, self.rand_int_body_max) * energy_mult if abs(chosen.body_x) > 1e-3 else 1.0,
            "by": random.uniform(self.rand_int_body_min, self.rand_int_body_max) * energy_mult if abs(chosen.body_y) > 1e-3 else 1.0,
        }
        self.current_action = chosen
        self.action_progress = 0.0
        self.action_timer = time.time()

    def set_mood(self, mood: str, energy: Optional[float] = None, mood_details: Optional[dict] = None):
        """Set mood and adjust motion parameters accordingly with comprehensive emotion support"""
        try:
            m = (mood or "happy").lower()
            self._mood = m
            if energy is not None:
                self._mood_energy = float(max(0.0, min(1.0, energy)))
            self._mood_details = mood_details or {}
            
            # Enhanced smile adjustment based on mood and context
            if m == "happy":
                # Default to wide smile as specified in requirements
                base_smile = 0.95 if self._mood_details.get("context") == "friendly" else 0.95
                self.smile_base_min = base_smile
            elif m == "pleased":
                self.smile_base_min = 0.98  # Even wider smile for compliments
            elif m == "curious":
                self.smile_base_min = 0.88  # Slight smile for questions
            elif m == "friendly":
                self.smile_base_min = 0.92  # Warm smile for greetings
            elif m == "surprised":
                self.smile_base_min = 0.90
            elif m == "neutral":
                self.smile_base_min = 0.86
            elif m == "sad":
                self.smile_base_min = 0.25
            elif m == "angry":
                self.smile_base_min = 0.20
            elif m == "thinking":
                self.smile_base_min = 0.80
            else:
                # Default to happy with wide smile as per requirements
                self.smile_base_min = 0.92
            
            # Enhanced action timing based on energy and context
            e = self._mood_energy
            base_rest_min = 0.35
            base_rest_max = 0.90
            
            # Adjust for energy level
            if e > 0.8:
                energy_mult_min = 0.7
                energy_mult_max = 0.8
            elif e > 0.7:
                energy_mult_min = 0.8
                energy_mult_max = 0.9
            elif e < 0.3:
                energy_mult_min = 1.4
                energy_mult_max = 1.5
            elif e < 0.4:
                energy_mult_min = 1.2
                energy_mult_max = 1.3
            else:
                energy_mult_min = 1.0
                energy_mult_max = 1.0
            
            # Adjust for mood-specific timing
            if m == "surprised":
                energy_mult_min *= 0.8  # Faster reactions
                energy_mult_max *= 0.9
            elif m == "thinking":
                energy_mult_min *= 1.2  # Slower, more contemplative
                energy_mult_max *= 1.3
            elif m == "angry":
                energy_mult_min *= 0.9  # More agitated movement
                energy_mult_max *= 0.95
            
            self.action_rest_min_sec = max(0.25, base_rest_min * energy_mult_min)
            self.action_rest_max_sec = max(self.action_rest_min_sec + 0.35, base_rest_max * energy_mult_max)
            
            # Adjust movement intensity based on context
            if self._mood_details.get("is_question"):
                self._context_intensity_mult = 1.1  # Slightly more expressive for questions
            elif self._mood_details.get("is_greeting"):
                self._context_intensity_mult = 1.2  # More welcoming movements
            else:
                self._context_intensity_mult = 1.0
            
            logger.info(f"🎚️ Mood set: {self._mood} (energy={self._mood_energy:.2f}) smile_base={self.smile_base_min:.2f}")
            if self._mood_details:
                context_info = f"context: {self._mood_details.get('context', 'neutral')}"
                if self._mood_details.get('is_question'):
                    context_info += ", question"
                if self._mood_details.get('is_greeting'):
                    context_info += ", greeting"
                logger.info(f"   Context: {context_info}")
            logger.info(f"   Rest timing: {self.action_rest_min_sec:.2f}-{self.action_rest_max_sec:.2f}s")
        except Exception:
            pass

    def _ease_cubic(self, t: float) -> float:
        t = max(0.0, min(1.0, t))
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 3) / 2

    def _ease_quintic(self, t: float) -> float:
        """Quintic ease-in-out for ultra-smooth motion (more natural than cubic)"""
        if t < 0.5:
            return 16 * t * t * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 5) / 2

    def _ease_elastic(self, t: float, amplitude: float = 0.1) -> float:
        """Subtle elastic easing for more human-like motion with micro-bounces"""
        if t == 0 or t == 1:
            return t
        
        c4 = (2 * math.pi) / 3
        if t < 0.5:
            return -(pow(2, 20 * t - 10) * math.sin((20 * t - 11.125) * c4)) / 2 * amplitude + t
        else:
            return (pow(2, -20 * t + 10) * math.sin((20 * t - 11.125) * c4)) / 2 * amplitude + t

    def _apply_advanced_smoothing(self, current: float, target: float, dt: float, 
                                 smoothing_factor: float = None, motion_type: str = "normal") -> float:
        """Advanced smoothing with motion-type-aware interpolation"""
        if smoothing_factor is None:
            smoothing_factor = self.smoothing
        
        # Calculate base alpha
        alpha = 1.0 - pow(smoothing_factor, dt / self.base_dt)
        
        # Adjust alpha based on motion type and distance
        distance = abs(target - current)
        
        if motion_type == "head":
            # Head movements should be more responsive but still smooth
            if distance > 0.1:  # Large movements
                alpha *= 1.2  # Faster response
            elif distance < 0.01:  # Micro movements
                alpha *= 0.7  # Slower, more stable
        elif motion_type == "body":
            # Body movements should be more stable
            alpha *= 0.85
        elif motion_type == "mouth":
            # Mouth movements need to be responsive for lip-sync
            if distance > 0.2:
                alpha *= 1.5  # Very responsive for speech
            else:
                alpha *= 1.1
        
        # Apply velocity-based damping to prevent overshooting
        if hasattr(self, '_motion_state'):
            velocity_key = f"velocity_{motion_type}" if motion_type in ["x", "y", "z"] else "velocity_x"
            if velocity_key in self._motion_state:
                velocity = self._motion_state[velocity_key]
                # Reduce alpha if velocity is high to prevent overshooting
                velocity_damping = max(0.3, 1.0 - abs(velocity) * 10)
                alpha *= velocity_damping
        
        # Clamp alpha to reasonable bounds
        alpha = max(0.01, min(0.95, alpha))
        
        return current + (target - current) * alpha

    async def _motion_loop(self):
        logger.info("🎭 Neuro Motion Loop started")
        last_time = time.time()
        smile_phase = random.random() * 10.0

        while not self.should_stop:
            try:
                now = time.time()
                dt = now - last_time
                if dt <= 0:
                    dt = self.update_dt
                last_time = now

                if not hasattr(self.vts, "_is_connected") or not self.vts._is_connected():
                    await asyncio.sleep(0.5)
                    continue

                self.breath_time += dt

                # Randomize idle sway frequencies periodically
                if time.time() >= self._next_idle_freq_reset:
                    self._idle_freq_x = random.uniform(self.idle_freq_x_min, self.idle_freq_x_max)
                    self._idle_freq_y = random.uniform(self.idle_freq_y_min, self.idle_freq_y_max)
                    self._idle_freq_z = random.uniform(self.idle_freq_z_min, self.idle_freq_z_max)
                    self._next_idle_freq_reset = time.time() + random.uniform(8.0, 18.0)
                    logger.info(f"🔄 Idle freq reset: x={self._idle_freq_x:.2f}, y={self._idle_freq_y:.2f}, z={self._idle_freq_z:.2f}")

                if not self.current_action and time.time() >= self.next_action_time:
                    if random.random() < self.idle_hold_prob and self.idle_actions:
                        self.current_action = random.choice(self.idle_actions)
                        self.current_action.duration = max(0.4, self.current_action.duration * random.uniform(0.9, 1.25))
                        self.action_progress = 0.0
                        self.action_timer = time.time()
                        self._recent_actions.append(self.current_action)
                    else:
                        self._pick_random_action()

                # Enhanced stall recovery with motion continuity tracking
                movement_magnitude = self._track_motion_continuity(dt)
                
                # Ensure minimum idle motion even when no action is active
                self._ensure_minimum_idle_motion(dt)
                
                # Stall recovery: if idle longer than expected, force a new action
                if (not self.current_action) and (time.time() > self.next_action_time + self.stall_recovery_sec):
                    logger.warning("⚠️ Motion stall detected; forcing new action")
                    self._pick_random_action()
                
                # Additional emergency check for complete motion stops
                time_since_movement = time.time() - self._motion_continuity["last_significant_movement"]
                if time_since_movement > (self.stall_recovery_sec * 1.5):
                    logger.warning(f"🚨 Extended motion stall detected ({time_since_movement:.1f}s)")
                    self._trigger_emergency_motion()

                if self.current_action:
                    self.action_progress += dt / max(0.001, self.current_action.duration)
                    finished = self.action_progress >= 1.0
                    t = self._ease_cubic(self.action_progress)
                    a = self.current_action
                    # Apply context-based intensity multiplier if available
                    context_mult = getattr(self, '_context_intensity_mult', 1.0)
                    intensity_mult = a.intensity * self.intensity * context_mult

                    target_head_x = a.head_x * self._axis_mult.get("x", 1.0) * t * intensity_mult
                    target_head_y = a.head_y * self._axis_mult.get("y", 1.0) * t * intensity_mult
                    target_head_z = a.head_z * self._axis_mult.get("z", 1.0) * t * intensity_mult
                    target_body_x = a.body_x * self._axis_mult.get("bx", 1.0) * t * intensity_mult
                    target_body_y = a.body_y * self._axis_mult.get("by", 1.0) * t * intensity_mult

                    # micro-noise to avoid static posture (remove vertical y noise)
                    noise_strength = 0.022 * (1.0 if not self.is_speaking else 0.010)
                    target_head_x += math.sin(self.breath_time * 3.2 + random.uniform(-0.2,0.2)) * noise_strength
                    target_head_z += math.sin(self.breath_time * 4.0 + random.uniform(-0.2,0.2)) * noise_strength

                    # Use advanced easing for more natural motion
                    eased_t = self._ease_quintic(t) if a.intensity > 0.7 else self._ease_cubic(t)
                    
                    # Calculate velocity for smooth transitions
                    prev_head_x = self.current_head_x
                    prev_head_y = self.current_head_y
                    prev_head_z = self.current_head_z
                    
                    # Apply advanced smoothing with motion-type awareness
                    self.current_head_x = self._apply_advanced_smoothing(
                        self.current_head_x, target_head_x, dt, motion_type="head"
                    )
                    self.current_head_y = self._apply_advanced_smoothing(
                        self.current_head_y, target_head_y, dt, motion_type="head"
                    )
                    self.current_head_z = self._apply_advanced_smoothing(
                        self.current_head_z, target_head_z, dt, motion_type="head"
                    )
                    self.current_body_x = self._apply_advanced_smoothing(
                        self.current_body_x, target_body_x, dt, motion_type="body"
                    )
                    self.current_body_y = self._apply_advanced_smoothing(
                        self.current_body_y, target_body_y, dt, motion_type="body"
                    )
                    
                    # Update velocity tracking for motion state
                    if dt > 0:
                        self._motion_state["velocity_x"] = (self.current_head_x - prev_head_x) / dt
                        self._motion_state["velocity_y"] = (self.current_head_y - prev_head_y) / dt
                        self._motion_state["velocity_z"] = (self.current_head_z - prev_head_z) / dt

                    if finished:
                        self.current_action = None
                        self.action_progress = 0.0
                        self.next_action_time = time.time() + random.uniform(self.action_rest_min_sec, self.action_rest_max_sec)

                else:
                    # Enhanced idle sway with natural variation and no vertical y component
                    base_sway_x = math.sin(self.breath_time * self._idle_freq_x) * 0.035
                    base_sway_z = math.cos(self.breath_time * self._idle_freq_z) * 0.03
                    
                    # Add subtle secondary motion layers for more natural idle
                    secondary_x = math.sin(self.breath_time * self._idle_freq_x * 0.7 + 1.2) * 0.015
                    secondary_z = math.cos(self.breath_time * self._idle_freq_z * 1.3 + 0.8) * 0.012
                    
                    # Combine primary and secondary motions
                    target_sway_x = base_sway_x + secondary_x
                    target_sway_z = base_sway_z + secondary_z
                    
                    # Apply advanced smoothing for natural idle motion
                    self.current_head_x = self._apply_advanced_smoothing(
                        self.current_head_x, target_sway_x, dt, motion_type="head"
                    )
                    # Keep head_y stable (no random up-down movement)
                    self.current_head_z = self._apply_advanced_smoothing(
                        self.current_head_z, target_sway_z, dt, motion_type="head"
                    )

                self.breath_value = (math.sin(self.breath_time * self.breath_speed) + 1.0) * 0.5 * self.breath_intensity

                if time.time() >= self.blink_timer:
                    asyncio.create_task(self._do_blink())
                    self.blink_timer = time.time() + random.uniform(2.0, 6.0)

                # ยิ้มคงที่และชัดเจน พร้อมสุ่มน้อยลง (เพิ่ม ~20–30%)
                smile_base = self.smile_base_min
                smile_var = (math.sin(smile_phase * 0.7) + math.sin(smile_phase * 0.37 + 1.1)) * self.smile_var_amp
                # trigger pulse เป็นครั้งคราวและไม่ถี่
                if not hasattr(self, "_smile_pulse_until"):
                    self._smile_pulse_until = 0.0
                    self._smile_pulse_phase = 0.0
                if time.time() > self._smile_pulse_until and random.random() < 0.06:
                    dur = random.uniform(1.2, 2.4)
                    self._smile_pulse_until = time.time() + dur
                    self._smile_pulse_phase = 0.0
                pulse_add = 0.0
                if time.time() < self._smile_pulse_until:
                    # ease-in-out pulse สูงสุด ~0.5
                    self._smile_pulse_phase += dt
                    pt = max(0.0, min(1.0, self._smile_pulse_phase / (self._smile_pulse_until - (self._smile_pulse_until - self._smile_pulse_phase))))
                    if pt < 0.5:
                        e = 4 * pt * pt * pt
                    else:
                        e = 1 - pow(-2 * pt + 2, 3) / 2
                    pulse_add = min(self.smile_pulse_max, self.smile_pulse_max * e)
                mouth_smile = max(self.smile_base_min, min(1.0, smile_base + smile_var + pulse_add))
                eye_smile = max(0.0, min(1.0, 0.25 + math.sin(self.breath_time * 0.5) * 0.05))

                if self.is_speaking:
                    # ใช้ envelope เท่านั้น; เมื่อหมด envelope ให้หยุดพูดและไม่ใช้ oscillator
                    if self._mouth_envelope and time.time() >= self._mouth_next_time:
                        mouth_open_target = float(self._mouth_envelope.popleft())
                        self._mouth_next_time = time.time() + self._mouth_sample_interval
                        if not self._mouth_envelope:
                            try:
                                self.set_speaking(False)
                            except Exception:
                                pass
                    else:
                        if not self._mouth_envelope:
                            try:
                                self.set_speaking(False)
                            except Exception:
                                pass
                        mouth_open_target = self.current_mouth_open
                else:
                    # ไม่พูด: ปิดปากลงแบบนุ่มนวล (ไม่มีการขยับเกินคำพูด)
                    mouth_open_target = 0.0

                # Apply advanced smoothing for mouth movement (lip-sync accuracy)
                self.current_mouth_open = self._apply_advanced_smoothing(
                    self.current_mouth_open, mouth_open_target, dt, motion_type="mouth"
                )

                # Smoothness guard: clamp sudden deltas to prevent jerk/jitter
                if self.smooth_guard_enabled:
                    dt_scale = dt / max(1e-3, self.update_dt)
                    max_h = self.max_delta_head * dt_scale
                    max_b = self.max_delta_body * dt_scale
                    max_m = self.max_delta_mouth * dt_scale
                    self.current_head_x = max(self._prev_state["head_x"] - max_h, min(self._prev_state["head_x"] + max_h, self.current_head_x))
                    self.current_head_y = max(self._prev_state["head_y"] - max_h, min(self._prev_state["head_y"] + max_h, self.current_head_y))
                    self.current_head_z = max(self._prev_state["head_z"] - max_h, min(self._prev_state["head_z"] + max_h, self.current_head_z))
                    self.current_body_x = max(self._prev_state["body_x"] - max_b, min(self._prev_state["body_x"] + max_b, self.current_body_x))
                    self.current_body_y = max(self._prev_state["body_y"] - max_b, min(self._prev_state["body_y"] + max_b, self.current_body_y))
                    self.current_mouth_open = max(self._prev_state["mouth"] - max_m, min(self._prev_state["mouth"] + max_m, self.current_mouth_open))

                # จำกัดมุมเอียงหัวให้อยู่ในช่วง ~15°
                cz = max(-0.5, min(0.5, self.current_head_z))
                # ห้ามขยับขึ้นลง: ตัดการส่ง FacePositionY ออก
                params = {
                    "FaceAngleX": float(self.current_head_x * 30.0),
                    "FaceAngleY": float(self.current_head_y * 30.0),
                    "FaceAngleZ": float(cz * 30.0),
                    "FacePositionX": float(self.current_body_x * 8.0),
                    # ไม่ส่ง FacePositionY ตามข้อกำหนด
                    "MouthSmile": float(mouth_smile),
                    "ParamEyeLSmile": float(eye_smile),
                    "ParamEyeRSmile": float(eye_smile),
                }
                # รวม MouthOpen กับ motion เสมอ (เพราะลิปซิงค์ถูกส่งผ่าน envelope มาที่ motion แล้ว)
                params["MouthOpen"] = float(max(0.0, min(1.0, self.current_mouth_open)))
                # เผื่อบางโมเดลใช้ชื่อพารามิเตอร์อื่นของ smile
                try:
                    params["ParamMouthSmile"] = params["MouthSmile"]
                except Exception:
                    pass

                try:
                    await self.vts.inject_parameters_bulk(params)
                except Exception as e:
                    logger.debug(f"VTS inject error (ignored): {e}")

                # CSV logging of motion params
                if time.time() >= self._csv_next_log_time:
                    try:
                        with self._csv_path.open("a", newline="") as f:
                            w = csv.writer(f)
                            w.writerow([
                                time.time(),
                                round(self.current_head_x,5), round(self.current_head_y,5), round(self.current_head_z,5),
                                round(self.current_body_x,5), round(self.current_body_y,5),
                                round(self.current_mouth_open,5),
                                round(mouth_smile,5), round(eye_smile,5)
                            ])
                    except Exception:
                        pass
                    self._csv_next_log_time = time.time() + self._csv_log_every_sec

                # update prev state for smoothness guard
                self._prev_state.update({
                    "head_x": self.current_head_x,
                    "head_y": self.current_head_y,
                    "head_z": self.current_head_z,
                    "body_x": self.current_body_x,
                    "body_y": self.current_body_y,
                    "mouth": self.current_mouth_open,
                })

                await asyncio.sleep(self.update_dt)
                smile_phase += dt * 0.6

                # Periodic motion refresh to avoid long static states
                if time.time() >= self._next_motion_refresh:
                    self._next_motion_refresh = time.time() + self.motion_refresh_sec
                    if not self.is_speaking and not self.is_generating:
                        if not self.current_action:
                            self._pick_random_action()
                        else:
                            # ensure continuous motion by shortening next rest window
                            self.next_action_time = time.time() + random.uniform(self.action_rest_min_sec, max(self.action_rest_min_sec, self.action_rest_min_sec + 0.15))
                    logger.info("♻️ Periodic motion refresh executed")

            except Exception as e:
                logger.exception(f"Motion error: {e}")
                await asyncio.sleep(0.5)

        logger.info("🛑 Motion loop stopped")

    async def _do_blink(self):
        try:
            await self.vts.inject_parameters_bulk({"EyeOpenLeft": 0.0, "EyeOpenRight": 0.0})
            await asyncio.sleep(0.12 + random.uniform(0.0, 0.06))
            await self.vts.inject_parameters_bulk({"EyeOpenLeft": 1.0, "EyeOpenRight": 1.0})
        except Exception:
            pass

    async def trigger_emotion(self, emotion: str):
        try:
            if not hasattr(self.vts, "_is_connected") or not self.vts._is_connected():
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
            logger.error(f"Emotion error: {e}", exc_info=True)

def create_motion_controller(vts_client, env_config: dict):
    config = {
        "smoothing": env_config.get("VTS_MOVEMENT_SMOOTHING", "0.92"),
        "intensity": env_config.get("VTS_MOTION_INTENSITY", "1.15"),
        "update_dt": env_config.get("VTS_UPDATE_DT", "0.028"),
        "VTS_BREATH_SPEED": env_config.get("VTS_BREATH_SPEED", "1.0"),
        "VTS_BREATH_INTENSITY": env_config.get("VTS_BREATH_INTENSITY", "0.28"),
        "action_duration_scale": env_config.get("VTS_ACTION_DURATION_SCALE", "1.10"),
        # ลดความถี่การขยับเริ่มต้นเล็กน้อยให้สมูทขึ้นและไม่ถี่เกินไป
        "action_rest_min_sec": env_config.get("VTS_ACTION_REST_MIN_SEC", "0.35"),
        "action_rest_max_sec": env_config.get("VTS_ACTION_REST_MAX_SEC", "0.90"),
        "idle_hold_prob": env_config.get("VTS_IDLE_HOLD_PROB", "0.12"),
        "mouth_base": env_config.get("VTS_MOUTH_BASE", "0.06"),
        "mouth_peak": env_config.get("VTS_MOUTH_PEAK", "0.65"),
        "mouth_freq": env_config.get("VTS_MOUTH_FREQ", "8.0"),
        # lip-sync & smoothness
        "mouth_decay_sec": env_config.get("VTS_MOUTH_DECAY_SEC", "0.18"),
        "SMOOTHNESS_GUARD": env_config.get("VTS_SMOOTHNESS_GUARD", "1"),
        "SMOOTH_MAX_DELTA_HEAD": env_config.get("VTS_SMOOTH_MAX_DELTA_HEAD", "0.08"),
        "SMOOTH_MAX_DELTA_BODY": env_config.get("VTS_SMOOTH_MAX_DELTA_BODY", "0.12"),
        "SMOOTH_MAX_DELTA_MOUTH": env_config.get("VTS_SMOOTH_MAX_DELTA_MOUTH", "0.55"),
        # motion logging
        "MOTION_LOG_INTERVAL_SEC": env_config.get("VTS_MOTION_LOG_INTERVAL_SEC", "0.2"),
        "MOTION_LOG_FILE": env_config.get("VTS_MOTION_LOG_FILE", str(Path("logs") / "motion_params.csv")),
        # random intensity (per axis)
        "RAND_INT_X_MIN": env_config.get("VTS_RAND_INT_X_MIN", "0.85"),
        "RAND_INT_X_MAX": env_config.get("VTS_RAND_INT_X_MAX", "1.25"),
        "RAND_INT_Y_MIN": env_config.get("VTS_RAND_INT_Y_MIN", "0.85"),
        "RAND_INT_Y_MAX": env_config.get("VTS_RAND_INT_Y_MAX", "1.25"),
        "RAND_INT_Z_MIN": env_config.get("VTS_RAND_INT_Z_MIN", "0.85"),
        "RAND_INT_Z_MAX": env_config.get("VTS_RAND_INT_Z_MAX", "1.25"),
        "RAND_INT_BODY_MIN": env_config.get("VTS_RAND_INT_BODY_MIN", "0.90"),
        "RAND_INT_BODY_MAX": env_config.get("VTS_RAND_INT_BODY_MAX", "1.35"),
        # idle sway frequency ranges
        "IDLE_FREQ_X_MIN": env_config.get("VTS_IDLE_FREQ_X_MIN", "0.55"),
        "IDLE_FREQ_X_MAX": env_config.get("VTS_IDLE_FREQ_X_MAX", "0.85"),
        "IDLE_FREQ_Y_MIN": env_config.get("VTS_IDLE_FREQ_Y_MIN", "0.75"),
        "IDLE_FREQ_Y_MAX": env_config.get("VTS_IDLE_FREQ_Y_MAX", "1.10"),
        "IDLE_FREQ_Z_MIN": env_config.get("VTS_IDLE_FREQ_Z_MIN", "0.35"),
        "IDLE_FREQ_Z_MAX": env_config.get("VTS_IDLE_FREQ_Z_MAX", "0.75"),
        # stall recovery
        "MOTION_STALL_RECOVERY_SEC": env_config.get("VTS_MOTION_STALL_RECOVERY_SEC", "3.0"),
        # smile consistency & refresh
        "SMILE_BASE_MIN": env_config.get("VTS_SMILE_BASE_MIN", "0.86"),
        "SMILE_VAR_AMP": env_config.get("VTS_SMILE_VAR_AMP", "0.015"),
        "SMILE_PULSE_MAX": env_config.get("VTS_SMILE_PULSE_MAX", "0.25"),
        "MOTION_REFRESH_SEC": env_config.get("VTS_MOTION_REFRESH_SEC", "30.0"),
    }
    for k,v in list(config.items()):
        try:
            config[k] = float(v)
        except Exception:
            pass
    return MotionController(vts_client, config)
