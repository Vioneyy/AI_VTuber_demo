"""
Discord Bot Adapter - Fixed Version
แก้ปัญหา Voice Connection Error 4006
"""
import discord
from discord.ext.voice_recv import sinks as voice_sinks, VoiceRecvClient
from discord.ext import commands
import asyncio
import logging
from typing import Optional, Callable
import io
import wave
import numpy as np

logger = logging.getLogger(__name__)

class DiscordBotAdapter:
    """Discord Bot สำหรับรับ voice commands"""
    
    def __init__(self, token: str, admin_ids: set):
        """
        Args:
            token: Discord bot token
            admin_ids: Set of admin user IDs
        """
        # สร้าง intents (ต้องเปิด Message Content Intent ใน Discord Developer Portal)
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
        self.on_text_command: Optional[Callable] = None
        
        # Voice recording state
        self.is_recording = False
        self.voice_client: Optional[discord.VoiceClient] = None
        self.audio_buffer = []
        self.sample_rate = 48000  # Discord uses 48kHz
        self._stopped = False
        self._voice_connect_lock = asyncio.Lock()
        # Always-On voice: auto join a configured voice channel on ready
        self.auto_join_channel_id: Optional[int] = None
        # External component status (set by main application)
        self._ext_status = {
            'vts_connected': False,
            'tts_ready': False,
            'queue_ready': False,
        }
        # Keep the latest error message to surface in status
        self.last_error_message: Optional[str] = None
        
        # Register events and commands
        self._register_events()
        self._register_commands()
        
        logger.info("✅ Discord Bot initialized")
    
    def _register_events(self):
        """ลงทะเบียน events"""
        
        @self.bot.event
        async def on_ready():
            """เมื่อ bot พร้อมใช้งาน"""
            logger.info(f"✅ Discord Bot พร้อมแล้ว: {self.bot.user}")
            
            # Set status
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="👋 พร้อมรับคำสั่ง!"
                )
            )

            # Auto-join voice channel if configured
            try:
                if self.auto_join_channel_id:
                    channel = self.bot.get_channel(self.auto_join_channel_id)
                    if isinstance(channel, discord.VoiceChannel):
                        logger.info(f"🔊 Auto-join กำลังเชื่อมต่อไปยัง: {channel.name}")
                        # ป้องกันการเชื่อมต่อซ้อนกัน
                        async with self._voice_connect_lock:
                            # Disconnect ก่อนถ้ามี connection เก่า
                            if self.voice_client:
                                try:
                                    await self.voice_client.disconnect(force=True)
                                except Exception:
                                    pass
                                self.voice_client = None
                                await asyncio.sleep(0.5)

                            # Connect ด้วย VoiceRecvClient
                            self.voice_client = await channel.connect(
                                cls=VoiceRecvClient,
                                timeout=15.0,
                                reconnect=False
                            )
                            # เริ่มฟังทันที
                            await self._start_listening()
                            logger.info("👂 Auto-join เริ่มฟังเสียงแล้ว")
                    else:
                        logger.warning("⚠️ Auto-join: ไม่พบ voice channel ตาม ID ที่ตั้งค่า")
            except Exception as e:
                logger.warning(f"⚠️ Auto-join ล้มเหลว: {e}")

    def update_external_status(self, *, vts_connected: Optional[bool] = None, tts_ready: Optional[bool] = None, queue_ready: Optional[bool] = None):
        """อัปเดตสถานะระบบภายนอกสำหรับการรายงานในห้องข้อความ"""
        if vts_connected is not None:
            self._ext_status['vts_connected'] = bool(vts_connected)
        if tts_ready is not None:
            self._ext_status['tts_ready'] = bool(tts_ready)
        if queue_ready is not None:
            self._ext_status['queue_ready'] = bool(queue_ready)

    def _build_status_text(self) -> str:
        """สร้างข้อความสรุปสถานะระบบและคู่มือคำสั่ง"""
        lines = []
        lines.append("📊 สถานะระบบ:")
        lines.append(f"• 🎤 Voice: {'Connected' if (self.voice_client and self.voice_client.is_connected()) else 'Disconnected'}")
        lines.append(f"• 👂 Listening: {'Yes' if self.is_recording else 'No'}")
        lines.append(f"• 🎬 VTS: {'Connected' if self._ext_status.get('vts_connected') else 'Not connected'}")
        lines.append(f"• 🔊 TTS: {'Ready' if self._ext_status.get('tts_ready') else 'Unavailable'}")
        lines.append(f"• 📦 Queue: {'Running' if self._ext_status.get('queue_ready') else 'Stopped'}")
        if self.last_error_message:
            lines.append(f"• 🧯 บัคล่าสุด: {self.last_error_message}")
        lines.append("")
        lines.append("🧭 คำสั่งที่ใช้ได้:")
        lines.append("• `!join` เข้าห้องเสียงของคุณ")
        lines.append("• `!listen` เริ่มรับเสียง")
        lines.append("• `!stop` หยุดรับเสียงชั่วคราว")
        lines.append("• `!leave` ออกจากห้องเสียง")
        lines.append("• `!alwayson [off|channel_id]` เปิด/ปิดโหมดรับเสียงตลอดเวลา")
        lines.append("• `!admin status` แสดงสถานะระบบแบบย่อ")
        lines.append("• `!test` ทดสอบว่า bot ทำงาน")
        return "\n".join(lines)
        
        @self.bot.event
        async def on_voice_state_update(member, before, after):
            """เมื่อมีการเปลี่ยนแปลง voice state"""
            # ถ้า bot ถูก disconnect
            if member == self.bot.user:
                if before.channel and not after.channel:
                    logger.info("👋 ถูก disconnect จากห้องเสียง")
                    self.voice_client = None
                    self.is_recording = False
                
                # ถ้าถูกย้ายห้อง
                elif before.channel != after.channel:
                    logger.info(f"📍 ถูกย้ายไป: {after.channel.name if after.channel else 'None'}")
        
        @self.bot.event
        async def on_command_error(ctx, error):
            """จัดการ errors"""
            if isinstance(error, commands.CommandNotFound):
                return
            logger.error(f"Command error: {error}")
            try:
                if not self.bot.is_closed():
                    await ctx.send(f"❌ Error: {error}")
            except Exception:
                # เมื่อ session ปิดอยู่ ให้ข้ามการส่งข้อความ error ที่ช่อง
                pass
    
    def _register_commands(self):
        """ลงทะเบียนคำสั่ง"""
        
        @self.bot.command(name='join')
        async def join(ctx):
            """เข้าห้องเสียง"""
            try:
                # ป้องกันการเชื่อมต่อซ้อนกัน
                async with self._voice_connect_lock:
                    # ตรวจสอบว่า user อยู่ในห้องเสียงหรือไม่
                    if not ctx.author.voice:
                        await ctx.send("❌ คุณต้องอยู่ในห้องเสียงก่อนนะคะ!")
                        return
                    
                    channel = ctx.author.voice.channel
                    
                    # ตรวจสอบสถานะ voice client ทั้งจาก context และตัวแปรภายใน
                    vc = (
                        ctx.voice_client
                        or getattr(ctx.guild, "voice_client", None)
                        or self.voice_client
                    )

                    # ถ้าอยู่ในห้องอยู่แล้ว
                    if vc and vc.is_connected():
                        if vc.channel == channel:
                            self.voice_client = vc
                            await ctx.send("✅ อยู่ในห้องนี้อยู่แล้วค่ะ!")
                            return
                        else:
                            await vc.move_to(channel)
                            self.voice_client = vc
                            await ctx.send(f"📍 ย้ายไปห้อง {channel.name} แล้วค่ะ!")
                            return
                    
                    # เชื่อมต่อใหม่ (แก้ไข error 4006) ด้วย backoff ควบคุมเอง
                    try:
                        # Disconnect ก่อนถ้ามี connection เก่า
                        if vc:
                            try:
                                await vc.disconnect(force=True)
                            except Exception:
                                pass
                            self.voice_client = None
                            await asyncio.sleep(1.0)  # รอให้ disconnect เสร็จ

                        # พยายามเชื่อมต่อด้วย backoff (ปิด auto-reconnect ภายในไลบรารี)
                        attempts = 0
                        last_error = None
                        while attempts < 5:
                            attempts += 1
                            try:
                                await asyncio.sleep(1.0 if attempts == 1 else min(3.0, attempts))
                                self.voice_client = await channel.connect(
                                    cls=VoiceRecvClient,
                                    timeout=15.0,
                                    reconnect=False
                                )
                                logger.info(f"✅ เชื่อมต่อห้อง: {channel.name}")
                                await ctx.send(f"✅ เข้าห้อง {channel.name} แล้วค่ะ!")
                                # เริ่มฟัง voice
                                await self._start_listening()
                                # รายงานสถานะและคู่มือคำสั่ง
                                try:
                                    await ctx.send(self._build_status_text())
                                except Exception:
                                    pass
                                break
                            except discord.errors.ConnectionClosed as e:
                                code = getattr(e, 'code', None)
                                logger.warning(f"⚠️ Voice WS closed (code={code}) on attempt {attempts}")
                                last_error = e
                                # เคลียร์ state และลองใหม่
                                try:
                                    if self.voice_client:
                                        await self.voice_client.disconnect(force=True)
                                except Exception:
                                    pass
                                self.voice_client = None
                                await asyncio.sleep(2.0)
                                continue
                            except asyncio.TimeoutError as e:
                                logger.warning(f"⚠️ Voice connect timeout: {e} (attempt {attempts})")
                                last_error = e
                                await asyncio.sleep(2.0)
                                continue
                            except discord.errors.ClientException as e:
                                msg = str(e)
                                if "Already connected to a voice channel" in msg:
                                    # ใช้ move_to แทน connect ถ้าบอทยังต่ออยู่ที่ช่องอื่น
                                    vc2 = (
                                        ctx.voice_client
                                        or getattr(ctx.guild, "voice_client", None)
                                        or self.voice_client
                                    )
                                    if vc2:
                                        try:
                                            await vc2.move_to(channel)
                                            self.voice_client = vc2
                                            logger.info(f"📍 ย้ายไปห้อง {channel.name} แล้วค่ะ (fallback)")
                                            await ctx.send(f"📍 ย้ายไปห้อง {channel.name} แล้วค่ะ!")
                                            # รอให้เชื่อมต่อสำเร็จหลัง move_to (rehydrate และกัน None)
                                            connected = False
                                            for _ in range(30):  # ~6s
                                                await asyncio.sleep(0.2)
                                                cur_vc = (
                                                    ctx.voice_client
                                                    or getattr(ctx.guild, "voice_client", None)
                                                    or self.voice_client
                                                )
                                                if cur_vc and cur_vc.is_connected():
                                                    self.voice_client = cur_vc
                                                    connected = True
                                                    break
                                            if not connected:
                                                # ถ้ายังไม่เชื่อมต่อ ให้ disconnect แล้วลองใหม่ในรอบถัดไป
                                                cur_vc = (
                                                    ctx.voice_client
                                                    or getattr(ctx.guild, "voice_client", None)
                                                    or self.voice_client
                                                )
                                                if cur_vc:
                                                    try:
                                                        await cur_vc.disconnect(force=True)
                                                    except Exception:
                                                        pass
                                                self.voice_client = None
                                                last_error = e
                                                await asyncio.sleep(1.0)
                                                continue

                                            # พยายามเริ่มฟังทันทีหลังย้าย (มีการรอความพร้อมใน _start_listening)
                                            await self._start_listening()
                                            # รายงานสถานะและคู่มือคำสั่ง
                                            try:
                                                await ctx.send(self._build_status_text())
                                            except Exception:
                                                pass
                                            break
                                        except Exception as move_err:
                                            logger.warning(f"Move_to failed after already-connected: {move_err}")
                                    last_error = e
                                    await asyncio.sleep(1.5)
                                    continue
                                else:
                                    logger.warning(f"⚠️ Voice connect failed: {e} (attempt {attempts})")
                                    last_error = e
                                    await asyncio.sleep(2.0)
                                    continue
                            except Exception as e:
                                last_error = e
                                self.last_error_message = f"{type(e).__name__}: {e}"
                                logger.error(f"Unexpected error during voice connect: {e}")
                                break

                        if self.voice_client is None:
                            raise last_error or RuntimeError("Voice connect failed")
                    except Exception as e:
                        logger.error(f"Connection error: {e}")
                        self.last_error_message = f"{type(e).__name__}: {e}"
                        try:
                            await ctx.send(f"❌ ไม่สามารถเชื่อมต่อได้: {e}")
                        except Exception:
                            pass
                
            except Exception as e:
                logger.error(f"Error in join command: {e}")
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
                logger.info("👋 ออกจากห้องเสียงแล้ว")
                await ctx.send("👋 บายบาย~")
            except Exception as e:
                logger.error(f"Error leaving voice: {e}")
                self.last_error_message = f"{type(e).__name__}: {e}"
                await ctx.send(f"❌ Error: {e}")

        @self.bot.command(name='alwayson')
        async def always_on(ctx, channel_id: Optional[int] = None):
            """เปิด/ปิดโหมด Always-On (auto-join และรับเสียงตลอดเวลา)

            - หากระบุ channel_id: ตั้งค่าช่องสำหรับ auto-join
            - หากไม่ระบุ: ใช้ช่องที่ผู้ใช้กำลังอยู่
            - ใช้ `!alwayson off` เพื่อปิดโหมด
            """
            try:
                # ปิดโหมด
                if isinstance(channel_id, str) and channel_id.lower() == 'off':
                    self.auto_join_channel_id = None
                    await ctx.send("🧯 ปิดโหมด Always-On แล้วค่ะ")
                    return

                # ตั้งค่าจากพารามิเตอร์หรือจากช่องที่ผู้ใช้กำลังอยู่
                target_channel = None
                if isinstance(channel_id, int):
                    target_channel = self.bot.get_channel(channel_id)
                elif ctx.author.voice and ctx.author.voice.channel:
                    target_channel = ctx.author.voice.channel

                if not isinstance(target_channel, discord.VoiceChannel):
                    await ctx.send("❌ กรุณาระบุ channel_id ของห้องเสียง หรือเข้าห้องเสียงก่อนค่ะ")
                    return

                self.auto_join_channel_id = target_channel.id
                await ctx.send(f"🔊 เปิดโหมด Always-On สำหรับห้อง `{target_channel.name}` แล้วค่ะ")

                # หากยังไม่เชื่อมต่อ ให้เชื่อมต่อทันที
                vc = (
                    ctx.voice_client
                    or getattr(ctx.guild, "voice_client", None)
                    or self.voice_client
                )
                if not (vc and vc.is_connected() and vc.channel == target_channel):
                    async with self._voice_connect_lock:
                        try:
                            if vc:
                                try:
                                    await vc.disconnect(force=True)
                                except Exception:
                                    pass
                                self.voice_client = None
                                await asyncio.sleep(0.5)
                            self.voice_client = await target_channel.connect(
                                cls=VoiceRecvClient,
                                timeout=15.0,
                                reconnect=False
                            )
                            await self._start_listening()
                            await ctx.send("👂 เริ่มฟังเสียงแล้วค่ะ (Always-On)")
                            try:
                                await ctx.send(self._build_status_text())
                            except Exception:
                                pass
                        except Exception as e:
                            logger.error(f"Always-On connect error: {e}")
                            self.last_error_message = f"{type(e).__name__}: {e}"
                            await ctx.send(f"❌ เชื่อมต่อไม่สำเร็จ: {e}")
            except Exception as e:
                logger.error(f"Error in alwayson command: {e}")
                try:
                    await ctx.send(f"❌ Error: {e}")
                except Exception:
                    pass

        @self.bot.command(name='listen')
        async def start_listening(ctx):
            """เริ่มฟังเสียง"""
            # Rehydrate voice client จาก context/guild กันกรณี session เปลี่ยนระหว่างทาง
            vc = (
                ctx.voice_client
                or getattr(ctx.guild, "voice_client", None)
                or self.voice_client
            )
            if not (vc and vc.is_connected()):
                await ctx.send("❌ ต้องเข้าห้องเสียงก่อนค่ะ (ใช้ !join)")
                return
            self.voice_client = vc
            
            if self.is_recording:
                await ctx.send("✅ กำลังฟังอยู่แล้วค่ะ!")
                return
            
            try:
                await self._start_listening()
                await ctx.send("👂 เริ่มฟังแล้วค่ะ! พูดได้เลย~")
            except Exception as e:
                logger.error(f"Start listening error: {e}")
                self.last_error_message = f"{type(e).__name__}: {e}"
                await ctx.send(f"❌ เริ่มฟังไม่สำเร็จ: {e}")
        
        @self.bot.command(name='stop')
        async def stop_listening(ctx):
            """หยุดฟังเสียง"""
            if not self.is_recording:
                await ctx.send("❌ ไม่ได้ฟังอยู่ค่ะ")
                return
            
            try:
                if self.voice_client and hasattr(self.voice_client, 'stop_listening'):
                    self.voice_client.stop_listening()
            except Exception:
                pass
            self.is_recording = False
            await ctx.send("🛑 หยุดฟังแล้วค่ะ")
        
        @self.bot.command(name='test')
        async def test(ctx):
            """ทดสอบว่า bot ทำงานหรือไม่"""
            await ctx.send("✅ ระบบทำงานปกติค่ะ!")
        
        # Admin commands
        @self.bot.command(name='admin')
        async def admin_command(ctx, action: str = None):
            """คำสั่งแอดมิน"""
            # ตรวจสอบสิทธิ์
            if str(ctx.author.id) not in self.admin_ids:
                await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ค่ะ")
                return
            
            if not action:
                await ctx.send(
                    "📋 Admin Commands:\n"
                    "• `!admin status` - ตรวจสอบสถานะ\n"
                    "• `!admin reload` - โหลดใหม่\n"
                    "• `!admin debug` - Debug mode"
                )
                return
            
            if action == 'status':
                status = self._build_status_text()
                await ctx.send(status)
            
            elif action == 'reload':
                await ctx.send("🔄 Reloading...")
                # TODO: Implement reload logic
            
            elif action == 'debug':
                await ctx.send("🐛 Debug mode enabled")
                # TODO: Implement debug mode
    
    async def _start_listening(self):
        """เริ่มฟังเสียงจาก voice channel"""
        if not self.voice_client:
            logger.warning("⚠️  ยังไม่มี voice client")
            return
        
        # รอให้เชื่อมต่อ voice สำเร็จ (กัน race หลัง move_to/connect)
        if not (self.voice_client and self.voice_client.is_connected()):
            for _ in range(25):  # ~5s
                await asyncio.sleep(0.2)
                if self.voice_client and self.voice_client.is_connected():
                    break
            if not (self.voice_client and self.voice_client.is_connected()):
                logger.error("❌ Voice client ยังไม่เชื่อมต่อ - ยกเลิกการเริ่มฟัง")
                return
        
        self.is_recording = True
        logger.info("👂 เริ่มฟังเสียง...")
        
        # สร้าง audio sink
        sink = VoiceRecorderSink(self._on_audio_received)
        
        # เริ่มรับเสียงด้วย VoiceRecvClient.listen
        try:
            self.voice_client.listen(sink, after=self._recording_finished)
        except AttributeError:
            logger.error("Voice client ไม่รองรับการรับเสียง (listen)")
            self.is_recording = False
            return
    
    def _on_audio_received(self, user: discord.User, audio_data: bytes):
        """เมื่อได้รับเสียงจาก user"""
        if not self.is_recording:
            return

        # ส่ง audio ไปประมวลผล (thread-safe จาก voice router thread)
        if self.on_voice_input:
            try:
                loop = getattr(self.bot, "loop", None)
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self.on_voice_input(user, audio_data, self.sample_rate),
                        loop,
                    )
                else:
                    # fallback: ถ้ามี running loop ในบริบทนี้
                    try:
                        asyncio.get_running_loop().create_task(
                            self.on_voice_input(user, audio_data, self.sample_rate)
                        )
                    except RuntimeError:
                        # ไม่มี event loop ก็ข้าม (ป้องกัน crash)
                        logger.debug("No running loop to schedule voice input")
            except Exception as e:
                logger.error(f"Error scheduling voice input: {e}")
    
    def _recording_finished(self, error: Optional[Exception] = None):
        """เมื่อการ record เสร็จสิ้น (after callback ของ VoiceRecvClient)"""
        self.is_recording = False
        if error:
            logger.error(f"🛑 Recording stopped with error: {error}")
            self.last_error_message = f"{type(error).__name__}: {error}"
        else:
            logger.info("🛑 Recording stopped")
    
    async def play_audio(self, audio_data: np.ndarray, sample_rate: int):
        """เล่นเสียงในห้อง voice"""
        if not self.voice_client or not self.voice_client.is_connected():
            logger.warning("⚠️  ไม่ได้เชื่อมต่อ voice channel")
            return
        
        try:
            # แปลง numpy array เป็น audio file
            audio_source = NumpyAudioSource(audio_data, sample_rate)
            
            # รอถ้ากำลังเล่นอยู่
            while self.voice_client.is_playing():
                await asyncio.sleep(0.1)
            
            # เล่นเสียง
            self.voice_client.play(audio_source)
            
            # รอจนเล่นเสร็จ
            while self.voice_client.is_playing():
                await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error playing audio: {e}")
    
    async def start(self):
        """เริ่ม bot"""
        try:
            await self.bot.start(self.token)
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise
    
    async def stop(self):
        """หยุด bot"""
        try:
            if self._stopped:
                logger.info("ℹ️ Discord Bot already stopped")
                return

            # Stop recording first to teardown voice UDP cleanly
            try:
                if self.voice_client and self.is_recording:
                    self.is_recording = False
                    try:
                        if hasattr(self.voice_client, 'stop_listening'):
                            self.voice_client.stop_listening()
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Stop recording error (ignored): {e}")

            # Disconnect from voice
            try:
                if self.voice_client:
                    await self.voice_client.disconnect(force=True)
            except Exception as e:
                logger.debug(f"Voice disconnect error (ignored): {e}")
            finally:
                self.voice_client = None

            # Close bot websocket/session gracefully (avoid double close)
            if not self.bot.is_closed():
                await self.bot.close()
            self._stopped = True
            logger.info("👋 Discord Bot stopped")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")


