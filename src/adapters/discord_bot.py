"""
discord_bot.py - Discord Bot with STT, Queue, and Audio Player
แก้ไขเพื่อรองรับ: STT, Sequential Queue, Audio Playback, Lip Sync
"""

import discord
from discord.ext import commands
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from src.core.queue_manager import QueuedMessage, MessageSource, get_queue_manager
from src.core.admin_commands import get_admin_handler
from src.adapters.audio_player import DiscordAudioPlayer

logger = logging.getLogger(__name__)


class DiscordBot:
    """Discord Bot with Voice Support"""
    
    def __init__(
        self,
        token: str,
        motion_controller=None,
        stt_system=None,
        prefix: str = "!"
    ):
        # Discord setup
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        intents.members = True
        
        self.bot = commands.Bot(command_prefix=prefix, intents=intents)
        self.token = token
        
        # Components
        self.motion_controller = motion_controller
        self.stt_system = stt_system
        self.audio_player = DiscordAudioPlayer(motion_controller)
        
        # Queue manager
        self.queue_manager = get_queue_manager()
        
        # Admin handler
        self.admin_handler = get_admin_handler()
        
        # State
        self.is_ready = False
        self.voice_client: Optional[discord.VoiceClient] = None
        
        # Setup events and commands
        self._setup_events()
        self._setup_commands()
    
    def _setup_events(self):
        """Setup Discord events"""
        
        @self.bot.event
        async def on_ready():
            logger.info(f"Discord Bot logged in as {self.bot.user.name} (id={self.bot.user.id})")
            self.is_ready = True
            
            # ตั้งชื่อในเซิร์ฟเวอร์
            for guild in self.bot.guilds:
                try:
                    me = guild.me
                    if me.display_name != self.bot.user.name:
                        await me.edit(nick=self.bot.user.name)
                        logger.info(f"✅ ตั้งชื่อในเซิร์ฟเวอร์ '{guild.name}' เป็น '{self.bot.user.name}' แล้ว")
                except Exception as e:
                    logger.warning(f"ไม่สามารถตั้งชื่อในเซิร์ฟเวอร์ {guild.name}: {e}")
        
        @self.bot.event
        async def on_message(message):
            # ข้าม message จาก bot
            if message.author.bot:
                return
            
            # ถ้าเป็น command ให้ process
            if message.content.startswith(self.bot.command_prefix):
                await self.bot.process_commands(message)
                return
            
            # ถ้าไม่ใช่ command แต่เป็นข้อความปกติ
            # (ไม่เอาเข้าคิวเพราะจะใช้แค่ voice)
            pass
    
    def _setup_commands(self):
        """Setup Discord commands"""
        
        # === Voice Commands ===
        
        @self.bot.command(name='join')
        async def join_voice(ctx):
            """เข้า voice channel"""
            if not ctx.author.voice:
                await ctx.send("❌ คุณต้องอยู่ใน voice channel ก่อน")
                return
            
            voice_channel = ctx.author.voice.channel
            
            try:
                if ctx.voice_client:
                    await ctx.voice_client.move_to(voice_channel)
                else:
                    self.voice_client = await voice_channel.connect()
                
                await ctx.send(f"✅ เข้า voice channel: {voice_channel.name}")
                logger.info(f"Bot เข้า voice channel: {voice_channel.name}")
            
            except Exception as e:
                await ctx.send(f"❌ ไม่สามารถเข้า voice channel ได้: {e}")
                logger.error(f"Join voice error: {e}")
        
        @self.bot.command(name='leave')
        async def leave_voice(ctx):
            """ออกจาก voice channel"""
            if ctx.voice_client:
                await ctx.voice_client.disconnect()
                self.voice_client = None
                await ctx.send("👋 ออกจาก voice channel แล้ว")
                logger.info("Bot ออกจาก voice channel")
            else:
                await ctx.send("❌ ไม่ได้อยู่ใน voice channel")
        
        @self.bot.command(name='listen')
        async def listen_voice(ctx, duration: int = 5):
            """
            ฟังเสียงและแปลงเป็นข้อความ
            Usage: !listen [duration]
            """
            if not ctx.voice_client:
                await ctx.send("❌ Bot ต้องอยู่ใน voice channel ก่อน (ใช้ !join)")
                return
            
            if not self.stt_system:
                await ctx.send("❌ STT system ไม่พร้อม")
                return
            
            # จำกัดเวลา
            duration = max(1, min(duration, 30))  # 1-30 วินาที
            
            await ctx.send(f"🎤 กำลังฟัง {duration} วินาที...")
            
            try:
                # บันทึกและแปลงเสียง
                text = await self.stt_system.record_and_transcribe(
                    ctx.voice_client,
                    duration
                )
                
                if not text or text.strip() == "":
                    await ctx.send("❌ ไม่ได้ยินเสียงอะไร ลองใหม่อีกครั้ง")
                    return
                
                await ctx.send(f"📝 ได้ยิน: {text}")
                logger.info(f"STT Result: {text}")
                
                # เพิ่มเข้าคิว
                message = QueuedMessage(
                    text=text,
                    source=MessageSource.DISCORD_VOICE,
                    user=str(ctx.author.id),
                    timestamp=asyncio.get_event_loop().time(),
                    metadata={
                        "username": ctx.author.name,
                        "voice_client": ctx.voice_client
                    }
                )
                await self.queue_manager.add_message(message)
                
                await ctx.send("⏳ กำลังคิดคำตอบ...")
            
            except Exception as e:
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")
                logger.error(f"Listen error: {e}", exc_info=True)
        
        # === Admin Commands ===
        
        @self.bot.command(name='approve')
        async def approve_request(ctx, approval_id: str):
            """อนุมัติคำถาม"""
            if not self.admin_handler.is_admin(str(ctx.author.id)):
                await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้")
                return
            
            response = await self.admin_handler.handle_command(
                "approve",
                [approval_id],
                str(ctx.author.id),
                {"safety_filter": self.queue_manager}
            )
            await ctx.send(response)
        
        @self.bot.command(name='reject')
        async def reject_request(ctx, approval_id: str):
            """ปฏิเสธคำถาม"""
            if not self.admin_handler.is_admin(str(ctx.author.id)):
                await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้")
                return
            
            response = await self.admin_handler.handle_command(
                "reject",
                [approval_id],
                str(ctx.author.id),
                {"safety_filter": self.queue_manager}
            )
            await ctx.send(response)
        
        @self.bot.command(name='status')
        async def show_status(ctx):
            """ดูสถานะระบบ"""
            if not self.admin_handler.is_admin(str(ctx.author.id)):
                await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้")
                return
            
            response = await self.admin_handler.handle_command(
                "status",
                [],
                str(ctx.author.id),
                {"queue_manager": self.queue_manager}
            )
            await ctx.send(response)
        
        @self.bot.command(name='queue')
        async def show_queue(ctx):
            """ดูคิว"""
            if not self.admin_handler.is_admin(str(ctx.author.id)):
                await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้")
                return
            
            response = await self.admin_handler.handle_command(
                "queue",
                [],
                str(ctx.author.id),
                {"queue_manager": self.queue_manager}
            )
            await ctx.send(response)
        
        @self.bot.command(name='unlock')
        async def unlock_project(ctx, code: str):
            """ปลดล็อคข้อมูลโปรเจค"""
            if not self.admin_handler.is_owner(str(ctx.author.id)):
                await ctx.send("❌ เฉพาะ owner เท่านั้น")
                return
            
            response = await self.admin_handler.handle_command(
                "unlock",
                [code],
                str(ctx.author.id),
                {}
            )
            await ctx.send(response)
        
        @self.bot.command(name='lock')
        async def lock_project(ctx):
            """ล็อคข้อมูลโปรเจค"""
            if not self.admin_handler.is_owner(str(ctx.author.id)):
                await ctx.send("❌ เฉพาะ owner เท่านั้น")
                return
            
            response = await self.admin_handler.handle_command(
                "lock",
                [],
                str(ctx.author.id),
                {}
            )
            await ctx.send(response)
        
        # === Test Commands ===
        
        @self.bot.command(name='speak')
        async def speak_test(ctx, *, text: str):
            """ทดสอบให้ bot พูด"""
            if not ctx.voice_client:
                await ctx.send("❌ Bot ต้องอยู่ใน voice channel ก่อน (ใช้ !join)")
                return
            
            await ctx.send(f"💬 กำลังพูด: {text}")
            
            # เพิ่มเข้าคิวเพื่อทดสอบ
            message = QueuedMessage(
                text=text,
                source=MessageSource.DISCORD_TEXT,
                user=str(ctx.author.id),
                timestamp=asyncio.get_event_loop().time(),
                metadata={
                    "username": ctx.author.name,
                    "voice_client": ctx.voice_client
                }
            )
            await self.queue_manager.add_message(message)
    
    async def play_audio_response(
        self,
        voice_client: discord.VoiceClient,
        audio_file: str,
        text: str
    ) -> bool:
        """
        เล่นเสียงตอบกลับพร้อม lip sync
        
        Args:
            voice_client: Discord VoiceClient
            audio_file: path ไฟล์เสียง
            text: ข้อความที่พูด
        
        Returns:
            True = สำเร็จ, False = ล้มเหลว
        """
        try:
            success = await self.audio_player.play_audio_with_lipsync(
                voice_client,
                audio_file,
                text
            )
            return success
        except Exception as e:
            logger.error(f"❌ Play audio error: {e}", exc_info=True)
            return False
    
    async def start(self):
        """เริ่ม Discord bot"""
        try:
            logger.info("🚀 Starting Discord bot...")
            await self.bot.start(self.token)
        except Exception as e:
            logger.error(f"❌ Discord bot error: {e}", exc_info=True)
    
    async def stop(self):
        """หยุด Discord bot"""
        try:
            if self.voice_client:
                await self.voice_client.disconnect()
            await self.bot.close()
            logger.info("✅ Discord bot stopped")
        except Exception as e:
            logger.error(f"❌ Stop error: {e}")


# Factory function
def create_discord_bot(
    token: str,
    motion_controller=None,
    stt_system=None
) -> DiscordBot:
    """สร้าง Discord bot instance"""
    return DiscordBot(
        token=token,
        motion_controller=motion_controller,
        stt_system=stt_system
    )