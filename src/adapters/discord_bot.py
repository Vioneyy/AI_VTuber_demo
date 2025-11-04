"""
Discord Bot Adapter สำหรับ AI VTuber
แก้ไขปัญหา: Voice connection state, STT recording
"""
import discord
from discord.ext import commands
import asyncio
import os
import wave
import struct
import logging
from pathlib import Path
from typing import Optional
import time

logger = logging.getLogger(__name__)

class DiscordBot:
    def __init__(self, token: str, scheduler, stt_engine=None, config=None):
        """
        Initialize Discord Bot
        
        Args:
            token: Discord bot token
            scheduler: Message queue scheduler
            stt_engine: Speech-to-text engine (Whisper)
            config: Bot configuration
        """
        self.token = token
        self.scheduler = scheduler
        self.stt_engine = stt_engine
        self.config = config or {}
        
        # Bot setup with proper intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.voice_states = True
        intents.members = True
        
        self.bot = commands.Bot(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        
        # Voice state tracking
        self.voice_client: Optional[discord.VoiceClient] = None
        self.is_recording = False
        self.recorded_audio = []
        self.connection_ready = asyncio.Event()
        self.last_join_time = 0
        self.connection_stable_delay = 2.0  # รอให้ connection stable
        
        # Stats
        self.stats = {
            'messages_processed': 0,
            'voice_recordings': 0,
            'errors': 0
        }
        
        self._register_events()
        self._register_commands()
        
    def _register_events(self):
        """Register bot events"""
        
        @self.bot.event
        async def on_ready():
            logger.info(f"✅ Discord Bot พร้อมแล้ว: {self.bot.user}")
            # แสดงสถานะ online
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name="!join เพื่อเข้าห้อง"
                ),
                status=discord.Status.online
            )
        
        @self.bot.event
        async def on_voice_state_update(member, before, after):
            """ตรวจจับเมื่อมีคนเข้า/ออกห้องเสียง"""
            if member == self.bot.user:
                # Bot ถูก disconnect
                if before.channel and not after.channel:
                    logger.info("👋 ถูก disconnect จากห้องเสียง")
                    self.voice_client = None
                    self.connection_ready.clear()
                    await self.bot.change_presence(
                        activity=discord.Activity(
                            type=discord.ActivityType.listening,
                            name="!join เพื่อเข้าห้อง"
                        )
                    )
                # Bot ถูก move
                elif before.channel != after.channel and after.channel:
                    logger.info(f"📍 ถูกย้ายไป: {after.channel.name}")
                    
    def _register_commands(self):
        """Register bot commands"""
        
        @self.bot.command(name='join')
        async def join(ctx):
            """เข้าห้องเสียงของผู้ใช้"""
            try:
                # ตรวจสอบว่าผู้ใช้อยู่ในห้องเสียงหรือไม่
                if not ctx.author.voice:
                    await ctx.send("❌ คุณต้องอยู่ในห้องเสียงก่อน!")
                    return
                
                channel = ctx.author.voice.channel
                
                # ถ้ายังไม่ได้เชื่อมต่อ
                if not self.voice_client or not self.voice_client.is_connected():
                    await ctx.send(f"🔄 กำลังเข้าห้อง **{channel.name}**...")
                    
                    # Disconnect old connection ถ้ามี
                    if self.voice_client:
                        await self.voice_client.disconnect(force=True)
                        await asyncio.sleep(0.5)
                    
                    # Connect to voice channel
                    self.voice_client = await channel.connect(timeout=10.0, reconnect=True)
                    self.last_join_time = time.time()
                    
                    # รอให้ connection stable
                    await asyncio.sleep(self.connection_stable_delay)
                    
                    # ตรวจสอบว่า connection สำเร็จจริงๆ
                    if self.voice_client and self.voice_client.is_connected():
                        self.connection_ready.set()
                        await ctx.send(f"✅ เข้าห้อง **{channel.name}** แล้ว!")
                        await self.bot.change_presence(
                            activity=discord.Activity(
                                type=discord.ActivityType.listening,
                                name=f"ใน {channel.name}"
                            )
                        )
                        logger.info(f"✅ เชื่อมต่อห้อง {channel.name} สำเร็จ")
                    else:
                        raise Exception("Connection ไม่สำเร็จ")
                        
                # ถ้าอยู่ห้องอื่น ให้ย้าย
                elif self.voice_client.channel != channel:
                    await ctx.send(f"🔄 กำลังย้ายไป **{channel.name}**...")
                    await self.voice_client.move_to(channel)
                    await asyncio.sleep(self.connection_stable_delay)
                    self.connection_ready.set()
                    await ctx.send(f"✅ ย้ายมา **{channel.name}** แล้ว!")
                    
                # ถ้าอยู่ห้องเดียวกันแล้ว
                else:
                    self.connection_ready.set()
                    await ctx.send(f"✅ อยู่ในห้อง **{channel.name}** อยู่แล้ว!")
                    
            except asyncio.TimeoutError:
                await ctx.send("⏰ Connection timeout! ลองใหม่อีกครั้ง")
                self.voice_client = None
                self.connection_ready.clear()
                logger.error("Connection timeout")
            except Exception as e:
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {str(e)}")
                self.voice_client = None
                self.connection_ready.clear()
                logger.error(f"Error in join command: {e}")
                self.stats['errors'] += 1
        
        @self.bot.command(name='leave')
        async def leave(ctx):
            """ออกจากห้องเสียง"""
            if self.voice_client and self.voice_client.is_connected():
                channel_name = self.voice_client.channel.name
                await self.voice_client.disconnect()
                self.voice_client = None
                self.connection_ready.clear()
                await ctx.send(f"👋 ออกจากห้อง **{channel_name}** แล้ว!")
                await self.bot.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.listening,
                        name="!join เพื่อเข้าห้อง"
                    )
                )
            else:
                await ctx.send("❌ ไม่ได้อยู่ในห้องเสียง!")
        
        @self.bot.command(name='listen')
        async def listen(ctx, duration: int = 5):
            """
            บันทึกเสียงและถอดความด้วย STT
            Usage: !listen [seconds] (default: 5)
            """
            # ตรวจสอบว่ามี STT engine หรือไม่
            if not self.stt_engine:
                await ctx.send("❌ STT engine ไม่พร้อมใช้งาน!")
                return
            
            # ตรวจสอบว่า bot อยู่ในห้องเสียงหรือไม่
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ หนูต้องอยู่ในห้องเสียงก่อน! ใช้ `!join`")
                return
            
            # ตรวจสอบว่า connection พร้อมหรือยัง
            if not self.connection_ready.is_set():
                # รอให้ connection พร้อม
                try:
                    await asyncio.wait_for(self.connection_ready.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    await ctx.send("⏰ Connection ยังไม่พร้อม ลอง `!join` อีกครั้ง")
                    return
            
            # ตรวจสอบว่ามีคนในห้องไหม (นอกจาก bot)
            if len(self.voice_client.channel.members) <= 1:
                await ctx.send("❌ ไม่มีใครในห้องเสียง!")
                return
            
            # ตรวจสอบว่ากำลังบันทึกอยู่หรือไม่
            if self.is_recording:
                await ctx.send("⏺️ กำลังบันทึกอยู่แล้ว!")
                return
            
            # จำกัด duration
            duration = max(1, min(duration, 30))  # 1-30 วินาที
            
            try:
                await ctx.send(f"🎤 กำลังบันทึก {duration} วินาที...")
                self.is_recording = True
                self.recorded_audio = []
                
                # Start recording
                sink = AudioSink()
                self.voice_client.start_recording(
                    sink,
                    self._recording_callback,
                    ctx
                )
                
                # Record for duration
                await asyncio.sleep(duration)
                
                # Stop recording
                self.voice_client.stop_recording()
                self.is_recording = False
                
                # Process audio
                if sink.audio_data:
                    await ctx.send("🔄 กำลังถอดความ...")
                    
                    # Save to temporary file
                    temp_file = Path("temp_audio.wav")
                    self._save_audio(sink.audio_data, temp_file)
                    
                    # Transcribe
                    try:
                        text = await self._transcribe_audio(temp_file)
                        
                        if text and text.strip():
                            await ctx.send(f"💬 ได้ยิน: `{text}`")
                            
                            # Add to processing queue
                            await self.scheduler.add_message(
                                text=text,
                                source="discord_voice",
                                metadata={
                                    'user': ctx.author.name,
                                    'channel': ctx.channel.name
                                }
                            )
                            self.stats['voice_recordings'] += 1
                        else:
                            await ctx.send("❌ ไม่ได้ยินอะไรชัดเจน")
                    finally:
                        # Cleanup
                        if temp_file.exists():
                            temp_file.unlink()
                else:
                    await ctx.send("❌ ไม่มีข้อมูลเสียง")
                    
            except Exception as e:
                self.is_recording = False
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {str(e)}")
                logger.error(f"Error in listen command: {e}")
                self.stats['errors'] += 1
        
        @self.bot.command(name='test')
        async def test(ctx):
            """ทดสอบบอท"""
            status = []
            status.append("🤖 **สถานะบอท**")
            status.append(f"├─ ชื่อ: {self.bot.user.name}")
            status.append(f"├─ Latency: {round(self.bot.latency * 1000)}ms")
            
            if self.voice_client and self.voice_client.is_connected():
                status.append(f"├─ เสียง: ✅ อยู่ในห้อง **{self.voice_client.channel.name}**")
                status.append(f"├─ พร้อมใช้งาน: {'✅' if self.connection_ready.is_set() else '⏳'}")
            else:
                status.append(f"├─ เสียง: ❌ ไม่ได้อยู่ในห้องเสียง")
            
            status.append(f"└─ STT: {'✅' if self.stt_engine else '❌'}")
            
            await ctx.send("\n".join(status))
        
        @self.bot.command(name='ping')
        async def ping(ctx):
            """ตรวจสอบ latency"""
            await ctx.send(f"🏓 Pong! {round(self.bot.latency * 1000)}ms")
        
        @self.bot.command(name='stats')
        async def stats(ctx):
            """แสดงสถิติ"""
            stats_text = [
                "📊 **สถิติการใช้งาน**",
                f"├─ ข้อความที่ประมวลผล: {self.stats['messages_processed']}",
                f"├─ การบันทึกเสียง: {self.stats['voice_recordings']}",
                f"└─ ข้อผิดพลาด: {self.stats['errors']}"
            ]
            await ctx.send("\n".join(stats_text))
    
    def _recording_callback(self, sink, ctx):
        """Callback when recording finishes"""
        pass  # จัดการใน listen command แล้ว
    
    def _save_audio(self, audio_data: list, output_path: Path):
        """บันทึกเสียงเป็นไฟล์ WAV"""
        # Discord audio: 48kHz, 16-bit, stereo
        with wave.open(str(output_path), 'wb') as wav_file:
            wav_file.setnchannels(2)  # Stereo
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(48000)  # 48kHz
            
            # Convert audio data to bytes
            audio_bytes = b''.join(audio_data)
            wav_file.writeframes(audio_bytes)
    
    async def _transcribe_audio(self, audio_path: Path) -> Optional[str]:
        """ถอดความเสียงด้วย STT"""
        if not self.stt_engine:
            return None
        
        try:
            # เรียก STT engine (async)
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(
                None,
                self.stt_engine.transcribe,
                str(audio_path)
            )
            return text
        except Exception as e:
            logger.error(f"STT Error: {e}")
            return None
    
    async def start(self):
        """Start the bot"""
        try:
            await self.bot.start(self.token)
        except Exception as e:
            logger.error(f"Bot error: {e}")
            raise
    
    async def stop(self):
        """Stop the bot"""
        if self.voice_client:
            await self.voice_client.disconnect()
        await self.bot.close()


class AudioSink(discord.sinks.WaveSink):
    """Custom audio sink สำหรับบันทึกเสียง"""
    
    def __init__(self):
        super().__init__()
        self.audio_data = []
    
    def write(self, data):
        """เก็บข้อมูลเสียง"""
        if data:
            self.audio_data.append(data)


# ==================== คำแนะนำการใช้งาน ====================
"""
1. ติดตั้ง dependencies:
   pip install py-cord

2. ตั้งค่าใน .env:
   DISCORD_BOT_TOKEN=your_token_here
   DISCORD_VOICE_STT_ENABLED=true
   
3. สร้าง bot instance:
   bot = DiscordBot(token, scheduler, stt_engine, config)
   await bot.start()

4. คำสั่งที่ใช้ได้:
   !join       - เข้าห้องเสียง (รอ 2 วินาทีให้ connection stable)
   !leave      - ออกจากห้องเสียง
   !listen 5   - บันทึกเสียง 5 วินาที และถอดความ
   !test       - ตรวจสอบสถานะ
   !ping       - ตรวจสอบ latency
   !stats      - แสดงสถิติการใช้งาน

5. การแก้ปัญหา:
   - ถ้า !join แล้วไม่มีข้อความ = ปรับ connection_stable_delay
   - ถ้า !listen ไม่ทำงาน = ตรวจสอบว่า connection_ready.is_set()
   - ถ้า bot หยุดทำงาน = ดู logs ใน logger
"""