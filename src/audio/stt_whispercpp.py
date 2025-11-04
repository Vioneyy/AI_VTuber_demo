"""
ตัวห่อ Whisper.cpp STT ให้เข้ากับทั้ง main.py และสคริปต์ทดสอบ
ให้คลาส:
- WhisperCppSTT: เมธอด transcribe_file(path)
- WhisperCPP: เมธอด transcribe(path) ที่เรียกใช้ตัวบน
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

from core.config import config


class WhisperCppSTT:
    def __init__(self,
                 bin_path: Optional[Path] = None,
                 model_path: Optional[Path] = None,
                 lang: Optional[str] = None,
                 threads: Optional[int] = None,
                 n_gpu_layers: Optional[int] = None,
                 timeout_ms: Optional[int] = None):
        # ตั้งค่าเริ่มจาก config และ ENV
        self.bin_path = Path(os.getenv("WHISPER_CPP_BIN_PATH", str(bin_path or config.stt.whisper_bin_path))).resolve()
        self.model_path = Path(os.getenv("WHISPER_CPP_MODEL_PATH", str(model_path or config.stt.model_path))).resolve()
        self.lang = os.getenv("WHISPER_CPP_LANG", lang or config.stt.lang or "th")
        self.threads = int(os.getenv("WHISPER_CPP_THREADS", str(threads or (config.stt.threads or 0))) or 0) or None
        self.n_gpu_layers = int(os.getenv("WHISPER_CPP_NGL", str(n_gpu_layers or (config.stt.n_gpu_layers or 0))) or 0) or None
        self.timeout_ms = int(os.getenv("WHISPER_CPP_TIMEOUT_MS", str(timeout_ms or (config.stt.timeout_ms or 120000))) or 120000)

    def _build_cmd(self, wav_path: Path):
        exe = self.bin_path
        # รองรับการชี้ไปที่โฟลเดอร์ที่มี binary ชื่อที่คาดเดาได้
        if exe.is_dir():
            candidates = ["main.exe", "whisper.exe", "main"]
            for c in candidates:
                p = exe / c
                if p.exists():
                    exe = p
                    break
        args = [str(exe), "-m", str(self.model_path), "-f", str(wav_path), "-l", self.lang, "-nt"]
        if self.threads and self.threads > 0:
            args += ["-t", str(self.threads)]
        if self.n_gpu_layers and self.n_gpu_layers > 0:
            args += ["-ngl", str(self.n_gpu_layers)]
        return args

    def transcribe_file(self, wav_path: Path) -> str:
        wav_path = Path(wav_path)
        if not wav_path.exists():
            return ""
        try:
            cmd = self._build_cmd(wav_path)
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout_ms / 1000.0)
            if proc.returncode != 0:
                return ""
            # พยายามดึงบรรทัดสุดท้ายที่มีข้อความ
            out = proc.stdout.strip()
            # Whisper.cpp ปกติจะพิมพ์ผลรวมท้าย ๆ ใน stdout
            return out.splitlines()[-1] if out else ""
        except Exception:
            return ""


class WhisperCPP:
    """Wrapper บาง ๆ ให้ main.py เรียกใช้ชื่อคลาสนี้ได้"""
    def __init__(self,
                 bin_path: Optional[str] = None,
                 model_path: Optional[str] = None,
                 language: Optional[str] = None,
                 threads: Optional[int] = None,
                 n_gpu_layers: Optional[int] = None):
        # map 'language' → 'lang'
        self._stt = WhisperCppSTT(
            bin_path=Path(bin_path) if bin_path else None,
            model_path=Path(model_path) if model_path else None,
            lang=language,
            threads=threads,
            n_gpu_layers=n_gpu_layers,
        )

    def transcribe(self, wav_path: Path) -> str:
        return self._stt.transcribe_file(Path(wav_path))