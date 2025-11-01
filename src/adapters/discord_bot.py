"""
discord_bot.py - Discord Bot with Voice Connection Fix
เวอร์ชันสมบูรณ์ที่แก้ปัญหา Error 4006
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
from src.adapters.discord_voice_fix import VoiceConnectionFixer

logger = logging.getLogger(__name__)


class DiscordBot:
    """Discord Bot with Fixed Voice Support"""
    
    def __init__(
        self,
        token: str,
        motion_controller=None,
        stt_system=None,
        auto_join_voice: bool = True,
        prefix: str = "!"
    ):
        # Check voice dependencies
        logger.info("🔍 Checking voice dependencies...")
        issues = VoiceConnectionFixer.check_voice_dependencies()
        if issues:
            logger.warning("⚠️ Voice dependency issues found:")
            for issue in issues:
                logger.warning(f"   {issue}")
            logger.warning("💡 Install: pip install PyNaCl opuslib")
        
        # Discord setup with proper intents
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
        
        # Queue & Admin
        self.queue_manager = get_queue_manager()
        self.admin_handler = get_admin_handler()
        
        # Voice state
        self.auto_join_voice = auto_join_voice
        self.target_voice_channel_id = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.voice_reconnect_task: Optional[asyncio.Task] = None
        
        # Error tracking
        self.last_voice_error = None
        self.last_voice_close_code = None
        self.voice_connection_attempts = 0
        
        # Setup
        self._setup_events()
        self._setup_commands()
    
    def _setup_events(self):
        """Setup Discord events"""
        
        @self.bot.event
        async def on_ready():
            logger.info(f"Discord Bot logged in as {self.bot.user.name} (id={self.bot.user.id})")
            
            # Auto join voice channel
            if self.auto_join_voice:
                await self._auto_join_voice()
            
            # Start voice reconnect monitor
            self.voice_reconnect_task = asyncio.create_task(self._voice_reconnect_monitor())
        
        @self.bot.event
        async def on_message(message):
            if message.author.bot:
                return
            
            # Process commands
            if message.content.startswith(self.bot.command_prefix):
                await self.bot.process_commands(message)
                return
            
            # Text message → Queue
            if not message.guild:
                return
            
            queued_msg = QueuedMessage(
                text=message.content,
                source=MessageSource.DISCORD_TEXT,
                user=str(message.author.id),
                timestamp=asyncio.get_event_loop().time(),
                metadata={
                    "username": message.author.name,
                    "channel": message.channel,
                    "voice_client": self.voice_client
                }
            )
            await self.queue_manager.add_message(queued_msg)
        
        @self.bot.event
        async def on_voice_state_update(member, before, after):
            """ติดตามการเปลี่ยนแปลง voice state"""
            if member.id == self.bot.user.id:
                if before.channel and not after.channel:
                    logger.warning("⚠️ Bot ถูก disconnect จาก voice channel")
                    self.voice_client = None
    
    async def _auto_join_voice(self):
        """เข้า voice channel อัตโนมัติ"""
        try:
            if not self.bot.guilds:
                logger.warning("⚠️ Bot ไม่ได้อยู่ใน guild ไหนเลย")
                return
            
            guild = self.bot.guilds[0]
            
            # หา voice channel ที่มีคนอยู่
            for channel in guild.voice_channels:
                if len(channel.members) > 0:
                    logger.info(f"🎯 พบ voice channel: {channel.name} ({len(channel.members)} คน)")
                    success = await self._connect_to_voice(channel)
                    if success:
                        logger.info(f"✅ Auto joined voice: {channel.name}")
                        return
                    else:
                        logger.warning(f"⚠️ ไม่สามารถเข้า {channel.name} ได้")
                        continue
            
            logger.warning("⚠️ ไม่พบ voice channel ที่มีคนอยู่")
        
        except Exception as e:
            logger.error(f"❌ Auto join error: {e}", exc_info=True)
    
    async def _connect_to_voice(
        self,
        channel: discord.VoiceChannel,
        timeout: float = 15.0
    ) -> bool:
        """
        เชื่อมต่อ voice channel แบบ robust (ใช้ VoiceConnectionFixer)
        
        Args:
            channel: Voice channel ที่จะเชื่อมต่อ
            timeout: Timeout ในการเชื่อมต่อ
        
        Returns:
            True = สำเร็จ, False = ล้มเหลว
        """
        try:
            # ถ้าเชื่อมต่ออยู่แล้ว
            if self.voice_client and self.voice_client.is_connected():
                if self.voice_client.channel.id == channel.id:
                    logger.info("✅ เชื่อมต่ออยู่แล้ว")
                    return True
                else:
                    # Move to new channel
                    await self.voice_client.move_to(channel)
                    logger.info(f"✅ ย้ายไป: {channel.name}")
                    self.target_voice_channel_id = channel.id
                    return True
            
            # Disconnect ก่อนถ้ามี
            if self.voice_client:
                try:
                    await self.voice_client.disconnect(force=True)
                except Exception:
                    pass
                self.voice_client = None
            
            logger.info(f"📞 กำลังเชื่อมต่อ: {channel.name}...")
            self.voice_connection_attempts += 1
            
            # ใช้ VoiceConnectionFixer
            self.voice_client = await VoiceConnectionFixer.robust_voice_connect(
                channel,
                timeout=timeout,
                max_retries=3
            )
            
            if self.voice_client:
                self.target_voice_channel_id = channel.id
                self.last_voice_error = None
                self.last_voice_close_code = None
                logger.info(f"✅ เชื่อมต่อสำเร็จ: {channel.name}")
                return True
            else:
                logger.error("❌ ไม่สามารถเชื่อมต่อได้")
                return False
        
        except discord.errors.ClientException as e:
            # Error 4006 handling
            if "4006" in str(e):
                self.last_voice_close_code = 4006
                self.last_voice_error = str(e)
                logger.error("❌ Voice invalid session (4006) — cleaned up. Will retry later.")
                
                # Cleanup
                if self.voice_client:
                    try:
                        await self.voice_client.disconnect(force=True)
                    except Exception:
                        pass
                    self.voice_client = None
                
                return False
            else:
                logger.error(f"❌ Client error: {e}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Connection error: {e}", exc_info=True)
            return False
    
    async def _voice_reconnect_monitor(self):
        """ตรวจสอบและ reconnect voice อัตโนมัติ"""
        logger.info("🔄 Voice reconnect monitor เริ่มทำงาน")
        
        while True:
            try:
                await asyncio.sleep(15)  # เช็คทุก 15 วินาที
                
                # ถ้าไม่มี target channel = ข้าม
                if not self.target_voice_channel_id:
                    continue
                
                # ถ้าเชื่อมต่ออยู่ = ข้าม
                if self.voice_client and self.voice_client.is_connected():
                    continue
                
                # ถ้าล้มเหลวมากเกิน 5 ครั้ง = หยุด retry
                if self.voice_connection_attempts > 5:
                    logger.warning("⚠️ Voice connection failed too many times. Stopped auto-retry.")
                    logger.warning("💡 Use !join to retry manually")
                    continue
                
                # Reconnect
                logger.warning("⚠️ Voice connection หลุด กำลัง reconnect...")
                
                channel = self.bot.get_channel(self.target_voice_channel_id)
                if channel:
                    await self._connect_to_voice(channel)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Reconnect monitor error: {e}")
    
    def _setup_commands(self):
        """Setup commands"""
        
        @self.bot.command(name='join')
        async def join_voice(ctx):
            """เข้า voice channel"""
            if not ctx.author.voice:
                await ctx.send("❌ คุณต้องอยู่ใน voice channel ก่อน")
                return
            
            channel = ctx.author.voice.channel
            success = await self._connect_to_voice(channel)
            
            if success:
                await ctx.send(f"✅ เข้า voice: {channel.name}")
            else:
                error_msg = "❌ ไม่สามารถเข้า voice ได้"
                
                if self.last_voice_close_code == 4006:
                    error_msg += "\n⚠️ Error 4006 (Invalid Session) detected."
                    error_msg += "\n💡 Possible causes:"
                    error_msg += "\n   - Windows Firewall blocking UDP"
                    error_msg += "\n   - Missing PyNaCl: `pip install PyNaCl`"
                    error_msg += "\n   - Network/Router blocking Discord voice"
                    error_msg += "\n\nTry: `!voicelog` for details"
                
                await ctx.send(error_msg)
        
        @self.bot.command(name='leave')
        async def leave_voice(ctx):
            """ออกจาก voice"""
            if self.voice_client:
                await self.voice_client.disconnect()
                self.voice_client = None
                self.target_voice_channel_id = None
                self.voice_connection_attempts = 0
                await ctx.send("👋 ออกจาก voice แล้ว")
            else:
                await ctx.send("❌ ไม่ได้อยู่ใน voice")
        
        @self.bot.command(name='speak')
        async def speak_test(ctx, *, text: str):
            """ทดสอบพูด"""
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ Bot ต้องอยู่ใน voice ก่อน (ใช้ !join)")
                return
            
            await ctx.send(f"💬 กำลังพูด: {text}")
            
            queued_msg = QueuedMessage(
                text=text,
                source=MessageSource.DISCORD_TEXT,
                user=str(ctx.author.id),
                timestamp=asyncio.get_event_loop().time(),
                metadata={
                    "username": ctx.author.name,
                    "channel": ctx.channel,
                    "voice_client": self.voice_client
                }
            )
            await self.queue_manager.add_message(queued_msg)
        
        @self.bot.command(name='voicelog')
        async def voice_log(ctx):
            """ดู voice connection log"""
            voice_status = "✅ Connected" if (self.voice_client and self.voice_client.is_connected()) else "❌ Disconnected"
            
            log_msg = f"""
