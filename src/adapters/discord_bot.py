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
    
    def __init__(self, token: str, admin_ids: set, motion_controller=None):
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
        # ตัวควบคุม VTS สำหรับ lipsync ตรงกับเสียงที่เล่น
        self.motion_controller = motion_controller
        
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
            # แสดง presence สั้น ๆ ให้รู้ว่ามีคำสั่งอะไรบ้าง
            try:
                await self.bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.listening,
                        name="ใช้ !help | !join | !voice | !ask"
                    )
                )
            except Exception:
                pass
            
            # ส่งข้อความช่วยเหลือไปยัง system channel (ถ้ามีสิทธิ์และยังไม่ส่ง)
            try:
                if not hasattr(self, "_help_broadcasted") or not self._help_broadcasted:
                    help_text = (
                        "📝 **คำสั่ง Jeed Bot**\n"
                        "!join — ให้บอทเข้าห้องเสียง\n"
                        "!leave — ให้บอทออกจากห้องเสียง\n"
                        "!voice on/off — เปิด/ปิดการรับเสียงจากผู้ใช้\n"
                        "!ask <ข้อความ> — ส่งคำถามเพื่อให้บอทคิด-พูดตอบ\n"
                        "!status — ดูสถานะระบบโดยย่อ\n"
                        "!help — แสดงคู่มือคำสั่งนี้อีกครั้ง"
                    )
                    for guild in self.bot.guilds:
                        channel = getattr(guild, 'system_channel', None)
                        if channel:
                            perms = channel.permissions_for(guild.me)
                            if getattr(perms, 'send_messages', False):
                                try:
                                    await channel.send(help_text)
                                except Exception:
                                    continue
                    self._help_broadcasted = True
            except Exception:
                pass
        
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
                
                # ไม่เริ่มฟังอัตโนมัติ ให้ใช้ !voice on เพื่อเริ่มรับเสียง
                
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
                    # หากระบบปิด STT ไว้ ให้บล็อคการรับเสียงและแนะนำให้ใช้ !ask
                    stt_enabled = bool(getattr(config, 'DISCORD_VOICE_STT_ENABLED', False)) or bool(getattr(config.discord, 'stt_enabled', False))
                    if not stt_enabled:
                        await ctx.send("🔇 ปิด STT ตามการตั้งค่า (.env) — จะไม่รับเสียงนะคะ ใช้ !ask เพื่อถามด้วยข้อความแทน")
                        return
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

        # ลบคำสั่ง RVC ออก (ใช้งานเฉพาะ TTS เท่านั้น)

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
        # หาก STT ถูกปิดใช้งาน ให้ไม่เริ่มรับเสียงเพื่อหลีกเลี่ยงการใช้ทรัพยากร
        stt_enabled = bool(getattr(config, 'DISCORD_VOICE_STT_ENABLED', False)) or bool(getattr(config.discord, 'stt_enabled', False))
        if not stt_enabled:
            logger.info("🔇 ข้ามการเริ่มฟังเสียง: STT ถูกปิดใช้งาน")
            self.is_recording = False
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
            # หาก STT ถูกปิดใช้งาน ให้ไม่ประมวลผลเสียงใด ๆ
            stt_enabled = bool(getattr(config, 'DISCORD_VOICE_STT_ENABLED', False)) or bool(getattr(config.discord, 'stt_enabled', False))
            if not stt_enabled:
                return
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
        """เล่นเสียง (ไม่บล็อก event loop)"""
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
            
            # บันทึกเสียงออกจากบอท (PCM16 stereo @48kHz) เป็นไฟล์ WAV
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
                        wf.setnchannels(2)
                        wf.setsampwidth(2)  # 16-bit
                        wf.setframerate(48000)
                        wf.writeframes(audio_source.audio_bytes)
                    logger.info(f"💾 Saved bot playback: {out_path}")
            except Exception as rec_e:
                logger.warning(f"⚠️ Failed to save bot playback: {rec_e}")
            
            # ใช้ Event เพื่อรอจบการเล่นแบบ non-blocking
            playback_done = asyncio.Event()
            audio_source.finished_callback = lambda: playback_done.set()

            # เล่นเสียง
            self.voice_client.play(audio_source)
            logger.info("🔊 Playing audio...")

            # เริ่มลิปซิงค์พร้อมกับการเล่นเสียง (ถ้ามี motion_controller)
            lipsync_task = None
            if self.motion_controller is not None:
                lipsync_task = asyncio.create_task(self._lipsync_for_playback(audio_source))

            try:
                await asyncio.wait_for(playback_done.wait(), timeout=60.0)
                logger.info("✅ Audio playback completed")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Audio playback timeout; stopping.")
            finally:
                self._is_playing = False
                # ปิดปากและกลับสู่ idle อย่างนุ่มนวล
                if self.motion_controller is not None:
                    try:
                        await self.motion_controller.stop_speaking()
                        await self.motion_controller.update_idle_motion()
                    except Exception:
                        pass
            
        except Exception as e:
            logger.error(f"Error playing audio: {e}", exc_info=True)
        finally:
            # เปิดการฟังเสียงอีกครั้งหลังเล่นเสร็จ
            self.is_recording = prev_recording

    async def _lipsync_for_playback(self, audio_source: 'NumpyAudioSource'):
        """ขับเคลื่อนลิปซิงค์แบบ realtime ตามเสียงที่เล่นจริง"""
        try:
            # รอจนเริ่มเล่นจริงเพื่อซิงค์เวลาให้ตรงที่สุด
            for _ in range(50):
                if self.voice_client and self.voice_client.is_playing():
                    break
                await asyncio.sleep(0.01)

            # เปิดโหมดพูดเมื่อเริ่มเล่นจริง เพื่อลดการกระตุกก่อนเริ่มเสียง
            try:
                if self.motion_controller is not None:
                    await self.motion_controller.set_talking(True)
                    logger.info("🗣️ เริ่มลิปซิงค์หลังเสียงเริ่มเล่นจริง")
            except Exception:
                pass

            samples = getattr(audio_source, 'mono_samples', None)
            if samples is None or samples.size == 0:
                return

            sr = 48000
            chunk = 480  # 10ms chunks สำหรับ response ที่ดีขึ้น

            # ✅ ปรับค่า smoothing ให้เร็วและตอบสนองดีขึ้น
            ema = 0.0
            attack = 0.85   # เปิดปากเร็ว
            release = 0.75  # ปิดปากเร็ว (แก้ไขจาก 0.12)
            scale = 1.6     # เพิ่มการอ้าปาก

            # ✅ Silence detection ที่แม่นยำขึ้น
            silence_threshold = 0.015
            consecutive_silent = 0
            max_silent_chunks = 3  # ปิดปากเร็วหลังเงียบ 30ms

            i = 0
            mouth_open = 0.0
            last_mouth = 0.0
            while self.voice_client and self.voice_client.is_playing() and i < samples.size:
                seg = samples[i:i+chunk]
                if seg.size == 0:
                    break

                # คำนวณ RMS และตอบสนองแบบ realtime
                rms = float(np.sqrt(np.mean(seg.astype(np.float32) ** 2)))
                
                # ✅ ตรวจจับเงียบ
                if rms < silence_threshold:
                    consecutive_silent += 1
                else:
                    consecutive_silent = 0

                # ✅ ปิดปากทันทีเมื่อเงียบ
                if consecutive_silent >= max_silent_chunks:
                    mouth_open = 0.0
                    ema = 0.0
                else:
                    # Normalize volume ให้ sensitive ขึ้น
                    vol = min(rms / 0.15, 1.0)
                    
                    # Smoothing
                    if vol > ema:
                        ema = attack * vol + (1 - attack) * ema
                    else:
                        ema = release * vol + (1 - release) * ema
                    
                    # ✅ เพิ่ม micro-variation ให้ดูเป็นธรรมชาติ
                    variation = float(np.random.uniform(0.95, 1.05))
                    mouth_open = max(0.0, min(1.0, ema * scale * variation))

                # ✅ ส่งเฉพาะเมื่อเปลี่ยนแปลงมากพอ (ลด jitter)
                if abs(mouth_open - last_mouth) > 0.03:
                    try:
                        await self.motion_controller.set_parameter_value(
                            "MouthOpen", mouth_open, immediate=False
                        )
                        last_mouth = mouth_open
                    except Exception:
                        pass

                i += chunk
                await asyncio.sleep(chunk / sr)

            # ปิดปากอย่างนุ่มนวล
            try:
                steps = 4
                for step in range(steps):
                    val = last_mouth * (1 - (step + 1) / steps)
                    await self.motion_controller.set_parameter_value("MouthOpen", val, immediate=False)
                    await asyncio.sleep(0.015)
                await self.motion_controller.set_parameter_value("MouthOpen", 0.0)
                logger.info("🔚 จบลิปซิงค์และปิดปากอย่างนุ่มนวล")
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Lipsync error: {e}")
    
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
                # เรียก change_presence เฉพาะเมื่อ websocket พร้อมแล้ว เพื่อหลีกเลี่ยง Task exception
                if getattr(self.bot, 'ws', None) is not None:
                    status_txt = f"🎤 Voice {'ON' if self.is_recording else 'OFF'} | TTS {'OK' if tts_ready else 'X'}"
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
        # ✅ callback เมื่อจบการเล่น
        self.finished_callback = None
        # Debug stats (before any processing)
        try:
            pre_mean = float(np.mean(audio_data))
            pre_peak = float(np.max(np.abs(audio_data)))
            pre_rms = float(np.sqrt(np.mean(audio_data**2)))
            logger.info(f"[Playback] In stats: mean={pre_mean:.6f}, peak={pre_peak:.6f}, rms={pre_rms:.6f}, sr={sample_rate}")
        except Exception:
            pass

        # จัดการจำนวนแชนเนลให้เป็น mono ก่อน (ถ้าจำเป็น)
        try:
            if isinstance(audio_data, np.ndarray) and audio_data.ndim == 2:
                # ถ้าเป็นสเตอริโออยู่แล้ว ให้แปลงเป็น mono โดยเฉลี่ย เพื่อหลีกเลี่ยงการแตกต่างของ channel
                if audio_data.shape[1] >= 2:
                    audio_data = audio_data.mean(axis=1).astype(np.float32)
                else:
                    audio_data = audio_data.reshape(-1).astype(np.float32)
        except Exception:
            # หากตรวจรูปทรงล้มเหลว ใช้แบบเดิม
            try:
                audio_data = audio_data.astype(np.float32)
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
                from math import gcd
                from scipy.signal import resample_poly
                g = gcd(int(sample_rate), 48000)
                up = int(48000 // g)
                down = int(sample_rate // g)
                audio_data = resample_poly(audio_data, up, down).astype(np.float32)
            except Exception:
                # Fallback: linear interpolation (คุณภาพรองลงมา)
                new_len = int(len(audio_data) * 48000 / float(sample_rate))
                x_old = np.linspace(0.0, 1.0, num=len(audio_data), endpoint=False)
                x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
                audio_data = np.interp(x_new, x_old, audio_data).astype(np.float32)
        
        # Remove DC offset (เฉพาะกรณีมี DC จริง ๆ)
        try:
            mean_val = float(np.mean(audio_data))
            if abs(mean_val) > 1e-5:
                audio_data = (audio_data - mean_val).astype(np.float32)
            else:
                audio_data = audio_data.astype(np.float32)
        except Exception:
            pass

        # Gentle low-pass ~18 kHz เพื่อลดภาพการ upsample โดยไม่ทำให้เสียงทึบ
        try:
            from scipy.signal import butter, filtfilt
            nyq = 0.5 * 48000.0
            cutoff = 18000.0 / nyq  # 18kHz
            if 0.0 < cutoff < 1.0:
                b, a = butter(2, cutoff, btype='low')
                audio_data = filtfilt(b, a, audio_data).astype(np.float32)
        except Exception:
            pass

        # เอา soft limiter ออกเพื่อหลีกเลี่ยงการบีบไดนามิก

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
        
        # เก็บสัญญาณโมโน 48k หลังประมวลผลไว้สำหรับลิปซิงค์แบบเฟรม
        try:
            self.mono_samples = audio_data.astype(np.float32).copy()
        except Exception:
            self.mono_samples = audio_data
        
        # Convert to int16 (mono)
        audio_data = np.clip(audio_data, -1.0, 1.0)
        mono_int16 = (audio_data * 32767).astype(np.int16)

        # Convert to stereo (duplicate mono to L/R and interleave)
        try:
            stereo_int16 = np.stack([mono_int16, mono_int16], axis=1).reshape(-1)
        except Exception:
            # Fallback if stacking fails for any reason
            stereo_int16 = np.repeat(mono_int16, 2)

        # Convert to bytes
        self.audio_bytes = stereo_int16.tobytes()

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
                    wf.setnchannels(2)
                    wf.setsampwidth(2)
                    wf.setframerate(48000)
                    wf.writeframes(self.audio_bytes)
        except Exception as e:
            logger.debug(f"Debug save (final-pcm) failed: {e}")
        
        # Pad trailing silence to help Opus encoder flush (≈40ms)
        try:
            tail_pad_ms = 40
            pad_samples = int(48000 * (tail_pad_ms / 1000.0))
            pad_bytes = pad_samples * 4  # int16 stereo (2 channels)
            if pad_bytes > 0:
                self.audio_bytes += b"\x00" * pad_bytes
                try:
                    # เพิ่ม pad ในสัญญาณโมโนสำหรับลิปซิงค์ให้ความยาวตรงกัน
                    self.mono_samples = np.concatenate(
                        [self.mono_samples, np.zeros(pad_samples, dtype=np.float32)]
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Tail pad failed: {e}")
        self.position = 0
        
        # Discord expects 20ms frames at 48kHz, stereo (2 channels)
        # 48000 samples/sec * 0.02 sec = 960 samples per channel
        # 960 samples * 2 bytes * 2 channels = 3840 bytes per frame
        self.frame_size = 3840
    
    def read(self) -> bytes:
        """Read next audio frame"""
        if self.position >= len(self.audio_bytes):
            return b''
        
        frame = self.audio_bytes[self.position:self.position + self.frame_size]
        self.position += self.frame_size
        
        # ✅ เมื่อจบ ให้เรียก callback
        if self.position >= len(self.audio_bytes):
            if self.finished_callback:
                try:
                    self.finished_callback()
                except Exception:
                    pass
        
        # Pad if needed
        if len(frame) < self.frame_size:
            frame += b'\x00' * (self.frame_size - len(frame))
        
        return frame
    
    def is_opus(self) -> bool:
        """Not Opus encoded"""
        return False