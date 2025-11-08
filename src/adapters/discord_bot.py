"""
Discord Bot Adapter - Fixed Voice Reception
แก้ไข:
1. รับเสียงซ้ำๆ รัวๆ
2. Voice activity detection
3. Proper audio buffering
"""
import discord
from discord.ext import commands, voice_recv
import asyncio
import logging
from typing import Optional, Callable
import io
import time
import numpy as np
import wave
from pathlib import Path
from datetime import datetime
from core.config import config

logger = logging.getLogger(__name__)

class DiscordBotAdapter:
    """Discord Bot with fixed voice reception"""
    
    def __init__(self, token: str, admin_ids: set):
        """Initialize bot"""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        intents.members = True
        
        self.bot = commands.Bot(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        
        self.token = token
        self.admin_ids = admin_ids
        
        # Callbacks
        self.on_voice_input: Optional[Callable] = None
        # callback สำหรับคำสั่งข้อความ end-to-end
        self.on_text_command: Optional[Callable] = None
        
        # Voice state
        self.is_recording = False
        self.voice_client: Optional[discord.VoiceClient] = None
        
        # Voice activity detection
        self.user_audio_buffers = {}  # user_id -> audio_buffer
        self.user_last_voice = {}  # user_id -> timestamp
        # ปรับได้ผ่าน .env: DISCORD_VOICE_SILENCE_THRESHOLD, DISCORD_VOICE_MIN_AUDIO_DURATION
        self.silence_threshold = getattr(config.discord, "voice_silence_threshold", 0.7)
        self.min_audio_duration = getattr(config.discord, "voice_min_audio_duration", 0.35)
        
        # Prevent duplicate processing
        self.processing_users = set()  # users currently being processed
        
        # สถานะจากระบบภายนอก (VTS/Queue/TTS)
        self.external_status = {
            'vts_connected': False,
            'tts_ready': False,
            'queue_ready': False
        }
        
        self._register_events()
        self._register_commands()
        
        logger.info("✅ Discord Bot initialized")
        logger.info(
            f"Discord voice settings: silence_threshold={self.silence_threshold}, min_audio_duration={self.min_audio_duration}"
        )
    
    def _register_events(self):
        """Register bot events"""
        
        @self.bot.event
        async def on_ready():
            """Bot ready"""
            logger.info(f"✅ Discord Bot พร้อมแล้ว: {self.bot.user}")
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name="🎤 คำสั่งเสียง"
                )
            )
        
        @self.bot.event
        async def on_voice_state_update(member, before, after):
            """Voice state changed"""
            if member == self.bot.user:
                if before.channel and not after.channel:
                    logger.info("👋 ถูก disconnect จากห้องเสียง")
                    self.voice_client = None
                    self.is_recording = False
                    self._clear_audio_buffers()
    
    def _register_commands(self):
        """Register commands"""
        
        @self.bot.command(name='join')
        async def join(ctx):
            """เข้าห้องเสียง"""
            try:
                if not ctx.author.voice:
                    await ctx.send("❌ คุณต้องอยู่ในห้องเสียงก่อนค่ะ!")
                    return
                
                channel = ctx.author.voice.channel
                
                # Disconnect ก่อนถ้ามี
                if self.voice_client:
                    try:
                        await self.voice_client.disconnect(force=True)
                    except:
                        pass
                    self.voice_client = None
                    await asyncio.sleep(1)
                
                # Connect with VoiceRecvClient to enable voice receiving
                self.voice_client = await channel.connect(
                    timeout=10.0,
                    reconnect=False,
                    cls=voice_recv.VoiceRecvClient
                )
                
                logger.info(f"✅ เชื่อมต่อห้อง: {channel.name}")
                await ctx.send(f"✅ เข้าห้อง {channel.name} แล้วค่ะ!")
                
                # เริ่มฟัง
                await self._start_listening()
                
            except Exception as e:
                logger.error(f"Error in join: {e}")
                await ctx.send(f"❌ Error: {e}")
        
        @self.bot.command(name='leave')
        async def leave(ctx):
            """ออกจากห้องเสียง"""
            if not self.voice_client:
                await ctx.send("❌ ไม่ได้อยู่ในห้องเสียงค่ะ")
                return
            
            try:
                await self.voice_client.disconnect(force=True)
                self.voice_client = None
                self.is_recording = False
                self._clear_audio_buffers()
                logger.info("👋 ออกจากห้องเสียง")
                await ctx.send("👋 บายบาย~")
            except Exception as e:
                logger.error(f"Error leaving: {e}")
        
        @self.bot.command(name='test')
        async def test(ctx):
            """ทดสอบ"""
            await ctx.send("✅ ระบบทำงานปกติค่ะ!")

        @self.bot.command(name='voice')
        async def voice(ctx, state: Optional[str] = None):
            """เปิด/ปิดการรับเสียง: !voice on / !voice off"""
            try:
                if not self.voice_client:
                    await ctx.send("ℹ️ กรุณาใช้ !join เพื่อเข้าห้องเสียงก่อนนะคะ")
                    return

                if not state:
                    await ctx.send(f"🎤 สถานะรับเสียงตอนนี้: {'เปิด' if self.is_recording else 'ปิด'} (ใช้ !voice on/off)")
                    return

                s = state.lower()
                if s == 'on':
                    self.is_recording = True
                    # เริ่มฟังใหม่เพื่อเคลียร์บัฟเฟอร์และตั้ง callback
                    await self._start_listening()
                    await ctx.send("🎤 เปิดรับเสียงแล้วค่ะ")
                elif s == 'off':
                    self.is_recording = False
                    await ctx.send("🔇 ปิดรับเสียงแล้วค่ะ")
                else:
                    await ctx.send("❌ ใช้: !voice on หรือ !voice off")
            except Exception as e:
                logger.error(f"voice command error: {e}")
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

        @self.bot.command(name='ask')
        async def ask(ctx, *, question: Optional[str] = None):
            """ส่งคำถามแบบ end-to-end: !ask <ข้อความ>"""
            try:
                if not question or not question.strip():
                    await ctx.send("❌ ใช้: !ask <คำถามของคุณ>")
                    return

                if not self.on_text_command:
                    await ctx.send("⚠️ ระบบยังไม่พร้อมรับคำถามผ่านข้อความ")
                    return

                await ctx.send("🧠 รับคำถามแล้ว กำลังคิดคำตอบให้ค่ะ…")
                # ส่งไปให้ pipeline หลักจัดคิวและสร้างเสียง
                await self.on_text_command(str(ctx.author.id), question.strip())
            except Exception as e:
                logger.error(f"ask command error: {e}")
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

        @self.bot.command(name='rvc')
        async def rvc(ctx, state: Optional[str] = None):
            """เปิด/ปิด RVC: !rvc on / !rvc off"""
            try:
                # จำกัดสิทธิ์เบื้องต้น: เฉพาะ admin_ids หากกำหนดไว้
                if self.admin_ids and str(ctx.author.id) not in {str(x) for x in self.admin_ids}:
                    await ctx.send("❌ คุณไม่มีสิทธิ์เปลี่ยนการตั้งค่า RVC")
                    return

                if not state:
                    await ctx.send(f"🎵 RVC: {'เปิด' if getattr(config.rvc, 'enabled', False) else 'ปิด'} | โมเดล: {getattr(config.rvc, 'model_path', 'ไม่ตั้งค่า')}")
                    return

                s = state.lower()
                if s == 'on':
                    config.rvc.enabled = True
                    await ctx.send("🎵 เปิด RVC แล้วค่ะ")
                elif s == 'off':
                    config.rvc.enabled = False
                    await ctx.send("🎵 ปิด RVC แล้วค่ะ (จะใช้เสียง TTS ตรง)")
                else:
                    await ctx.send("❌ ใช้: !rvc on หรือ !rvc off")
            except Exception as e:
                logger.error(f"rvc command error: {e}")
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

        @self.bot.command(name='status')
        async def status(ctx):
            """แสดงสถานะระบบโดยย่อ"""
            try:
                lines = [
                    "📊 **สถานะระบบ**",
                    f"- Discord Voice: {'เชื่อมต่อ' if self.voice_client else 'ไม่ได้เชื่อมต่อ'}",
                    f"- รับเสียง: {'เปิด' if self.is_recording else 'ปิด'}",
                    f"- VTS: {'พร้อม' if self.external_status.get('vts_connected') else 'ไม่พร้อม'}",
                    f"- TTS: {'พร้อม' if self.external_status.get('tts_ready') else 'ไม่พร้อม'}",
                    f"- Queue: {'พร้อม' if self.external_status.get('queue_ready') else 'ไม่พร้อม'}",
                    f"- RVC: {'เปิด' if getattr(config.rvc, 'enabled', False) else 'ปิด'}",
                ]
                await ctx.send("\n".join(lines))
            except Exception as e:
                logger.error(f"status command error: {e}")
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

        @self.bot.command(name='help')
        async def help_cmd(ctx):
            """แสดงคู่มือคำสั่งสั้น ๆ"""
            try:
                cmds = [
                    "📝 **คำสั่ง Jeed Bot**",
                    "!join — ให้บอทเข้าห้องเสียง",
                    "!leave — ให้บอทออกจากห้องเสียง",
                    "!voice on/off — เปิด/ปิดการรับเสียงจากผู้ใช้",
                    "!ask <ข้อความ> — ส่งคำถามเพื่อให้บอทคิด-พูดตอบ",
                    "!rvc on/off — เปิด/ปิดการใช้ RVC",
                    "!status — ดูสถานะระบบโดยย่อ",
                ]
                await ctx.send("\n".join(cmds))
            except Exception as e:
                logger.error(f"help command error: {e}")
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")
    
    async def _start_listening(self):
        """เริ่มฟังเสียง"""
        if not self.voice_client:
            return
        
        self.is_recording = True
        self._clear_audio_buffers()
        
        logger.info("👂 เริ่มฟังเสียง...")
        
        # Create callback sink
        def voice_callback(user, data):
            """Callback เมื่อได้รับเสียง (เรียกจาก thread ของ voice router)"""
            if not self.is_recording:
                return

            # Ignore bot
            if user.bot:
                return

            # Copy PCM bytes to avoid cross-thread object lifetime issues
            try:
                audio_bytes = bytes(data.pcm)
            except Exception:
                return

            # Schedule coroutine on bot's event loop thread-safely
            try:
                self.bot.loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._buffer_audio(user, audio_bytes))
                )
            except Exception as e:
                logger.error(f"Error scheduling audio buffer: {e}")
        
        # Start recording
        self.voice_client.listen(voice_recv.BasicSink(voice_callback))
    
    async def _buffer_audio(self, user, audio_bytes: bytes):
        """
        Buffer audio และตรวจจับว่าผู้ใช้พูดจบแล้วหรือยัง
        """
        user_id = str(user.id)
        current_time = time.time()
        
        # Initialize buffer
        if user_id not in self.user_audio_buffers:
            self.user_audio_buffers[user_id] = bytearray()
        
        # เช็คว่ากำลัง process อยู่หรือไม่
        if user_id in self.processing_users:
            return  # ข้ามไปเพราะยังไม่เสร็จ
        
        # Append audio
        self.user_audio_buffers[user_id].extend(audio_bytes)
        self.user_last_voice[user_id] = current_time
        
        # เช็คว่าเงียบนานพอหรือยัง (หมายถึงพูดจบแล้ว)
        await asyncio.sleep(self.silence_threshold)
        
        # เช็คอีกครั้งว่ายังเงียบอยู่หรือไม่
        if user_id in self.user_last_voice:
            time_since_last = time.time() - self.user_last_voice[user_id]
            
            if time_since_last >= self.silence_threshold:
                # พูดจบแล้ว - ส่งไป process
                await self._process_buffered_audio(user, user_id)
    
    async def _process_buffered_audio(self, user, user_id: str):
        """Process audio ที่ buffer ไว้"""
        try:
            # ป้องกันการ process ซ้ำ
            if user_id in self.processing_users:
                return
            
            self.processing_users.add(user_id)
            
            # Get buffered audio
            if user_id not in self.user_audio_buffers:
                return
            
            audio_bytes = bytes(self.user_audio_buffers[user_id])

            # เช็คความยาว
            # Discord voice_recv provides PCM int16 mono @ 48kHz
            duration = len(audio_bytes) / (48000 * 2)  # 48kHz, mono, int16

            if duration < self.min_audio_duration:
                logger.debug(f"Audio too short: {duration:.2f}s from {user.name}")
                return

            logger.info(f"🎤 Received voice from {user.name}")

            # บันทึกเสียงที่พูดเป็นไฟล์ WAV (mono 16-bit @48kHz)
            try:
                if config.discord.voice_record_enabled:
                    record_dir = Path(config.discord.voice_record_dir)
                    record_dir.mkdir(parents=True, exist_ok=True)

                    safe_name = ''.join(c for c in user.name if c.isalnum() or c in ('-', '_')) or 'user'
                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                    out_path = record_dir / f"{safe_name}_{ts}.wav"

                    with wave.open(str(out_path), 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)  # int16
                        wf.setframerate(48000)
                        wf.writeframes(audio_bytes)

                    logger.info(f"💾 Saved voice recording: {out_path} ({duration:.2f}s)")
            except Exception as rec_err:
                logger.warning(f"⚠️ Failed to save voice recording: {rec_err}")

            # Clear buffer
            del self.user_audio_buffers[user_id]
            del self.user_last_voice[user_id]

            # Send to callback
            if self.on_voice_input:
                await self.on_voice_input(user, audio_bytes, 48000)
            
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
        finally:
            # อนุญาตให้ process ใหม่ได้
            if user_id in self.processing_users:
                self.processing_users.remove(user_id)
    
    def _clear_audio_buffers(self):
        """ล้าง audio buffers"""
        self.user_audio_buffers.clear()
        self.user_last_voice.clear()
        self.processing_users.clear()
        logger.debug("🧹 Cleared audio buffers")
    
    async def _ensure_single_playback(self):
        """หยุดการเล่นเดิมให้หมดก่อนเริ่มใหม่ และล้างบัฟเฟอร์"""
        try:
            if self.voice_client and self.voice_client.is_playing():
                logger.debug("🛑 VoiceClient is playing, stopping current audio")
                self.voice_client.stop()
                # รอเล็กน้อยเพื่อให้ Opus flush เฟรมที่ค้างอยู่
                await asyncio.sleep(0.1)
        except Exception:
            pass
        # ล้างบัฟเฟอร์รับเสียงเพื่อหลีกเลี่ยง feedback/queue ทับซ้อน
        self._clear_audio_buffers()

    
    async def play_audio(self, audio_data: np.ndarray, sample_rate: int):
        """เล่นเสียง"""
        if not self.voice_client or not self.voice_client.is_connected():
            logger.warning("⚠️  ไม่ได้เชื่อมต่อ voice channel")
            return
        
        try:
            # ป้องกันเล่นหลายสตรีมซ้อนกัน และป้องกันฟังเสียงตัวเองระหว่างเล่น
            # ปิดการบันทึกชั่วคราว
            prev_recording = self.is_recording
            self.is_recording = False

            # หยุดการเล่นเดิมให้หมดและล้างบัฟเฟอร์
            await self._ensure_single_playback()

            # แปลง numpy array เป็น audio source
            audio_source = NumpyAudioSource(audio_data, sample_rate)
            
            # บันทึกเสียงออกจากบอท (PCM16 mono @48kHz) เป็นไฟล์ WAV
            try:
                from core.config import config
                if getattr(config.discord, 'voice_playback_record_enabled', False):
                    from datetime import datetime
                    record_dir = Path(getattr(config.discord, 'voice_playback_record_dir', 'temp/recordings/discord_out'))
                    record_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                    # ใช้ชื่อไฟล์ระบุว่าเป็นบอท
                    out_path = record_dir / f"bot_{ts}.wav"
                    # เขียนเป็น WAV 16-bit @48kHz จาก audio_source.audio_bytes
                    import wave
                    with wave.open(str(out_path), 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)  # 16-bit
                        wf.setframerate(48000)
                        wf.writeframes(audio_source.audio_bytes)
                    logger.info(f"💾 Saved bot playback: {out_path}")
            except Exception as rec_e:
                logger.warning(f"⚠️ Failed to save bot playback: {rec_e}")
            
            # เล่นเสียง
            self.voice_client.play(audio_source)
            
            logger.info("🔊 Playing audio...")
            
            # รอจนเล่นเสร็จ
            while self.voice_client.is_playing():
                await asyncio.sleep(0.1)
            
            logger.info("✅ Audio playback completed")
            
        except Exception as e:
            logger.error(f"Error playing audio: {e}", exc_info=True)
        finally:
            # เปิดการฟังเสียงอีกครั้งหลังเล่นเสร็จ
            self.is_recording = prev_recording
    
    async def start(self):
        """Start bot"""
        try:
            await self.bot.start(self.token)
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise
    
    async def stop(self):
        """Stop bot"""
        try:
            self.is_recording = False
            self._clear_audio_buffers()
            
            if self.voice_client:
                await self.voice_client.disconnect(force=True)
            
            await self.bot.close()
            logger.info("👋 Discord Bot stopped")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")

    def update_external_status(self, vts_connected: bool = False, tts_ready: bool = False, queue_ready: bool = False):
        """อัปเดตสถานะจากระบบภายนอก (สำหรับ !status)"""
        try:
            self.external_status.update({
                'vts_connected': bool(vts_connected),
                'tts_ready': bool(tts_ready),
                'queue_ready': bool(queue_ready),
            })
            # ปรับ presence เล็กน้อยตามสถานะ
            try:
                status_txt = f"🎤 Voice {'ON' if self.is_recording else 'OFF'} | TTS {'OK' if tts_ready else 'X'} | RVC {'ON' if getattr(config.rvc, 'enabled', False) else 'OFF'}"
                asyncio.create_task(self.bot.change_presence(
                    activity=discord.Activity(type=discord.ActivityType.listening, name=status_txt)
                ))
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"update_external_status error: {e}")