class VoiceRecorderSink(voice_sinks.BasicSink):
    """Sink สำหรับบันทึกเสียง"""
    
    def __init__(self, callback):
        # สร้าง callback สำหรับ BasicSink ที่รับ (user, VoiceData)
        self.callback = callback
        self.audio_data = {}
        # เกณฑ์ตัดความเงียบแบบง่ายด้วย RMS ของสัญญาณ (int16)
        try:
            import os as _os
            self._rms_thresh = int(_os.getenv("DISCORD_VOICE_RMS_THRESHOLD", "350"))
        except Exception:
            self._rms_thresh = 350
        super().__init__(event=self._on_voice_data)

    def _on_voice_data(self, user, data):
        """Callback ที่ถูกเรียกจาก BasicSink เมื่อมี VoiceData เข้ามา"""
        try:
            pcm = getattr(data, 'data', None)
            if pcm is None and hasattr(data, 'pcm'):
                pcm = data.pcm
            payload = pcm if isinstance(pcm, (bytes, bytearray)) else bytes(pcm or b"")
        except Exception:
            payload = b""

        if user not in self.audio_data:
            self.audio_data[user] = bytearray()
        self.audio_data[user].extend(payload)

        # ถ้าได้เสียงครบ 1 วินาที (48000 * 2 bytes)
        if len(self.audio_data[user]) >= 96000:
            audio_bytes = bytes(self.audio_data[user])
            self.audio_data[user].clear()
            # กรองความเงียบ/เสียงรบกวน: คำนวณ RMS ในโดเมน int16
            try:
                import numpy as _np
                if len(audio_bytes) % 2 == 0 and len(audio_bytes) > 0:
                    pcm = _np.frombuffer(audio_bytes, dtype=_np.int16)
                    # หลีกเลี่ยง overflow ด้วยการ cast เป็น float32
                    rms = float(_np.sqrt(_np.mean((_np.asarray(pcm, dtype=_np.float32))**2)))
                else:
                    rms = 0.0
            except Exception:
                rms = 0.0

            # ถ้า RMS ต่ำกว่าเกณฑ์ ให้ข้ามเพื่อไม่ให้เรียก STT โดยเปลืองทรัพยากร
            if rms < self._rms_thresh:
                try:
                    import logging as _logging
                    _logging.getLogger(__name__).debug(f"🔇 Skipping silent chunk (RMS={rms:.1f} < {self._rms_thresh})")
                except Exception:
                    pass
                return

            # ส่งไปประมวลผล (ส่งผู้ใช้และบล็อกเสียง 1s)
            self.callback(user, audio_bytes)

    def cleanup(self):
        """ทำความสะอาด"""
        try:
            buf = getattr(self, 'audio_data', None)
            if isinstance(buf, dict):
                buf.clear()
        except Exception:
            pass


