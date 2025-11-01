import discord
from discord.ext import commands
import asyncio
import logging
from typing import Optional
import io

# Import admin + safety systems (support both package and module run modes)
try:
    from core.admin_commands import get_admin_handler
    from core.safety_filter import get_safety_filter
except ModuleNotFoundError:
    from src.core.admin_commands import get_admin_handler
    from src.core.safety_filter import get_safety_filter

logger = logging.getLogger(__name__)

class DiscordBot:
    def __init__(self, token: str, audio_player, queue_manager):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        
        self.bot = commands.Bot(command_prefix='!', intents=intents)
        self.token = token
        self.audio_player = audio_player
        self.queue_manager = queue_manager
        self.voice_client: Optional[discord.VoiceClient] = None
        self.admin_handler = get_admin_handler()
        self.safety_filter = get_safety_filter()
        
        self._setup_events()
        self._setup_commands()

    def _setup_events(self):
        @self.bot.event
        async def on_ready():
            logger.info(f"Discord Bot logged in as {self.bot.user} (id={self.bot.user.id})")
            logger.info("🔄 Voice reconnect monitor เริ่มทำงาน")

        @self.bot.event
        async def on_voice_state_update(member, before, after):
            # ตรวจสอบว่า bot ถูก disconnect
            if member == self.bot.user and after.channel is None:
                logger.warning("⚠️ Bot ถูก disconnect จาก voice channel")
                self.voice_client = None

    def _setup_commands(self):
        @self.bot.command(name='join')
        async def join(ctx):
            """เข้า voice channel"""
            if not ctx.author.voice:
                await ctx.send("❌ คุณต้องอยู่ใน voice channel ก่อน!")
                return

            channel = ctx.author.voice.channel
            
            # ถ้ามี voice_client อยู่แล้ว ให้ disconnect ก่อน
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
                await asyncio.sleep(0.5)
            
            try:
                logger.info(f"📞 กำลังเชื่อมต่อ: {channel.name}...")
                self.voice_client = await channel.connect(timeout=10.0, reconnect=True)
                logger.info(f"✅ เชื่อมต่อสำเร็จ: {channel.name}")
                await ctx.send(f"✅ เข้า {channel.name} แล้ว!")
            except Exception as e:
                logger.error(f"❌ ไม่สามารถเชื่อมต่อได้: {e}")
                await ctx.send(f"❌ เชื่อมต่อไม่สำเร็จ: {e}")

        @self.bot.command(name='leave')
        async def leave(ctx):
            """ออกจาก voice channel"""
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
                self.voice_client = None
                await ctx.send("👋 ออกจาก voice channel แล้ว")
            else:
                await ctx.send("❌ ไม่ได้อยู่ใน voice channel")

        @self.bot.command(name='speak')
        async def speak(ctx, *, message: str):
            """พูดข้อความ"""
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ ต้องเข้า voice channel ก่อน! ใช้ `!join`")
                return

            await ctx.send(f"💬 กำลังประมวลผล: {message}")
            
            # ส่งไปยัง queue
            await self.queue_manager.add_message(
                source='discord_text',
                content=message,
                metadata={
                    'voice_client': self.voice_client,
                    'ctx': ctx
                }
            )

        # === Admin commands ===
        @self.bot.command(name='unlock')
        async def unlock(ctx, code: str):
            """ปลดล็อคการเปิดเผยข้อมูลโปรเจค: !unlock <code> (เฉพาะ owner)"""
            await self._run_admin_command(ctx, 'unlock', [code])

        @self.bot.command(name='lock')
        async def lock(ctx):
            """ล็อคการเปิดเผยข้อมูลโปรเจค (เฉพาะ owner)"""
            await self._run_admin_command(ctx, 'lock', [])

        @self.bot.command(name='status')
        async def status(ctx):
            """ดูสถานะระบบ"""
            await self._run_admin_command(ctx, 'status', [])

        @self.bot.command(name='queue')
        async def queue(ctx):
            """ดูคิวข้อความ"""
            await self._run_admin_command(ctx, 'queue', [])

        @self.bot.command(name='approve')
        async def approve(ctx, approval_id: str):
            """อนุมัติคำขอ: !approve <approval_id> (เฉพาะ admin)"""
            await self._run_admin_command(ctx, 'approve', [approval_id])

        @self.bot.command(name='reject')
        async def reject(ctx, approval_id: str):
            """ปฏิเสธคำขอ: !reject <approval_id> (เฉพาะ admin)"""
            await self._run_admin_command(ctx, 'reject', [approval_id])

        @self.bot.command(name='skip')
        async def skip(ctx):
            """ข้ามข้อความปัจจุบันในคิว (เฉพาะ admin)"""
            await self._run_admin_command(ctx, 'skip', [])

    async def play_audio(self, audio_data: bytes, voice_client: discord.VoiceClient):
        """เล่นเสียงใน Discord voice channel"""
        if not voice_client or not voice_client.is_connected():
            logger.error("❌ Voice client ไม่ได้เชื่อมต่อ")
            return False

        try:
            # ตรวจสอบว่ากำลังเล่นอยู่หรือไม่
            if voice_client.is_playing():
                logger.info("⏸️ กำลังเล่นเสียงอยู่ รอให้เสร็จก่อน...")
                voice_client.stop()
                await asyncio.sleep(0.3)

            # สร้าง audio source จาก bytes
            audio_source = discord.PCMAudio(io.BytesIO(audio_data))
            
            # สร้าง event สำหรับรอให้เล่นเสร็จ
            finished = asyncio.Event()
            
            def after_playing(error):
                if error:
                    logger.error(f"❌ เล่นเสียงผิดพลาด: {error}")
                else:
                    logger.info("✅ เล่นเสียงเสร็จแล้ว")
                finished.set()

            # เล่นเสียง
            logger.info("🔊 กำลังเล่นเสียง...")
            voice_client.play(audio_source, after=after_playing)
            
            # รอให้เล่นเสร็จ (timeout 30 วินาที)
            try:
                await asyncio.wait_for(finished.wait(), timeout=30.0)
                return True
            except asyncio.TimeoutError:
                logger.error("❌ เล่นเสียงเกิน timeout")
                voice_client.stop()
                return False

        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการเล่นเสียง: {e}", exc_info=True)
            return False

    async def start(self):
        """เริ่ม Discord bot"""
        logger.info("🚀 Starting Discord bot...")
        try:
            await self.bot.start(self.token)
        except Exception as e:
            logger.error(f"❌ Discord bot error: {e}")

    async def stop(self):
        """หยุด Discord bot"""
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.disconnect(force=True)
        await self.bot.close()
        logger.info("✅ Discord bot stopped")

    async def _run_admin_command(self, ctx, command: str, args: list):
        """Helper: เรียกใช้ระบบ admin command แล้วส่งผลลัพธ์กลับไปใน Discord"""
        try:
            # ดึง queue manager ที่มี get_status (QueueBridge มี base เป็น SequentialQueueManager)
            queue_for_status = getattr(self.queue_manager, 'base', self.queue_manager)

            user_id = str(getattr(ctx.author, 'id', ''))
            context = {
                'safety_filter': self.safety_filter,
                'queue_manager': queue_for_status,
            }
            result = await self.admin_handler.handle_command(command, args, user_id, context)
            if result:
                await ctx.send(result)
        except Exception as e:
            logger.error(f"❌ Admin command error: {e}", exc_info=True)
            try:
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")
            except Exception:
                pass