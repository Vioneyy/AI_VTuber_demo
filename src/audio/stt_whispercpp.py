from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ..core.config import get_settings

class WhisperCppSTT:
    """
    Wrapper for whisper.cpp CLI to transcribe audio with GPU acceleration.

    Requirements:
      - Build whisper.cpp with CUDA/cuBLAS or OpenCL for GPU acceleration.
      - Provide paths via .env:
        WHISPER_CPP_BIN_PATH, WHISPER_CPP_MODEL_PATH
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.bin_path = self._require_path(self.settings.WHISPER_CPP_BIN_PATH, "WHISPER_CPP_BIN_PATH")
        self.model_path = self._require_path(self.settings.WHISPER_CPP_MODEL_PATH, "WHISPER_CPP_MODEL_PATH")
        self.lang = self.settings.WHISPER_CPP_LANG or "th"
        self.threads = int(self.settings.WHISPER_CPP_THREADS)
        self.ngl = int(self.settings.WHISPER_CPP_NGL)
        self.timeout_ms = int(self.settings.WHISPER_CPP_TIMEOUT_MS)

    def _require_path(self, p: Optional[str], name: str) -> Path:
        if not p:
            raise RuntimeError(f"Missing required setting: {name}")
        rp = Path(p)
        if not rp.exists():
            raise RuntimeError(f"Path not found for {name}: {rp}")
        return rp

    def transcribe_wav_bytes(self, audio_bytes: bytes, language: Optional[str] = None) -> str:
        """Transcribe given WAV PCM bytes to text using whisper.cpp.
        Returns plain text transcript (may be empty on failure).
        """
        lang = language or self.lang
        with tempfile.TemporaryDirectory() as td:
            tmp_dir = Path(td)
            in_wav = tmp_dir / "input.wav"
            out_txt = tmp_dir / "output.txt"
            in_wav.write_bytes(audio_bytes)

            cmd = [
                str(self.bin_path),
                "-m", str(self.model_path),
                "-f", str(in_wav),
                "-l", lang,
                "-otxt",
                "-of", str(out_txt),
                "-t", str(self.threads),
                "-ngl", str(self.ngl),
            ]
            try:
                subprocess.run(cmd, check=True, timeout=max(1.0, float(self.timeout_ms) / 1000.0))
                if out_txt.exists():
                    return out_txt.read_text(encoding="utf-8", errors="ignore").strip()
            except subprocess.TimeoutExpired:
                return ""  # timeout
            except Exception:
                return ""  # generic failure
        return ""

    def transcribe_file(self, wav_path: Path, language: Optional[str] = None) -> str:
        return self.transcribe_wav_bytes(Path(wav_path).read_bytes(), language)