class NumpyAudioSource(discord.AudioSource):
    """Audio source จาก numpy array"""
    
    def __init__(self, audio_data: np.ndarray, sample_rate: int):
        """
        Args:
            audio_data: Audio data (numpy array)
            sample_rate: Sample rate (Hz)
        """
        # Resample to 48kHz (Discord requirement)
        if sample_rate != 48000:
            from scipy import signal
            audio_data = signal.resample(
                audio_data,
                int(len(audio_data) * 48000 / sample_rate)
            )
        
        # Convert to int16
        audio_data = (audio_data * 32767).astype(np.int16)
        
        # Convert to bytes
        self.audio_bytes = audio_data.tobytes()
        self.position = 0
        
        # Discord expects 20ms frames at 48kHz (1920 samples, 3840 bytes)
        self.frame_size = 3840
    
    def read(self) -> bytes:
        """อ่าน audio frame ถัดไป"""
        if self.position >= len(self.audio_bytes):
            return b''
        
        frame = self.audio_bytes[self.position:self.position + self.frame_size]
        self.position += self.frame_size
        
        # Pad ถ้าไม่ครบ
        if len(frame) < self.frame_size:
            frame += b'\x00' * (self.frame_size - len(frame))
        
        return frame
    
    def is_opus(self) -> bool:
        """ไม่ใช่ Opus encoded"""
        return False
        @self.bot.command(name='status')
        async def status(ctx):
            """แสดงสถานะการเชื่อมต่อเสียงของบอท"""
            vc = (
                ctx.voice_client
                or getattr(ctx.guild, "voice_client", None)
                or self.voice_client
            )
            if not vc:
                await ctx.send("ℹ️ ยังไม่มี voice client")
                return
            ch = getattr(vc, "channel", None)
            ch_name = ch.name if ch else "None"
            await ctx.send(
                f"ℹ️ voice_client: {'connected' if vc.is_connected() else 'disconnected'}, channel: {ch_name}"
            )