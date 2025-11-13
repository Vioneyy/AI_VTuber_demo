"""
Jeed AI VTuber - Main Application (เพิ่ม VTS Debug)
แก้ไข: เพิ่ม log ตรวจสอบ VTS connection
"""
import asyncio
import logging
import signal
import sys
from pathlib import Path
from logging.handlers import QueueHandler, QueueListener
import queue as _log_queue
import io
import os
import numpy as np
import pytchat
from urllib.parse import urlparse, parse_qs

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from core.queue_manager import SmartQueueManager, QueueItem, Priority
from adapters.discord_bot import DiscordBotAdapter
# หมายเหตุ: STT จะ lazy-import ภายใน initialize() เฉพาะเมื่อเปิดใช้งาน เพื่อลดเวลาเริ่มต้นระบบ
from audio.f5_tts_handler import F5TTSHandler
from core.response_generator import get_response_generator
from personality.jeed_persona import jeed_persona
from llm.chatgpt_client import ChatGPTClient
from core.config import config as core_config
from core.motion_analyzer import motion_analyzer

# Setup logging
# Configure logging with UTF-8 safe console handler
try:
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception:
    utf8_stdout = sys.stdout

logging.basicConfig(level=logging.INFO)  # root level INFO; per-logger levels will filter noise

# Queue-based logging to avoid event-loop stalls on I/O
LOG_QUEUE_LISTENER = None
try:
    log_queue = _log_queue.Queue(maxsize=1000)
    root_logger = logging.getLogger()

    # Handlers processed by background listener
    stream_handler = logging.StreamHandler(utf8_stdout)
    # แสดงเฉพาะ WARNING ขึ้นไปบน console เพื่อลด noise
    stream_handler.setLevel(logging.WARNING)
    # ใช้ฟอร์แมตที่กระชับสำหรับ terminal
    stream_handler.setFormatter(logging.Formatter('%(levelname)s %(name)s: %(message)s'))

    # เพิ่มช่องทาง INFO เฉพาะบรรทัดสำคัญ (ใช้ extra={'console': True})
    class ConsoleInfoFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return bool(getattr(record, 'console', False))

    console_info_handler = logging.StreamHandler(utf8_stdout)
    console_info_handler.setLevel(logging.INFO)
    console_info_handler.setFormatter(logging.Formatter('%(message)s'))
    console_info_handler.addFilter(ConsoleInfoFilter())

    file_handler = logging.FileHandler(str(Path(core_config.system.log_dir) 
                                           / 'ai_vtuber.log'), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))

    # Remove any direct handlers attached by basicConfig
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    # Attach queue handler to root
    queue_handler = QueueHandler(log_queue)
    queue_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(queue_handler)

    # Start listener (background thread does actual I/O)
    # เริ่ม QueueListener โดยเคารพระดับของ handler
    # stream: WARNING (ข้อความเตือน/ผิดพลาดเท่านั้น)
    # file: INFO (เก็บรายละเอียดทั้งหมด)
    # console_info_handler: INFO เฉพาะบรรทัดที่ติดธง extra={'console': True}
    LOG_QUEUE_LISTENER = QueueListener(log_queue, file_handler, stream_handler, console_info_handler, respect_handler_level=True)
    LOG_QUEUE_LISTENER.start()
except Exception:
    LOG_QUEUE_LISTENER = None

# หมายเหตุ: ระดับของ stream/file ถูกตั้งไว้ข้างต้นก่อนเริ่ม QueueListener แล้ว

# ลดสแปม log จากไลบรารีภายนอกที่สร้างข้อความบ่อย
# เช่น httpx/pytchat/websockets ที่มักจะพิมพ์ HTTP Request/Connection
for noisy_logger in [
    "httpx",
    "pytchat",
    "websockets",
    "websockets.client",
    "websockets.server",
]:
    try:
        nl = logging.getLogger(noisy_logger)
        nl.setLevel(logging.WARNING)
        # ปิดการ propagate เพื่อไม่ให้เด้งขึ้น root handlers
        nl.propagate = False
    except Exception:
        pass

# เพิ่ม debug เฉพาะโมดูล VTS เพื่อดูจังหวะส่งพารามิเตอร์ (ปล่อยให้ propagate ไปยัง root QueueHandler)
try:
    vts_logger = logging.getLogger("adapters.vts.vtube_controller")
    vts_logger.setLevel(logging.DEBUG)
    vts_logger.propagate = True
