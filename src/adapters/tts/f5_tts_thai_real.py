"""
F5-TTS-Thai Engine (Real Implementation)
✅ รองรับ API จริงของ F5-TTS-Thai
"""
import os
import asyncio
import subprocess
import numpy as np
import torch
import torchaudio
from io import BytesIO
import logging

logger = logging.getLogger(__name__)

class F5TTSThai:
    def __init__(self, device: str | None = None):
        # Device selection from .env or override; fallback to CUDA if available
        env_device = os.getenv("TTS_DEVICE")
        if device:
            self.device = device
        elif env_device:
            self.device = env_device
        else:
            # Map from global GPU preference when available
            try:
                from core.config import config as _cfg
                self.device = 'cuda' if _cfg.system.use_gpu else 'cpu'
            except Exception:
                self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Safety: if CUDA requested but unavailable, fall back to CPU
        if self.device.startswith('cuda') and not torch.cuda.is_available():
            logger.warning("CUDA requested for F5-TTS but not available. Falling back to CPU.")
            self.device = 'cpu'

        self.use_reference = os.getenv("F5_TTS_USE_REFERENCE", "false").lower() == "true"
        # ค่าเริ่มต้นพาธไฟล์อ้างอิงเสียงชี้ไปยังไฟล์ในโปรเจ็กต์โดยตรง
        self.ref_audio_path = os.getenv("TTS_REFERENCE_WAV", "reference_audio/jeed_voice.wav")
        self.ref_text = os.getenv("F5_TTS_REF_TEXT", "")
        self.speed = float(os.getenv("F5_TTS_SPEED", "1.0"))
        self.steps = int(os.getenv("F5_TTS_STEPS", "32"))  # default 32
        self.cfg_strength = float(os.getenv("F5_TTS_CFG_STRENGTH", "2.0"))
        self.sample_rate = int(os.getenv("F5_TTS_SAMPLE_RATE", "24000"))
        
        logger.info(f"F5-TTS-Thai: device={self.device}, speed={self.speed}, steps={self.steps}")
        
        try:
            # ✅ วิธีที่ถูกต้อง: ใช้ TTS class จาก f5_tts_th.tts
            from f5_tts_th.tts import TTS
            
            logger.info("📦 กำลังโหลด F5-TTS-Thai model...")
            
            # โหลด model ด้วย TTS class
            # Note: F5 TTS-TH selects GPU automatically if available; we log chosen device.
            self.tts = TTS(model="v1")  # ใช้ model v1 ตาม Hugging Face
            
            logger.info("✅ F5-TTS-Thai โหลดสำเร็จ!")

            
        except ImportError as e:
            logger.error(f"❌ ไม่สามารถ import F5-TTS-Thai: {e}")
            logger.error("ติดตั้งด้วย: pip install f5-tts-thai")
            raise
        except Exception as e:
            logger.error(f"❌ โหลด F5-TTS-Thai ไม่สำเร็จ: {e}")
            raise

    def set_use_reference(self, use_ref: bool):
        """เปิด/ปิด reference runtime"""
        self.use_reference = use_ref
        logger.info(f"F5-TTS: use_reference = {use_ref}")

    def _sanitize_text(self, text: str) -> str:
        """ทำความสะอาดข้อความ"""
        text = text.strip()
        import re
        # ลบ emoji และ special characters
        text = re.sub(r'[^\w\s\u0E00-\u0E7F.,!?-]', '', text)
        return text

    def synthesize(self, text: str) -> bytes:
        """
        สังเคราะห์เสียงจากข้อความ
        """
        try:
            text = self._sanitize_text(text)
            
            if not text:
                logger.warning("ข้อความว่าง")
                return self._generate_silence(1.0)

            logger.info(f"🎤 F5-TTS-Thai กำลังสังเคราะห์: {text[:50]}...")

            # ใช้ไฟล์อ้างอิงตาม .env พร้อมเตรียมให้เป็น mono/24kHz
            ref_path_orig = self.ref_audio_path if os.path.exists(self.ref_audio_path) else self._get_silent_reference()
            ref_path = self._prepare_reference_audio(ref_path_orig)
            # หากไม่กำหนด ref_text ใน .env ให้ถอดเสียงอ้างอิงเป็นภาษาไทยเพื่อเพิ่มโอกาสตรงกับไฟล์
            ref_text_final = (self.ref_text or self._transcribe_thai(ref_path) or "").strip()
            if self.use_reference:
                logger.info(f"🎙️ ใช้ reference (audio='{ref_path}', text='{(ref_text_final or '[auto-th]').strip()[:30]}')")
            else:
                logger.info(f"🔧 ไม่ใช้ reference ตาม config (audio='{ref_path}')")

            # เรียกใช้ด้วยอาร์กิวเมนต์หลักเท่านั้น เพื่อลดความเสี่ยงจากชื่อพารามิเตอร์ที่ต่างเวอร์ชัน
            generated_audio = self.tts.infer(ref_path, ref_text_final, text)

            # ensure numpy
            try:
                if isinstance(generated_audio, torch.Tensor):
                    generated_audio = generated_audio.detach().cpu().float().numpy()
                elif isinstance(generated_audio, (list, tuple)):
                    generated_audio = np.asarray(generated_audio, dtype=np.float32).reshape(-1)
                else:
                    generated_audio = np.asarray(generated_audio, dtype=np.float32)
            except Exception:
                pass

            # Clean audio
            audio_data = self._clean_audio(generated_audio)
            # หากได้เสียงเงียบ ให้ fallback โดยไม่ใช้ reference เพื่อหลีกเลี่ยงความเงียบ
            if np.max(np.abs(audio_data)) < 1e-6:
                logger.warning("⚠️ ผลลัพธ์เป็นเสียงเงียบ ลองสังเคราะห์แบบไม่ใช้ reference")
                try:
                    generated_audio = self.tts.infer(self._get_silent_reference(), "", text)
                    audio_data = self._clean_audio(generated_audio)
                except Exception as e:
                    logger.error(f"❌ fallback non-reference ล้มเหลว: {e}")
                    return self._generate_silence(1.0)
            
            # แปลงเป็น WAV bytes
            wav_bytes = self._to_wav_bytes(audio_data, self.sample_rate)
            # หากยังเงียบ ให้ fallback สุดท้ายด้วย Edge-TTS (โหมดทำงานได้ก่อน)
            if np.max(np.abs(audio_data)) < 1e-6:
                logger.warning("⚠️ ผลลัพธ์เงียบหลัง fallback non-reference ลองใช้ Edge-TTS เป็นทางเลือกสุดท้าย")
                try:
                    wav_bytes = self._synthesize_with_edge_tts(text)
                    if wav_bytes and len(wav_bytes) > 0:
                        logger.info(f"✅ Edge-TTS fallback สำเร็จ: {len(wav_bytes)} bytes")
                        return wav_bytes
                except Exception as e:
                    logger.error(f"❌ Edge-TTS fallback ล้มเหลว: {e}")
            
            logger.info(f"✅ สังเคราะห์สำเร็จ: {len(wav_bytes)} bytes")
            return wav_bytes

        except Exception as e:
            logger.error(f"❌ F5-TTS synthesis error: {e}", exc_info=True)
            # หากเกิดข้อผิดพลาด ให้คืนเสียงเงียบสั้น ๆ เพื่อไม่ให้ Discord เล่นไฟล์ว่าง
            return self._generate_silence(1.0)

    def _clean_audio(self, audio: np.ndarray) -> np.ndarray:
        """ทำความสะอาดเสียง"""
        # ลบ NaN/Inf
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        
        # Clip
        audio = np.clip(audio, -1.0, 1.0)
        
        # RMS Normalize
        rms = np.sqrt(np.mean(audio**2))
        if rms > 1e-6:
            target_rms = 0.2  # เพิ่มระดับเสียงเล็กน้อยเพื่อให้ได้ยินชัดขึ้น
            audio = audio * (target_rms / rms)
        
        # Fade in/out (10ms)
        fade_samples = int(self.sample_rate * 0.01)
        if len(audio) > fade_samples * 2:
            fade_in = np.linspace(0, 1, fade_samples)
            fade_out = np.linspace(1, 0, fade_samples)
            audio[:fade_samples] *= fade_in
            audio[-fade_samples:] *= fade_out
        
        return audio

    def _to_wav_bytes(self, audio: np.ndarray, sample_rate: int) -> bytes:
        """แปลง numpy array เป็น WAV bytes"""
        buffer = BytesIO()
        
        audio_tensor = torch.from_numpy(audio).float()
        if audio_tensor.dim() == 1:
            audio_tensor = audio_tensor.unsqueeze(0)
        
        torchaudio.save(buffer, audio_tensor, sample_rate, format="wav")
        buffer.seek(0)
        
        return buffer.read()

    def _prepare_reference_audio(self, ref_path: str) -> str:
        """แปลงไฟล์อ้างอิงให้เป็น mono/24kHz และเลือกส่วนที่เป็นภาษาไทย ~3-6 วินาที"""
        try:
            if not os.path.exists(ref_path):
                return ref_path
            wav, sr = torchaudio.load(ref_path)
            # to mono
            if wav.shape[0] > 1:
                wav = wav.mean(dim=0, keepdim=True)
            # resample to target
            target_sr = self.sample_rate
            if sr != target_sr:
                resampler = torchaudio.transforms.Resample(sr, target_sr)
                wav = resampler(wav)
                sr = target_sr
            # พยายามเลือกช่วงที่เป็นภาษาไทยโดยใช้ faster-whisper
            try:
                seg_wav = self._extract_thai_segment_wav(wav, sr)
                if seg_wav is not None:
                    wav = seg_wav
            except Exception:
                pass
            # จำกัดความยาวสูงสุด ~6s
            max_len = int(sr * 6.0)
            if wav.shape[1] > max_len:
                wav = wav[:, :max_len]
            # write temp
            out_path = os.path.join(os.getcwd(), "temp_ref_prepared.wav")
            torchaudio.save(out_path, wav, sr)
            return out_path
        except Exception:
            # หากเตรียมไม่ได้ ใช้ต้นฉบับ
            return ref_path

    def _extract_thai_segment_wav(self, wav: torch.Tensor, sr: int) -> torch.Tensor | None:
        """สแกนหา segment ที่เป็นภาษาไทยในสัญญาณ และตัดมาเป็นช่วง ~3-6 วินาที
        คืนค่า tensor mono ถ้าพบ มิฉะนั้นคืน None
        """
        try:
            import tempfile
            import re
            # เขียน wav ลงไฟล์ชั่วคราวเพื่อให้ faster-whisperอ่าน
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            try:
                torchaudio.save(tmp.name, wav, sr)
            finally:
                tmp.flush(); tmp.close()
            from faster_whisper import WhisperModel
            model_name = os.getenv('WHISPER_MODEL', 'base')
            device = os.getenv('WHISPER_DEVICE', 'cpu')
            model = WhisperModel(model_name, device=device)
            segments, info = model.transcribe(tmp.name, language=os.getenv('WHISPER_LANG', 'th'))
            thai_re = re.compile(r"[\u0E00-\u0E7F]")
            # เลือกเซกเมนต์แรกที่มีอักษรไทย และมีความยาว > 1.0s
            chosen = None
            for seg in segments:
                if thai_re.search(seg.text or "") and (seg.end - seg.start) >= 1.0:
                    chosen = seg
                    break
            if not chosen:
                return None
            start_s = max(0.0, chosen.start - 0.2)
            end_s = min(wav.shape[1] / sr, chosen.end + 0.2)
            start_i = int(start_s * sr)
            end_i = int(end_s * sr)
            return wav[:, start_i:end_i]
        except Exception:
            return None

    def _transcribe_thai(self, audio_path: str) -> str:
        """ถอดข้อความจากไฟล์อ้างอิงด้วย Faster-Whisper บังคับภาษาไทย
        หากล้มเหลวหรือไม่พบข้อความ จะคืนค่าว่าง
        """
        try:
            from faster_whisper import WhisperModel
            model_name = os.getenv('WHISPER_MODEL', 'base')
            device = os.getenv('WHISPER_DEVICE', 'cpu')
            model = WhisperModel(model_name, device=device)
            segments, info = model.transcribe(audio_path, language=os.getenv('WHISPER_LANG', 'th'))
            text = ''.join(seg.text for seg in segments).strip()
            if text:
                logger.info(f"📝 Thai ref_text from Faster-Whisper: {text[:50]}")
            else:
                logger.info("📝 Thai ref_text empty from Faster-Whisper")
            return text
        except Exception as e:
            logger.info(f"⚠️ Thai transcription failed, will let TTS auto-transcribe: {e}")
            return ""

    def _get_silent_reference(self) -> str:
        """สร้างไฟล์เงียบสำหรับ reference"""
        silent_path = "temp_silent_ref.wav"
        
        if not os.path.exists(silent_path):
            duration = 0.5
            silent_audio = np.zeros(int(self.sample_rate * duration), dtype=np.float32)
            silent_tensor = torch.from_numpy(silent_audio).unsqueeze(0)
            torchaudio.save(silent_path, silent_tensor, self.sample_rate)
            logger.info(f"สร้างไฟล์เงียบ: {silent_path}")
        
        return silent_path

    def _generate_silence(self, duration: float) -> bytes:
        """สร้างเสียงเงียบ"""
        silent_audio = np.zeros(int(self.sample_rate * duration), dtype=np.float32)
        return self._to_wav_bytes(silent_audio, self.sample_rate)

    def _synthesize_with_edge_tts(self, text: str) -> bytes:
        """สังเคราะห์เสียงด้วย Edge-TTS (ผ่าน CLI) แล้วแปลงเป็น WAV 24kHz mono เพื่อให้ระบบใช้งานได้ทันที"""
        # ใช้ CLI เพื่อลดปัญหา event loop
        voice = os.getenv("EDGE_TTS_VOICE", "th-TH-AcharaNeural")
        rate = os.getenv("EDGE_TTS_RATE", "+10%")
        pitch = os.getenv("EDGE_TTS_PITCH", "+150Hz")
        ffmpeg_bin = os.getenv("FFMPEG_BINARY", "ffmpeg")

        tmp_dir = os.path.join(os.getcwd(), "temp")
        os.makedirs(tmp_dir, exist_ok=True)
        mp3_path = os.path.join(tmp_dir, "edge_fallback.mp3")
        wav_path = os.path.join(tmp_dir, "edge_fallback.wav")

        # เรียกใช้ edge-tts CLI ผ่าน python -m เพื่อตัดปัญหาการ await
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
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"edge-tts CLI failed: {e}")

        # แปลง MP3 -> WAV 24kHz mono
        try:
            subprocess.check_call([
                ffmpeg_bin,
                "-y",
                "-i", mp3_path,
                "-ar", str(self.sample_rate),
                "-ac", "1",
                wav_path,
            ])
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg convert failed: {e}")

        with open(wav_path, "rb") as rf:
            return rf.read()