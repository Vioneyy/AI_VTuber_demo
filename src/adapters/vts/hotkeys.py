"""
Minimal HotkeyManager stub to keep ai_vtuber orchestrator running.
Implements environment-based configuration, optional safe motion loop,
and simple emotion auto-triggering via VTSClient.

This version does not register real OS-level hotkeys; it focuses on
compatibility so other adapters can start and lipsync can be tested.
"""

from __future__ import annotations
import asyncio
import os
import random
from typing import Optional


class HotkeyManager:
    def __init__(self, vts_client):
        self.vts = vts_client
        self.enabled: bool = False
        # Names (mapped to emotions) read from env/config
        self.hk_neutral: str = os.getenv("VTS_HK_NEUTRAL", "thinking")
        self.hk_thinking: str = os.getenv("VTS_HK_THINKING", "thinking")
        self.hk_happy: str = os.getenv("VTS_HK_HAPPY", "happy")
        self.hk_sad: str = os.getenv("VTS_HK_SAD", "sad")

    def configure_from_env(self, settings: Optional[object] = None):
        # Keep values from settings if provided; fall back to env defaults
        if settings is not None:
            try:
                self.hk_neutral = getattr(settings, "VTS_HK_NEUTRAL", self.hk_neutral)
                self.hk_thinking = getattr(settings, "VTS_HK_THINKING", self.hk_thinking)
                self.hk_happy = getattr(settings, "VTS_HK_HAPPY", self.hk_happy)
                self.hk_sad = getattr(settings, "VTS_HK_SAD", self.hk_sad)
            except Exception:
                pass

    async def start_emotion_keyboard_listener(self):
        # Stub: no real keyboard hook; mark enabled
        self.enabled = True

    def stop_emotion_keyboard_listener(self):
        self.enabled = False

    async def safe_motion_mode(self, interval: float = 8.0):
        # Stub: periodic sleep to simulate a running background task
        try:
            while True:
                await asyncio.sleep(max(0.5, float(interval)))
        except asyncio.CancelledError:
            return

    async def auto_trigger_emotion_from_response(
        self,
        ai_response: str,
        user_input: str,
        response_time: float,
        base_probability: float = 0.3,
    ):
        # Simple heuristic + probability gate
        try:
            if random.random() > float(base_probability):
                return
            txt = (ai_response or "") + "\n" + (user_input or "")
            low = txt.strip().lower()
            emo = "thinking"
            if any(k in low for k in ["ดีใจ", "ขอบคุณ", "สุดยอด", "เยี่ยม", "happy", "great", "thanks"]):
                emo = "happy"
            elif any(k in low for k in ["เศร้า", "เสียใจ", "หดหู่", "sad", "worry"]):
                emo = "sad"
            else:
                emo = "thinking"
            try:
                await self.vts.trigger_manual_emotion(emo)
            except Exception:
                pass
        except Exception:
            # Any failure should not interrupt main flow
            return