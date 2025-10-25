from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from ..core.config import get_settings
from ..adapters.tts.f5_tts_thai import F5TTSThaiEngine
from .rvc_v2 import convert as rvc_convert


@dataclass
class SampleOptions:
    speed: float = 1.0
    gain_db: float = 0.0
    emotion: str = "neutral"
    apply_rvc: bool = True
    voice_preset: str = "anime_girl"


class SampleVoiceService:
    def __init__(self, tts_engine: Optional[F5TTSThaiEngine] = None):
        self.settings = get_settings()
        self.tts = tts_engine or F5TTSThaiEngine()
        self._pool = ThreadPoolExecutor(max_workers=2)

    def generate(self, text: str, options: Optional[SampleOptions] = None) -> Dict[str, bytes]:
        """Generate sample voice audio.
        Returns dict with keys: 'raw' (bytes) and 'processed' (bytes, may equal raw if RVC disabled).
        """
        opts = options or SampleOptions(
            speed=self.settings.F5_TTS_SPEED,
            gain_db=0.0,
            emotion=self.settings.TTS_EMOTION_DEFAULT,
            apply_rvc=self.settings.ENABLE_RVC,
            voice_preset=self.settings.VOICE_PRESET,
        )

        audio_raw = self.tts.speak(
            text,
            voice_id=self.settings.TTS_VOICE_ID,
            emotion=opts.emotion,
            prosody={"rate": float(opts.speed), "gain_db": float(opts.gain_db)},
        )
        if not audio_raw:
            return {"raw": b"", "processed": b""}

        audio_proc = audio_raw
        if bool(opts.apply_rvc):
            # Enforce RVC timeout using a thread pool
            try:
                fut = self._pool.submit(rvc_convert, audio_raw, str(opts.voice_preset))
                audio_proc = fut.result(timeout=max(0.5, float(self.settings.RVC_TIMEOUT_MS) / 1000.0))
            except FuturesTimeout:
                audio_proc = audio_raw  # Fallback to raw if conversion too slow
            except Exception:
                audio_proc = audio_raw
        return {"raw": audio_raw, "processed": audio_proc}

    @staticmethod
    def save_files(out_dir: str, audio: Dict[str, bytes], raw_name: str = "sample_raw.wav", proc_name: str = "sample_rvc.wav") -> Dict[str, str]:
        from pathlib import Path
        p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        raw_path = p / raw_name
        proc_path = p / proc_name
        raw_path.write_bytes(audio.get("raw", b""))
        proc_path.write_bytes(audio.get("processed", b""))
        return {"raw": str(raw_path.resolve()), "processed": str(proc_path.resolve())}