except Exception:
    pass

logger = logging.getLogger(__name__)

class JeedAIVTuber:
    """Main AI VTuber application"""
    
    def __init__(self):
        """Initialize AI VTuber"""
        self.config = core_config
        # โหมด TTS-only: ตัด RVC ออกทั้งหมด
        
        # Components
        self.queue_manager: SmartQueueManager = None
        self.discord_bot: DiscordBotAdapter = None
        self.vts_client = None  # VTube Studio client
        self.tts_engine = None  # TTS engine
        self.llm_processor = None  # LLM processor
        self.stt_handler = None  # STT engine (Faster-Whisper)
        # YouTube Live
        self.youtube_task = None
        self.youtube_chat = None
        # แจ้ง YouTube connect ครั้งแรกที่ระดับ INFO ครั้งถัดไปเป็น DEBUG
        self._yt_connected_once = False
        # เก็บ comment IDs ที่อ่านไปแล้ว เพื่อกันการอ่านซ้ำข้ามรอบ
        self._yt_seen_ids = set()
        self._yt_read_once = False
        
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

        # Initialize STT Engine (Faster-Whisper) — only when enabled
        if self.config.DISCORD_VOICE_STT_ENABLED:
            logger.info("📦 Loading STT engine (Faster-Whisper)...")
            try:
                # Lazy import เพื่อลดเวลาเริ่มต้น
                from audio.hybrid_stt import HybridSTT as STTHandler
                self.stt_handler = STTHandler(
                    model_size=self.config.WHISPER_MODEL,
                    device=self.config.WHISPER_DEVICE,
                    language=self.config.WHISPER_LANG
                )
                logger.info("✅ STT handler loaded")
                # แสดงสถานะ STT ปัจจุบันเพื่อการวินิจฉัย
                try:
                    stt_status = getattr(self.stt_handler, 'get_status', lambda: None)()
                    if stt_status:
                        logger.info(
                            f"🔍 STT status: backend={stt_status.get('backend')} "
                            f"device={stt_status.get('device')} compute_type={stt_status.get('compute_type')} "
                            f"model={stt_status.get('model_size')} lang={stt_status.get('language')}"
                        )
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"⚠️  STT handler failed to load: {e}")
                self.stt_handler = None
                logger.warning("⚠️  Continuing without STT")
        else:
            logger.info("🔇 ปิดใช้งาน STT ตาม .env (DISCORD_VOICE_STT_ENABLED=false)")
            self.stt_handler = None
        
        # Initialize TTS Engine (F5-TTS-Thai)
        logger.info("📦 Loading TTS engine (F5-TTS-Thai)...")
        try:
            # ใช้ reference_wav จาก config หากตั้งค่าไว้
            ref_wav = None
            try:
                ref_wav = getattr(self.config.tts, 'reference_wav', None)
            except Exception:
                ref_wav = None

            self.tts_engine = F5TTSHandler(reference_wav=ref_wav)
            logger.info("✅ TTS handler loaded")
            # Warm-up เพื่อลดดีเลย์ครั้งแรกของ TTS (โหลดโมเดล/คอมไพล์กราฟ)
            try:
                logger.info("🔥 Warming up TTS engine...")
                _audio, _sr = await self.tts_engine.generate_speech("สวัสดีค่ะ", output_path=None)
                logger.info("✅ TTS warm-up done")
            except Exception as warm_e:
                logger.warning(f"⚠️  TTS warm-up skipped: {warm_e}")
        except Exception as e:
            logger.warning(f"⚠️  TTS handler failed to load: {e}")
            self.tts_engine = None
            logger.warning("⚠️  Continuing without TTS")

        # RVC ถูกปิดใช้งาน — รันแบบ TTS-only เพื่อความเร็ว

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
        
        # Initialize VTube Studio Controller ตามสวิตช์
        if self.config.VTS_ENABLED:
            logger.info("📡 กำลังเชื่อมต่อ VTube Studio...")
            try:
                from adapters.vts.vts_controller import VTSController
                # ใช้ค่า plugin_name จาก Config หากมี
                self.vts_client = VTSController(plugin_name=self.config.VTS_PLUGIN_NAME)
                # ✅ เพิ่ม: ตรวจสอบการเชื่อมต่อ
                connected = await self.vts_client.connect()
                
                if connected:
                    logger.info("✅ VTube Studio พร้อมใช้งาน")
                    
                    # ✅ ตรวจสอบว่า animation loop เริ่มแล้วหรือยัง
                    await asyncio.sleep(1)  # รอให้ loop เริ่ม
                    controller = self.vts_client._controller
                    if controller.running and controller.animation_task:
                        logger.info("✅ Animation loop กำลังทำงาน")
                    else:
                        logger.error("❌ Animation loop ไม่ได้เริ่ม!")
                        logger.error(f"   - running: {controller.running}")
                        logger.error(f"   - task: {controller.animation_task}")
                else:
                    logger.error("❌ VTube Studio เชื่อมต่อล้มเหลว")
                    self.vts_client = None
            except Exception as e:
                logger.error(f"❌ VTube Studio error: {e}", exc_info=True)
                self.vts_client = None
        else:
            logger.info("⚠️ ปิดใช้งาน VTS ตาม .env (VTS_ENABLED=false)")
            self.vts_client = None
        
        # Initialize Discord Bot ตามสวิตช์
        if self.config.DISCORD_ENABLED:
            logger.info("🤖 เริ่ม Discord Bot...")
            self.discord_bot = DiscordBotAdapter(
                token=self.config.DISCORD_BOT_TOKEN,
                admin_ids=self.config.ADMIN_USER_IDS,
                motion_controller=self.vts_client
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
        else:
            logger.info("⚠️ ปิดใช้งาน Discord ตาม .env (DISCORD_ENABLED=false)")
            self.discord_bot = None
        
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
            
            # Start Discord Bot (ถ้าเปิดใช้งาน)
            if self.discord_bot and self.config.DISCORD_ENABLED:
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

            # Start YouTube Live chat reader if enabled
            try:
                yt_cfg = getattr(self.config, 'youtube', None)
                if yt_cfg and getattr(yt_cfg, 'enabled', False):
                    # อ่านนโยบายการอ่านคอมเมนต์ (ครั้งเดียว)
                    self._yt_read_once = bool(getattr(yt_cfg, 'read_comment_once', True))
                    raw_id = getattr(yt_cfg, 'stream_id', '') or getattr(yt_cfg, 'video_id', '')
                    if raw_id:
                        self.youtube_task = asyncio.create_task(
                            self._youtube_live_loop(),
                            name="youtube_live"
                        )
                        self.tasks.append(self.youtube_task)
                        logger.info(f"📺 เริ่มอ่านคอมเมนต์ YouTube Live (raw): {raw_id}")
                    else:
                        logger.info("ℹ️ YouTube Live เปิดใช้งาน แต่ไม่มีค่า stream/video ID — จะไม่เริ่มลูป YouTube")
                else:
                    logger.info("ℹ️ YouTube Live ถูกปิดใช้งาน (YOUTUBE_ENABLED=false) — ข้ามการเริ่มลูป YouTube")
            except Exception as e:
                logger.warning(f"⚠️ ไม่สามารถเริ่ม YouTube Live ได้: {e}")
            
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

        # Stop YouTube Live
        try:
            if self.youtube_chat:
                logger.info("🛑 ปิดการเชื่อมต่อ YouTube Live")
                self.youtube_chat.terminate()
        except Exception:
            pass

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

        # หยุด QueueListener ของระบบ log (ถ้ามี) เพื่อปิด thread อย่างเรียบร้อย
        try:
            global LOG_QUEUE_LISTENER
            if LOG_QUEUE_LISTENER:
                LOG_QUEUE_LISTENER.stop()
                LOG_QUEUE_LISTENER = None
        except Exception:
            pass

    async def _run_discord_bot_supervisor(self):
        """รัน Discord bot และรีสตาร์ทอัตโนมัติเมื่อหลุดด้วยโค้ด 4006/ข้อผิดพลาดชั่วคราว"""
        # หากไม่มี token ให้ข้ามการเริ่ม Discord เพื่อหลีกเลี่ยงการค้างระหว่างทดสอบ/ออฟไลน์
        if not (self.config.DISCORD_BOT_TOKEN and self.config.DISCORD_BOT_TOKEN.strip()):
            logger.info("⚠️ ข้ามการเริ่ม Discord Bot: ไม่พบ DISCORD_BOT_TOKEN")
            return

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
            source="voice",  # ให้ความสำคัญเทียบเท่าเสียง เพื่อความเร็วตอบใน Discord
            user_id=user_id,
            user_name="User",
            priority=Priority.VOICE
        )

    async def _run_lip_sync_concurrent(self, audio_file: str):
        """รัน lip sync เป็น concurrent task (ไม่รอ)"""
        try:
            if self.vts_client:
                # ตั้งสถานะกำลังพูด เพื่อให้โมเดลเข้าสู่โหมด SPEAKING
                await self.vts_client.set_talking(True)
                # เริ่ม lip sync แบบไม่บล็อก เพื่อไม่ให้แอปค้าง
                asyncio.create_task(self.vts_client.start_lip_sync_from_file(audio_file))
        except Exception as e:
            logger.debug(f"Concurrent lip sync error: {e}")
    
    async def _process_queue_item(self, item: QueueItem):
        """Process queue item: LLM -> TTS -> Discord playback + VTS talking"""
        try:
            logger.info(f"🧾 Processing item from {item.user_name} ({item.source})")
            
            # ✅ เช็ค VTS status ก่อนเริ่ม
            if self.vts_client:
                controller = self.vts_client._controller
                logger.info(
                    f"🎮 VTS Status: running={controller.running}, "
                    f"authenticated={controller.authenticated}, "
                    f"model_loaded={controller.model_loaded}"
                )

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
            # ✅ ส่ง motion command แบบ await พร้อม log
            motion_cmd = motion_analyzer.analyze(response_text)
            if self.vts_client:
                logger.info(f"🎭 Sending motion: {motion_cmd}")
                await self.vts_client.execute_motion_command(motion_cmd)
            else:
                logger.warning("⚠️ VTS not available, skipping motion")

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

            # 2) Generate speech via TTS (TTS-only)
            if not self.tts_engine:
                logger.warning("⚠️ TTS engine not ready; cannot speak")
                return

            try:
                audio_data, tts_sample_rate = await self.tts_engine.generate_speech(response_text)
            except Exception as gen_e:
                logger.warning(f"⚠️ Speech generation error: {gen_e}")
                audio_data, tts_sample_rate = None, None
            if audio_data is None:
                logger.warning("⚠️ TTS failed to generate audio")
                return

            # 3) เตรียมข้อมูลเป็น float32 เท่านั้น (ย้าย normalize ไปทำใน playback)
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # ใช้ผลลัพธ์จาก TTS โดยตรงเพื่อให้ตอบสนองเร็ว

            # 4) Play audio in Discord
            sample_rate = tts_sample_rate or core_config.tts.sample_rate
            if self.discord_bot and self.discord_bot.voice_client:
                # ✅ เล่นเสียง (non-blocking แล้ว)
                await self.discord_bot.play_audio(audio_data, sample_rate)

                # ✅ ตรวจสอบสถานะหลังเล่นเสร็จ และรีเซ็ตกลับ idle
                if self.vts_client:
                    try:
                        controller = self.vts_client._controller
                        logger.info(
                            f"🎮 VTS After playback: running={controller.running}, "
                            f"lip_sync_running={controller._lip_sync_running}"
                        )
                    except Exception:
                        pass
                logger.info("✅ Audio played successfully")
            else:
                logger.warning("⚠️ Not connected to a Discord voice channel; cannot play audio")

        except Exception as e:
            logger.error(f"❌ Error processing queue item: {e}", exc_info=True)

    async def _youtube_live_loop(self):
        """อ่านคอมเมนต์ YouTube Live แล้วส่งเข้าคิว"""
        try:
            yt_cfg = getattr(self.config, 'youtube', None)
            if not yt_cfg or not getattr(yt_cfg, 'enabled', False):
                logger.info("ℹ️ YouTube Live ถูกปิดใช้งาน — ข้ามลูป YouTube", extra={'console': True})
                return

            raw_id = getattr(yt_cfg, 'stream_id', '') or getattr(yt_cfg, 'video_id', '')
            if not raw_id:
                logger.info("ℹ️ YouTube Live ไม่มีค่า stream/video ID — ข้ามลูป YouTube", extra={'console': True})
                return

            video_id = self._normalize_youtube_id(raw_id)
            logger.info(f"📺 เริ่มอ่าน YouTube Live: raw='{raw_id}' → id='{video_id}'", extra={'console': True})

            backoff = 5.0
            while self.running:
                try:
                    self.youtube_chat = pytchat.create(video_id=video_id)
                    if not self._yt_connected_once:
                        logger.info(f"✅ เชื่อมต่อ YouTube Live: {video_id}", extra={'console': True})
                        self._yt_connected_once = True
                    else:
                        logger.debug(f"✅ เชื่อมต่อ YouTube Live: {video_id}")

                    interval = float(getattr(yt_cfg, 'check_interval', 5.0))
                    max_batch = int(getattr(yt_cfg, 'max_comments_per_batch', 5))
                    while self.running and self.youtube_chat.is_alive():
                        try:
                            # Backpressure guard: หากคิวแน่น ให้พักก่อนเพื่อไม่ให้ภาระไปกวน animation
                            try:
                                qsize = self.queue_manager.queue.qsize()
                                qmax = getattr(self.queue_manager, 'max_size', 50)
                            except Exception:
                                qsize, qmax = 0, 50
                            if qsize >= max(1, int(qmax * 0.7)):
                                logger.info(f"⏸️  YouTube พักอ่านชั่วคราว (queue {qsize}/{qmax})", extra={'console': True})
                                await asyncio.sleep(interval)
                                continue

                            # อ่านรายการคอมเมนต์ใน thread แยก เพื่อไม่บล็อค event loop หลัก
                            # ห่อทั้ง get() และ sync_items() ใน thread แยก
                            items = await asyncio.to_thread(lambda: self.youtube_chat.get().sync_items())
                            processed = 0
                            for c in items:
                                # จำกัดจำนวนต่อรอบเพื่อลดภาระและป้องกันการคิวสะสมมากเกิน
                                if processed >= max_batch:
                                    break
                                # กันอ่านซ้ำ: ใช้ id ของคอมเมนต์ถ้ามี, ถ้าไม่มีก็ fallback เป็น tuple
                                cid = getattr(c, 'id', None)
                                if self._yt_read_once:
                                    key = cid or (getattr(c.author, 'channelId', ''), getattr(c, 'message', ''), getattr(c, 'elapsedTime', None))
                                    if key in self._yt_seen_ids:
                                        continue
                                msg = c.message
                                user_id = c.author.channelId
                                user_name = c.author.name
                                await self.queue_manager.add_to_queue(
                                    content=msg,
                                    source="youtube",
                                    user_id=str(user_id),
                                    user_name=user_name,
                                    priority=Priority.YOUTUBE
                                )
                                if self._yt_read_once:
                                    self._yt_seen_ids.add(key)
                                    # จำกัดขนาดชุดกันอ่านซ้ำเพื่อไม่ให้โตเกินไป
                                    if len(self._yt_seen_ids) > 2000:
                                        self._yt_seen_ids.clear()
                                processed += 1
                                # cooperative yield เพื่อให้ task อื่น (เช่น animation) ทำงานได้ต่อเนื่อง
                                await asyncio.sleep(0)
                            await asyncio.sleep(interval)
                        except Exception as e:
                            logger.warning(f"⚠️ YouTube Chat Error: {e}")
                            await asyncio.sleep(max(3.0, interval))

                    logger.info("👋 หยุดอ่านคอมเมนต์ YouTube Live", extra={'console': True})
                    break
                except Exception as e:
                    logger.warning(f"⚠️ สร้าง YouTube chat client ล้มเหลว: {e}. จะลองใหม่ใน {backoff:.0f}s")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
        except Exception as e:
            logger.error(f"❌ YouTube Live loop error: {e}", exc_info=True)

    def _normalize_youtube_id(self, raw: str) -> str:
        """รับทั้ง URL และตัว ID แล้วคืน video_id ที่ pytchat รองรับ"""
        if not raw:
            return ""
        raw = raw.strip()
        try:
            if ('://' not in raw) and ('/' not in raw) and ('=' not in raw):
                return raw
            u = urlparse(raw)
            host = (u.netloc or '').lower()
            if 'youtube.com' in host:
                qs = parse_qs(u.query)
                if 'v' in qs and qs['v']:
                    return qs['v'][0]
                parts = u.path.strip('/').split('/')
                if len(parts) >= 2 and parts[0] in ('embed', 'live'):
                    return parts[1]
            if 'youtu.be' in host:
                parts = u.path.strip('/').split('/')
                if parts:
                    return parts[0]
        except Exception:
            pass
        return raw
    
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
    try:
        await vtuber.start()
    except KeyboardInterrupt:
        logger.info("🛑 รับ Ctrl+C — กำลังหยุดระบบ…")
        await vtuber.stop()
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