import os
import asyncio
import logging
from typing import Optional

from core.config import get_settings
from core.types import Message, Source
from core.scheduler import PriorityScheduler
from core.policy import PolicyGuard
from llm.chatgpt_client import ChatGPTClient

# TTS engines
from adapters.tts.tts_interface import TTSEngine
from adapters.tts.tts_stub import StubTTSEngine
try:
    from adapters.tts.f5_tts_thai import F5TTSThaiEngine  # optional if configured
except Exception:
    F5TTSThaiEngine = None  # type: ignore

# VTS
from adapters.vts.vts_client import VTSClient
try:
    from adapters.vts.human_motion import HumanMotionEngine
except Exception:
    HumanMotionEngine = None  # type: ignore
from adapters.vts.hotkeys import HotkeyManager

# Discord / YouTube adapters
from adapters.discord_bot import DiscordAdapter
try:
    from adapters.youtube_live import YouTubeLiveAdapter  # type: ignore
except Exception:
    YouTubeLiveAdapter = None  # type: ignore

logger = logging.getLogger("ai_vtuber")
logging.basicConfig(level=logging.INFO)


def create_tts_engine(settings) -> Optional[TTSEngine]:
    engine = (settings.TTS_ENGINE or "stub").lower()
    if engine == "f5_tts_thai" and F5TTSThaiEngine is not None:
        # F5TTSThaiEngine จัดการการตั้งค่าจาก env/settings ภายในเอง
        return F5TTSThaiEngine()
    # default stub for training-in-progress model
    return StubTTSEngine()


async def orchestrator():
    settings = get_settings()
    scheduler = PriorityScheduler()
    policy = PolicyGuard(allow_mild_profanity=True)

    # LLM
    llm = ChatGPTClient()

    # VTS
    vts = VTSClient(
        plugin_name=settings.VTS_PLUGIN_NAME,
        plugin_developer="AI VTuber",
        host=settings.VTS_HOST,
        port=settings.VTS_PORT,
        config=settings,
    )
    await vts.connect()
    await vts.verify_connection()
    # เริ่ม motion พื้นหลังเพื่อให้โมเดลขยับหัว/กะพริบ/หายใจ และ bob ตามการพูด
    try:
        await vts.start_motion()
    except Exception:
        pass

    # Hotkeys manager (F1/F2/F3 via names from .env)
    hotkeys = HotkeyManager(vts)
    hotkeys.configure_from_env(settings)
    if settings.ENABLE_GLOBAL_HOTKEYS:
        await hotkeys.start_emotion_keyboard_listener()
    safe_task = None
    if getattr(settings, "SAFE_MOTION_MODE", False):
        try:
            safe_task = asyncio.create_task(hotkeys.safe_motion_mode(interval=float(getattr(settings, "SAFE_HOTKEY_INTERVAL", 8.0))))
        except Exception:
            safe_task = None
    # TTS
    tts_engine = create_tts_engine(settings)

    # Discord (priority first)
    discord = DiscordAdapter(scheduler=scheduler, llm_client=llm, tts_engine=tts_engine, vts_client=vts)
    # YouTube (secondary)
    yt = None
    if YouTubeLiveAdapter and settings.YOUTUBE_STREAM_ID:
        try:
            yt = YouTubeLiveAdapter(scheduler=scheduler, llm_client=llm, tts_engine=tts_engine)
        except Exception:
            yt = None

    # Worker loop: consume messages in order, do not interrupt current speaking
    async def worker_loop():
        speaking = False
        while True:
            msg: Message = await scheduler.dequeue()
            if msg.source == Source.DISCORD:
                priority = 10
            else:
                priority = 50
            # re-enforce priority: Discord messages come first
            msg.priority = priority

            # privacy/internals policy checks and sanitization
            ok, reason = policy.check_message_ok(msg)
            if not ok:
                continue

            # determine whether to answer (if question or high-priority chat)
            should_answer = msg.is_question or msg.source == Source.DISCORD
            if not should_answer:
                continue

            # LLM response with timing measurement for emotion analysis
            import time
            response_start_time = time.time()
            system_prompt = "ตอบให้เข้าใจง่าย ไม่เกินจำเป็น เคารพนโยบายความเป็นส่วนตัวและความเหมาะสม"
            resp = llm.generate_reply(msg.text, system_prompt)
            response_time = time.time() - response_start_time
            reply_text = policy.sanitize_output(resp.text)

            # Automatic emotion triggering based on AI response and context
            try:
                await hotkeys.auto_trigger_emotion_from_response(
                    ai_response=reply_text,
                    user_input=msg.text,
                    response_time=response_time,
                    base_probability=float(getattr(settings, "VTS_EMOTION_TRIGGER_PROBABILITY", 0.2))
                )
            except Exception as e:
                logger.debug(f"Emotion trigger failed: {e}")

            # speak via TTS and lipsync
            audio_bytes: Optional[bytes] = None
            if tts_engine:
                audio_bytes = tts_engine.speak(
                    reply_text,
                    voice_id=os.getenv("TTS_VOICE_ID", "default"),
                    emotion=resp.emotion.value,
                    prosody={"rate": float(os.getenv("F5_TTS_SPEED", str(getattr(settings, "F5_TTS_SPEED", 1.0))))},
                )
            if audio_bytes:
                # lip sync with VTS concurrently
                try:
                    await vts.lipsync_bytes(audio_bytes)
                except Exception:
                    pass
                # Discord bot will handle playback upon commands; here we can extend to auto-play if desired

            # small cooldown before next message
            await asyncio.sleep(0.2)

    # Run background worker
    worker_task = asyncio.create_task(worker_loop())

    # Start adapters
    async def start_discord():
        token = settings.DISCORD_BOT_TOKEN
        if not token:
            logger.warning("DISCORD_BOT_TOKEN ไม่ได้ตั้งค่า — ข้าม Discord")
            return
        await discord.bot.start(token)

    async def start_youtube():
        if yt:
            try:
                await yt.start()
            except Exception as e:
                logger.error(f"YouTube adapter start failed: {e}")

    await asyncio.gather(start_discord(), start_youtube(), return_exceptions=True)

    # shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    # ไม่ต้องหยุดลูป motion เพราะเราไม่ได้เริ่มไว้
    try:
        hotkeys.stop_emotion_keyboard_listener()
    except Exception:
        pass
    if safe_task:
        try:
            safe_task.cancel()
            await safe_task
        except Exception:
            pass
    await vts.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(orchestrator())
    except KeyboardInterrupt:
        print("🛑 Shutdown by user")