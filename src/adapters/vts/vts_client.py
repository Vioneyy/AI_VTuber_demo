"""
Compatibility VTSClient wrapper built on VTSHumanMotionController.
Provides lipsync from WAV bytes/file and simple emotion triggers
so existing adapters (Discord) can work with the new motion controller.
"""

import asyncio
import io
import time
import wave
import audioop
from typing import Optional

from .motion_controller import VTSHumanMotionController


class VTSClient:
    def __init__(
        self,
        plugin_name: str = "AI VTuber",
        plugin_developer: str = "AI VTuber",
        host: str = "127.0.0.1",
        port: int = 8001,
        config: Optional[object] = None,
    ) -> None:
        self.ctrl = VTSHumanMotionController(
            plugin_name=plugin_name,
            plugin_developer=plugin_developer,
            host=host,
            port=port,
        )
        self.config = config
        self._mouth_id: Optional[str] = None
        self._smile_id: Optional[str] = None
        self._motion_task: Optional[asyncio.Task] = None
        # Expose ws for compatibility
        self.ws = None
        # Optional compatibility fields
        self.available_parameters = []
        self.available_hotkeys = []

    async def connect(self):
        await self.ctrl.connect()
        ok = await self.ctrl.authenticate()
        if not ok:
            raise RuntimeError("VTS authentication failed")
        await self.ctrl._resolve_param_map()
        self._mouth_id = self.ctrl.param_map.get("MouthOpen")
        self._smile_id = self.ctrl.param_map.get("MouthSmile")
        # ใช้แหล่ง amplitude จากลิปซิงก์ ไม่ใช้ไมค์
        self.ctrl.enable_mic = False
        # Mirror ws for external checks
        self.ws = self.ctrl.ws
        # คืนค่า True เพื่อรองรับสคริปต์ที่ตรวจผลลัพธ์การเชื่อมต่อ
        return True

    async def verify_connection(self):
        # Minimal check: ensure websocket is open and authenticated
        return bool(self.ctrl.ws and self.ctrl.authenticated)

    async def disconnect(self):
        await self.ctrl.disconnect()
        # หยุด motion หากกำลังทำงาน
        try:
            if self._motion_task and not self._motion_task.done():
                self._motion_task.cancel()
        finally:
            self._motion_task = None
        self.ws = None

    async def reconnect(self):
        """Disconnect then connect + authenticate again. Returns True if OK."""
        try:
            await self.disconnect()
        except Exception:
            pass
        await self.connect()
        return await self.verify_connection()

    def get_status(self) -> dict:
        """Return basic connection and parameter mapping status."""
        return {
            "connected": bool(self.ctrl.ws and self.ctrl.authenticated),
            "host": self.ctrl.host,
            "port": self.ctrl.port,
            "mapped": dict(self.ctrl.param_map),
        }

    async def inject_parameter(self, name: str, value: float):
        """Compatibility method used by MotionController to inject single parameter."""
        try:
            await self.ctrl.set_parameters({name: float(value)}, weight=1.0)
        except Exception:
            pass

    async def trigger_hotkey(self, name: str):
        try:
            await self.ctrl.trigger_hotkey(name)
        except Exception:
            pass

    async def lipsync_wav(self, wav_path: str):
        """Stream mouth-open values by reading a local WAV file path."""
        data = None
        try:
            with open(wav_path, "rb") as f:
                data = f.read()
        except Exception:
            data = None
        if not data:
            return
        await self.lipsync_bytes(data)

    async def lipsync_bytes(self, wav_bytes: bytes):
        """Compute amplitude envelope from WAV bytes and inject MouthOpen into VTS.

        - Expects PCM WAV bytes. Falls back silently if parsing fails.
        - Sends parameter updates ~30–60 Hz depending on chunk.
        """
        if not self.ctrl.authenticated:
            return
        mouth_id = self._mouth_id
        if not mouth_id:
            # No mouth parameter mapped; nothing to update
            return
        try:
            bio = io.BytesIO(wav_bytes)
            with wave.open(bio, "rb") as wf:
                nch = wf.getnchannels()
                width = wf.getsampwidth()
                rate = wf.getframerate()
                total_frames = wf.getnframes()

                # Target update cadence ~30ms
                chunk_frames = max(256, int(rate * 0.03))
                prev = 0.0
                t_start = time.time()

                while True:
                    frames = wf.readframes(chunk_frames)
                    if not frames:
                        break
                    # If stereo, mix to mono for RMS
                    if nch > 1:
                        try:
                            frames_mono = audioop.tomono(frames, width, 0.5, 0.5)
                        except Exception:
                            frames_mono = frames
                    else:
                        frames_mono = frames

                    try:
                        rms = audioop.rms(frames_mono, width)  # 0..(2**(8*width-1))
                    except Exception:
                        rms = 0
                    # Normalize to 0..1 (tuneable scaling)
                    max_val = float(1 << (8 * width - 1))
                    lvl = min(1.0, max(0.0, (rms / max_val) * 2.0))
                    # Smooth for natural mouth motion
                    val = prev + (lvl - prev) * 0.6
                    prev = val

                    # ส่ง amplitude ไปยัง motion controller เพื่อให้หัว bob ตามการพูด
                    try:
                        self.ctrl.speech_target = float(val)
                        self.ctrl.speaking = val > 0.05
                    except Exception:
                        pass
                    # อัปเดตปากใน VTS
                    try:
                        await self.ctrl.set_parameters({mouth_id: float(val)}, weight=1.0)
                    except Exception:
                        pass

                    # Sleep according to chunk duration
                    dt = max(0.0, float(len(frames_mono)) / float(width * max(1, nch) * rate))
                    await asyncio.sleep(min(0.06, max(0.01, dt)))

                # Gracefully close mouth at the end
                try:
                    await self.ctrl.set_parameters({mouth_id: 0.0}, weight=1.0)
                except Exception:
                    pass
            # ปิดสถานะการพูดหลังจบ
            try:
                self.ctrl.speaking = False
                self.ctrl.speech_target = 0.0
            except Exception:
                pass
        except Exception:
            # Parsing failed; ignore
            return

    async def trigger_manual_emotion(self, emotion_type: str):
        """Simple manual emotion pulse via MouthSmile if available."""
        emo = (emotion_type or "").strip().lower()
        smile_id = self._smile_id
        if not smile_id:
            return
        # Map emotion to smile level
        target = 1.0
        if emo == "sad":
            target = 0.5
        elif emo == "thinking":
            target = 0.8
        elif emo == "happy":
            target = 1.1
        else:
            target = 0.9

        # Pulse for ~2 seconds
        t_end = time.time() + 2.0
        val = float(target)
        try:
            while time.time() < t_end:
                await self.ctrl.set_parameters({smile_id: val}, weight=1.0)
                await asyncio.sleep(0.08)
        except Exception:
            pass

    async def start_motion(self):
        """Start background human-like motion loop (head, blink, breathing)."""
        if self._motion_task and not self._motion_task.done():
            return
        async def _runner():
            try:
                await self.ctrl.run()
            except asyncio.CancelledError:
                pass
            except Exception:
                # Avoid crashing the orchestrator
                pass
        self._motion_task = asyncio.create_task(_runner())

    async def stop_motion(self):
        """Stop background motion loop."""
        if self._motion_task and not self._motion_task.done():
            self._motion_task.cancel()
        self._motion_task = None