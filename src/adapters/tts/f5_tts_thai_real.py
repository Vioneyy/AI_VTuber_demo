"""
F5-TTS-Thai Engine (Fixed Integration)
อ้างอิงแนวทางจาก d:\AI_VTuber_demo\f5_tts_thai_fixed.py และปรับให้เข้ากับโปรเจกต์:
- โหลด reference audio จากพาธที่กำหนด/ค่าเริ่มต้นในโปรเจกต์
- ให้เมธอด synthesize(text) คืน WAV bytes (mono) สำหรับ pipeline ปัจจุบัน
- ตกลงไปใช้ Edge-TTS/เสียงเงียบเมื่อ F5-TTS-Thai ใช้งานไม่ได้
"""

import os
import io
import wave
import logging
import subprocess
from pathlib import Path

import numpy as np
import torch
import torchaudio

logger = logging.getLogger(__name__)


class F5TTSThai:
    def __init__(self, device: str | None = None, reference_wav: str | None = None):
        # Patch: บางเวอร์ชันของ f5-tts-th อ้างถึง torch.xpu ซึ่งไม่อยู่ในบิลด์ปกติบน Windows
        try:
            if not hasattr(torch, "xpu"):
                class _FakeXPU:
                    @staticmethod
                    def is_available():
                        return False
                setattr(torch, "xpu", _FakeXPU())
        except Exception:
            pass
        # เลือกอุปกรณ์ (device)
        env_device = os.getenv("TTS_DEVICE")
        if device:
            self.device = device
        elif env_device:
            self.device = env_device
        else:
            try:
                from core.config import config as _cfg
                self.device = 'cuda' if _cfg.system.use_gpu else 'cpu'
            except Exception:
                self.device = "cuda" if torch.cuda.is_available() else "cpu"

        if self.device.startswith('cuda') and not torch.cuda.is_available():
            logger.warning("CUDA requested for F5-TTS but not available. Falling back to CPU.")
            self.device = 'cpu'

        # กำหนด reference audio path: param -> env -> defaults ในโปรเจกต์
        ref_candidates: list[str] = []
        if reference_wav:
            ref_candidates.append(reference_wav)
        ref_env = os.getenv("TTS_REFERENCE_WAV", "")
        if ref_env:
            ref_candidates.append(ref_env)
        # ค่าที่ผู้ใช้ให้มาในไฟล์ตัวอย่าง
        ref_candidates.append("reference_audio/Jeed_anime.wav")
        # ค่าเดิมในโปรเจกต์
        ref_candidates.append("reference_audio/jeed_voice.wav")

        self.ref_audio_path = self._first_existing(ref_candidates) or ref_candidates[-1]

        # Sample rate ที่จะใช้สำหรับผลลัพธ์ (Discord = 48000)
        try:
            self.sample_rate = int(os.getenv("TTS_SAMPLE_RATE", "48000"))
        except Exception:
            self.sample_rate = 48000

        # F5 specific params
        try:
            self.f5_sr = int(os.getenv("F5_TTS_SAMPLE_RATE", "24000"))
        except Exception:
            self.f5_sr = 24000
        try:
            self.speed = float(os.getenv("F5_TTS_SPEED", os.getenv("TTS_SPEED", "1.0")))
        except Exception:
            self.speed = 1.0
        try:
            self.steps = int(os.getenv("F5_TTS_STEPS", os.getenv("TTS_STEPS", "32")))
        except Exception:
            self.steps = 32
        try:
            self.cfg_strength = float(os.getenv("F5_TTS_CFG_STRENGTH", "2.0"))
        except Exception:
            self.cfg_strength = 2.0
        # ตั้งค่า ref_text แบบสั้นเป็นดีฟอลต์ เพื่อหลีกเลี่ยงการต้องถอดเสียง reference ทุกครั้ง
        self.ref_text = os.getenv("F5_TTS_REF_TEXT", "สวัสดีค่ะ ฉันชื่อจี๊ด")
        if not os.getenv("F5_TTS_REF_TEXT", ""):
            try:
                logger.info("ℹ️ F5_TTS_REF_TEXT not set, using short default to skip transcription.")
            except Exception:
                pass

        # โหลด reference audio หากมี
        self.ref_waveform = None
        self.ref_sr = None
        try:
            if self.ref_audio_path and os.path.exists(self.ref_audio_path):
                wav, sr = torchaudio.load(self.ref_audio_path)
                if wav.shape[0] > 1:
                    wav = wav.mean(dim=0, keepdim=True)
                self.ref_waveform = wav.to(self.device)
                self.ref_sr = int(sr)
                dur = float(wav.shape[1]) / float(sr)
                logger.info(f"✅ Reference audio loaded: {self.ref_audio_path} ({dur:.2f}s @ {sr}Hz)")
            else:
                logger.info("ℹ️ No reference audio loaded.")
        except Exception as e:
            logger.warning(f"Failed to load reference audio '{self.ref_audio_path}': {e}")

        # พยายามโหลด backend ของ F5-TTS-Thai จริง
        self._tts = None
        try:
            from f5_tts_th.tts import TTS
            self._tts = TTS(model="v1")
            logger.info("✅ F5-TTS-Thai model initialized")
        except Exception as e:
            logger.warning(f"⚠️ F5-TTS-Thai backend not available: {e}")
            self._tts = None

    def synthesize(self, text: str) -> bytes:
        """
        สังเคราะห์เสียงจากข้อความ
        คืนค่าเป็น WAV bytes (mono) เพื่อใช้ใน pipeline ถัดไป
        """
        strict_only = str(os.getenv("TTS_STRICT_ONLY", "false")).lower() == "true"

        # 1) พยายามใช้ F5-TTS-Thai หากพร้อมใช้งาน
        if self._tts is not None:
            try:
                audio_np = None
                # ลอง signature หลายแบบตามเวอร์ชัน พร้อมส่ง reference และพารามิเตอร์
                # 1) ตามเอกสาร: ใช้ ref_audio/ref_text + gen_text
                try:
                    audio_np = self._tts.infer(
                        ref_audio=self.ref_audio_path,
                        ref_text=self.ref_text or "",
                        gen_text=text,
                        step=self.steps,
                        cfg=self.cfg_strength,
                        speed=self.speed,
                    )
                except TypeError:
                    # 2) แบบย่อ (ไม่รองรับบาง args)
                    try:
                        audio_np = self._tts.infer(ref_audio=self.ref_audio_path, gen_text=text)
                    except Exception:
                        pass
                # 3) แบบพาธอื่น ๆ ของ reference
                if audio_np is None:
                    try:
                        audio_np = self._tts.infer(ref_audio=self.ref_audio_path, ref_text=self.ref_text or "", gen_text=text)
                    except Exception:
                        pass
                # 3.1) บังคับปิด half precision หากไลบรารีรองรับ
                if audio_np is None:
                    for arg_name, arg_val in (
                        ("half", False),
                        ("use_fp16", False),
                        ("fp16", False),
                        ("dtype", "float32"),
                        ("precision", "fp32"),
                    ):
                        try:
                            kwargs = dict(ref_audio=self.ref_audio_path, ref_text=self.ref_text or "", gen_text=text)
                            kwargs[arg_name] = arg_val
                            audio_np = self._tts.infer(**kwargs)
                            if audio_np is not None:
                                break
                        except TypeError:
                            # พารามิเตอร์ไม่รองรับ ข้าม
                            pass
                        except Exception:
                            pass
                # 4) ส่ง waveform โดยตรง หากโหลดได้
                if audio_np is None and self.ref_waveform is not None:
                    try:
                        audio_np = self._tts.infer(ref_audio=self.ref_audio_path, ref_text=self.ref_text or "", gen_text=text)
                    except Exception:
                        pass
                # 5) ชื่อพารามิเตอร์อื่นของพาธ reference
                if audio_np is None:
                    try:
                        audio_np = self._tts.infer(ref_wav_path=self.ref_audio_path, gen_text=text)
                    except Exception:
                        pass
                if audio_np is None:
                    try:
                        audio_np = self._tts.infer(prompt_wav_path=self.ref_audio_path, prompt_text=self.ref_text or "", gen_text=text)
                    except Exception:
                        pass
                if audio_np is None:
                    try:
                        audio_np = self._tts.infer(spk_ref=self.ref_audio_path, spk_ref_text=self.ref_text or "", gen_text=text)
                    except Exception:
                        pass
                if audio_np is None:
                    try:
                        # บางเวอร์ชันอาจเป็น callable
                        audio_np = self._tts(text)
                    except Exception:
                        pass
                if audio_np is None:
                    try:
                        # หรือมีเมธอดชื่อ synthesize
                        audio_np = self._tts.synthesize(text)
                    except Exception:
                        pass

                out_sr = None
                if isinstance(audio_np, tuple):
                    if len(audio_np) > 1 and isinstance(audio_np[1], (int, float)):
                        out_sr = int(audio_np[1])
                    audio_np = audio_np[0]
                elif isinstance(audio_np, dict):
                    if 'audio' in audio_np:
                        out_sr = int(audio_np.get('sr') or audio_np.get('sample_rate') or (self.f5_sr or 24000))
                        audio_np = audio_np['audio']
                    elif 'wav' in audio_np:
                        out_sr = int(audio_np.get('sr') or audio_np.get('sample_rate') or (self.f5_sr or 24000))
                        audio_np = audio_np['wav']
                elif isinstance(audio_np, bytes):
                    # ได้เป็น WAV แล้ว
                    return audio_np
                elif isinstance(audio_np, str):
                    # ได้พาธไฟล์
                    try:
                        p = Path(audio_np)
                        if p.exists():
                            with open(p, 'rb') as f:
                                return f.read()
                    except Exception:
                        pass
                if audio_np is None:
                    raise RuntimeError("F5-TTS returned None")

                # แปลงเป็น numpy float32 mono
                if not isinstance(audio_np, np.ndarray):
                    try:
                        audio_np = np.asarray(audio_np, dtype=np.float32)
                    except Exception:
                        raise RuntimeError("Unexpected F5-TTS output type")
                audio_np = audio_np.astype(np.float32)
                if audio_np.ndim > 1:
                    audio_np = audio_np.mean(axis=0).astype(np.float32)
                # Resample จาก out_sr/f5_sr -> sample_rate หากจำเป็น
                orig_sr = int(out_sr or self.f5_sr or 24000)
                target_sr = int(self.sample_rate or orig_sr)
                if target_sr != orig_sr:
                    audio_np = self._resample_np(audio_np, orig_sr, target_sr)
                return self._to_wav_bytes(audio_np, target_sr)
            except Exception as e:
                if strict_only:
                    logger.error(f"❌ F5-TTS-Thai synthesis failed (strict mode): {e}")
                    # โหมด strict: ไม่ fallback ใดๆ
                    raise
                else:
                    logger.warning(f"F5-TTS-Thai synthesis failed, using fallback: {e}")

        if strict_only:
            # โหมด strict: หาก F5 ใช้งานไม่ได้ ให้ยกเว้นทันที
            raise RuntimeError("F5-TTS-Thai not available (strict mode)")

        # 2) Fallback: ใช้ Edge-TTS ผ่าน CLI แล้วแปลงเป็น WAV mono
        try:
            return self._synthesize_with_edge_tts(text)
        except Exception as e:
            logger.error(f"Edge-TTS fallback failed: {e}")

        # 3) สุดท้าย: เงียบ 1 วินาที
        return self._generate_silence(duration=1.0)

    # ===== Helpers =====
    def _to_wav_bytes(self, audio: np.ndarray, sr: int) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            pcm16 = np.clip(audio, -1.0, 1.0)
            pcm16 = (pcm16 * 32767.0).astype(np.int16)
            w.writeframes(pcm16.tobytes())
        return buf.getvalue()

    def _resample_np(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        if orig_sr == target_sr:
            return audio
        try:
            from scipy import signal
            num_samples = int(len(audio) * target_sr / orig_sr)
            audio = signal.resample(audio, num_samples).astype(np.float32)
            return audio
        except Exception:
            # fallback: nearest-neighbor (ง่ายมาก)
            ratio = float(target_sr) / float(orig_sr)
            idx = (np.arange(int(len(audio) * ratio)) / ratio).astype(np.int64)
            idx = np.clip(idx, 0, len(audio) - 1)
            return audio[idx].astype(np.float32)

    def _generate_silence(self, duration: float) -> bytes:
        audio = np.zeros(int(self.sample_rate * duration), dtype=np.float32)
        return self._to_wav_bytes(audio, self.sample_rate)

    def _synthesize_with_edge_tts(self, text: str) -> bytes:
        """สังเคราะห์เสียงด้วย Edge-TTS (ผ่าน CLI) แล้วแปลงเป็น WAV mono 24kHz"""
        voice = os.getenv("EDGE_TTS_VOICE", "th-TH-AcharaNeural")
        rate = os.getenv("EDGE_TTS_RATE", "+10%")
        pitch = os.getenv("EDGE_TTS_PITCH", "+0Hz")
        ffmpeg_bin = os.getenv("FFMPEG_BINARY", "ffmpeg")

        tmp_dir = os.path.join(os.getcwd(), "temp")
        os.makedirs(tmp_dir, exist_ok=True)
        mp3_path = os.path.join(tmp_dir, "edge_tts.mp3")
        wav_path = os.path.join(tmp_dir, "edge_tts.wav")

        import sys
        cmd = [
            sys.executable,
            "-m", "edge_tts",
            "--text", text,
            "--voice", voice,
            "--rate", rate,
            "--pitch", pitch,
            "--write-media", mp3_path,
        ]
        subprocess.check_call(cmd)

        subprocess.check_call([
            ffmpeg_bin, "-y", "-i", mp3_path, "-ar", str(self.sample_rate), "-ac", "1", wav_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open(wav_path, "rb") as f:
            data = f.read()
        try:
            os.remove(mp3_path)
            os.remove(wav_path)
        except Exception:
            pass
        return data

    def _first_existing(self, candidates: list[str]) -> str | None:
        for p in candidates:
            if not p:
                continue
            q = Path(p)
            if q.exists():
                return str(q)
        return None