📊 **Voice Connection Status**

**Status:** {voice_status}
**Connection Attempts:** {self.voice_connection_attempts}
**Last Error Code:** {self.last_voice_close_code or 'None'}
**Last Error:** {self.last_voice_error or 'None'}

**Target Channel ID:** {self.target_voice_channel_id or 'None'}
"""
            
            if self.last_voice_close_code == 4006:
                log_msg += """
⚠️ **Error 4006 Detected**

**Possible Solutions:**
1. Install PyNaCl: `pip install PyNaCl opuslib`
2. Add Windows Firewall rule for Python UDP
3. Try different network (mobile hotspot)
4. Check bot permissions (Connect, Speak)
5. Use `!diagnose` to run full diagnostics
"""
            
            await ctx.send(log_msg)
        
        @self.bot.command(name='diagnose')
        async def diagnose(ctx):
            """วินิจฉัยปัญหา voice"""
            await ctx.send("🔍 กำลังวินิจฉัยปัญหา...")
            
            issues = VoiceConnectionFixer.check_voice_dependencies()
            
            if not issues:
                await ctx.send("✅ ไม่พบปัญหา dependencies")
            else:
                msg = "❌ พบปัญหา:\n"
                for issue in issues:
                    msg += f"   {issue}\n"
                msg += "\n💡 แก้ไข: `pip install PyNaCl opuslib`"
                await ctx.send(msg)
        
        # Admin commands
        @self.bot.command(name='status')
        async def show_status(ctx):
            if not self.admin_handler.is_admin(str(ctx.author.id)):
                return
            
            voice_status = "✅ Connected" if (self.voice_client and self.voice_client.is_connected()) else "❌ Disconnected"
            queue_status = self.queue_manager.get_status()
            
            status_msg = f"""
