"""
Main entry point สำหรับระบบ AI VTuber
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# เพิ่ม src directory เข้า Python path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import Config
from core.scheduler import PriorityScheduler
from core.types import IncomingMessage, MessageSource
from personality.personality import PersonalityManager
from llm.chatgpt_client import ChatGPTClient
from adapters.discord_bot import DiscordBot
from adapters.youtube_live import YouTubeLiveAdapter
from adapters.tts.f5_tts_thai import F5TTSThai
from adapters.vts.vts_client import VTSClient
from adapters.vts.hotkeys import HotkeyManager, Emotion

# ตั้งค่า logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class AIVTuber:
    """คลาสหลักสำหรับระบบ AI VTuber"""
    
    def __init__(self):
        self.config = Config()
        self.scheduler = PriorityScheduler()
        self.personality = PersonalityManager()
        self.llm_client = ChatGPTClient(
            api_key=self.config.OPENAI_API_KEY,
            model=self.config.LLM_MODEL
        )
        self.tts = None
        self.vts_client = None
        self.hotkey_manager = None
        self.discord_bot = None
        self.youtube = None
        
        # Task สำหรับ process messages
        self.processing_task = None
        self.safe_motion_task = None
        self.running = False
    
    async def initialize(self):
        """เริ่มต้นระบบทั้งหมด"""
        logger.info("="*60)
        logger.info("🚀 เริ่มต้นระบบ AI VTuber")
        logger.info("="*60)
        
        # 1. โหลด TTS
        try:
            logger.info("\n📢 [1/5] โหลด TTS Engine...")
            self.tts = F5TTSThai(
                reference_wav=self.config.TTS_REFERENCE_WAV,
                reference_text=self.config.TTS_REFERENCE_TEXT
            )
            logger.info("✅ โหลด TTS สำเร็จ")
        except Exception as e:
            logger.error(f"❌ ไม่สามารถโหลด TTS: {e}")
            raise
        
        # 2. เชื่อมต่อ VTube Studio
        try:
            logger.info("\n🎭 [2/5] เชื่อมต่อ VTube Studio...")
            self.vts_client = VTSClient(
                plugin_name=self.config.VTS_PLUGIN_NAME,
                plugin_developer="VIoneyy",
                host=self.config.VTS_HOST,
                port=self.config.VTS_PORT,
                config=self.config  # ส่ง config เข้าไป
            )
            
            if await self.vts_client.connect():
                logger.info("✅ เชื่อมต่อ VTS สำเร็จ")
                
                # สร้าง HotkeyManager
                self.hotkey_manager = HotkeyManager(self.vts_client)
                self.hotkey_manager.configure_from_env(self.config)
                
                # เริ่ม Safe Motion Mode (ถ้าเปิดใช้งาน)
                if getattr(self.config, "SAFE_MOTION_MODE", False):
                    interval = getattr(self.config, "SAFE_HOTKEY_INTERVAL", 6.0)
                    logger.info(f"🔒 เริ่ม Safe Motion Mode (interval={interval}s)")
                    self.safe_motion_task = asyncio.create_task(
                        self.hotkey_manager.safe_motion_mode(interval)
                    )
                else:
                    # เริ่มการเคลื่อนไหวแบบสุ่ม (Parameter injection)
                    await self.vts_client.start_random_motion()
                
                # เริ่ม keyboard listener (ถ้าเปิดใช้งาน)
                if getattr(self.config, "ENABLE_GLOBAL_HOTKEYS", False):
                    await self.hotkey_manager.start_emotion_keyboard_listener()
                
            else:
                logger.warning("⚠️ ไม่สามารถเชื่อมต่อ VTS - ข้ามขั้นตอนนี้")
                self.vts_client = None
                self.hotkey_manager = None
                
        except Exception as e:
            logger.error(f"❌ VTS Error: {e}")
            self.vts_client = None
            self.hotkey_manager = None
        
        # 3. เริ่ม Discord Bot
        logger.info("\n💬 [3/5] เริ่มต้น Discord Bot...")
        if self.config.DISCORD_BOT_TOKEN:
            try:
                self.discord_bot = DiscordBot(
                    token=self.config.DISCORD_BOT_TOKEN,
                    scheduler=self.scheduler
                )
                # เริ่ม bot แบบ background task
                asyncio.create_task(self.discord_bot.start())
                logger.info("✅ Discord Bot พร้อมใช้งาน")
            except Exception as e:
                logger.error(f"❌ Discord Bot Error: {e}")
        else:
            logger.info("⏭️  ข้าม Discord: ไม่ได้ตั้งค่า DISCORD_BOT_TOKEN")
        
        # 4. เริ่ม YouTube Live
        logger.info("\n📺 [4/5] เริ่มต้น YouTube Live...")
        if self.config.YOUTUBE_STREAM_ID:
            try:
                self.youtube = YouTubeLiveAdapter(
                    stream_id=self.config.YOUTUBE_STREAM_ID,
                    scheduler=self.scheduler
                )
                asyncio.create_task(self.youtube.start())
                logger.info("✅ YouTube Live พร้อมใช้งาน")
            except Exception as e:
                logger.error(f"❌ YouTube Error: {e}")
        else:
            logger.info("⏭️  ข้าม YouTube: ไม่ได้ตั้งค่า YOUTUBE_STREAM_ID")
        
        # 5. เสร็จสิ้น
        logger.info("\n🎉 [5/5] ระบบพร้อมทำงาน!")
        logger.info("="*60 + "\n")
    
    async def process_messages(self):
        """ประมวลผลข้อความจาก scheduler"""
        logger.info("📝 เริ่ม message processing loop...\n")
        
        while self.running:
            try:
                # ดึงข้อความจาก queue
                message = await self.scheduler.get_next_message()
                
                if message:
                    await self._handle_message(message)
                else:
                    # ไม่มีข้อความ รอสักครู่
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"❌ Error processing message: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _handle_message(self, message: IncomingMessage):
        """จัดการข้อความหนึ่งข้อความ"""
        try:
            logger.info("="*60)
            logger.info(f"💬 [{message.source.value}] {message.author}:")
            logger.info(f"   {message.content[:100]}{'...' if len(message.content) > 100 else ''}")
            
            # 1. ส่งข้อความไปยัง LLM
            system_prompt = self.personality.get_system_prompt()
            response = await self.llm_client.chat(
                user_message=message.content,
                system_prompt=system_prompt,
                username=message.author
            )
            
            if not response:
                logger.warning("⚠️ LLM ไม่ส่งคำตอบกลับมา")
                return
            
            logger.info(f"🤖 AI: {response[:100]}{'...' if len(response) > 100 else ''}")
            
            # 2. วิเคราะห์อารมณ์และกด hotkey (ก่อนพูด)
            if self.hotkey_manager:
                # วิเคราะห์อารมณ์จากคำตอบ
                emotion = await self.hotkey_manager.analyze_emotion(response)
                
                # กด hotkey ตามบริบท
                # ถ้ากำลังคิดหรือตอบคำถามยาวๆ
                if len(response) > 100 or "?" in message.content:
                    await self.hotkey_manager.trigger_emotion(
                        Emotion.THINKING, 
                        probability=0.7
                    )
                else:
                    # ใช้อารมณ์ที่วิเคราะห์ได้
                    await self.hotkey_manager.trigger_emotion(
                        emotion,
                        probability=0.5
                    )
            
            # 3. สร้างเสียงพูดด้วย TTS
            try:
                audio_path = await self.tts.synthesize(response)
                
                if audio_path and os.path.exists(audio_path):
                    logger.info(f"🔊 สร้างเสียง: {audio_path}")
                    
                    # เล่นเสียงผ่าน Discord (ถ้ามี)
                    if self.discord_bot and message.source == MessageSource.DISCORD_VOICE:
                        await self.discord_bot.play_audio(audio_path)
                    
            except Exception as e:
                logger.error(f"❌ TTS Error: {e}")
            
            # 4. ตอบกลับในแชท (ถ้าเป็น text)
            if message.source == MessageSource.DISCORD_TEXT:
                if self.discord_bot:
                    # แบ่งข้อความยาวๆ
                    if len(response) > 2000:
                        chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                        for chunk in chunks:
                            await self.discord_bot.send_message(message.channel_id, chunk)
                    else:
                        await self.discord_bot.send_message(message.channel_id, response)
            
            logger.info("="*60 + "\n")
            
        except Exception as e:
            logger.error(f"❌ Error handling message: {e}", exc_info=True)
    
    async def start(self):
        """เริ่มระบบ"""
        self.running = True
        
        # เริ่มต้นระบบ
        await self.initialize()
        
        # เริ่ม processing loop
        self.processing_task = asyncio.create_task(self.process_messages())
        
        # รอจนกว่าจะถูกหยุด
        try:
            await self.processing_task
        except asyncio.CancelledError:
            pass
    
    async def stop(self):
        """หยุดระบบ"""
        logger.info("\n" + "="*60)
        logger.info("🛑 กำลังหยุดระบบ...")
        logger.info("="*60)
        
        self.running = False
        
        # หยุด processing task
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        
        # หยุด safe motion task
        if self.safe_motion_task:
            self.safe_motion_task.cancel()
            try:
                await self.safe_motion_task
            except asyncio.CancelledError:
                pass
        
        # ปิด keyboard listener
        if self.hotkey_manager:
            self.hotkey_manager.stop_emotion_keyboard_listener()
        
        # ปิดการเชื่อมต่อ VTS
        if self.vts_client:
            await self.vts_client.disconnect()
        
        # ปิด Discord bot
        if self.discord_bot:
            await self.discord_bot.close()
        
        # ปิด YouTube
        if self.youtube:
            await self.youtube.stop()
        
        logger.info("✅ ระบบหยุดทำงานเรียบร้อย")
        logger.info("="*60 + "\n")


async def main():
    """ฟังก์ชันหลัก"""
    vtuber = AIVTuber()
    
    try:
        await vtuber.start()
    except KeyboardInterrupt:
        logger.info("\n⚠️ ได้รับสัญญาณหยุด (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        await vtuber.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass