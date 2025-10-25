from __future__ import annotations
import threading
import asyncio
from typing import Optional

from core.config import get_settings

try:
    import keyboard  # type: ignore
except Exception:  # pragma: no cover
    keyboard = None  # type: ignore


class EmotionHotkeyController:
    """
    Global hotkey controller for triggering VTube Studio emotions.
    F1 -> Neutral, F2 -> Happy, F3 -> Sad (configurable via Settings).

    This uses the `keyboard` package to register global hotkeys. If the
    package is not available, it will print a warning and do nothing.
    """

    def __init__(self, vts_client) -> None:
        self.vts_client = vts_client
        self.settings = get_settings()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start hotkey listener in a background thread."""
        self.loop = loop
        if getattr(self.settings, "ENABLE_GLOBAL_HOTKEYS", True) is False:
            print("Global hotkeys disabled by config (ENABLE_GLOBAL_HOTKEYS=False)")
            return
        if keyboard is None:
            print("keyboard package is not available; install 'keyboard' to enable F1-F3 hotkeys")
            return
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="EmotionHotkeys", daemon=True)
        self._thread.start()
        print("Emotion hotkeys started: F1=Neutral, F2=Happy, F3=Sad")

    def stop(self) -> None:
        self._running = False
        # keyboard hooks will stop when thread exits

    def _run(self) -> None:
        assert keyboard is not None
        # Map from keys to emotion names (settings may override hotkey mapping inside VTS)
        f1_emotion = getattr(self.settings, "F1_EMOTION", "Neutral")
        f2_emotion = getattr(self.settings, "F2_EMOTION", "Happy")
        f3_emotion = getattr(self.settings, "F3_EMOTION", "Sad")

        def make_handler(emotion_name: str):
            def handler(event):
                if not self.loop:
                    return
                try:
                    # Schedule the coroutine on the main loop
                    asyncio.run_coroutine_threadsafe(self.vts_client.trigger_hotkey(emotion_name), self.loop)
                except Exception:
                    pass
            return handler

        keyboard.on_press_key("f1", make_handler(f1_emotion))
        keyboard.on_press_key("f2", make_handler(f2_emotion))
        keyboard.on_press_key("f3", make_handler(f3_emotion))

        # Keep thread alive while running
        while self._running:
            keyboard.wait("esc")  # just wait on a key to avoid busy loop; not required
            # If ESC pressed, we can continue running unless stop() called; no-op here
            # Prevent tight loop
            # Note: keyboard.wait blocks until 'esc' is pressed; to keep responsiveness,
            # we simply sleep occasionally if needed