📊 **สถานะระบบ**
- Voice: {voice_status}
- Queue: {queue_status['queue_size']} ข้อความ
- Processing: {'✅' if queue_status['is_processing'] else '❌'}
- Total Processed: {queue_status['total_processed']}
- Errors: {queue_status['total_errors']}
"""
            await ctx.send(status_msg)
    
    async def play_audio_response(
        self,
        voice_client: discord.VoiceClient,
        audio_file: str,
        text: str
    ) -> bool:
        """เล่นเสียงพร้อม lip sync"""
        if not voice_client or not voice_client.is_connected():
            logger.error("❌ Voice client ไม่ได้เชื่อมต่อ")
            return False
        
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
        """เริ่ม bot"""
        try:
            logger.info("🚀 Starting Discord bot...")
            await self.bot.start(self.token)
        except Exception as e:
            logger.error(f"❌ Discord bot error: {e}", exc_info=True)
    
    async def stop(self):
        """หยุด bot"""
        try:
            if self.voice_reconnect_task:
                self.voice_reconnect_task.cancel()
                try:
                    await self.voice_reconnect_task
                except asyncio.CancelledError:
                    pass
            
            if self.voice_client:
                await self.voice_client.disconnect()
            
            await self.bot.close()
            logger.info("✅ Discord bot stopped")
        except Exception as e:
            logger.error(f"❌ Stop error: {e}")


def create_discord_bot(
    token: str,
    motion_controller=None,
    stt_system=None,
    auto_join_voice: bool = True
) -> DiscordBot:
    """สร้าง Discord bot"""
    return DiscordBot(
        token=token,
        motion_controller=motion_controller,
        stt_system=stt_system,
        auto_join_voice=auto_join_voice
    )