"""
Main entry point สำหรับ AI VTuber
แก้ไขปัญหา: Processing/Animation Loop หยุดเมื่อมี Discord error
"""
import asyncio
import logging
import sys
import signal
from pathlib import Path
from typing import Optional

# Import core modules
from core.config import Config
from core.scheduler import PriorityScheduler
from personality.personality import PersonalityManager

# Import adapters
from adapters.discord_bot import DiscordBot
from adapters.youtube_live import YouTubeLive
from adapters.vts.vts_controller import VTSController
from adapters.tts.f5_tts_thai import F5TTSThai

# Import audio modules
from audio.rvc_v2 import RVCProcessor
from audio.stt_whispercpp import WhisperCPP

# Import LLM
from llm.chatgpt_client import ChatGPTClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('vtuber.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class AIVTuber:
    """Main AI VTuber application"""
    
    def __init__(self):
        self.config = Config()
        self.running = False
        self.shutdown_event = asyncio.Event()
        
        # Core components
        self.scheduler: Optional[PriorityScheduler] = None
        self.personality: Optional[PersonalityManager] = None
        self.llm: Optional[ChatGPTClient] = None
        self.tts: Optional[F5TTSThai] = None
        self.rvc: Optional[RVCProcessor] = None
        self.vts: Optional[VTSController] = None
        
        # Adapters
        self.discord_bot: Optional[DiscordBot] = None
        self.youtube_live: Optional[YouTubeLive] = None
        self.stt: Optional[WhisperCPP] = None
        
        # Tasks
        self.tasks = []
        
    async def initialize(self):
        """Initialize all components"""
        try:
            logger.info("="*60)
            logger.info("🎮 Jeed AI VTuber Starting...")
            logger.info("="*60)
            
            # Validate configuration
            self.config.validate()
            logger.info("✅ การตั้งค่าถูกต้องทั้งหมด")
            
            # Print configuration
            self._print_config()
            
            # Initialize TTS
            logger.info("📦 Loading TTS engine...")
            self.tts = F5TTSThai(
                device=self.config.AUDIO_DEVICE,
                reference_wav=self.config.TTS_REFERENCE_WAV
            )
            logger.info("✅ TTS loaded")
            
            # Initialize RVC if enabled
            if self.config.ENABLE_RVC:
                logger.info("📦 Loading RVC model...")
                self.rvc = RVCProcessor(
                    model_path=self.config.RVC_MODEL_PATH,
                    device=self.config.AUDIO_DEVICE
                )
                logger.info("✅ RVC loaded")
            
            # Initialize STT if enabled
            if self.config.DISCORD_VOICE_STT_ENABLED:
                logger.info("📦 Loading STT engine...")
                self.stt = WhisperCPP(
                    bin_path=self.config.WHISPER_CPP_BIN_PATH,
                    model_path=self.config.WHISPER_CPP_MODEL_PATH,
                    language=self.config.WHISPER_CPP_LANG,
                    threads=self.config.WHISPER_CPP_THREADS,
                    n_gpu_layers=self.config.WHISPER_CPP_NGL
                )
                logger.info("✅ STT loaded")
            
            # Initialize scheduler
            self.scheduler = PriorityScheduler(
                response_timeout=self.config.RESPONSE_TIMEOUT
            )
            
            # Initialize personality
            self.personality = PersonalityManager(
                persona_path=Path("src/personality/persona.json")
            )
            
            # Initialize LLM
            self.llm = ChatGPTClient(
                api_key=self.config.OPENAI_API_KEY,
                model=self.config.LLM_MODEL,
                temperature=self.config.LLM_TEMPERATURE,
                max_tokens=self.config.LLM_MAX_TOKENS
            )
            
            # Initialize VTS
            if self.config.VTS_PLUGIN_NAME:
                logger.info("📡 เชื่อมต่อ VTube Studio...")
                self.vts = VTSController(
                    plugin_name=self.config.VTS_PLUGIN_NAME,
                    model_name=self.config.VTS_MODEL_NAME
                )
                await self.vts.connect()
                logger.info("✅ VTube Studio พร้อมใช้งาน")
            
            # Initialize Discord Bot
            if self.config.DISCORD_BOT_TOKEN:
                logger.info("🤖 เริ่ม Discord Bot...")
                self.discord_bot = DiscordBot(
                    token=self.config.DISCORD_BOT_TOKEN,
                    scheduler=self.scheduler,
                    stt_engine=self.stt,
                    config=self.config
                )
            
            # Initialize YouTube Live
            if self.config.YOUTUBE_STREAM_ID:
                logger.info("📺 เริ่ม YouTube Live...")
                self.youtube_live = YouTubeLive(
                    stream_id=self.config.YOUTUBE_STREAM_ID,
                    scheduler=self.scheduler
                )
            
            logger.info("="*60)
            logger.info("✅ Jeed AI VTuber พร้อมแล้ว!")
            logger.info("="*60)
            self._print_commands()
            logger.info("="*60)
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            raise
    
    def _print_config(self):
        """Print current configuration"""
        print("="*50)
        print("🎮 Jeed AI VTuber Configuration")
        print("="*50)
        print(f"LLM Model: {self.config.LLM_MODEL}")
        print(f"TTS Engine: {self.config.TTS_ENGINE}")
        print(f"RVC Enabled: {self.config.ENABLE_RVC}")
        print(f"VTube Studio: {self.config.VTS_MODEL_NAME}")
        print(f"Discord Bot: {'Enabled' if self.config.DISCORD_BOT_TOKEN else 'Disabled'}")
        print(f"YouTube Live: {'Enabled' if self.config.YOUTUBE_STREAM_ID else 'Disabled'}")
        print(f"GPU Acceleration: {self.config.AUDIO_DEVICE != 'cpu'}")
        print("="*50)
    
    def _print_commands(self):
        """Print available commands"""
        if self.discord_bot:
            print("คำสั่ง Discord Bot:")
            print("  !join         - เข้าห้องเสียง")
            print("  !leave        - ออกจากห้องเสียง")
            print("  !listen [วินาที] - บันทึกเสียงและถอดความ")
            print("  !test         - ทดสอบบอท")
            print("  !ping         - ตรวจสอบ latency")
            print("  !stats        - แสดงสถิติ")
        if self.youtube_live:
            print("  !youtube on/off - เปิด/ปิดรับคอมเม้น YouTube ในคิว")
    
    async def start(self):
        """Start all components"""
        try:
            self.running = True
            
            # Start processing loop (CRITICAL: ไม่ให้หยุดแม้มี error)
            processing_task = asyncio.create_task(
                self._processing_loop(),
                name="ProcessingLoop"
            )
            self.tasks.append(processing_task)
            
            # Start animation loop (CRITICAL: ไม่ให้หยุดแม้มี error)
            if self.vts:
                animation_task = asyncio.create_task(
                    self._animation_loop(),
                    name="AnimationLoop"
                )
                self.tasks.append(animation_task)
            
            # Start Discord Bot (แยก task เพื่อไม่ให้ crash ระบบ)
            if self.discord_bot:
                discord_task = asyncio.create_task(
                    self._run_discord_bot(),
                    name="DiscordBot"
                )
                self.tasks.append(discord_task)
            
            # Start YouTube Live
            if self.youtube_live:
                youtube_task = asyncio.create_task(
                    self.youtube_live.start(),
                    name="YouTubeLive"
                )
                self.tasks.append(youtube_task)
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"❌ Error in start: {e}")
            raise
    
    async def _run_discord_bot(self):
        """Run Discord bot in separate task with error handling"""
        try:
            await self.discord_bot.start()
        except Exception as e:
            logger.error(f"❌ Discord bot error: {e}")
            # ไม่ raise error เพื่อไม่ให้ระบบหยุด
            # แค่ log error และให้ระบบทำงานต่อ
    
    async def _processing_loop(self):
        """
        Main processing loop - MUST NEVER STOP
        ประมวลผลข้อความจาก queue อย่างต่อเนื่อง
        """
        logger.info("🔄 เริ่ม Processing Loop")
        
        while self.running:
            try:
                # Get next message from queue
                message = await self.scheduler.get_next()
                
                if not message:
                    await asyncio.sleep(0.1)
                    continue
                
                # Process message
                await self._process_message(message)
                
            except asyncio.CancelledError:
                logger.info("🛑 Processing Loop cancelled")
                break
            except Exception as e:
                # CRITICAL: Log error แต่ไม่หยุดทำงาน
                logger.error(f"❌ Error in processing loop: {e}", exc_info=True)
                await asyncio.sleep(1)  # รอแป๊บก่อน retry
                continue  # ทำงานต่อไป
        
        logger.info("🛑 Processing Loop หยุดทำงาน")
    
    async def _animation_loop(self):
        """
        Animation loop for VTS - MUST NEVER STOP
        อัพเดท animation อย่างต่อเนื่อง
        """
        logger.info("🎬 เริ่ม Animation Loop")
        
        while self.running and self.vts:
            try:
                # Update VTS animations
                await self.vts.update_idle_motion()
                await asyncio.sleep(0.1)  # 10 FPS
                
            except asyncio.CancelledError:
                logger.info("🛑 Animation Loop cancelled")
                break
            except Exception as e:
                # CRITICAL: Log error แต่ไม่หยุดทำงาน
                logger.error(f"❌ Error in animation loop: {e}", exc_info=True)
                await asyncio.sleep(1)
                continue  # ทำงานต่อไป
        
        logger.info("🛑 Animation Loop หยุดทำงาน")
    
    async def _process_message(self, message):
        """Process a single message"""
        try:
            # Get LLM response
            response = await self.llm.get_response(
                message.text,
                personality=self.personality.get_prompt()
            )
            
            # Generate TTS
            audio_data = await self.tts.generate(response)
            
            # Apply RVC if enabled
            if self.rvc and audio_data:
                audio_data = await self.rvc.convert(audio_data)
            
            # Update VTS expressions
            if self.vts:
                await self.vts.set_talking(True)
                # Play audio and update lip sync
                await asyncio.sleep(len(audio_data) / 48000)  # Duration
                await self.vts.set_talking(False)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("🛑 กำลังหยุดระบบ...")
        self.running = False
        self.shutdown_event.set()
        
        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to finish
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Disconnect VTS
        if self.vts:
            logger.info("🛑 กำลังตัดการเชื่อมต่อ VTS...")
            await self.vts.disconnect()
            logger.info("👋 ตัดการเชื่อมต่อ VTS เรียบร้อย")
        
        # Stop Discord bot
        if self.discord_bot:
            await self.discord_bot.stop()
        
        # Stop YouTube live
        if self.youtube_live:
            await self.youtube_live.stop()
        
        logger.info("👋 ระบบหยุดแล้ว")


async def main():
    """Main entry point"""
    vtuber = AIVTuber()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("🛑 รับ signal หยุดทำงาน")
        asyncio.create_task(vtuber.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize
        await vtuber.initialize()
        
        # Start
        await vtuber.start()
        
    except KeyboardInterrupt:
        logger.info("🛑 รับ Ctrl+C")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        await vtuber.shutdown()
        logger.info("👋 บ๊ายบาย~")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass