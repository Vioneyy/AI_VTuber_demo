# src/ai_vtuber.py
"""
AI VTuber Orchestrator (Robust component init + non-blocking TTS + Discord retry)
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

logger = logging.getLogger("ai_vtuber")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


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

        self._discord_task: asyncio.Task | None = None
        self._youtube_task: asyncio.Task | None = None
        self._worker_task: asyncio.Task | None = None

        self._initialize_components()

    def _initialize_components(self):
        logger.info("🔧 เริ่มสร้าง components...")

        try:
            from src.core.scheduler import PriorityScheduler
            self.scheduler = PriorityScheduler()
            logger.info("✅ Scheduler สร้างแล้ว")
        except Exception as e:
            logger.error(f"Scheduler creation failed: {e}", exc_info=True)
            self.scheduler = None

        try:
            from src.core.policy import PolicyGuard
            self.policy = PolicyGuard()
            logger.info("✅ Policy Guard สร้างแล้ว")
        except Exception as e:
            logger.error(f"PolicyGuard creation failed: {e}", exc_info=True)
            self.policy = None

        try:
            from src.llm.chatgpt_client import ChatGPTClient
            persona_name = os.getenv("PERSONA_NAME", "miko")
            self.llm = ChatGPTClient(persona_name=persona_name)
            logger.info(f"✅ LLM สร้างแล้ว (persona: {persona_name})")
        except Exception as e:
            logger.error(f"LLM creation failed: {e}", exc_info=True)
            self.llm = None

        # TTS: ใช้ factory เพื่อให้มีตัวเลือก fallback (เช่น gTTS) ที่ใช้งานได้จริง
        try:
            from src.adapters.tts.f5_tts_thai import create_tts_engine
            self.tts = create_tts_engine()
            logger.info("✅ TTS สร้างแล้วผ่าน factory (พร้อม fallback)")
        except Exception as e:
            logger.error(f"TTS factory creation failed: {e}", exc_info=True)
            self.tts = None

        try:
            from src.adapters.vts.vts_client import VTSClient
            vts_host = os.getenv("VTS_HOST", "127.0.0.1")
            vts_port = int(os.getenv("VTS_PORT", "8001"))
            self.vts = VTSClient(host=vts_host, port=vts_port)
            logger.info("✅ VTS Client สร้างแล้ว")
        except Exception as e:
            logger.error(f"VTSClient creation failed: {e}", exc_info=True)
            self.vts = None

        try:
            from src.adapters.vts.motion_controller import create_motion_controller
            self.motion = create_motion_controller(self.vts, os.environ)
            logger.info("✅ Motion Controller สร้างแล้ว")
        except Exception as e:
            logger.error(f"MotionController creation failed: {e}", exc_info=True)
            self.motion = None

        try:
            from src.adapters.discord_bot import DiscordBotAdapter
            try:
                self.discord_bot = DiscordBotAdapter(self)
            except Exception:
                self.discord_bot = DiscordBotAdapter()
            logger.info("✅ Discord Bot สร้างเสร็จแล้ว")
        except Exception as e:
            logger.error(f"DiscordBotAdapter creation failed: {e}", exc_info=True)
            self.discord_bot = None

        try:
            from src.adapters.youtube_live import YouTubeAdapter
            self.youtube = YouTubeAdapter()
            logger.info("✅ YouTube Adapter สร้างเสร็จแล้ว")
        except Exception:
            self.youtube = None
            logger.info("ℹ️ YouTube Adapter ไม่ถูกใช้งาน or ไม่สามารถสร้างได้")

        logger.info("🔧 การสร้าง components เสร็จสิ้น (บางตัวอาจล้ม)")

    async def _start_discord_safe(self, token: str):
        """
        Start Discord one-shot and report clear errors. Avoid infinite retry when token invalid.
        """
        if not self.discord_bot:
            logger.warning("Discord adapter not available; skipping Discord start.")
            return

        try:
            logger.info("🚀 Starting Discord bot...")
            await self.discord_bot.start_bot(token)
            logger.info("✅ Discord bot exited normally.")
        except asyncio.CancelledError:
            logger.info("Discord start task cancelled.")
        except Exception as e:
            logger.error(f"Discord bot start failed: {e}", exc_info=True)
            try:
                from discord.errors import LoginFailure
                if isinstance(e, LoginFailure):
                    logger.error("❌ โทเคน Discord ไม่ถูกต้อง: ใช้ 'Bot Token' จาก Developer Portal และเชิญบอทเข้ากิลด์ให้ถูกต้อง")
            except Exception:
                pass
            # เคลียร์ resource เพื่อไม่ให้ค้าง
            try:
                if self.discord_bot and getattr(self.discord_bot, "stop", None):
                    await self.discord_bot.stop()
            except Exception:
                pass
            logger.info("ℹ️ ข้ามการเริ่ม Discord ต่อเนื่อง — โปรดแก้ไขโทเคนแล้วรันใหม่")

    async def start(self):
        try:
            logger.info("="*60)
            logger.info("🎬 เริ่มระบบ AI VTuber")
            logger.info("="*60)

            logger.info("📡 กำลังเชื่อมต่อ VTS...")
            if self.vts:
                try:
                    await self.vts.connect()
                except Exception as e:
                    logger.error(f"VTS connect raised: {e}", exc_info=True)
            else:
                logger.warning("⚠️ VTS client not available (skipping connect)")

            connected = False
            try:
                connected = bool(self.vts and getattr(self.vts, "_is_connected", lambda: False)())
            except Exception:
                connected = False

            if not connected:
                logger.warning("⚠️ ไม่สามารถเชื่อมต่อ VTS (ระบบจะพยายามทำงานต่อได้ แต่ VTS จะไม่ถูกควบคุม)")
            else:
                if self.motion:
                    try:
                        await self.motion.start()
                    except Exception as e:
                        logger.error(f"Motion controller start failed: {e}", exc_info=True)

            logger.info("⚙️ เริ่ม Message Worker...")
            self._worker_task = asyncio.create_task(self._message_worker())

            if self.youtube:
                try:
                    if hasattr(self.youtube, "start"):
                        self._youtube_task = asyncio.create_task(self.youtube.start())
                        logger.info("✅ YouTube Adapter started (background).")
                except Exception as e:
                    logger.error(f"YouTube adapter start failed (will continue): {e}", exc_info=True)

            discord_token = os.getenv("DISCORD_BOT_TOKEN")
            if not discord_token:
                logger.error("❌ ไม่มี DISCORD_BOT_TOKEN ใน .env — ข้ามการเริ่ม Discord bot")
            else:
                self._discord_task = asyncio.create_task(self._start_discord_safe(discord_token))

            logger.info("✅ ระบบเริ่มทำงานเรียบร้อย — อยู่ในโหมดรันหลัก (กด Ctrl+C เพื่อหยุด)")
            try:
                while True:
                    await asyncio.sleep(1.0)
            except KeyboardInterrupt:
                logger.info("\n⚠️ รับสัญญาณหยุด (Ctrl+C) — กำลังปิดระบบ...")

            await self._shutdown()

        except Exception as e:
            logger.error(f"❌ Start error: {e}", exc_info=True)
            try:
                await self._shutdown()
            except Exception as se:
                logger.error(f"Error during shutdown after start failure: {se}", exc_info=True)

    async def _message_worker(self):
        """Message worker — non-blocking TTS/LLM (heavy ops run in thread)"""
        logger.info("👷 Message worker เริ่มทำงาน")

        if not self.scheduler:
            logger.warning("No scheduler available; message worker will idle.")
            while True:
                try:
                    await asyncio.sleep(1.0)
                except asyncio.CancelledError:
                    break
            return

        while True:
            try:
                message = None
                try:
                    message = await self.scheduler.get_next_message(timeout=1.0)
                except Exception:
                    try:
                        message = await self.scheduler.get_next(timeout=1.0)
                    except Exception:
                        message = None

                if not message:
                    await asyncio.sleep(0.1)
                    continue

                text = getattr(message, "text", "") or ""
                logger.info(f"📨 ประมวลผล: [{getattr(message, 'source', '?')}] {text[:80]}")

                if self.policy and not self.policy.should_respond(text):
                    logger.info("🚫 ข้ามข้อความ (policy)")
                    continue

                # กำหนดอารมณ์เบื้องต้นจากข้อความเพื่อให้ motion สอดคล้องสถานการณ์
                mood, energy, mood_details = _infer_comprehensive_mood(text)
                try:
                    if self.motion:
                        self.motion.set_mood(mood, energy, mood_details)
                        # แทรก emotion ผ่าน hotkey ถ้ามี แมป
                        await self.motion.trigger_emotion(mood)
                except Exception:
                    pass

                # Generate response (if LLM blocking, run in thread)
                answer = None
                if self.llm:
                    try:
                        if asyncio.iscoroutinefunction(getattr(self.llm, "generate_response", None)):
                            answer = await self.llm.generate_response(text)
                        else:
                            answer = await asyncio.to_thread(self.llm.generate_response, text)
                    except Exception as e:
                        logger.error(f"LLM generation failed: {e}", exc_info=True)
                        answer = "ขอโทษ, เกิดข้อผิดพลาดขณะสร้างคำตอบ"
                else:
                    answer = "ขอโทษ ฉันไม่สามารถตอบได้ในขณะนี้"

                logger.info(f"💬 คำตอบ: {str(answer)[:80]}")

                # tell motion we're generating
                if self.motion:
                    try:
                        self.motion.set_generating(True)
                    except Exception:
                        pass

                # TTS synth (run in thread to avoid blocking)
                audio_bytes = None
                if self.tts:
                    try:
                        if hasattr(self.tts, "synthesize"):
                            audio_bytes = await asyncio.to_thread(self.tts.synthesize, str(answer))
                        elif hasattr(self.tts, "speak"):
                            audio_bytes = await asyncio.to_thread(self.tts.speak, str(answer), os.getenv("TTS_VOICE", "default"), "neutral")
                        else:
                            logger.warning("TTS adapter present but no known synthesize method.")
                    except Exception as e:
                        logger.error(f"TTS synth failed: {e}", exc_info=True)
                        audio_bytes = None
                else:
                    logger.warning("TTS not available; skipping audio synth.")

                # Play via discord (non-blocking)
                if self.discord_bot and audio_bytes:
                    try:
                        if self.motion:
                            self.motion.set_speaking(True)
                        # play_audio_bytes is async; it handles voice join internally
                        await self.discord_bot.play_audio_bytes(audio_bytes)
                    except Exception as e:
                        logger.error(f"Discord play error: {e}", exc_info=True)
                    finally:
                        if self.motion:
                            try:
                                self.motion.set_speaking(False)
                            except Exception:
                                pass

                # สร้าง mouth envelope เพื่อส่งผ่าน Motion (รวมกับ body motion เพื่อไม่ชน rate-limit)
                if self.vts and self.motion and audio_bytes and hasattr(self.vts, "compute_mouth_envelope"):
                    try:
                        series, interval_sec = await self.vts.compute_mouth_envelope(audio_bytes)
                        if series:
                            self.motion.set_mouth_envelope(series, interval_sec)
                    except Exception as e:
                        logger.debug(f"Compute mouth envelope failed: {e}")

                if self.motion:
                    try:
                        self.motion.set_generating(False)
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"Message worker error: {e}", exc_info=True)
                await asyncio.sleep(0.5)

    async def _shutdown(self):
        logger.info("🔌 กำลังปิด components...")
        try:
            if self._youtube_task and not self._youtube_task.done():
                self._youtube_task.cancel()
            if self._discord_task and not self._discord_task.done():
                self._discord_task.cancel()
            if self._worker_task and not self._worker_task.done():
                self._worker_task.cancel()
        except Exception:
            pass

        try:
            if self.motion:
                await self.motion.stop()
        except Exception as e:
            logger.debug(f"Motion stop error: {e}")

        try:
            if self.vts:
                await self.vts.disconnect()
        except Exception as e:
            logger.debug(f"VTS disconnect error: {e}")

        try:
            if self.discord_bot and getattr(self.discord_bot, "stop", None):
                await self.discord_bot.stop()
        except Exception as e:
            logger.debug(f"Discord stop error: {e}")

        try:
            if self.youtube and getattr(self.youtube, "stop", None):
                await self.youtube.stop()
        except Exception as e:
            logger.debug(f"YouTube stop error: {e}")

        logger.info("✅ ปิดระบบเรียบร้อย")


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

    # ---------- Enhanced Emotion Detection System ----------
def _is_positive(text: str) -> bool:
    """Detect positive emotions in both Thai and English"""
    t = (text or "").lower()
    # Thai positive keywords
    thai_positive = ["ดี", "เยี่ยม", "สุดยอด", "ขอบคุณ", "โอเค", "ยินดี", "ชอบ", "หัวเราะ", "สนุก", 
                     "มีความสุข", "ดีใจ", "รัก", "น่ารัก", "เก่ง", "เจ๋ง", "วิเศษ", "ยอดเยี่ยม"]
    # English positive keywords
    english_positive = ["good", "great", "excellent", "awesome", "amazing", "wonderful", "fantastic", 
                       "love", "like", "happy", "joy", "smile", "laugh", "fun", "nice", "cool", "perfect"]
    
    for kw in thai_positive + english_positive:
        if kw in t:
            return True
    return False

def _is_negative(text: str) -> bool:
    """Detect negative emotions in both Thai and English"""
    t = (text or "").lower()
    # Thai negative keywords
    thai_negative = ["เศร้า", "เสียใจ", "ไม่ดี", "แย่", "หดหู่", "เหงา", "ร้องไห้", "ผิดหวัง", 
                     "น่าเศร้า", "เสียดาย", "ท้อ", "หมดหวัง"]
    # English negative keywords
    english_negative = ["sad", "bad", "terrible", "awful", "disappointed", "upset", "cry", "crying", 
                       "depressed", "lonely", "hurt", "pain", "sorry", "regret"]
    
    for kw in thai_negative + english_negative:
        if kw in t:
            return True
    return False

def _is_angry(text: str) -> bool:
    """Detect anger in both Thai and English"""
    t = (text or "").lower()
    # Thai angry keywords
    thai_angry = ["โกรธ", "โมโห", "เดือด", "ฉุน", "หงุดหงิด", "รำคาญ", "เบื่อ", "ขุ่นข้อง"]
    # English angry keywords
    english_angry = ["angry", "mad", "furious", "annoyed", "irritated", "frustrated", "rage", 
                    "hate", "damn", "stupid", "idiot", "shut up"]
    
    for kw in thai_angry + english_angry:
        if kw in t:
            return True
    return False

def _is_surprised(text: str) -> bool:
    """Detect surprise in both Thai and English"""
    t = (text or "").lower()
    # Thai surprised keywords
    thai_surprised = ["ตกใจ", "ว้าว", "อึ้ง", "งง", "ประหลาดใจ", "แปลก", "เอ๊ะ", "หา", "โอ้"]
    # English surprised keywords
    english_surprised = ["wow", "omg", "oh my", "surprised", "shocked", "amazing", "incredible", 
                        "unbelievable", "what", "really", "seriously", "no way"]
    
    for kw in thai_surprised + english_surprised:
        if kw in t:
            return True
    return False

def _is_thinking(text: str) -> bool:
    """Detect thinking/contemplative state"""
    t = (text or "").lower()
    # Thai thinking keywords
    thai_thinking = ["คิด", "ใคร่ครวญ", "ตรึกตรอง", "สงสัย", "สำคัญ", "ยาก", "ซับซ้อน", "ลึกซึ้ง"]
    # English thinking keywords
    english_thinking = ["think", "thinking", "wonder", "wondering", "consider", "hmm", "hm", 
                       "complex", "difficult", "interesting", "question", "why", "how"]
    
    for kw in thai_thinking + english_thinking:
        if kw in t:
            return True
    return False

def _detect_energy_level(text: str) -> float:
    """Detect energy level from text intensity markers"""
    t = (text or "").lower()
    
    # High energy indicators
    high_energy = ["มาก", "สุด", "เร็ว", "แรง", "ตื่นเต้น", "กระตือรือร้น", "very", "extremely", 
                   "super", "really", "so", "totally", "absolutely", "!!!", "wow", "amazing"]
    
    # Low energy indicators  
    low_energy = ["นิดหน่อย", "เบาๆ", "ช้า", "ค่อยๆ", "เงียบๆ", "slightly", "little", "bit", 
                  "quietly", "softly", "gently", "maybe", "perhaps"]
    
    # Count exclamation marks and caps for energy
    exclamation_count = t.count('!')
    caps_ratio = sum(1 for c in text if c.isupper()) / max(1, len(text))
    
    energy_score = 0.6  # baseline
    
    # Adjust based on keywords
    for kw in high_energy:
        if kw in t:
            energy_score += 0.15
    
    for kw in low_energy:
        if kw in t:
            energy_score -= 0.15
    
    # Adjust based on punctuation and caps
    energy_score += min(0.2, exclamation_count * 0.1)
    energy_score += min(0.15, caps_ratio * 0.3)
    
    return max(0.2, min(1.0, energy_score))

def _detect_context_mood(text: str) -> str:
    """Detect contextual mood from message content"""
    t = (text or "").lower()
    
    # Question context
    if any(marker in t for marker in ["?", "ไหม", "หรือ", "อะไร", "ทำไม", "อย่างไร", "what", "how", "why", "when", "where"]):
        return "curious"
    
    # Greeting context
    if any(marker in t for marker in ["สวัสดี", "หวัดดี", "ไง", "hello", "hi", "hey", "good morning", "good evening"]):
        return "friendly"
    
    # Compliment context
    if any(marker in t for marker in ["สวย", "หล่อ", "เก่ง", "เจ๋ง", "beautiful", "handsome", "smart", "clever", "good job"]):
        return "pleased"
    
    return "neutral"

def _infer_comprehensive_mood(text: str, response: str = "") -> tuple[str, float, dict]:
    """
    Comprehensive mood inference that considers input text, response context, and situational factors
    Returns: (primary_mood, energy_level, mood_details)
    """
    # Analyze both input and response
    combined_text = f"{text} {response}".strip()
    
    # Primary emotion detection (priority order matters)
    if _is_angry(combined_text):
        primary_mood = "angry"
    elif _is_surprised(combined_text):
        primary_mood = "surprised"  
    elif _is_negative(combined_text):
        primary_mood = "sad"
    elif _is_thinking(combined_text):
        primary_mood = "thinking"
    elif _is_positive(combined_text):
        primary_mood = "happy"
    else:
        # Default to happy with wide smile as specified
        primary_mood = "happy"
    
    # Detect energy level
    energy_level = _detect_energy_level(combined_text)
    
    # Detect contextual mood
    context_mood = _detect_context_mood(text)
    
    # Create detailed mood information
    mood_details = {
        "primary": primary_mood,
        "context": context_mood,
        "energy": energy_level,
        "is_question": "?" in text or any(q in text.lower() for q in ["ไหม", "หรือ", "what", "how", "why"]),
        "is_greeting": any(g in text.lower() for g in ["สวัสดี", "หวัดดี", "hello", "hi"]),
        "intensity_markers": {
            "exclamations": text.count("!"),
            "caps_ratio": sum(1 for c in text if c.isupper()) / max(1, len(text)),
            "length": len(text)
        }
    }
    
    return primary_mood, energy_level, mood_details

# Legacy functions for backward compatibility
def _mood_from_text(text: str) -> str:
    mood, _, _ = _infer_comprehensive_mood(text)
    return mood

def _energy_hint(text: str) -> float:
    _, energy, _ = _infer_comprehensive_mood(text)
    return energy

def _infer_mood(text: str) -> tuple[str, float]:
    mood, energy, _ = _infer_comprehensive_mood(text)
    return mood, energy
