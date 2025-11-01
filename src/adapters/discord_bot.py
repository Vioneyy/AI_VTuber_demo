"""
discord_bot.py

Discord adapter / bot wrapper for AI VTuber project.

สิ่งที่แก้:
- รองรับกรณี voice invalid session (4006) และ cleanup
- ป้องกันการเชื่อมต่อซ้อนด้วย asyncio.Lock()
- voice reconnect monitor + exponential backoff
- auto-join (ควบคุมด้วย ENV DISCORD_AUTO_JOIN)
- safer connect workflow (permissions, existing voice client handling)
- log เพิ่มเติมเพื่อ debugging
"""

import asyncio
import logging
import socket
from typing import Optional

import discord
from discord.ext import commands

# project imports (assumed to exist in repository)
from src.core.queue_manager import QueuedMessage, MessageSource, get_queue_manager
from src.core.admin_commands import get_admin_handler
from src.adapters.audio_player import DiscordAudioPlayer

logger = logging.getLogger(__name__)


class DiscordBot:
    """
    High-level Discord bot wrapper used by AI VTuber orchestrator.

    - token: bot token (full)
    - motion_controller: optional, passed to audio player for lip-sync
    - stt_system: optional speech-to-text system
    - auto_join_voice: auto join a voice channel on_ready if True
    """

    def __init__(self, token: str, motion_controller=None, stt_system=None, auto_join_voice: bool = False,
                 prefix: str = "!"):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.voice_states = True
        intents.members = True

        # Use commands.Bot for convenience with commands extension
        self.bot = commands.Bot(command_prefix=prefix, intents=intents)
        self.token = token

        # components
        self.motion_controller = motion_controller
        self.stt_system = stt_system
        self.audio_player = DiscordAudioPlayer(motion_controller)

        self.queue_manager = get_queue_manager()
        self.admin_handler = get_admin_handler()

        # voice tracking
        self.voice_client: Optional[discord.VoiceClient] = None
        self.target_voice_channel_id: Optional[int] = None

        # reconnect monitor
        self._connect_lock = asyncio.Lock()
        self._reconnect_backoff = 10.0
        self._max_reconnect_backoff = 60.0
        self.voice_reconnect_task: Optional[asyncio.Task] = None

        # state for diagnostics
        self.last_voice_close_code: Optional[int] = None
        self.last_voice_error: Optional[str] = None

        self.auto_join_voice = auto_join_voice

        # register events & commands
        self._setup_events()
        self._setup_commands()

    def _setup_events(self):
        @self.bot.event
        async def on_ready():
            logger.info(f"Discord Bot logged in as {self.bot.user} (id={self.bot.user.id})")
            # start reconnect monitor
            if not self.voice_reconnect_task:
                self.voice_reconnect_task = asyncio.create_task(self._voice_reconnect_monitor())

            # auto-join if requested
            if self.auto_join_voice:
                # schedule auto join short delay to ensure guilds cached
                asyncio.create_task(self._delayed_auto_join())

        @self.bot.event
        async def on_disconnect():
            logger.warning("Discord client disconnected from gateway.")

        @self.bot.event
        async def on_resumed():
            logger.info("Discord session resumed.")

        @self.bot.event
        async def on_error(event_method, *args, **kwargs):
            logger.exception(f"Discord on_error: event={event_method}")

        @self.bot.event
        async def on_message(message: discord.Message):
            # ignore bots
            if message.author.bot:
                return

            # allow commands to process
            await self.bot.process_commands(message)

            # non-command messages -> queue (example)
            if not message.content.startswith(self.bot.command_prefix):
                if message.guild:
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
            # Track if bot gets disconnected from voice
            if member.id == self.bot.user.id:
                if before.channel and not after.channel:
                    logger.warning("⚠️ Bot ถูก disconnect จาก voice channel")
                    self.voice_client = None

    async def _delayed_auto_join(self, delay: float = 2.0):
        await asyncio.sleep(delay)
        try:
            await self._auto_join_voice()
        except Exception as e:
            logger.error(f"Auto-join failed: {e}", exc_info=True)

    async def _auto_join_voice(self):
        """
        Auto-join first available voice channel with members.
        Controlled by ENV in ai_vtuber orchestration.
        """
        if not self.bot.guilds:
            logger.warning("⚠️ Bot ไม่ได้อยู่ใน guild ไหนเลย")
            return

        # Try to find a voice channel with members
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                if len(channel.members) > 0:
                    try:
                        ok = await self._connect_to_voice(channel)
                        if ok:
                            logger.info(f"✅ Auto joined voice {channel.name} in Guild {guild.name}")
                            return
                    except Exception as e:
                        logger.error(f"Auto join error for channel {channel.name}: {e}", exc_info=True)
        logger.warning("⚠️ ไม่พบ voice channel ที่มีคนอยู่สำหรับ auto-join")

    async def _connect_to_voice(self, channel: discord.VoiceChannel, timeout: float = 15.0) -> bool:
        """
        Robust voice connect.

        - Use a connect lock to prevent concurrent connections
        - Do permissions check
        - Handle existing guild voice client
        - Detect and cleanup 4006/invalid session
        """
        async with self._connect_lock:
            try:
                # if already connected to same channel
                existing_vc = channel.guild.voice_client
                if existing_vc and existing_vc.is_connected():
                    # if it's already in intended channel, reuse
                    if existing_vc.channel.id == channel.id:
                        self.voice_client = existing_vc
                        self.target_voice_channel_id = channel.id
                        logger.info("✅ พบการเชื่อมต่อเดิมใน guild และช่องเดียวกัน — reuse voice client")
                        return True
                    else:
                        # attempt move
                        try:
                            await existing_vc.move_to(channel)
                            self.voice_client = existing_vc
                            self.target_voice_channel_id = channel.id
                            logger.info(f"✅ ย้าย voice client ไปยัง channel: {channel.name}")
                            return True
                        except Exception:
                            # fallback: disconnect existing and try fresh connect
                            try:
                                await existing_vc.disconnect(force=True)
                            except Exception:
                                pass

                # disconnect current client if present (clean state)
                if self.voice_client:
                    try:
                        await self.voice_client.disconnect(force=True)
                    except Exception:
                        pass
                    self.voice_client = None

                # Permission check
                perms = channel.permissions_for(channel.guild.me)
                if not perms.connect or not perms.speak:
                    logger.error("❌ Bot ไม่มีสิทธิ์ Connect หรือ Speak ในช่องนี้")
                    return False

                # Force IPv4 address resolution as a fallback (some voice endpoints prefer IPv4)
                original_getaddrinfo = socket.getaddrinfo

                def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
                    return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

                socket.getaddrinfo = _ipv4_only

                try:
                    logger.info(f"📞 กำลังเชื่อมต่อ voice -> {channel.name} (Timeout {timeout}s)")
                    vc = await asyncio.wait_for(channel.connect(timeout=timeout, reconnect=False), timeout=timeout)
                    self.voice_client = vc
                    self.target_voice_channel_id = channel.id
                    # small delay to let internal handshake settle
                    await asyncio.sleep(1.5)
                    logger.info(f"✅ เชื่อมต่อ voice สำเร็จ: {channel.name}")
                    # reset reconnect backoff
                    self._reconnect_backoff = 10.0
                    return True
                finally:
                    socket.getaddrinfo = original_getaddrinfo

            except asyncio.TimeoutError:
                logger.error(f"❌ Timeout connecting to voice channel {channel.name}")
                return False
            except discord.errors.ClientException as e:
                # handle "Already connected" or invalid session errors surfaced here
                msg = str(e).lower()
                logger.error(f"discord ClientException while connecting: {e}")
                if "4006" in msg or "invalid session" in msg:
                    # cleanup existing voice client
                    try:
                        existing_vc = channel.guild.voice_client
                        if existing_vc:
                            await existing_vc.disconnect(force=True)
                        self.voice_client = None
                    except Exception:
                        pass
                    self.last_voice_close_code = 4006
                    self.last_voice_error = str(e)
                    logger.error("❌ Voice invalid session (4006) — cleaned up. Will retry later.")
                    return False
                # other client exception
                return False
            except Exception as e:
                # attempt to detect close code attribute if present
                code = getattr(e, "code", None)
                if code == 4006:
                    try:
                        existing_vc = channel.guild.voice_client
                        if existing_vc:
                            await existing_vc.disconnect(force=True)
                        self.voice_client = None
                    except Exception:
                        pass
                    self.last_voice_close_code = 4006
                    self.last_voice_error = str(e)
                    logger.error("❌ Voice invalid session (4006) — cleaned up. Will retry later.")
                    return False

                logger.exception(f"❌ Unknown error connecting to voice: {e}")
                return False

    async def _voice_reconnect_monitor(self):
        """
        Background task to ensure voice connection is maintained.

        - Exponential backoff when reconnect fails
        - Attempts to reconnect to the target_voice_channel_id
        """
        logger.info("🔄 Voice reconnect monitor started")
        try:
            while True:
                await asyncio.sleep(self._reconnect_backoff)

                # if no target channel set, skip
                if not self.target_voice_channel_id:
                    continue

                # if already connected, reset backoff and continue
                if self.voice_client and self.voice_client.is_connected():
                    self._reconnect_backoff = 10.0
                    continue

                # try to reconnect
                logger.warning("⚠️ Voice connection lost — attempting reconnect")
                channel = self.bot.get_channel(self.target_voice_channel_id)
                if channel:
                    success = await self._connect_to_voice(channel)
                    if success:
                        logger.info("✅ Reconnected to voice")
                        self._reconnect_backoff = 10.0
                    else:
                        # increase backoff with cap
                        self._reconnect_backoff = min(self._reconnect_backoff * 2, self._max_reconnect_backoff)
                        logger.info(f"🔁 Reconnect failed — next backoff {self._reconnect_backoff}s")
                else:
                    logger.warning("⚠️ Target voice channel not found in cache")
        except asyncio.CancelledError:
            logger.info("Voice reconnect monitor cancelled")
        except Exception as e:
            logger.exception(f"Voice reconnect monitor error: {e}")

    def _setup_commands(self):
        @self.bot.command(name="join")
        async def join(ctx: commands.Context):
            """Join the voice channel that the command user is in."""
            if not ctx.author.voice:
                await ctx.send("❌ คุณต้องอยู่ใน voice channel ก่อน")
                return
            channel = ctx.author.voice.channel
            ok = await self._connect_to_voice(channel)
            if ok:
                await ctx.send(f"✅ เข้า voice: {channel.name}")
            else:
                if self.last_voice_close_code == 4006:
                    await ctx.send("❌ เข้าห้องไม่สำเร็จ: Voice invalid session (4006). โปรดตรวจ firewall/UDP และลองใหม่")
                else:
                    await ctx.send("❌ ไม่สามารถเข้า voice ได้")

        @self.bot.command(name="leave")
        async def leave(ctx: commands.Context):
            """Disconnect the bot from voice (if connected)."""
            if self.voice_client:
                try:
                    await self.voice_client.disconnect()
                except Exception:
                    pass
                self.voice_client = None
                self.target_voice_channel_id = None
                await ctx.send("👋 ออกจาก voice แล้ว")
            else:
                await ctx.send("❌ ไม่ได้อยู่ใน voice")

        @self.bot.command(name="voicelog")
        async def voicelog(ctx: commands.Context):
            """Show last voice error / close code."""
            code = self.last_voice_close_code
            err = self.last_voice_error or "-"
            status = "✅ Connected" if (self.voice_client and self.voice_client.is_connected()) else "❌ Disconnected"
            msg = (
                f"📜 Voice Log\n"
                f"- Status: {status}\n"
                f"- Close Code: {code if code is not None else '-'}\n"
                f"- Error: {err}"
            )
            await ctx.send(msg)

        @self.bot.command(name="speak")
        async def speak(ctx: commands.Context, *, text: str):
            """Queue text to be spoken (for testing)."""
            # ensure channel
            if not ctx.guild:
                await ctx.send("❌ คำสั่งนี้ต้องใช้ใน server เท่านั้น")
                return

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
            await ctx.send(f"💬 ข้อความถูกเพิ่มในคิว: {text[:120]}")

        @self.bot.command(name="status")
        async def status_cmd(ctx: commands.Context):
            """Admin command: show system status."""
            if not self.admin_handler.is_admin(str(ctx.author.id)):
                return
            voice_status = "✅ Connected" if (self.voice_client and self.voice_client.is_connected()) else "❌ Disconnected"
            status_msg = (
                f"📊 **สถานะระบบ**\n"
                f"- Voice: {voice_status}\n"
                f"- Queue: {self.queue_manager.get_status().get('queue_size', '-')}\n"
            )
            await ctx.send(status_msg)

    async def play_audio_response(self, voice_client: discord.VoiceClient, audio_file: str, text: str) -> bool:
        """
        Play an audio file in the provided voice_client and attempt lip-sync via audio_player.
        audio_file expected to be a WAV/OGG path playable by FFmpegPCMAudio.
        """
        if not voice_client or not voice_client.is_connected():
            logger.error("❌ Voice client ไม่ได้เชื่อมต่อ")
            return False

        try:
            # Delegate to audio player component for lipsync + playing
            success = await self.audio_player.play_audio_with_lipsync(voice_client, audio_file, text)
            return bool(success)
        except Exception as e:
            logger.exception(f"❌ Play audio error: {e}")
            return False

    async def start(self):
        """Start the bot (this will block until the bot closed)."""
        logger.info("🚀 Starting Discord bot...")
        try:
            await self.bot.start(self.token)
        except Exception as e:
            logger.exception(f"❌ Discord bot start failed: {e}")

    async def stop(self):
        """Stop bot gracefully."""
        logger.info("🛑 Stopping Discord bot...")
        # cancel reconnect monitor
        try:
            if self.voice_reconnect_task:
                self.voice_reconnect_task.cancel()
                try:
                    await self.voice_reconnect_task
                except asyncio.CancelledError:
                    pass
        except Exception:
            pass

        # disconnect voice
        try:
            if self.voice_client:
                await self.voice_client.disconnect()
                self.voice_client = None
        except Exception:
            pass

        # close bot
        try:
            await self.bot.close()
            logger.info("✅ Discord bot stopped")
        except Exception as e:
            logger.exception(f"❌ Error closing bot: {e}")


def create_discord_bot(token: str, motion_controller=None, stt_system=None, auto_join_voice: bool = False) -> DiscordBot:
    return DiscordBot(token=token, motion_controller=motion_controller, stt_system=stt_system,
                      auto_join_voice=auto_join_voice)
