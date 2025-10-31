from __future__ import annotations
import subprocess
import tempfile
import asyncio
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

    async def record_and_transcribe(self, voice_client, duration_sec: int = 5) -> str:
        """
        บันทึกเสียงจาก Discord voice channel ชั่วคราว แล้วถอดความด้วย whisper.cpp

        - ใช้ `py-cord` sinks (WaveSink) หากมี
        - รองรับ GPU offload ผ่านการตั้งค่า `WHISPER_CPP_NGL`

        Returns: ข้อความถอดความ (string) หรือว่างเปล่าหากไม่สำเร็จ
        """
        try:
            if not voice_client or not voice_client.is_connected():
                return ""

            # นำเข้า sinks จาก py-cord
            import discord
            from discord import sinks

            recorded = {"file": None}

            def _finished_callback(sink: sinks.Sink, *args):
                # พยายามเลือกไฟล์แรกที่บันทึกได้จาก sink
                try:
                    # py-cord ให้รายการไฟล์ใน sink.files
                    if hasattr(sink, "files") and sink.files:
                        recorded["file"] = sink.files[0]
                    else:
                        # fallback: ดึงจาก audio_data หากมี
                        if hasattr(sink, "audio_data") and sink.audio_data:
                            for _uid, data in sink.audio_data.items():
                                # data.file เป็นพาธไฟล์ wav ต่อผู้ใช้ (หาก WaveSink)
                                fp = getattr(data, "file", None)
                                if fp:
                                    recorded["file"] = fp
                                    break
                except Exception:
                    recorded["file"] = None

            # เริ่มบันทึก
            sink = sinks.WaveSink()
            voice_client.start_recording(sink, _finished_callback, None)
            await asyncio.sleep(max(1, int(duration_sec)))
            voice_client.stop_recording()

            wav_path = recorded.get("file")
            if not wav_path:
                return ""

            try:
                wav_bytes = Path(wav_path).read_bytes()
            except Exception:
                return ""
            finally:
                # ลบไฟล์ชั่วคราวหากมี
                try:
                    Path(wav_path).unlink(missing_ok=True)
                except Exception:
                    pass

            return self.transcribe_wav_bytes(wav_bytes)

        except Exception:
            # กรณีเวอร์ชัน py-cord ไม่รองรับการบันทึก หรือเกิดข้อผิดพลาดอื่น ๆ
            return ""