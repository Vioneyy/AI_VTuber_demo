"""
ai_vtuber.py

Main entry for AI VTuber Orchestrator.

- สร้าง component ต่าง ๆ (LLM, TTS, VTS, DiscordBot, QueueManager ฯลฯ)
- เรียก DiscordBot.start() เป็น background task
- ประมวลผลข้อความจากคิว -> generate response -> tts -> play in discord or fallback

หมายเหตุ:
- โค้ดนี้ assume ว่าโมดูลอื่นๆ (src.*) มีอยู่แล้ว
- environment variables ควบคุมบางค่าเช่น DISCORD_BOT_TOKEN, DISCORD_AUTO_JOIN
"""

import asyncio
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

import discord  # optional usage for file upload fallback

# project modules (assume provided)
from src.core.safety_filter import get_safety_filter
from src.core.queue_manager import get_queue_manager, QueuedMessage, MessageSource
from src.core.admin_commands import get_admin_handler
from src.core.response_generator import get_response_generator

from src.adapters.vts.vts_client import VTSClient
from src.adapters.vts.motion_controller import create_motion_controller
from src.adapters.audio_player import DiscordAudioPlayer
from src.adapters.discord_bot import create_discord_bot
from src.adapters.youtube_live import create_youtube_live_adapter

from src.llm.chatgpt_client import ChatGPTClient
from src.personality.personality import PersonalitySystem
from src.adapters.tts.tts_factory import create_tts_engine

logger = logging.getLogger(__name__)


