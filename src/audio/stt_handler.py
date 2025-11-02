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

import sys
sys.path.append('..')
from core.config import config

class STTHandler:
    """จัดการ Speech-to-Text"""
    
    def __init__(self):
        self.whisper_bin = Path(config.stt.whisper_bin_path)
        self.model_path = Path(config.stt.whisper_model_path)
        self.total_processed = 0
        
        # ตรวจสอบไฟล์
        if not self.whisper_bin.exists():
            print(f"⚠️ ไม่พบ Whisper.cpp: {self.whisper_bin}")
        if not self.model_path.exists():
            print(f"⚠️ ไม่พบโมเดล: {self.model_path}")
    
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
            
            # เรียก Whisper.cpp
            text = await self._run_whisper(tmp_path)
            
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
    
    def _save_wav(self, path: str, audio_data: bytes, sample_rate: int):
        """บันทึกไฟล์ WAV"""
        # แปลง bytes เป็น numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16)
        
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
        
        return await self._run_whisper(file_path)
    
    def get_stats(self):
        """ดูสถิติ"""
        return {
            "total_processed": self.total_processed
        }

# Global STT handler
stt_handler = STTHandler()