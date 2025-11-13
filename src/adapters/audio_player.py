"""
audio_player.py - Discord Audio Player with Lip Sync
เล่นเสียงใน Discord พร้อม Lip Sync กับ VTS
"""

import asyncio
import discord
import logging
import wave
import numpy as np
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DiscordAudioPlayer:
    """เล่นเสียงใน Discord Voice Channel พร้อม Lip Sync"""
    
    def __init__(self, motion_controller=None):
        self.motion_controller = motion_controller
        self.is_playing = False
        self.current_audio_source = None
    
    async def play_audio_with_lipsync(
        self,
        voice_client: discord.VoiceClient,
        audio_file: str,
        text: str = ""
    ) -> bool:
        """
        เล่นเสียงพร้อม Lip Sync
        
        Args:
            voice_client: Discord VoiceClient
            audio_file: path ไฟล์เสียง
            text: ข้อความที่พูด (สำหรับ fallback lip sync)
        
        Returns:
            True = สำเร็จ, False = ล้มเหลว
        """
        if not voice_client or not voice_client.is_connected():
            logger.error("❌ Voice client ไม่ได้เชื่อมต่อ")
            return False
        
        if not Path(audio_file).exists():
            logger.error(f"❌ ไม่พบไฟล์เสียง: {audio_file}")
            return False
        
        try:
            self.is_playing = True
            logger.info(f"🎵 กำลังเล่นเสียง: {audio_file}")
            
            # สร้าง audio source
            audio_source = discord.FFmpegPCMAudio(audio_file)
            
            # เริ่ม lip sync task
            lipsync_task = None
            if self.motion_controller:
                lipsync_task = asyncio.create_task(
                    self._lipsync_from_audio(audio_file, text)
                )
            
            # เล่นเสียง
            voice_client.play(
                audio_source,
                after=lambda e: logger.error(f"Player error: {e}") if e else None
            )
            
            # รอให้เล่นเสร็จ
            while voice_client.is_playing():
                await asyncio.sleep(0.1)
            
            # รอให้ lip sync เสร็จ
            if lipsync_task:
                try:
                    await asyncio.wait_for(lipsync_task, timeout=2.0)
                except asyncio.TimeoutError:
                    lipsync_task.cancel()
            
            # ปิดปาก
            if self.motion_controller:
                try:
                    await self.motion_controller.set_parameter_value("MouthOpen", 0.0)
                except Exception:
                    pass
            
            logger.info("✅ เล่นเสียงเสร็จแล้ว")
            return True
            
        except Exception as e:
            logger.error(f"❌ เล่นเสียงล้มเหลว: {e}", exc_info=True)
            return False
        finally:
            self.is_playing = False
    
    async def _lipsync_from_audio(self, audio_file: str, text: str):
        """Lip sync จากไฟล์เสียง"""
        try:
            # อ่านไฟล์ WAV แบบ non-blocking เพื่อไม่บล็อก event loop
            def _read_wav(path: str):
                import wave as _w
                with _w.open(path, 'rb') as wav:
                    sr = wav.getframerate()
                    n_frames = wav.getnframes()
                    data = wav.readframes(n_frames)
                    return sr, data
            sample_rate, audio_data = await asyncio.to_thread(_read_wav, audio_file)
                
                # แปลงเป็น numpy array
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                
                # คำนวณ RMS แต่ละ chunk (20ms) พร้อม smoothing (attack/decay)
                chunk_size = int(sample_rate * 0.02)  # 20ms
                ema = 0.0
                attack = 0.5   # เร็วขึ้นเมื่อเสียงดังขึ้น
                release = 0.1  # ช้าลงเมื่อเสียงเบาลง
                
                for i in range(0, len(audio_array), chunk_size):
                    chunk = audio_array[i:i+chunk_size]
                    
                    # คำนวณ volume (RMS)
                    rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))
                    # normalize ให้พอดีกับ 16-bit PCM ช่วงทั่วไป
                    volume = min(rms / 2500.0, 1.0)

                    # smoothing ด้วย envelope follower
                    if volume > ema:
                        ema = attack * volume + (1 - attack) * ema
                    else:
                        ema = release * volume + (1 - release) * ema

                    # map เป็นการเปิดปาก พร้อม soft clamp
                    mouth_open = max(0.0, min(1.0, ema * 1.4))
                    
                    if self.motion_controller:
                        await self.motion_controller.set_parameter_value(
                            "MouthOpen", mouth_open
                        )
                    
                    # รอตาม chunk duration
                    await asyncio.sleep(chunk_size / sample_rate)
        
        except Exception as e:
            logger.error(f"❌ Lip sync error: {e}")
            
            # Fallback: ใช้ text-based lip sync
            if text and self.motion_controller:
                await self._lipsync_from_text(text)
    
    async def _lipsync_from_text(self, text: str, speaking_rate: float = 10.0):
        """Lip sync จากข้อความ (fallback)"""
        try:
            vowels = 'aeiouแอะาิีึืุูเโไใไอ็'
            duration = len(text) / speaking_rate
            char_duration = duration / len(text) if len(text) > 0 else 0.1
            
            for char in text:
                if not self.is_playing:
                    break
                
                # กำหนดการเปิดปาก
                if char.lower() in vowels or char in 'าิีึืุู':
                    mouth_open = np.random.uniform(0.6, 1.0)
                elif char.isalpha():
                    mouth_open = np.random.uniform(0.3, 0.6)
                else:
                    mouth_open = 0.1
                
                if self.motion_controller:
                    await self.motion_controller.set_parameter_value(
                        "MouthOpen", mouth_open
                    )
                
                await asyncio.sleep(char_duration)
        
        except Exception as e:
            logger.error(f"❌ Text-based lip sync error: {e}")
    
    def stop(self):
        """หยุดเล่นเสียง"""
        self.is_playing = False