class AIVTuberOrchestrator:
    def __init__(self):
        logger.info("🚀 AI VTuber Orchestrator เริ่มต้น...")
        load_dotenv()

        # core
        self.safety_filter = get_safety_filter()
        self.queue_manager = get_queue_manager()
        self.admin_handler = get_admin_handler()

        # LLM & personality
        self.llm = None
        self.personality = None
        self.response_generator = None

        # VTS / motion
        self.vts_client: VTSClient = None
        self.motion_controller = None

        # TTS & audio
        self.tts = None
        self.audio_player = None
        self.rvc_enabled = os.getenv("ENABLE_RVC", "false").lower() == "true"
        self.rvc = None

        # adapters
        self.discord_bot = None
        self.youtube_adapter = None

        # STT (if present)
        self.stt_system = None

        # runtime state
        self.is_running = False

    async def initialize(self) -> bool:
        """Initialize all components."""
        try:
            logger.info("🔧 เริ่มสร้าง components...")

            # Personality
            persona_name = os.getenv("PERSONA_NAME", "default")
            self.personality = PersonalitySystem(persona_name)
            logger.info(f"✅ Personality: {persona_name}")

            # LLM
            self.llm = ChatGPTClient(
                api_key=os.getenv("OPENAI_API_KEY"),
                model=os.getenv("LLM_MODEL", "gpt-4"),
                personality_system=self.personality
            )
            logger.info("✅ LLM สร้างแล้ว")

            # Response generator
            self.response_generator = get_response_generator(self.llm, self.personality)
            logger.info("✅ Response Generator สร้างแล้ว")

            # VTS client and motion controller
            vts_host = os.getenv("VTS_HOST", "127.0.0.1")
            vts_port = int(os.getenv("VTS_PORT", "8001"))
            self.vts_client = VTSClient(vts_host, vts_port)
            await self.vts_client.connect()
            self.motion_controller = create_motion_controller(self.vts_client, env=dict(os.environ))
            await self.motion_controller.start()
            logger.info("✅ VTS Motion Controller พร้อมแล้ว")

            # TTS engine
            tts_engine_name = os.getenv("TTS_ENGINE", "f5_tts_thai")
            self.tts = create_tts_engine(tts_engine_name)
            logger.info(f"✅ TTS Engine: {tts_engine_name}")

            # Audio player
            self.audio_player = DiscordAudioPlayer(self.motion_controller)
            logger.info("✅ Audio Player พร้อมแล้ว")

            # RVC (if set up)
            if self.rvc_enabled:
                # placeholder for actual RVC initialization
                try:
                    # self.rvc = create_rvc_engine(...)
                    logger.info("✅ RVC enabled — initialization placeholder")
                except Exception as e:
                    logger.warning(f"⚠️ RVC initialization failed: {e}")

            # Discord Bot
            discord_token = os.getenv("DISCORD_BOT_TOKEN")
            if discord_token:
                discord_auto_join = os.getenv("DISCORD_AUTO_JOIN", "false").lower() in ("1", "true", "yes", "y")
                self.discord_bot = create_discord_bot(
                    token=discord_token,
                    motion_controller=self.motion_controller,
                    stt_system=self.stt_system,
                    auto_join_voice=discord_auto_join
                )
                logger.info("✅ Discord Bot สร้างแล้ว")

            # YouTube Live adapter
            youtube_stream_id = os.getenv("YOUTUBE_STREAM_ID")
            if youtube_stream_id:
                try:
                    self.youtube_adapter = create_youtube_live_adapter(stream_id=youtube_stream_id,
                                                                       motion_controller=self.motion_controller)
                    logger.info("✅ YouTube Live Adapter สร้างแล้ว")
                except Exception as e:
                    logger.warning(f"⚠️ YouTube adapter init failed: {e}")

            logger.info("=" * 60)
            logger.info("✅ ทุก components พร้อมแล้ว!")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.exception(f"❌ เกิดข้อผิดพลาดในการเริ่มต้น: {e}")
            return False

    async def process_message(self, message: QueuedMessage) -> bool:
        """
        Process a queued message:
         1) Generate response (with safety check)
         2) TTS generation
         3) (Optional) RVC conversion
         4) Play to Discord voice client OR fallback to text-channel file upload
        """
        try:
            logger.info(f"▶️ Processing: [{message.source.value}] {message.text[:120]}")

            # Safety + generate response
            response_text, rejection_reason = await self.response_generator.generate_response(
                user_message=message.text,
                user=message.user,
                source=message.source.value,
                repeat_question=message.metadata.get("repeat_question", False)
            )

            if not response_text:
                logger.warning(f"⚠️ Response rejected: {rejection_reason}")
                # Optionally send a deny message back to channel if present
                ch = message.metadata.get("channel")
                if ch and hasattr(ch, "send"):
                    await ch.send("❌ ข้อความไม่ผ่านการกรองความปลอดภัย")
                return False

            logger.info(f"💬 Response generated: {response_text[:200]}")

            # TTS produce an audio file path
            audio_file = await self.tts.generate(response_text)
            if not audio_file or not Path(audio_file).exists():
                logger.error("❌ TTS failed to produce audio file")
                return False
            logger.info(f"🎵 TTS saved to: {audio_file}")

            # RVC conversion if available
            if self.rvc_enabled and self.rvc:
                try:
                    audio_file = await self.rvc.convert(audio_file)
                    logger.info(f"🎤 RVC produced: {audio_file}")
                except Exception as e:
                    logger.warning(f"⚠️ RVC error, using original audio: {e}")

            # Play audio
            await self._play_audio_response(message, audio_file, response_text)
            return True

        except Exception as e:
            logger.exception(f"❌ Process message error: {e}")
            return False

    async def _play_audio_response(self, message: QueuedMessage, audio_file: str, text: str):
        """
        Play generated audio for a queued message:

        - If Discord voice_client is available, play there via discord_bot.play_audio_response
        - Else fallback: send audio file to text channel and/or log
        - If message is from YouTube chat, special handling (not implemented)
        """
        try:
            if message.source in (MessageSource.DISCORD_TEXT, MessageSource.DISCORD_VOICE):
                # prefer the orchestrator's discord bot's voice client
                voice_client = None
                if self.discord_bot:
                    voice_client = self.discord_bot.voice_client

                # fallback to metadata-supplied voice client
                if not voice_client:
                    voice_client = message.metadata.get("voice_client")

                if voice_client and getattr(voice_client, "is_connected", lambda: False)():
                    logger.info("🔊 Playing audio in Discord voice...")
                    ok = await self.discord_bot.play_audio_response(voice_client, audio_file, text)
                    if ok:
                        logger.info("✅ Audio played in voice")
                        return
                    else:
                        logger.warning("⚠️ Play in voice failed — fallback to text channel")

                # fallback: send file in channel (text)
                channel = message.metadata.get("channel")
                if channel:
                    try:
                        await channel.send(content=f"💬 {text}", file=discord.File(audio_file, filename="response.wav"))
                        logger.info("✅ Sent audio file in text channel as fallback")
                        return
                    except Exception as e:
                        logger.exception(f"❌ Sending audio file to text channel failed: {e}")
                        # final fallback: send text-only
                        try:
                            await channel.send(f"💬 {text}")
                        except Exception:
                            pass
                else:
                    logger.warning("⚠️ No text channel available to send fallback message")
            elif message.source == MessageSource.YOUTUBE_CHAT:
                # TODO: implement streaming audio into youtube/obs pipeline or local playback
                logger.info("🔊 (YouTube) would play audio here (not implemented)")
            else:
                logger.info("🔊 Unknown message source — skipping playback")
        except Exception as e:
            logger.exception(f"❌ _play_audio_response error: {e}")

    async def start(self):
        """Start everything and run main loop."""
        ok = await self.initialize()
        if not ok:
            logger.error("❌ Initialization failed — aborting run")
            return

        self.is_running = True

        # start queue processing
        self.queue_manager.start(self.process_message)
        logger.info("✅ Queue Manager เริ่มทำงาน")

        # start youtube adapter if configured
        if self.youtube_adapter:
            try:
                await self.youtube_adapter.start()
            except Exception as e:
                logger.warning(f"⚠️ YouTube adapter start failed: {e}")

        # start discord bot as background task
        discord_task = None
        if self.discord_bot:
            discord_task = asyncio.create_task(self.discord_bot.start())
            logger.info("✅ Discord Bot task started")

        logger.info("=" * 60)
        logger.info("✅ ระบบเริ่มทำงานเรียบร้อย!")
        logger.info("=" * 60)

        try:
            # keep running until external stop
            while self.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("⚠️ KeyboardInterrupt received — stopping")
        finally:
            # gracefully stop
            if discord_task:
                try:
                    # request stop on discord bot
                    await self.stop()
                    discord_task.cancel()
                    try:
                        await discord_task
                    except asyncio.CancelledError:
                        pass
                except Exception as e:
                    logger.exception(f"Error during shutdown: {e}")
            else:
                await self.stop()

    async def stop(self):
        """Stop all components gracefully."""
        logger.info("🛑 กำลังปิดระบบ...")
        self.is_running = False

        try:
            await self.queue_manager.stop()
        except Exception:
            pass

        try:
            if self.youtube_adapter:
                await self.youtube_adapter.stop()
        except Exception:
            pass

        try:
            if self.discord_bot:
                await self.discord_bot.stop()
        except Exception:
            pass

        try:
            if self.motion_controller:
                await self.motion_controller.stop()
        except Exception:
            pass

        try:
            if self.vts_client:
                await self.vts_client.disconnect()
        except Exception:
            pass

        logger.info("✅ ระบบปิดเรียบร้อย")


async def main():
    orchestrator = AIVTuberOrchestrator()
    await orchestrator.start()


if __name__ == "__main__":
    # basic logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    asyncio.run(main())