class NumpyAudioSource(discord.AudioSource):
    """Audio source จาก numpy array"""
    
    def __init__(self, audio_data: np.ndarray, sample_rate: int):
        """
        Args:
            audio_data: Audio data (numpy array, float32)
            sample_rate: Sample rate
        """
        # Debug stats (before any processing)
        try:
            pre_mean = float(np.mean(audio_data))
            pre_peak = float(np.max(np.abs(audio_data)))
            pre_rms = float(np.sqrt(np.mean(audio_data**2)))
            logger.info(f"[Playback] In stats: mean={pre_mean:.6f}, peak={pre_peak:.6f}, rms={pre_rms:.6f}, sr={sample_rate}")
        except Exception:
            pass

        # Optional: save raw input for debugging
        try:
            from core.config import config as _cfg
            if getattr(_cfg.discord, 'voice_playback_debug_enabled', False):
                from datetime import datetime
                from pathlib import Path as _P
                import soundfile as _sf
                dbg_dir = _P(getattr(_cfg.discord, 'voice_playback_debug_dir', 'temp/recordings/discord_out'))
                dbg_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                _sf.write(str(dbg_dir / f"bot_pre_in_{ts}.wav"), audio_data.astype(np.float32), sample_rate)
        except Exception as e:
            logger.debug(f"Debug save (pre-in) failed: {e}")

        # Resample to 48kHz (Discord requirement)
        if sample_rate != 48000:
            try:
                from scipy.signal import resample_poly
                audio_data = resample_poly(audio_data, 48000, sample_rate)
            except Exception:
                # Fallback: linear interpolation
                new_len = int(len(audio_data) * 48000 / sample_rate)
                x_old = np.linspace(0.0, 1.0, num=len(audio_data), endpoint=False)
                x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
                audio_data = np.interp(x_new, x_old, audio_data)
        
        # Remove DC offset
        try:
            audio_data = (audio_data - float(np.mean(audio_data))).astype(np.float32)
        except Exception:
            pass

        # Gentle low-pass to reduce hiss (~12 kHz)
        try:
            from scipy.signal import butter, filtfilt
            nyq = 0.5 * 48000.0
            cutoff = 12000.0 / nyq
            if 0.0 < cutoff < 1.0:
                b, a = butter(4, cutoff, btype='low')
                audio_data = filtfilt(b, a, audio_data).astype(np.float32)
        except Exception:
            pass

        # Soft limiter to avoid clicks/pops from sudden peaks
        try:
            audio_data = (np.tanh(1.2 * audio_data) / np.tanh(1.2)).astype(np.float32)
        except Exception:
            pass

        # Ensure in range [-1, 1]
        max_val = np.abs(audio_data).max()
        if max_val > 0:
            audio_data = audio_data / max_val * 0.95

        # Debug stats after processing (still float)
        try:
            aft_mean = float(np.mean(audio_data))
            aft_peak = float(np.max(np.abs(audio_data)))
            aft_rms = float(np.sqrt(np.mean(audio_data**2)))
            logger.info(f"[Playback] Proc stats: mean={aft_mean:.6f}, peak={aft_peak:.6f}, rms={aft_rms:.6f} @48k")
        except Exception:
            pass

        # Optional: save processed float audio at 48k for debugging
        try:
            from core.config import config as _cfg
            if getattr(_cfg.discord, 'voice_playback_debug_enabled', False):
                from datetime import datetime
                from pathlib import Path as _P
                import soundfile as _sf
                dbg_dir = _P(getattr(_cfg.discord, 'voice_playback_debug_dir', 'temp/recordings/discord_out'))
                dbg_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                _sf.write(str(dbg_dir / f"bot_post_proc_{ts}.wav"), audio_data.astype(np.float32), 48000)
        except Exception as e:
            logger.debug(f"Debug save (post-proc) failed: {e}")

        # Apply short fade in/out to reduce clicks/pops (10ms each)
        try:
            fade_samples = int(0.01 * 48000)
            if fade_samples > 0 and audio_data.size > (2 * fade_samples):
                ramp_in = np.linspace(0.0, 1.0, fade_samples, endpoint=False, dtype=np.float32)
                ramp_out = np.linspace(1.0, 0.0, fade_samples, endpoint=False, dtype=np.float32)
                audio_data[:fade_samples] *= ramp_in
                audio_data[-fade_samples:] *= ramp_out
        except Exception as e:
            logger.debug(f"Fade-in/out failed: {e}")
        
        # Convert to int16
        audio_data = np.clip(audio_data, -1.0, 1.0)
        audio_data = (audio_data * 32767).astype(np.int16)
        
        # Convert to bytes
        self.audio_bytes = audio_data.tobytes()

        # Optional: save final PCM16 stream as WAV (48k) for debugging
        try:
            from core.config import config as _cfg
            if getattr(_cfg.discord, 'voice_playback_debug_enabled', False):
                from datetime import datetime
                from pathlib import Path as _P
                import wave as _wave
                dbg_dir = _P(getattr(_cfg.discord, 'voice_playback_debug_dir', 'temp/recordings/discord_out'))
                dbg_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                out_path = dbg_dir / f"bot_final_pcm_{ts}.wav"
                with _wave.open(str(out_path), 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(48000)
                    wf.writeframes(self.audio_bytes)
        except Exception as e:
            logger.debug(f"Debug save (final-pcm) failed: {e}")
        
        # Pad trailing silence to help Opus encoder flush (≈40ms)
        try:
            tail_pad_ms = 40
            pad_samples = int(48000 * (tail_pad_ms / 1000.0))
            pad_bytes = pad_samples * 2  # int16 mono
            if pad_bytes > 0:
                self.audio_bytes += b"\x00" * pad_bytes
        except Exception as e:
            logger.debug(f"Tail pad failed: {e}")
        self.position = 0
        
        # Discord expects 20ms frames at 48kHz
        # 48000 samples/sec * 0.02 sec = 960 samples
        # 960 samples * 2 bytes = 1920 bytes per frame
        self.frame_size = 1920
    
    def read(self) -> bytes:
        """Read next audio frame"""
        if self.position >= len(self.audio_bytes):
            return b''
        
        frame = self.audio_bytes[self.position:self.position + self.frame_size]
        self.position += self.frame_size
        
        # Pad if needed
        if len(frame) < self.frame_size:
            frame += b'\x00' * (self.frame_size - len(frame))
        
        return frame
    
    def is_opus(self) -> bool:
        """Not Opus encoded"""
        return False