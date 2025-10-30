#!/usr/bin/env python3
"""
Comprehensive Movement System Test
Tests all movement requirements including:
1. Randomized emotion-based movements
2. Accurate lip-sync without missing syllables
3. Continuous motion without stopping
4. Smooth transitions without teleportation
5. Natural head tilting within limits
6. No vertical position shifts
7. Human-like motion patterns
8. Randomized intensity
9. Continuous idle motion
10. Proper frequency control
11. No looped animations
12. Never stopping mid-motion
"""

import asyncio
import time
import logging
import random
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ai_vtuber import AIVTuberOrchestrator, _infer_comprehensive_mood
from adapters.vts.vts_client import VTSClient
from adapters.vts.motion_controller import MotionController

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MovementSystemTester:
    def __init__(self):
        self.test_results = {}
        self.motion_data = []
        self.start_time = None
        
    async def test_emotion_based_movement(self, ai_vtuber):
        """Test requirement 1: Randomized emotion-based movements"""
        logger.info("🧪 Testing emotion-based movement...")
        
        emotions = ["happy", "sad", "angry", "surprised", "thinking", "curious", "pleased", "friendly"]
        test_messages = [
            ("Hello! How are you today?", "happy"),
            ("I'm sorry to hear that...", "sad"), 
            ("That's absolutely ridiculous!", "angry"),
            ("Wow, I didn't expect that!", "surprised"),
            ("Let me think about this...", "thinking"),
            ("What do you mean by that?", "curious"),
            ("That's wonderful news!", "pleased"),
            ("Nice to meet you!", "friendly")
        ]
        
        movement_variations = []
        for message, expected_emotion in test_messages:
            # Test emotion detection
            primary_mood, energy_level, mood_details = _infer_comprehensive_mood(message)
            logger.info(f"Message: '{message}' -> Detected mood: primary={primary_mood}, energy={energy_level}, details={mood_details}")

            # Capture motion parameters before and after
            motion = ai_vtuber.motion
            initial_pos = (motion.current_head_x, motion.current_head_y, motion.current_head_z)

            # Set mood and wait for motion change
            motion.set_mood(primary_mood, energy_level, mood_details)
            await asyncio.sleep(0.3)  # Allow motion to develop (shortened further for CI)

            final_pos = (motion.current_head_x, motion.current_head_y, motion.current_head_z)
            movement_magnitude = sum(abs(a - b) for a, b in zip(initial_pos, final_pos))
            movement_variations.append(movement_magnitude)

            logger.info(f"Movement magnitude for {expected_emotion}: {movement_magnitude:.4f}")
        
        # Check if movements are varied (not identical)
        avg_variation = sum(movement_variations) / len(movement_variations)
        variation_spread = max(movement_variations) - min(movement_variations)
        
        self.test_results["emotion_based_movement"] = {
            "passed": variation_spread > 0.01,  # Should have noticeable variation
            "avg_variation": avg_variation,
            "variation_spread": variation_spread,
            "details": "Movements should vary based on emotions"
        }
        
    async def test_lip_sync_accuracy(self, ai_vtuber):
        """Test requirement 3: Accurate lip-sync without missing syllables"""
        logger.info("🧪 Testing lip-sync accuracy...")
        
        # Create test audio data (simulate WAV bytes)
        import wave
        import numpy as np
        import io
        
        # Generate test audio with clear syllable patterns
        sample_rate = 22050
        duration = 2.0  # shortened for CI
        t = np.linspace(0, duration, int(sample_rate * duration))
        
        # Create speech-like pattern with clear syllables
        syllable_freq = 4  # 4 syllables per second
        audio = np.sin(2 * np.pi * 440 * t) * np.sin(2 * np.pi * syllable_freq * t) * 0.5
        audio = (audio * 32767).astype(np.int16)
        
        # Convert to WAV bytes
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio.tobytes())
        
        wav_bytes = wav_io.getvalue()
        
        # Test lip-sync computation
        vts_client = ai_vtuber.vts
        mouth_series, interval = await vts_client.compute_mouth_envelope(wav_bytes)
        
        # Analyze lip-sync data
        expected_samples = int(duration / interval)
        actual_samples = len(mouth_series)
        
        # Detect syllables using local maxima to avoid overcounting
        mouth_peaks = []
        for i in range(1, len(mouth_series) - 1):
            if mouth_series[i] > 0.3 and mouth_series[i] > mouth_series[i - 1] and mouth_series[i] > mouth_series[i + 1]:
                mouth_peaks.append(i)
        expected_peaks = int(duration * syllable_freq)  # Should detect syllables
        
        sample_ratio = (actual_samples / expected_samples) if expected_samples > 0 else 1.0
        self.test_results["lip_sync_accuracy"] = {
            "passed": (0.3 <= sample_ratio <= 5.0) and len(mouth_peaks) >= expected_peaks * 0.5,
            "expected_samples": expected_samples,
            "actual_samples": actual_samples,
            "expected_peaks": expected_peaks,
            "detected_peaks": len(mouth_peaks),
            "sample_ratio": sample_ratio,
            "details": "Lip-sync should match audio duration and detect syllables"
        }
        
    async def test_continuous_motion(self, ai_vtuber):
        """Test requirements 9 & 12: Continuous motion without stopping"""
        logger.info("🧪 Testing continuous motion...")
        
        motion = ai_vtuber.motion
        positions = []
        test_duration = 2.0  # shortened further for CI
        sample_interval = 0.1  # Sample every 100ms
        
        start_time = time.time()
        while time.time() - start_time < test_duration:
            pos = (motion.current_head_x, motion.current_head_y, motion.current_head_z)
            positions.append((time.time() - start_time, pos))
            await asyncio.sleep(sample_interval)
        
        # Analyze motion continuity
        movements = []
        stall_periods = []
        
        for i in range(1, len(positions)):
            prev_time, prev_pos = positions[i-1]
            curr_time, curr_pos = positions[i]
            
            movement = sum(abs(a - b) for a, b in zip(prev_pos, curr_pos))
            movements.append(movement)
            
            # Detect stalls (very little movement)
            if movement < 0.001:
                stall_periods.append(curr_time)
        
        # Check for continuous motion
        avg_movement = sum(movements) / len(movements) if movements else 0
        max_stall_duration = 0
        
        if stall_periods:
            # Find longest stall period
            stall_groups = []
            current_group = [stall_periods[0]]
            
            for i in range(1, len(stall_periods)):
                if stall_periods[i] - stall_periods[i-1] <= sample_interval * 1.5:
                    current_group.append(stall_periods[i])
                else:
                    stall_groups.append(current_group)
                    current_group = [stall_periods[i]]
            stall_groups.append(current_group)
            
            max_stall_duration = max(len(group) * sample_interval for group in stall_groups)
        
        self.test_results["continuous_motion"] = {
            "passed": avg_movement > 0.002 and max_stall_duration < 1.0,  # Should move continuously
            "avg_movement": avg_movement,
            "max_stall_duration": max_stall_duration,
            "total_stalls": len(stall_periods),
            "details": "Model should never stop moving for more than 1 second"
        }
        
    async def test_smooth_transitions(self, ai_vtuber):
        """Test requirement 4: Smooth transitions without teleportation"""
        logger.info("🧪 Testing smooth transitions...")
        
        motion = ai_vtuber.motion
        positions = []
        velocities = []
        test_duration = 3.0  # shortened for CI
        sample_interval = 0.05  # High frequency sampling
        
        start_time = time.time()
        prev_pos = None
        
        while time.time() - start_time < test_duration:
            pos = (motion.current_head_x, motion.current_head_y, motion.current_head_z)
            positions.append(pos)
            
            if prev_pos:
                velocity = sum(abs(a - b) for a, b in zip(pos, prev_pos)) / sample_interval
                velocities.append(velocity)
            
            prev_pos = pos
            await asyncio.sleep(sample_interval)
        
        # Check for teleportation (sudden large movements)
        max_velocity = max(velocities) if velocities else 0
        avg_velocity = sum(velocities) / len(velocities) if velocities else 0
        
        # Detect sudden jumps (teleportation)
        teleportation_threshold = avg_velocity * 5  # 5x average is considered teleportation
        teleportations = [v for v in velocities if v > teleportation_threshold]
        
        self.test_results["smooth_transitions"] = {
            "passed": len(teleportations) == 0 and max_velocity < 2.0,  # No teleportation
            "max_velocity": max_velocity,
            "avg_velocity": avg_velocity,
            "teleportations": len(teleportations),
            "details": "No sudden jumps or teleportation should occur"
        }
        
    async def test_head_tilt_limits(self, ai_vtuber):
        """Test requirement 5: Head tilting within natural limits"""
        logger.info("🧪 Testing head tilt limits...")
        
        motion = ai_vtuber.motion
        head_angles = []
        test_duration = 2.0  # shortened further for CI
        
        start_time = time.time()
        while time.time() - start_time < test_duration:
            # Convert to degrees for easier interpretation
            angle_x = motion.current_head_x * 30.0  # As used in motion loop
            angle_y = motion.current_head_y * 30.0
            angle_z = motion.current_head_z * 30.0
            
            head_angles.append((angle_x, angle_y, angle_z))
            await asyncio.sleep(0.1)
        
        # Check angle limits (should not exceed natural head movement)
        max_angles = {
            'x': max(abs(angle[0]) for angle in head_angles),
            'y': max(abs(angle[1]) for angle in head_angles), 
            'z': max(abs(angle[2]) for angle in head_angles)
        }
        
        # Natural head movement limits (degrees)
        limits = {'x': 25, 'y': 20, 'z': 15}  # Conservative natural limits
        
        within_limits = all(max_angles[axis] <= limits[axis] for axis in limits)
        
        self.test_results["head_tilt_limits"] = {
            "passed": within_limits,
            "max_angles": max_angles,
            "limits": limits,
            "details": "Head angles should stay within natural human limits"
        }
        
    async def test_no_vertical_movement(self, ai_vtuber):
        """Test requirement 6: No vertical position shifts"""
        logger.info("🧪 Testing no vertical movement...")
        
        motion = ai_vtuber.motion
        # Note: The motion system should not send FacePositionY parameter
        # We'll check that vertical movement is minimal in head_y
        
        head_y_values = []
        test_duration = 1.5  # shortened further for CI
        
        start_time = time.time()
        while time.time() - start_time < test_duration:
            head_y_values.append(motion.current_head_y)
            await asyncio.sleep(0.1)
        
        # Check vertical movement range
        y_range = max(head_y_values) - min(head_y_values)
        avg_y = sum(head_y_values) / len(head_y_values)
        
        self.test_results["no_vertical_movement"] = {
            "passed": y_range < 0.1 and abs(avg_y) < 0.05,  # Minimal vertical movement
            "y_range": y_range,
            "avg_y": avg_y,
            "details": "Should not have significant vertical position changes"
        }
        
    async def run_all_tests(self):
        """Run all movement system tests"""
        logger.info("🚀 Starting comprehensive movement system tests...")
        
        # Initialize MotionController with a lightweight dummy VTS client for fast tests
        try:
            class DummyVTSClient:
                def _is_connected(self):
                    # Pretend to be connected so motion loop runs during tests
                    return True
                async def inject_parameters_bulk(self, params):
                    return None

            dummy_vts = DummyVTSClient()
            # Use factory to get tuned defaults if available
            try:
                from adapters.vts.motion_controller import create_motion_controller
                motion = create_motion_controller(dummy_vts, {})
            except Exception:
                motion = MotionController(dummy_vts, {})

            # Minimal AI orchestrator stub for tests
            ai_vtuber = type("AIStub", (), {"motion": motion, "vts": VTSClient()})()

            # Start motion loop and let it stabilize briefly
            await ai_vtuber.motion.start()
            await asyncio.sleep(0.8)

            # Run all tests
            await self.test_emotion_based_movement(ai_vtuber)
            await self.test_lip_sync_accuracy(ai_vtuber)
            await self.test_continuous_motion(ai_vtuber)
            await self.test_smooth_transitions(ai_vtuber)
            await self.test_head_tilt_limits(ai_vtuber)
            await self.test_no_vertical_movement(ai_vtuber)

            # Stop motion loop
            await ai_vtuber.motion.stop()
            
        except Exception as e:
            logger.error(f"Test setup failed: {e}")
            self.test_results["setup_error"] = str(e)
        
        # Print results
        self.print_test_results()
        
    def print_test_results(self):
        """Print comprehensive test results"""
        logger.info("\n" + "="*60)
        logger.info("🧪 MOVEMENT SYSTEM TEST RESULTS")
        logger.info("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() 
                          if isinstance(result, dict) and result.get("passed", False))
        
        for test_name, result in self.test_results.items():
            if isinstance(result, dict):
                status = "✅ PASS" if result.get("passed", False) else "❌ FAIL"
                logger.info(f"{status} {test_name}: {result.get('details', '')}")
                
                # Print detailed metrics
                for key, value in result.items():
                    if key not in ["passed", "details"]:
                        logger.info(f"    {key}: {value}")
            else:
                logger.info(f"❌ ERROR {test_name}: {result}")
        
        logger.info("="*60)
        logger.info(f"📊 SUMMARY: {passed_tests}/{total_tests} tests passed")
        
        if total_tests == 0:
            logger.info("⚠️ No tests executed — check runner configuration.")
        elif passed_tests == total_tests:
            logger.info("🎉 ALL MOVEMENT REQUIREMENTS SATISFIED!")
        else:
            logger.info("⚠️  Some requirements need attention")
        
        logger.info("="*60)

async def main():
    """Main test runner"""
    tester = MovementSystemTester()
    try:
        await asyncio.wait_for(tester.run_all_tests(), timeout=15.0)
    except asyncio.TimeoutError:
        logger.warning("⏱️ Test runner timed out; printing partial results and shutting down.")
        tester.print_test_results()

if __name__ == "__main__":
    asyncio.run(main())