"""
ai_vtuber.py - Orchestrator
เชื่อม Discord Bot + STT (whisper.cpp) + LLM + TTS และเล่นเสียงแบบต่อเนื่อง
"""

import asyncio
import logging
import os
import time
from typing import Optional, Dict

# Imports แบบเข้ากันได้ทั้งการรันจากรากโปรเจกต์และแบบโมดูล
try:
    from core.queue_manager import (
        get_queue_manager,
        SequentialQueueManager,
        QueuedMessage,
        MessageSource,
    )
    from core.response_generator import get_response_generator
    from llm.chatgpt_client import ChatGPTClient
    from personality.personality import PersonalitySystem
    from adapters.tts.tts_factory import create_tts_engine
    from adapters.audio_player import DiscordAudioPlayer
    from audio.stt_whispercpp import WhisperCppSTT
    from adapters.discord_bot import DiscordBot
except ModuleNotFoundError:
    from src.core.queue_manager import (
        get_queue_manager,
        SequentialQueueManager,
        QueuedMessage,
        MessageSource,
    )
    from src.core.response_generator import get_response_generator
    from src.llm.chatgpt_client import ChatGPTClient
    from src.personality.personality import PersonalitySystem
    from src.adapters.tts.tts_factory import create_tts_engine
    from src.adapters.audio_player import DiscordAudioPlayer
    from src.audio.stt_whispercpp import WhisperCppSTT
    from src.adapters.discord_bot import DiscordBot


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class QueueBridge:
    """
    สะพานเชื่อมอินเทอร์เฟซ queue ของ DiscordBot (add_message(source, content, metadata))
    ให้เข้ากับ SequentialQueueManager (add_message(QueuedMessage))
    """

    def __init__(self, base: SequentialQueueManager):
        self.base = base

    async def add_message(self, *, source: str, content: str, metadata: Optional[Dict] = None):
        # map source เป็น MessageSource
        src_map = {
            'discord_voice': MessageSource.DISCORD_VOICE,
            'discord_text': MessageSource.DISCORD_TEXT,
            'youtube_chat': MessageSource.YOUTUBE_CHAT,
        }
        src_enum = src_map.get(str(source).lower(), MessageSource.DISCORD_TEXT)

        # ดึงชื่อผู้ใช้จาก metadata ถ้ามี
        user = 'user'
        try:
            ctx = metadata.get('ctx') if metadata else None
            if ctx and getattr(ctx, 'author', None):
                user = getattr(ctx.author, 'name', 'user')
            elif metadata and 'author' in metadata:
                user = str(metadata['author'])
        except Exception:
            pass

        qmsg = QueuedMessage(
            text=content,
            source=src_enum,
            user=user,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        await self.base.add_message(qmsg)

    def start(self, processor_func):
        self.base.start(processor_func)

    async def stop(self):
        await self.base.stop()


class AIVTuberApp:
    def __init__(self):
        # Discord token
        self.token = os.getenv('DISCORD_TOKEN')
        if not self.token:
            logger.warning('⚠️ ไม่พบ DISCORD_TOKEN ใน environment — Discord bot จะไม่เริ่มทำงาน')

        # Personality + LLM
        self.personality = PersonalitySystem(persona_name=os.getenv('PERSONA_NAME', 'miko'))
        self.llm_client = ChatGPTClient(personality_system=self.personality)
        self.response_gen = get_response_generator(self.llm_client, self.personality)

        # Queue
        self.queue = get_queue_manager()
        self.queue_bridge = QueueBridge(self.queue)

        # STT + TTS + Audio
        # อนุญาตปิด STT หากยังไม่ตั้งค่า หรือเกิดปัญหา path
        stt_enabled = os.getenv('STT_ENABLED', 'true').lower() != 'false' and os.getenv('DISABLE_STT', 'false').lower() != 'true'
        self.stt = None
        if stt_enabled:
            try:
                self.stt = WhisperCppSTT()
            except Exception as e:
                logger.warning(f'⚠️ STT ไม่พร้อมใช้งาน: {e}. ระบบจะทำงานโหมดข้อความเท่านั้น')
        self.tts = create_tts_engine('f5_tts_thai')
        self.audio_player = DiscordAudioPlayer()

        # Discord bot
        self.discord_bot: Optional[DiscordBot] = None
        if self.token:
            self.discord_bot = DiscordBot(self.token, self.audio_player, self.queue_bridge)

        # Background voice listen config
        self.auto_listen = (os.getenv('DISCORD_AUTO_VOICE_LISTEN', 'false').lower() == 'true')
        if self.auto_listen and self.stt is None:
            logger.info('ℹ️ ปิด auto voice listen เพราะ STT ยังไม่พร้อมใช้งาน')
            self.auto_listen = False
        try:
            self.listen_sec = int(os.getenv('VOICE_LISTEN_SEC', '5'))
        except Exception:
            self.listen_sec = 5

    async def process_message(self, message: QueuedMessage) -> bool:
        """ประมวลผลข้อความหนึ่งรายการจากคิว"""
        try:
            source = message.source.value
            metadata = message.metadata or {}
            ctx = metadata.get('ctx')
            voice_client = metadata.get('voice_client')

            # 1) ถ้าเป็นเสียงจาก Discord ให้ถอดความก่อน
            if message.source == MessageSource.DISCORD_VOICE:
                if self.stt is None:
                    logger.info('🔇 STT ถูกปิดหรือยังไม่ตั้งค่า — ข้ามโหมดเสียง')
                    if ctx:
                        try:
                            await ctx.send('ตอนนี้ยังไม่ได้ตั้งค่า STT เลยตอบได้แค่ข้อความน้า~ ใช้ !speak ได้เลย')
                        except Exception:
                            pass
                    return False
                if not voice_client or not voice_client.is_connected():
                    logger.warning('⚠️ ไม่มี voice_client หรือไม่ได้เชื่อมต่อ')
                    if ctx:
                        try:
                            await ctx.send('⚠️ ไม่ได้อยู่ใน voice channel หรือบันทึกเสียงไม่สำเร็จ')
                        except Exception:
                            pass
                    return False

                logger.info('🎙️ บันทึกและถอดความเสียงจาก Discord...')
                transcript = await self.stt.record_and_transcribe(voice_client, duration_sec=self.listen_sec)
                if not transcript:
                    logger.info('🤔 ไม่ได้ยินชัดเจนหรือถอดความไม่ได้')
                    if ctx:
                        try:
                            await ctx.send('เอ๊ะ~ ได้ยินไม่ชัด ลองพูดใหม่อีกทีนะคะ 😊')
                        except Exception:
                            pass
                    return False
                user_text = transcript
            else:
                # ข้อความปกติ (เช่น จาก !speak)
                user_text = (message.text or '').strip()
                if not user_text:
                    return False

            # 2) สร้างคำตอบด้วย LLM + Personality + Safety
            response_text, rejection_reason = await self.response_gen.generate_response(
                user_text,
                user=message.user,
                source=source,
                repeat_question=False,
            )

            if not response_text:
                logger.info(f'🚫 ปฏิเสธคำถาม: {rejection_reason}')
                if ctx:
                    try:
                        await ctx.send(str(rejection_reason or 'คำถามนี้ขอไม่ตอบนะคะ~'))
                    except Exception:
                        pass
                return False

            # 3) สร้างเสียง TTS (ได้ไฟล์ WAV)
            logger.info('🎤 กำลังสร้างเสียง TTS...')
            audio_file = await self.tts.generate(response_text)
            if not audio_file:
                logger.error('❌ สร้างเสียงไม่สำเร็จ')
                if ctx:
                    try:
                        await ctx.send(f'ขอโทษน้า~ ระบบเสียงมีปัญหา แต่ฉันตอบว่า: {response_text}')
                    except Exception:
                        pass
                return False

            # 4) เล่นเสียงใน Discord พร้อม Lip Sync (ถ้าอยู่ใน voice channel)
            played = False
            if voice_client and getattr(voice_client, 'is_connected', lambda: False)():
                played = await self.audio_player.play_audio_with_lipsync(voice_client, audio_file, text=response_text)
                if ctx:
                    try:
                        await ctx.send(f'💬 {response_text}')
                    except Exception:
                        pass

            # 5) สำรอง: ถ้าไม่มี voice_client ก็ถือว่าประมวลผลเสร็จ
            if not played and ctx:
                try:
                    await ctx.send(f'💬 {response_text}')
                except Exception:
                    pass

            logger.info('✅ ประมวลผลเสร็จสิ้น')
            return True

        except Exception as e:
            logger.error(f'❌ Process message error: {e}', exc_info=True)
            return False

    async def _voice_listen_loop(self):
        """ฟังเสียงอัตโนมัติจาก voice channel (ถ้าเปิดใช้งาน) แล้วส่งเข้าคิว"""
        if not self.auto_listen:
            return
        logger.info('👂 เริ่ม auto voice listen loop')
        while True:
            try:
                vc = getattr(self.discord_bot, 'voice_client', None) if self.discord_bot else None
                if vc and vc.is_connected():
                    # สร้างข้อความคิวสำหรับเสียง (content เป็น placeholder จะถูก STT ใน processor)
                    await self.queue.add_message(QueuedMessage(
                        text='(voice)',
                        source=MessageSource.DISCORD_VOICE,
                        user='voice',
                        timestamp=time.time(),
                        metadata={'voice_client': vc, 'ctx': None},
                    ))
                await asyncio.sleep(max(1, self.listen_sec))
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(2)

    async def run(self):
        """เริ่มระบบทั้งหมดและทำงานแบบไม่หยุด"""
        # เริ่ม queue processor
        self.queue.start(self.process_message)

        # งานพื้นหลังสำหรับ auto-listen ถ้าเปิด
        bg_tasks = []
        if self.auto_listen:
            bg_tasks.append(asyncio.create_task(self._voice_listen_loop()))

        # เริ่ม Discord bot (ถ้ามี token)
        bot_task = None
        if self.discord_bot:
            logger.info('🚀 เริ่ม Discord bot และระบบคิวต่อเนื่อง')
            bot_task = asyncio.create_task(self.discord_bot.start())

        try:
            # รอแบบไม่สิ้นสุด
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            # หยุดทุกอย่าง
            if bot_task:
                try:
                    await self.discord_bot.stop()
                except Exception:
                    pass
            for t in bg_tasks:
                t.cancel()
            try:
                await self.queue_bridge.stop()
            except Exception:
                pass


if __name__ == '__main__':
    try:
        # โหลด .env ถ้ามี
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass

        app = AIVTuberApp()
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass