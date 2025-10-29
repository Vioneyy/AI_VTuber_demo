"""
AI VTuber Orchestrator
"""
# Bootstrap sys.path so running this file directly can import the 'src' package
import sys as _sys
from pathlib import Path as _Path
_proj_root = _Path(__file__).resolve().parents[1]
_root_str = str(_proj_root)
if _root_str not in _sys.path:
    _sys.path.insert(0, _root_str)
import os
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AIVTuberOrchestrator:
    def __init__(self):
        logger.info("🚀 AI VTuber Orchestrator เริ่มต้น...")
        
        self.scheduler = None
        self.policy = None
        self.llm = None
        self.tts = None
        self.vts = None
        self.motion = None
        self.discord_bot = None
        self.youtube = None
        
        self._initialize_components()

    def _initialize_components(self):
        """สร้าง components ทั้งหมด"""
        try:
            from src.core.scheduler import PriorityScheduler
            self.scheduler = PriorityScheduler()
            logger.info("✅ Scheduler สร้างแล้ว")
            
            from src.core.policy import PolicyGuard
            self.policy = PolicyGuard()
            logger.info("✅ Policy Guard สร้างแล้ว")
            
            from src.llm.chatgpt_client import ChatGPTClient
            persona_name = os.getenv("PERSONA_NAME", "miko")
            self.llm = ChatGPTClient(persona_name=persona_name)
            logger.info(f"✅ LLM สร้างแล้ว (persona: {persona_name})")
            
            from src.adapters.tts.f5_tts_thai import create_tts_engine
            self.tts = create_tts_engine()
            logger.info("✅ TTS Engine สร้างแล้ว")
            
            from src.adapters.vts.vts_client import VTSClient
            vts_host = os.getenv("VTS_HOST", "localhost")
            vts_port = int(os.getenv("VTS_PORT", "8001"))
            vts_plugin = os.getenv("VTS_PLUGIN_NAME", "AI_VTuber_Plugin")
            
            # ใช้ keyword ให้ตรงกับ signature: (plugin_name, plugin_developer, host, port, config)
            self.vts = VTSClient(
                plugin_name=vts_plugin,
                plugin_developer="AI VTuber",
                host=vts_host,
                port=vts_port,
            )
            logger.info("✅ VTS Client สร้างแล้ว")
            
            from src.adapters.vts.motion_controller import create_motion_controller
            
            motion_config = {
                "VTS_MOVEMENT_SMOOTHING": os.getenv("VTS_MOVEMENT_SMOOTHING", "0.85"),
                "VTS_MOTION_INTENSITY": os.getenv("VTS_MOTION_INTENSITY", "0.4"),
                "VTS_IDLE_HEAD_INTENSITY": os.getenv("VTS_IDLE_HEAD_INTENSITY", "0.15"),
                "VTS_IDLE_BREATH_INTENSITY": os.getenv("VTS_IDLE_BREATH_INTENSITY", "0.25"),
                "VTS_BREATH_SPEED": os.getenv("VTS_BREATH_SPEED", "0.8"),
                "VTS_BREATH_INTENSITY": os.getenv("VTS_BREATH_INTENSITY", "0.3"),
                "VTS_BLINK_INTERVAL_MIN": os.getenv("VTS_BLINK_INTERVAL_MIN", "2.0"),
                "VTS_BLINK_INTERVAL_MAX": os.getenv("VTS_BLINK_INTERVAL_MAX", "6.0"),
                "VTS_BLINK_DURATION": os.getenv("VTS_BLINK_DURATION", "0.15"),
            }
            
            self.motion = create_motion_controller(self.vts, motion_config)
            logger.info("✅ Motion Controller สร้างแล้ว")
            
            from src.adapters.discord_bot import DiscordBot
            self.discord_bot = DiscordBot(self)
            logger.info("✅ Discord Bot สร้างแล้ว")
            
            youtube_stream_id = os.getenv("YOUTUBE_STREAM_ID")
            youtube_mock = os.getenv("YOUTUBE_MOCK_MODE", "false").lower() == "true"
            
            if youtube_stream_id or youtube_mock:
                from src.adapters.youtube_live import create_youtube_adapter
                self.youtube = create_youtube_adapter(self)
                logger.info("✅ YouTube Adapter สร้างแล้ว")
            else:
                logger.info("⏭️ ข้าม YouTube Adapter")
            
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาด: {e}", exc_info=True)
            raise

    async def start(self):
        """เริ่มระบบทั้งหมด"""
        try:
            logger.info("=" * 60)
            logger.info("🎬 เริ่มระบบ AI VTuber")
            logger.info("=" * 60)
            
            logger.info("📡 กำลังเชื่อมต่อ VTS...")
            await self.vts.connect()
            
            if not self.vts.ws or self.vts.ws.closed:
                logger.warning("⚠️ ไม่สามารถเชื่อมต่อ VTS")
            else:
                logger.info("🎭 เริ่ม Motion Controller...")
                await self.motion.start()
            
            logger.info("⚙️ เริ่ม Message Worker...")
            worker_task = asyncio.create_task(self._message_worker())
            
            youtube_task = None
            if self.youtube:
                logger.info("📺 เริ่ม YouTube Adapter...")
                await self.youtube.start()
                youtube_task = asyncio.create_task(self._keep_youtube_alive())
            
            logger.info("🤖 เริ่ม Discord Bot...")
            discord_token = os.getenv("DISCORD_BOT_TOKEN")
            
            if not discord_token:
                logger.error("❌ ไม่มี DISCORD_BOT_TOKEN ใน .env")
                return
            
            try:
                await self.discord_bot.start_bot(discord_token)
            except KeyboardInterrupt:
                logger.info("\n⚠️ รับสัญญาณหยุด")
            
            logger.info("🛑 กำลังปิดระบบ...")
            await self._shutdown()
            
        except Exception as e:
            logger.error(f"❌ Start error: {e}", exc_info=True)
            await self._shutdown()

    async def _message_worker(self):
        """Worker loop: ดึงข้อความจากคิวแล้วประมวลผล"""
        logger.info("👷 Message worker เริ่มทำงาน")
        
        while True:
            try:
                message = await self.scheduler.get_next_message(timeout=1.0)
                
                if not message:
                    await asyncio.sleep(0.1)
                    continue
                
                logger.info(f"📨 ประมวลผล: [{message.source}] {message.text[:50]}...")
                
                if not self.policy.should_respond(message.text):
                    logger.info("🚫 ข้ามข้อความ (policy)")
                    continue
                
                answer = self.llm.generate_response(message.text)
                answer = self.policy.sanitize_response(answer)
                
                logger.info(f"💬 คำตอบ: {answer[:50]}...")
                
                self.motion.set_generating(True)
                
                audio_bytes = self.tts.synthesize(answer)
                
                self.motion.set_generating(False)
                
                if audio_bytes and self.vts.ws and not self.vts.ws.closed:
                    await self.vts.lipsync_bytes(audio_bytes)
                
                logger.info("✅ ประมวลผลเสร็จสิ้น")
                
                await asyncio.sleep(0.5)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _keep_youtube_alive(self):
        """เช็คว่า YouTube adapter ยังทำงานอยู่"""
        while True:
            try:
                if self.youtube and self.youtube.task:
                    if self.youtube.task.done():
                        logger.warning("YouTube task หยุด กำลัง restart...")
                        await self.youtube.start()
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"YouTube keepalive error: {e}")
                await asyncio.sleep(10)

    async def _shutdown(self):
        """ปิดระบบอย่างเรียบร้อย"""
        logger.info("🔌 กำลังปิด components...")
        
        try:
            if self.youtube:
                await self.youtube.stop()
            
            if self.motion:
                await self.motion.stop()
            
            if self.vts:
                await self.vts.disconnect()
            
            if self.discord_bot:
                await self.discord_bot.close()
            
            logger.info("✅ ปิดระบบเรียบร้อย")
            
        except Exception as e:
            logger.error(f"Shutdown error: {e}", exc_info=True)


async def main():
    orchestrator = AIVTuberOrchestrator()
    await orchestrator.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 ปิดโปรแกรมด้วย Ctrl+C")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)