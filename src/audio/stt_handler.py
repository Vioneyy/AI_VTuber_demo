"""
จัดการ Speech-to-Text ด้วย Whisper.cpp
ตำแหน่ง: src/audio/stt_handler.py (แทนที่ stt_whispercpp.py)
"""

import asyncio
import subprocess
import tempfile
import os
import wave
import numpy as np
from pathlib import Path
from typing import Optional
import importlib

import sys
sys.path.append('..')
from core.config import config

class STTHandler:
    """จัดการ Speech-to-Text"""
    
    def __init__(self):
        self.whisper_bin = Path(config.stt.whisper_bin_path)
        self.model_path = Path(config.stt.whisper_model_path)
        self.total_processed = 0
        self._py_whisper_model = None
        self._py_whisper_model_name = os.getenv("PY_WHISPER_MODEL", "medium")
        # ปิด fp16 เป็นดีฟอลต์เพื่อหลีกเลี่ยง error บน GPU/ไดรเวอร์บางรุ่น
        self._py_whisper_fp16 = (os.getenv("PY_WHISPER_FP16", "false").lower() in ("1", "true", "yes"))
        self._py_whisper_fallback_warned = False
        
        # ตรวจสอบไฟล์
        if not self.whisper_bin.exists():
            print(f"⚠️ ไม่พบ Whisper.cpp: {self.whisper_bin}")
        if not self.model_path.exists():
            print(f"⚠️ ไม่พบโมเดล: {self.model_path}")

        # หากไม่มี whisper.cpp ให้เตรียมโหลดโมเดล Python Whisper เพียงครั้งเดียวล่วงหน้า
        try:
            if not self.whisper_bin.exists():
                self._preload_python_whisper()
        except Exception as e:
            # ไม่ให้ล้มเหลวทั้งระบบเพราะ fallback โหลดไม่ได้ในตอนเริ่มต้น
            print(f"⚠️ ไม่สามารถ preload Python Whisper: {e}")
    
    async def transcribe_audio(self, audio_data: bytes, sample_rate: int = 16000) -> Optional[str]:
        """
        แปลงเสียงเป็นข้อความ
        Args:
            audio_data: ข้อมูลเสียง (bytes)
            sample_rate: sample rate (Hz)
        Returns:
            ข้อความ หรือ None ถ้าล้มเหลว
        """
        try:
            # บันทึกเสียงเป็นไฟล์ชั่วคราว
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                tmp_path = tmp_file.name
                self._save_wav(tmp_path, audio_data, sample_rate)
            
            # เรียก Whisper.cpp หรือ fallback ไปใช้ Python Whisper
            text: Optional[str] = None
            if self.whisper_bin.exists():
                text = await self._run_whisper(tmp_path)
                # ถ้า Whisper.cpp ล้มเหลว ลอง fallback แบบ Python อีกครั้ง
                if not text:
                    print("🔁 Whisper.cpp ไม่ได้ผล ลองใช้ Python Whisper แทน")
                    text = await self._run_python_whisper(tmp_path)
            else:
                if not self._py_whisper_fallback_warned:
                    print("🔁 ใช้ Python Whisper fallback (ไม่พบ Whisper.cpp)")
                    self._py_whisper_fallback_warned = True
                text = await self._run_python_whisper(tmp_path)
            
            # ลบไฟล์ชั่วคราว
            try:
                os.unlink(tmp_path)
            except:
                pass
            
            if text:
                self.total_processed += 1
                print(f"🎤 STT Result: '{text}'")
                return text
            
            return None
            
        except Exception as e:
            print(f"❌ STT Error: {e}")
            return None
    
    async def _run_whisper(self, audio_path: str) -> Optional[str]:
        """เรียก Whisper.cpp"""
        try:
            cmd = [
                str(self.whisper_bin),
                "-m", str(self.model_path),
                "-f", audio_path,
                "-l", config.stt.language,
                "-t", str(config.stt.threads),
                "-ng", str(config.stt.n_gpu_layers),
                "-nt",  # no timestamps
                "-otxt"  # output text only
            ]
            
            # รันคำสั่ง
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # รอผลลัพธ์
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=config.stt.timeout_ms / 1000
                )
            except asyncio.TimeoutError:
                process.kill()
                print("⏰ Whisper timeout")
                return None
            
            # ดึงข้อความ
            if process.returncode == 0:
                # Whisper.cpp output ไฟล์ .txt
                txt_path = audio_path + ".txt"
                if Path(txt_path).exists():
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        text = f.read().strip()
                    os.unlink(txt_path)
                    return text if text else None
            
            return None
            
        except Exception as e:
            print(f"❌ Whisper Error: {e}")
            return None

    async def _run_python_whisper(self, audio_path: str) -> Optional[str]:
        """เรียก Python Whisper (openai-whisper) แบบ non-blocking ด้วย to_thread"""
        def _transcribe_blocking() -> Optional[str]:
            try:
                whisper = importlib.import_module("whisper")
            except Exception:
                print("❌ ไม่พบไลบรารี Python Whisper (openai-whisper). ติดตั้งด้วย: pip install -U openai-whisper")
                return None

            try:
                # ตรวจสอบ GPU แบบไดนามิก เพื่อหลีกเลี่ยง error เมื่อไม่มี CUDA
                try:
                    import torch  # ตรวจสอบสถานะ CUDA แบบ runtime
                    use_gpu = torch.cuda.is_available()
                except Exception:
                    use_gpu = False
                device = "cuda" if use_gpu else "cpu"
                # แคชโมเดลไว้ใช้งานซ้ำเพื่อความเร็ว (โหลดครั้งเดียว)
                if self._py_whisper_model is None:
                    # หากยังไม่ถูก preload ให้โหลดที่นี่ (ครั้งเดียว)
                    print(f"⬇️ กำลังโหลดโมเดล Python Whisper: {self._py_whisper_model_name} ({device})")
                    self._py_whisper_model = whisper.load_model(self._py_whisper_model_name, device=device)

                # ใช้ fp16 ตาม ENV เท่านั้น (ดีฟอลต์ False เพื่อความเสถียร)
                fp16 = bool(self._py_whisper_fp16 and use_gpu)
                try:
                    result = self._py_whisper_model.transcribe(
                        audio_path,
                        language=config.stt.language,
                        fp16=fp16,
                    )
                except Exception as e:
                    # แก้เคส GPU shape mismatch โดย retry แบบ fp16=False และ/หรือย้ายไป CPU
                    err_msg = str(e)
                    print(f"⚠️ Python Whisper Error (initial): {err_msg}")
                    try:
                        # Retry ครั้งที่ 1: บังคับ fp16=False บนอุปกรณ์เดิม
                        result = self._py_whisper_model.transcribe(
                            audio_path,
                            language=config.stt.language,
                            fp16=False,
                        )
                    except Exception as e2:
                        print(f"⚠️ Retry fp32 บน {device} ล้มเหลว: {e2}")
                        # Retry ครั้งที่ 2: สุดท้ายย้ายไป CPU ถ้ายังใช้ GPU อยู่
                        try:
                            if use_gpu:
                                cpu_model = whisper.load_model(self._py_whisper_model_name, device="cpu")
                                result = cpu_model.transcribe(
                                    audio_path,
                                    language=config.stt.language,
                                    fp16=False,
                                )
                            else:
                                raise e2
                        except Exception as e3:
                            print(f"❌ Python Whisper Error (retries failed): {e3}")
                            return None

                text = (result.get("text") or "").strip()
                return text if text else None
            except Exception as e:
                print(f"❌ Python Whisper Error: {e}")
                return None

        # รันงานบล็อกแบบ off-thread เพื่อไม่บล็อก event loop
        return await asyncio.to_thread(_transcribe_blocking)
    
    def _save_wav(self, path: str, audio_data: bytes, sample_rate: int):
        """บันทึกไฟล์ WAV"""
        # จัดระเบียบบัฟเฟอร์: ถ้าไม่เป็นจำนวนคู่ของไบต์ ให้แพด 0 เพื่อหลีกเลี่ยง wave error
        if len(audio_data) % 2 != 0:
            audio_data = audio_data + b"\x00"
        # แปลง bytes เป็น numpy array (mono 16-bit)
        audio_np = np.frombuffer(audio_data, dtype=np.int16)
        # ตัวเลือก: downsample เป็น 16k เพื่อช่วยลดภาระ ffmpeg/whisper (ถ้ามี scipy)
        try:
            if sample_rate != 16000:
                from scipy.signal import resample_poly
                # ใช้ polyphase resampling เพื่อคุณภาพและประสิทธิภาพ
                audio_np = resample_poly(audio_np.astype(np.float32), 1, int(sample_rate/16000)).astype(np.int16)
                sample_rate = 16000
        except Exception:
            # ถ้าไม่มี scipy ให้คง sample_rate เดิมไว้ ซอฟต์แวร์จะ resample เอง
            pass
        
        # บันทึกเป็น WAV
        with wave.open(path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_np.tobytes())
    
    async def transcribe_file(self, file_path: str) -> Optional[str]:
        """แปลงไฟล์เสียงเป็นข้อความ"""
        if not Path(file_path).exists():
            print(f"❌ ไม่พบไฟล์: {file_path}")
            return None
        # เลือกใช้ Whisper.cpp หรือ fallback Python
        if self.whisper_bin.exists():
            text = await self._run_whisper(file_path)
            if text:
                return text
            print("🔁 Whisper.cpp ไม่ได้ผล ลองใช้ Python Whisper แทน")
            return await self._run_python_whisper(file_path)
        else:
            print("🔁 ใช้ Python Whisper fallback (ไม่พบ Whisper.cpp)")
            return await self._run_python_whisper(file_path)
    
    def get_stats(self):
        """ดูสถิติ"""
        return {
            "total_processed": self.total_processed
        }

    # ภายใน: โหลดโมเดล Python Whisper ล่วงหน้า (ครั้งเดียว)
    def _preload_python_whisper(self):
        try:
            whisper = importlib.import_module("whisper")
        except Exception:
            print("❌ ไม่พบไลบรารี Python Whisper (openai-whisper). ติดตั้งด้วย: pip install -U openai-whisper")
            return

        # ตรวจสอบ GPU แบบไดนามิก
        try:
            import torch
            use_gpu = torch.cuda.is_available()
        except Exception:
            use_gpu = False
        device = "cuda" if use_gpu else "cpu"

        if self._py_whisper_model is None:
            print(f"⬇️ กำลังโหลดโมเดล Python Whisper: {self._py_whisper_model_name} ({device})")
            self._py_whisper_model = whisper.load_model(self._py_whisper_model_name, device=device)

# Global STT handler
stt_handler = STTHandler()