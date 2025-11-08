"""
Jeed AI VTuber - Main Application
เวอร์ชันที่แก้ไขปัญหาทั้งหมด
"""
import asyncio
import logging
import signal
import sys
from pathlib import Path
import io
import os
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from core.queue_manager import SmartQueueManager, QueueItem
from adapters.discord_bot import DiscordBotAdapter
from audio.faster_whisper_stt import FasterWhisperSTT as STTHandler  # ใช้ Faster-Whisper เพื่อความเร็วและความเสถียร
from audio.edge_tts_handler import EdgeTTSHandler  # ใช้ Edge-TTS แทน RVC เพื่อความเร็วและเสียงธรรมชาติ
from core.response_generator import get_response_generator
from personality.jeed_persona import jeed_persona
from llm.chatgpt_client import ChatGPTClient
from core.config import config as core_config

# Setup logging
# Configure logging with UTF-8 safe console handler
try:
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception:
    utf8_stdout = sys.stdout

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(str(Path(core_config.system.log_dir) / 'ai_vtuber.log'), encoding='utf-8'),
        logging.StreamHandler(utf8_stdout)
    ]
)

logger = logging.getLogger(__name__)

class JeedAIVTuber:
    """Main AI VTuber application"""
    
    def __init__(self):
        """Initialize AI VTuber"""
        self.config = core_config
        
        # Components
        self.queue_manager: SmartQueueManager = None
        self.discord_bot: DiscordBotAdapter = None
        self.vts_client = None  # VTube Studio client
        self.tts_engine = None  # TTS engine
        self.llm_processor = None  # LLM processor
        self.stt_handler = None  # STT engine (Faster-Whisper)
        
        # Tasks
        self.tasks = []
        self.running = False
        self._stopping = False
        
        logger.info("🎮 Jeed AI VTuber initialized")
    
    async def initialize(self):
        """Initialize all components"""
        logger.info("=" * 60)
        logger.info("🎮 Jeed AI VTuber Starting...")
        logger.info("=" * 60)
        
        # Validate config (core.config prints details internally)
        is_valid = self.config.validate()
        if not is_valid:
            logger.error("❌ Configuration invalid. Please check your .env settings.")
            raise ValueError("Critical configuration errors")
        
        logger.info("✅ การตั้งค่าถูกต้องทั้งหมด")
        
        # Initialize Queue Manager
        logger.info("📦 Initializing Queue Manager...")
        self.queue_manager = SmartQueueManager(
            max_size=self.config.QUEUE_MAX_SIZE,
            admin_ids=self.config.ADMIN_USER_IDS
        )
        logger.info("✅ Queue Manager ready")

        # Initialize STT Engine (Faster-Whisper)
        logger.info("📦 Loading STT engine (Faster-Whisper)...")
        try:
            self.stt_handler = STTHandler()
            logger.info("✅ STT handler loaded")
        except Exception as e:
            logger.warning(f"⚠️  STT handler failed to load: {e}")
            self.stt_handler = None
            logger.warning("⚠️  Continuing without STT")
        
        # Initialize TTS Engine (Edge-TTS)
        logger.info("📦 Loading TTS engine (Edge-TTS)...")
        try:
            self.tts_engine = EdgeTTSHandler()
            logger.info("✅ TTS handler loaded")
        except Exception as e:
            logger.warning(f"⚠️  TTS handler failed to load: {e}")
            self.tts_engine = None
            logger.warning("⚠️  Continuing without TTS")

        # Initialize LLM Response Generator
        logger.info("🧠 Initializing LLM ResponseGenerator...")
        try:
            llm_client = ChatGPTClient(
                api_key=self.config.OPENAI_API_KEY,
                model=self.config.LLM_MODEL,
                temperature=self.config.LLM_TEMPERATURE,
                max_tokens=self.config.LLM_MAX_TOKENS,
            )
            self.llm_processor = get_response_generator(llm_client, jeed_persona)
            logger.info("✅ LLM ResponseGenerator ready")
        except Exception as e:
            logger.error(f"❌ Failed to initialize LLM ResponseGenerator: {e}")
            self.llm_processor = None
        
        # Initialize VTube Studio Controller (updated import path)
        logger.info("📡 เชื่อมต่อ VTube Studio...")
        try:
            from adapters.vts.vts_controller import VTSController
            # ใช้ค่า plugin_name จาก Config หากมี
            self.vts_client = VTSController(plugin_name=self.config.VTS_PLUGIN_NAME)
            await self.vts_client.connect()
            logger.info("✅ VTube Studio พร้อมใช้งาน")
        except Exception as e:
            logger.warning(f"⚠️  VTube Studio connection failed: {e}")
            logger.warning("⚠️  Continuing without VTS")
            self.vts_client = None
        
        # Initialize Discord Bot
        logger.info("🤖 เริ่ม Discord Bot...")
        self.discord_bot = DiscordBotAdapter(
            token=self.config.DISCORD_BOT_TOKEN,
            admin_ids=self.config.ADMIN_USER_IDS
        )
        
        # Set callbacks
        self.discord_bot.on_voice_input = self._handle_voice_input
        self.discord_bot.on_text_command = self._handle_text_command
        # ส่งสถานะระบบภายนอกให้ Discord Bot สำหรับรายงานในห้อง
        try:
            self.discord_bot.update_external_status(
                vts_connected=(self.vts_client is not None),
                tts_ready=(self.tts_engine is not None),
                queue_ready=(self.queue_manager is not None)
            )
        except Exception:
            pass
        
        # Print config
        self.config.print_config()
        
        logger.info("=" * 60)
        logger.info("✅ Jeed AI VTuber พร้อมแล้ว!")
        logger.info("=" * 60)
    
    async def start(self):
        """Start the application"""
        try:
            await self.initialize()
            
            self.running = True
            
            # Start Discord Bot
            bot_task = asyncio.create_task(
                self._run_discord_bot_supervisor(),
                name="discord_bot"
            )
            self.tasks.append(bot_task)
            
            # Start Queue Processor
            logger.info("=" * 60)
            queue_task = asyncio.create_task(
                self.queue_manager.process_queue(self._process_queue_item),
                name="queue_processor"
            )
            self.tasks.append(queue_task)
            logger.info("🔄 เริ่ม Processing Loop")
            
            # Start VTS Animation (if available)
            if self.vts_client:
                animation_task = asyncio.create_task(
                    self._vts_animation_loop(),
                    name="vts_animation"
                )
                self.tasks.append(animation_task)
                logger.info("🎬 เริ่ม Animation Loop")
            
            # Wait for all tasks
            await asyncio.gather(*self.tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            logger.info("🛑 รับ signal หยุดทำงาน")
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}", exc_info=True)
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the application"""
        if self._stopping:
            logger.info("ℹ️ ระบบกำลังหยุดอยู่แล้ว")
            return
        self._stopping = True

        logger.info("🛑 กำลังหยุดระบบ...")

        # Signal loops to stop
        self.running = False

        # Stop Discord Bot first to close websocket and aiohttp session cleanly
        if self.discord_bot:
            try:
                await self.discord_bot.stop()
            except Exception as e:
                logger.debug(f"Ignoring Discord stop error: {e}")

        # Disconnect VTS next
        if self.vts_client:
            try:
                logger.info("🛑 กำลังตัดการเชื่อมต่อ VTS...")
                await self.vts_client.disconnect()
                logger.info("👋 ตัดการเชื่อมต่อ VTS เรียบร้อย")
            except Exception as e:
                logger.debug(f"Ignoring VTS disconnect error: {e}")

        # Stop Queue Manager
        if self.queue_manager:
            try:
                await self.queue_manager.stop()
            except Exception as e:
                logger.debug(f"Ignoring QueueManager stop error: {e}")

        # Cancel any remaining tasks (e.g., queue loop, animation loop)
        for task in list(self.tasks):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info(f"🛑 {task.get_name()} cancelled")
                except Exception as e:
                    logger.debug(f"Task {task.get_name()} stop error (ignored): {e}")

        logger.info("👋 ระบบหยุดแล้ว")
        logger.info("👋 บ๊ายบาย~")

    async def _run_discord_bot_supervisor(self):
        """รัน Discord bot และรีสตาร์ทอัตโนมัติเมื่อหลุดด้วยโค้ด 4006/ข้อผิดพลาดชั่วคราว"""
        while self.running and not self._stopping:
            try:
                await self.discord_bot.start()
            except Exception as e:
                # ไม่หยุดทั้งระบบเมื่อ bot หลุด ให้ลองใหม่หลังพักสั้น ๆ
                logger.warning(f"⚠️ Discord bot disconnected: {e}. Retrying in 3s...")
                await asyncio.sleep(3)
                continue
            else:
                # start() ออกมาแบบปกติ (ถูกสั่ง stop) ให้จบ loop
                break
    
    async def _handle_voice_input(self, user, audio_data: bytes, sample_rate: int):
        """Handle voice input from Discord"""
        try:
            logger.info(f"🎤 Received voice from {user}")

            # Transcribe using Whisper.cpp via STT handler
            try:
                # Discord PCM is 16-bit mono @ 48kHz from VoiceRecvClient
                if not self.stt_handler:
                    logger.warning("⚠️ STT handler not initialized")
                    text = None
                else:
                    text = await self.stt_handler.transcribe(audio_data, sample_rate=sample_rate)
            except Exception as e:
                logger.warning(f"⚠️ STT handler failed: {e}")
                text = None

            # If transcription is empty, ignore this chunk
            if not text or not text.strip():
                logger.debug("🕸️ Empty/undetected speech chunk, skipping queue")
                return

            # Enqueue transcribed text for LLM/TTS processing
            await self.queue_manager.add_to_queue(
                content=text.strip(),
                source="voice",
                user_id=str(user.id),
                user_name=user.name,
                metadata={'sample_rate': sample_rate}
            )
        
        except Exception as e:
            logger.error(f"Error handling voice input: {e}")
    
    async def _handle_text_command(self, user_id: str, content: str):
        """Handle text command"""
        await self.queue_manager.add_to_queue(
            content=content,
            source="text",
            user_id=user_id,
            user_name="User"
        )
    
    async def _process_queue_item(self, item: QueueItem):
        """Process queue item: LLM -> TTS -> Discord playback + VTS talking"""
        try:
            logger.info(f"🧾 Processing item from {item.user_name} ({item.source})")

            # 1) Generate response text via LLM with safety/personality
            if not self.llm_processor:
                logger.warning("⚠️ LLM processor not initialized; skipping")
                return

            response_text, rejection_reason = await self.llm_processor.generate_response(
                user_message=item.content,
                user=item.user_name,
                source=item.source,
                repeat_question=(item.source == "youtube")
            )

            if not response_text:
                logger.info(f"🚫 No response generated (reason: {rejection_reason})")
                return

            # Test mode: override final response with fixed text (e.g., "สวัสดีนะ")
            try:
                test_reply = core_config.discord.voice_test_reply_text
            except Exception:
                test_reply = ""

            if test_reply:
                logger.info(f"🧪 Test mode override: speaking fixed reply -> {test_reply}")
                response_text = test_reply

            logger.info(f"💬 Final response: {response_text}")

            # 2) Generate speech via TTS
            if not self.tts_engine:
                logger.warning("⚠️ TTS engine not ready; cannot speak")
                return

            # ใช้ RVC หากเปิดใช้งานและมีโมเดล
            try:
                use_rvc = getattr(core_config, 'rvc').enabled
                rvc_model = Path(getattr(core_config, 'rvc').model_path)
            except Exception:
                use_rvc = False
                rvc_model = None

            if use_rvc and rvc_model and rvc_model.exists():
                audio_data, tts_sample_rate = await self.tts_engine.generate_speech_with_rvc(response_text, rvc_model)
            else:
                audio_data, tts_sample_rate = await self.tts_engine.generate_speech(response_text)
            if audio_data is None:
                logger.warning("⚠️ TTS failed to generate audio")
                return

            # 3) Normalize and DC offset removal before playback
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)
            max_val = np.abs(audio_data).max()
            if max_val > 0:
                audio_data = audio_data / max_val * 0.95
            audio_data = audio_data - audio_data.mean()

            # 4) Play audio in Discord
            sample_rate = tts_sample_rate or core_config.tts.sample_rate
            if self.discord_bot and self.discord_bot.voice_client:
                if self.vts_client:
                    try:
                        await self.vts_client.set_talking(True)
                    except Exception:
                        pass

                await self.discord_bot.play_audio(audio_data, sample_rate)

                if self.vts_client:
                    try:
                        await self.vts_client.set_talking(False)
                    except Exception:
                        pass
                logger.info("✅ Audio played successfully")
            else:
                logger.warning("⚠️ Not connected to a Discord voice channel; cannot play audio")

        except Exception as e:
            logger.error(f"❌ Error processing queue item: {e}", exc_info=True)
    
    async def _vts_animation_loop(self):
        """VTube Studio animation loop"""
        try:
            while self.running:
                # Animation handled by VTSController internally; keep loop lightweight
                await asyncio.sleep(1/60)  # 60 FPS
        except asyncio.CancelledError:
            logger.info("🛑 Animation Loop cancelled")
        except Exception as e:
            logger.error(f"❌ Animation loop error: {e}")

async def main():
    """Main entry point"""
    vtuber = JeedAIVTuber()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("🛑 รับ signal หยุดทำงาน")
        asyncio.create_task(vtuber.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await vtuber.start()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        await vtuber.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)