"""
ai_vtuber.py - AI VTuber Main Orchestrator
แก้ไขเพื่อรองรับ: Queue, Safety Filter, Response Generator, Audio Player
"""

import asyncio
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# Core systems
from src.core.safety_filter import get_safety_filter
from src.core.queue_manager import get_queue_manager, QueuedMessage, MessageSource
from src.core.admin_commands import get_admin_handler
from src.core.response_generator import get_response_generator

# Adapters
from src.adapters.vts.motion_controller import create_motion_controller
from src.adapters.vts.vts_client import VTSClient
from src.adapters.audio_player import DiscordAudioPlayer
from src.adapters.discord_bot import create_discord_bot
from src.adapters.youtube_live import create_youtube_live_adapter

# LLM & TTS
from src.llm.chatgpt_client import ChatGPTClient
from src.personality.personality import PersonalitySystem
from src.adapters.tts.f5_tts_thai import create_tts_engine
from src.audio.stt_whispercpp import WhisperCppSTT

logger = logging.getLogger(__name__)


class AIVTuberOrchestrator:
    """Main orchestrator ควบคุมทุกส่วนของระบบ"""
    
    def __init__(self):
        logger.info("🚀 AI VTuber Orchestrator เริ่มต้น...")
        
        # โหลด .env
        load_dotenv()
        
        # Core components
        self.safety_filter = get_safety_filter()
        self.queue_manager = get_queue_manager()
        self.admin_handler = get_admin_handler()
        
        # LLM & Personality
        self.llm = None
        self.personality = None
        self.response_generator = None
        
        # VTS
        self.vts_client = None
        self.motion_controller = None
        
        # TTS & RVC
        self.tts = None
        self.rvc = None
        self.rvc_enabled = os.getenv("ENABLE_RVC", "false").lower() == "true"
        
        # Audio Player
        self.audio_player = None
        
        # Adapters
        self.discord_bot = None
        self.youtube_adapter = None
        
        # STT System
        self.stt_system = None
        
        # State
        self.is_running = False
    
    async def initialize(self):
        """เริ่มต้นทุก components"""
        try:
            logger.info("🔧 เริ่มสร้าง components...")
            
            # 1. Personality System
            persona_name = os.getenv("PERSONA_NAME", "miko")
            self.personality = PersonalitySystem(persona_name)
            logger.info(f"✅ Personality: {persona_name}")
            
            # 2. LLM
            self.llm = ChatGPTClient(
                api_key=os.getenv("OPENAI_API_KEY"),
                model=os.getenv("LLM_MODEL"),
                personality_system=self.personality
            )
            logger.info("✅ LLM สร้างแล้ว")
            
            # 3. Response Generator
            self.response_generator = get_response_generator(
                self.llm,
                self.personality
            )
            logger.info("✅ Response Generator สร้างแล้ว")
            
            # 4. VTS
            vts_host = os.getenv("VTS_HOST", "127.0.0.1")
            vts_port = int(os.getenv("VTS_PORT", "8001"))
            
            self.vts_client = VTSClient(vts_host, vts_port)
            await self.vts_client.connect()
            
            self.motion_controller = create_motion_controller(
                self.vts_client,
                env=dict(os.environ)
            )
            await self.motion_controller.start()
            logger.info("✅ VTS Motion Controller พร้อมแล้ว")
            
            # 5. TTS
            tts_engine = os.getenv("TTS_ENGINE", "f5_tts_thai")
            self.tts = create_tts_engine(tts_engine)
            logger.info(f"✅ TTS Engine: {tts_engine}")
            
            # 6. RVC (ถ้าเปิด)
            if self.rvc_enabled:
                # TODO: Initialize RVC
                logger.info("✅ RVC enabled")
            
            # 7. Audio Player
            self.audio_player = DiscordAudioPlayer(self.motion_controller)
            logger.info("✅ Audio Player พร้อมแล้ว")
            
            # 8. STT System (ถ้ามี)
            try:
                if os.getenv("DISCORD_VOICE_STT_ENABLED", "false").lower() == "true":
                    self.stt_system = WhisperCppSTT()
                    logger.info("✅ STT (Whisper.cpp) พร้อมใช้งาน")
                else:
                    logger.info("ℹ️ ปิด STT (ตั้งค่า DISCORD_VOICE_STT_ENABLED=true เพื่อเปิด)")
            except Exception as e:
                logger.warning(f"⚠️ STT (Whisper.cpp) ไม่พร้อม: {e}")
            
            # 9. Discord Bot
            discord_token = os.getenv("DISCORD_BOT_TOKEN")
            if discord_token:
                self.discord_bot = create_discord_bot(
                    token=discord_token,
                    motion_controller=self.motion_controller,
                    stt_system=self.stt_system
                )
                logger.info("✅ Discord Bot สร้างแล้ว")
            
            # 10. YouTube Live
            youtube_stream_id = os.getenv("YOUTUBE_STREAM_ID")
            if youtube_stream_id:
                self.youtube_adapter = create_youtube_live_adapter(
                    stream_id=youtube_stream_id,
                    motion_controller=self.motion_controller
                )
                if self.youtube_adapter:
                    logger.info("✅ YouTube Live Adapter สร้างแล้ว")
            
            logger.info("=" * 60)
            logger.info("✅ ทุก components พร้อมแล้ว!")
            logger.info("=" * 60)
            
            return True
        
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการเริ่มต้น: {e}", exc_info=True)
            return False
    
    async def process_message(self, message: QueuedMessage) -> bool:
        """
        ประมวลผลข้อความจากคิว
        
        Flow:
        1. Generate Response (มี safety check อยู่ในนี้)
        2. TTS
        3. RVC (ถ้าเปิด)
        4. Play Audio + Lip Sync
        
        Returns:
            True = สำเร็จ, False = ล้มเหลว
        """
        try:
            logger.info(f"▶️ Processing: [{message.source.value}] {message.text[:50]}")
            
            # 1. Generate Response
            response_text, rejection_reason = await self.response_generator.generate_response(
                user_message=message.text,
                user=message.user,
                source=message.source.value,
                repeat_question=message.metadata.get("repeat_question", False)
            )
            
            if not response_text:
                logger.warning(f"⚠️ Rejected: {rejection_reason}")
                # TODO: ส่งข้อความปฏิเสธกลับไปยัง user
                return False
            
            logger.info(f"💬 Response: {response_text[:100]}")
            
            # 2. TTS
            audio_file = await self.tts.generate(response_text)
            if not audio_file or not Path(audio_file).exists():
                logger.error("❌ TTS ล้มเหลว")
                return False
            
            logger.info(f"🎵 TTS: {audio_file}")
            
            # 3. RVC (ถ้าเปิด)
            if self.rvc_enabled and self.rvc:
                try:
                    audio_file = await self.rvc.convert(audio_file)
                    logger.info(f"🎤 RVC: {audio_file}")
                except Exception as e:
                    logger.warning(f"⚠️ RVC error (ใช้เสียงเดิม): {e}")
            
            # 4. Play Audio + Lip Sync
            await self._play_audio_response(message, audio_file, response_text)
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Process message error: {e}", exc_info=True)
            return False
    
    async def _play_audio_response(
        self,
        message: QueuedMessage,
        audio_file: str,
        text: str
    ):
        """เล่นเสียงตอบกลับ"""
        try:
            # Discord Voice
            if message.source == MessageSource.DISCORD_VOICE or message.source == MessageSource.DISCORD_TEXT:
                voice_client = message.metadata.get("voice_client")
                
                if voice_client and voice_client.is_connected():
                    logger.info("🔊 เล่นเสียงใน Discord...")
                    await self.audio_player.play_audio_with_lipsync(
                        voice_client,
                        audio_file,
                        text
                    )
                else:
                    logger.warning("⚠️ Voice client ไม่ได้เชื่อมต่อ")
            
            # YouTube Live (เล่นเสียงใน local หรือ stream)
            elif message.source == MessageSource.YOUTUBE_CHAT:
                logger.info("🔊 เล่นเสียงสำหรับ YouTube...")
                # TODO: Implement YouTube audio playback
                # อาจต้องเล่นเสียงใน local หรือ stream ไปยัง OBS
                pass
        
        except Exception as e:
            logger.error(f"❌ Play audio error: {e}", exc_info=True)
    
    async def start(self):
        """เริ่มระบบทั้งหมด"""
        if not await self.initialize():
            logger.error("❌ ไม่สามารถเริ่มระบบได้")
            return
        
        self.is_running = True
        
        # เริ่ม Queue Manager
        self.queue_manager.start(self.process_message)
        logger.info("✅ Queue Manager เริ่มทำงาน")
        
        # เริ่ม YouTube Live
        if self.youtube_adapter:
            await self.youtube_adapter.start()
        
        # เริ่ม Discord Bot (background task)
        discord_task = None
        if self.discord_bot:
            discord_task = asyncio.create_task(self.discord_bot.start())
            logger.info("✅ Discord Bot task started")
        
        logger.info("=" * 60)
        logger.info("✅ ระบบเริ่มทำงานเรียบร้อย!")
        logger.info("=" * 60)
        
        # รอจนกว่าจะหยุด
        try:
            while self.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n⚠️ กำลังปิดระบบ...")
        finally:
            await self.stop()
            
            if discord_task:
                discord_task.cancel()
                try:
                    await discord_task
                except asyncio.CancelledError:
                    pass
    
    async def stop(self):
        """หยุดระบบทั้งหมด"""
        logger.info("🛑 กำลังปิดระบบ...")
        
        self.is_running = False
        
        # หยุด Queue Manager
        await self.queue_manager.stop()
        
        # หยุด YouTube
        if self.youtube_adapter:
            await self.youtube_adapter.stop()
        
        # หยุด Discord
        if self.discord_bot:
            await self.discord_bot.stop()
        
        # หยุด Motion Controller
        if self.motion_controller:
            await self.motion_controller.stop()
        
        # หยุด VTS Client
        if self.vts_client:
            await self.vts_client.disconnect()
        
        logger.info("✅ ระบบปิดเรียบร้อย")


async def main():
    """Main entry point"""
    orchestrator = AIVTuberOrchestrator()
    await orchestrator.start()


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run
    asyncio.run(main())