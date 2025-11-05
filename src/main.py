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

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from core.queue_manager import SmartQueueManager, QueueItem
from adapters.discord_bot import DiscordBotAdapter
from audio.stt_handler import stt_handler  # โหลดครั้งเดียวเพื่อคงโมเดลไว้ในหน่วยความจำ

# Ensure required directories exist before configuring logging
try:
    Config.create_directories()
except Exception:
    # If directory creation fails, fallback to console-only logging
    pass

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
        logging.FileHandler(str(Config.LOGS_DIR / 'ai_vtuber.log'), encoding='utf-8'),
        logging.StreamHandler(utf8_stdout)
    ]
)

logger = logging.getLogger(__name__)

class JeedAIVTuber:
    """Main AI VTuber application"""
    
    def __init__(self):
        """Initialize AI VTuber"""
        self.config = Config
        
        # Components
        self.queue_manager: SmartQueueManager = None
        self.discord_bot: DiscordBotAdapter = None
        self.vts_client = None  # VTube Studio client
        self.tts_engine = None  # TTS engine
        self.llm_processor = None  # LLM processor
        
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
        
        # Validate config
        is_valid, errors = self.config.validate()
        if not is_valid:
            logger.error("❌ Configuration errors:")
            for error in errors:
                logger.error(f"  {error}")
            if any("❌" in e for e in errors):
                raise ValueError("Critical configuration errors")
        
        logger.info("✅ การตั้งค่าถูกต้องทั้งหมด")
        
        # Create directories
        self.config.create_directories()
        
        # Initialize Queue Manager
        logger.info("📦 Initializing Queue Manager...")
        self.queue_manager = SmartQueueManager(
            max_size=self.config.QUEUE_MAX_SIZE,
            admin_ids=self.config.ADMIN_USER_IDS
        )
        logger.info("✅ Queue Manager ready")
        
        # Initialize TTS Engine via unified handler (uses F5-TTS placeholder + RVC)
        logger.info("📦 Loading TTS engine...")
        try:
            from audio.tts_rvc_handler import tts_rvc_handler
            self.tts_engine = tts_rvc_handler
            logger.info("✅ TTS handler loaded")
        except Exception as e:
            logger.warning(f"⚠️  TTS handler failed to load: {e}")
            self.tts_engine = None
            logger.warning("⚠️  Continuing without TTS")
        
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
                text = await stt_handler.transcribe_audio(audio_data, sample_rate=sample_rate)
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
        """
        Process queue item
        
        This is where the magic happens:
        1. Get text input (from voice/text)
        2. Generate response with LLM
        3. Generate speech with TTS
        4. Animate VTube Studio model
        5. Play audio in Discord
        """
        try:
            # 1. Get input text (voice already transcribed at enqueue stage)
            text_input = item.content
            
            logger.info(f"💭 Input: {text_input}")
            
            # 2. Generate response with LLM (personality-aware)
            logger.info("🧠 Generating response...")
            try:
                from llm.llm_handler import llm_handler
                response_text = await llm_handler.generate_response(text_input)
            except Exception as e:
                logger.warning(f"⚠️ LLM generation failed: {e}")
                response_text = f"เอ๊ะ หนูติดขัดนิดหน่อย แต่ได้ยินว่า: {text_input[:60]}..."
            logger.info(f"💬 Response: {response_text}")
            
            # 3. Generate speech with TTS
            logger.info("🎤 Generating speech...")
            if self.tts_engine:
                audio_data, output_path = await self.tts_engine.generate_speech(
                    response_text
                )
                # ใช้ sample rate จาก core config ของ TTS
                try:
                    from core.config import config as core_config
                    sample_rate = core_config.tts.sample_rate
                except Exception:
                    sample_rate = self.config.AUDIO_SAMPLE_RATE
            else:
                logger.warning("⚠️  No TTS engine available")
                audio_data, sample_rate = None, None
            
            # 4. Animate VTube Studio model (minimal integration)
            if self.vts_client:
                try:
                    await self.vts_client.set_talking(True)
                except Exception:
                    pass
            
            # 5. Play audio in Discord
            if audio_data is not None and self.discord_bot.voice_client:
                logger.info("🔊 Playing audio...")
                await self.discord_bot.play_audio(audio_data, sample_rate)
            
            # Stop talking animation after playback
            if self.vts_client:
                try:
                    await self.vts_client.set_talking(False)
                except Exception:
                    pass
            
            logger.info("✅ Completed processing")
            
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