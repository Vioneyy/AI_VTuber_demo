# src/adapters/discord_bot.py
"""
Discord Bot Adapter (robust)
- intents.message_content enabled (required for prefix commands in many bots)
- retry-safe voice connect (fetch_channel fallback)
- play_audio_bytes writes temp WAV and uses FFmpegPCMAudio
"""
import os
import asyncio
import tempfile
import logging
from typing import Optional
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
from discord import sinks as discord_sinks

from src.audio.stt_whispercpp import WhisperCppSTT
from src.core.types import IncomingMessage, MessageSource

logger = logging.getLogger(__name__)

class DiscordBotAdapter:
    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        self.bot: Optional[commands.Bot] = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self._running = False
        self._play_lock = asyncio.Lock()
        self._stt_enabled = os.getenv("DISCORD_VOICE_STT_ENABLED", "0").lower() in ("1", "true", "yes")
        self._stt_chunk_sec = float(os.getenv("DISCORD_STT_CHUNK_SECONDS", "5"))
        self._stt_lang = os.getenv("WHISPER_CPP_LANG", "th")
        self._stt_task: Optional[asyncio.Task] = None
        self._stt_engine: Optional[WhisperCppSTT] = None

    async def start_bot(self, token: str):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        # non-privileged: messages (for basic commands)
        try:
            intents.messages = True
        except Exception:
            pass
        # privileged intents are disabled by default to avoid 4014
        enable_members = os.getenv("DISCORD_ENABLE_MEMBERS", "0") in ("1", "true", "yes")
        enable_msg_content = os.getenv("DISCORD_ENABLE_MESSAGE_CONTENT", "0") in ("1", "true", "yes")
        if enable_members:
            try:
                intents.members = True
            except Exception:
                pass
        if enable_msg_content:
            try:
                intents.message_content = True
            except Exception:
                # older versions may not have attribute
                pass

        self.bot = commands.Bot(command_prefix="!", intents=intents)

        @self.bot.event
        async def on_ready():
            logger.info(f"Discord Bot logged in as {self.bot.user} (id={self.bot.user.id})")
            # ตั้งสถานะออนไลน์และ activity เล็กน้อย
            try:
                await self.bot.change_presence(status=discord.Status.online, activity=discord.Game(name="jeed online"))
            except Exception as e:
                logger.debug(f"Presence set failed: {e}")
            # ตั้ง nickname เป็น jeed ในทุก guild ถ้ามีสิทธิ์
            try:
                for g in list(self.bot.guilds or []):
                    me = g.me if hasattr(g, 'me') else None
                    if me:
                        try:
                            await me.edit(nick="jeed")
                            logger.info(f"✅ ตั้งชื่อในเซิร์ฟเวอร์ '{g.name}' เป็น 'jeed' แล้ว")
                        except Exception as ne:
                            logger.debug(f"Set nickname failed in {g.name}: {ne}")
            except Exception:
                pass
            vc_id = os.getenv("DISCORD_VOICE_CHANNEL_ID")
            if vc_id:
                try:
                    chan = self.bot.get_channel(int(vc_id))
                    if not chan:
                        # fallback to fetch_channel (API call)
                        try:
                            chan = await self.bot.fetch_channel(int(vc_id))
                        except Exception as fe:
                            logger.error(f"fetch_channel failed: {fe}", exc_info=True)
                    if chan and isinstance(chan, discord.VoiceChannel):
                        try:
                            # Only connect if not already connected
                            if not (self.voice_client and self.voice_client.is_connected()):
                                self.voice_client = await chan.connect()
                                logger.info(f"✅ Joined voice channel: {chan.name}")
                                # start STT loop if enabled
                                if self._stt_enabled:
                                    try:
                                        self._stt_engine = WhisperCppSTT()
                                        if not self._stt_task or self._stt_task.done():
                                            self._stt_task = asyncio.create_task(self._stt_loop())
                                            logger.info("🎤 STT loop started (Discord voice)")
                                    except Exception as e:
                                        logger.error(f"Failed to start STT loop: {e}", exc_info=True)
                        except Exception as e:
                            logger.error(f"Failed to join voice channel: {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"Voice channel join error: {e}", exc_info=True)

        @self.bot.command(name="ping")
        async def _ping(ctx):
            await ctx.reply("pong")

        # start the bot — avoid infinite reconnect when token invalid
        # Use explicit login + connect(reconnect=False) to prevent auto-retry loops
        self._running = True
        try:
            await self.bot.login(token)
            await self.bot.connect(reconnect=False)
            logger.info("✅ Discord client exited (connect loop ended).")
        except discord.errors.LoginFailure as e:
            logger.error("❌ โทเคน Discord ไม่ถูกต้อง: โปรดตรวจสอบ 'Bot Token' ใน Developer Portal และเชิญบอทเข้ากิลด์ให้ถูกต้อง", exc_info=True)
            try:
                await self.bot.close()
            except Exception:
                pass
            self._running = False
            # re-raise so orchestrator can decide next steps without retrying
            raise
        except discord.errors.ConnectionClosed as e:
            # 4014: Disallowed intents — advise enabling env flags or portal settings
            if getattr(e, "code", None) == 4014:
                logger.error("❌ Discord Gateway ปฏิเสธ intents (4014): ปิด privileged intents หรือเปิดผ่าน Developer Portal. ตั้งค่า DISCORD_ENABLE_MEMBERS/DISCORD_ENABLE_MESSAGE_CONTENT=1 หากต้องการใช้งาน.", exc_info=True)
            else:
                logger.error(f"Discord connection closed: {e}", exc_info=True)
            try:
                await self.bot.close()
            except Exception:
                pass
            self._running = False
            raise
        except Exception as e:
            logger.error(f"Discord client error: {e}", exc_info=True)
            try:
                await self.bot.close()
            except Exception:
                pass
            self._running = False
            raise
        finally:
            self._running = False

    async def _ensure_voice_connected(self) -> bool:
        if self.voice_client and self.voice_client.is_connected():
            return True
        vc_id = os.getenv("DISCORD_VOICE_CHANNEL_ID")
        if not vc_id:
            return False
        if not self.bot:
            return False
        try:
            chan = self.bot.get_channel(int(vc_id))
            if not chan:
                try:
                    chan = await self.bot.fetch_channel(int(vc_id))
                except Exception as fe:
                    logger.error(f"fetch_channel in ensure_voice failed: {fe}", exc_info=True)
                    return False
            if chan and isinstance(chan, discord.VoiceChannel):
                try:
                    self.voice_client = await chan.connect()
                    return True
                except Exception as e:
                    logger.error(f"Failed to connect voice in ensure: {e}", exc_info=True)
                    return False
        except Exception as e:
            logger.error(f"Ensure voice connected error: {e}", exc_info=True)
            return False

    async def play_audio_bytes(self, audio_bytes: bytes):
        if not self.bot:
            logger.error("Discord bot not running — cannot play audio")
            return
        async with self._play_lock:
            try:
                connected = await self._ensure_voice_connected()
                if not connected:
                    logger.warning("Voice not connected — skipping audio play")
                    return

                fd, tmp_path = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                with open(tmp_path, "wb") as f:
                    f.write(audio_bytes)

                audio_source = FFmpegPCMAudio(
                    tmp_path,
                    before_options="-loglevel panic -nostdin",
                    options="-vn -f s16le -ar 48000 -ac 2 -filter:a volume=1.0"
                )

                if self.voice_client.is_playing():
                    self.voice_client.stop()

                self.voice_client.play(audio_source)
                while self.voice_client.is_playing():
                    await asyncio.sleep(0.1)

                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"Error playing audio on Discord: {e}", exc_info=True)

    async def stop(self):
        try:
            if self.voice_client and self.voice_client.is_connected():
                try:
                    await self.voice_client.disconnect()
                except Exception:
                    pass
            if self._stt_task and not self._stt_task.done():
                try:
                    self._stt_task.cancel()
                except Exception:
                    pass
            if self.bot and self._running:
                await self.bot.close()
        except Exception as e:
            logger.debug(f"Discord stop error: {e}", exc_info=True)

    async def _stt_loop(self):
        """
        Chunked recording loop using Pycord sinks to capture short segments,
        transcribe with whisper.cpp, and enqueue to scheduler immediately.
        """
        if not self.voice_client:
            return
        while True:
            try:
                # start recording a short chunk
                sink = discord_sinks.WaveSink()

                def _finished_callback(sink_: discord_sinks.Sink, *args, **kwargs):
                    try:
                        # Iterate per-user audio data
                        for user, audio in getattr(sink_, "audio_data", {}).items():
                            fpath = getattr(audio, "file", None)
                            if not fpath:
                                continue
                            try:
                                transcript = self._stt_engine.transcribe_file(fpath, language=self._stt_lang) if self._stt_engine else ""
                            except Exception:
                                transcript = ""
                            # Clean up file afterwards
                            try:
                                os.remove(fpath)
                            except Exception:
                                pass
                            if transcript:
                                # Enqueue as high-priority Discord message; answer immediately
                                try:
                                    msg = IncomingMessage(
                                        text=transcript,
                                        source=MessageSource.DISCORD,
                                        author=str(getattr(user, "name", getattr(user, "display_name", "unknown"))),
                                        is_question=True,  # treat voice queries as questions
                                        priority=0,
                                        meta={"stt": "whisper.cpp", "lang": self._stt_lang}
                                    )
                                    if self.orchestrator and self.orchestrator.scheduler:
                                        asyncio.create_task(self.orchestrator.scheduler.enqueue(msg))
                                except Exception as e:
                                    logger.error(f"Failed to enqueue STT message: {e}", exc_info=True)

                    except Exception as e:
                        logger.error(f"STT finished callback error: {e}", exc_info=True)

                try:
                    self.voice_client.start_recording(sink, _finished_callback)
                except Exception as e:
                    logger.error(f"start_recording failed: {e}", exc_info=True)
                    await asyncio.sleep(1.0)
                    continue

                await asyncio.sleep(max(1.0, self._stt_chunk_sec))
                try:
                    self.voice_client.stop_recording()
                except Exception as e:
                    logger.error(f"stop_recording failed: {e}", exc_info=True)
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"STT loop error: {e}", exc_info=True)
                await asyncio.sleep(1.0)
