"""
Discord Bot Adapter
"""
import discord
from discord.ext import commands
import asyncio
import logging
import os
import tempfile
import subprocess
from io import BytesIO

logger = logging.getLogger(__name__)

class DiscordBot(commands.Bot):
    def __init__(self, orchestrator):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        super().__init__(command_prefix="!", intents=intents)
        
        self.orchestrator = orchestrator
        self.voice_client = None
        self.is_recording = False
        
        self._register_commands()
        
        logger.info("✅ Discord Bot สร้างเสร็จแล้ว")

    def _register_commands(self):
        """ลงทะเบียนคำสั่งทั้งหมด"""
        
        @self.command(name="join")
        async def join(ctx):
            """เข้าช่องเสียง"""
            if ctx.author.voice is None:
                await ctx.send("❌ คุณต้องอยู่ในช่องเสียงก่อน!")
                return
            
            channel = ctx.author.voice.channel
            
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.move_to(channel)
                await ctx.send(f"✅ ย้ายไป {channel.name} แล้ว~")
            else:
                self.voice_client = await channel.connect()
                await ctx.send(f"✅ เข้า {channel.name} แล้วนะ!")
            
            logger.info(f"Joined voice channel: {channel.name}")

        @self.command(name="leave")
        async def leave(ctx):
            """ออกจากช่องเสียง"""
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect()
                self.voice_client = None
                await ctx.send("👋 บ๊ายบาย~")
                logger.info("Left voice channel")
            else:
                await ctx.send("❌ ไม่ได้อยู่ในช่องเสียงอยู่แล้ว")

        @self.command(name="say")
        async def say(ctx, *, text: str):
            """พูดข้อความที่กำหนด"""
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ ต้อง !join ก่อนนะ")
                return
            
            await ctx.send(f"💬 กำลังพูด: {text[:50]}...")
            
            try:
                logger.info(f"[SAY] สังเคราะห์เสียง: {text}")
                audio_bytes = await self._synthesize_speech(text)
                
                if not audio_bytes:
                    await ctx.send("❌ ไม่สามารถสังเคราะห์เสียงได้")
                    return
                
                await self._play_audio_and_lipsync(audio_bytes, ctx)
                
                logger.info("[SAY] เสร็จสิ้น")
                
            except Exception as e:
                logger.error(f"Say command error: {e}", exc_info=True)
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

        @self.command(name="ask")
        async def ask(ctx, *, question: str):
            """ถามคำถามแล้วให้ AI ตอบ"""
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ ต้อง !join ก่อนนะ")
                return
            
            await ctx.send(f"🤔 คำถาม: {question[:50]}...")
            
            try:
                logger.info(f"[ASK] คำถาม: {question}")
                answer = self.orchestrator.llm.generate_response(question)
                
                await ctx.send(f"💡 ตอบ: {answer}")
                
                audio_bytes = await self._synthesize_speech(answer)
                await self._play_audio_and_lipsync(audio_bytes, ctx)
                
            except Exception as e:
                logger.error(f"Ask command error: {e}", exc_info=True)
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

        @self.command(name="test_voice")
        async def test_voice(ctx, seconds: int = 5):
            """ทดสอบ Voice-to-Voice"""
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ ต้อง !join ก่อนนะ")
                return
            
            await ctx.send(f"🎙️ บันทึกเสียง {seconds} วินาที... เริ่ม!")
            
            try:
                logger.info(f"[TEST_VOICE] บันทึกเสียง {seconds}s")
                audio_file = await self._record_voice(seconds)
                
                if not audio_file:
                    await ctx.send("❌ ไม่สามารถบันทึกเสียงได้")
                    return
                
                await ctx.send("✅ บันทึกเสร็จแล้ว กำลังถอดความ...")
                
                text = await self._transcribe_audio(audio_file)
                
                if not text:
                    await ctx.send("❌ ไม่สามารถถอดเสียงได้")
                    return
                
                await ctx.send(f"📝 คุณพูดว่า: **{text}**")
                
                logger.info(f"[TEST_VOICE] LLM กำลังคิด: {text}")
                answer = self.orchestrator.llm.generate_response(text)
                
                await ctx.send(f"💬 ตอบ: {answer}")
                
                audio_bytes = await self._synthesize_speech(answer)
                await self._play_audio_and_lipsync(audio_bytes, ctx)
                
                logger.info("[TEST_VOICE] เสร็จสมบูรณ์")
                await ctx.send("✅ ทดสอบเสร็จสิ้น!")
                
            except Exception as e:
                logger.error(f"Test voice error: {e}", exc_info=True)
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

        @self.command(name="stt")
        async def stt(ctx, seconds: int = 5):
            """บันทึกเสียงแล้วถอดความ"""
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ ต้อง !join ก่อนนะ")
                return
            
            await ctx.send(f"🎙️ บันทึก {seconds} วินาที...")
            
            try:
                audio_file = await self._record_voice(seconds)
                if audio_file:
                    text = await self._transcribe_audio(audio_file)
                    if text:
                        await ctx.send(f"📝 ถอดความได้: {text}")
                    else:
                        await ctx.send("❌ ถอดเสียงไม่สำเร็จ")
                else:
                    await ctx.send("❌ บันทึกเสียงไม่สำเร็จ")
            except Exception as e:
                await ctx.send(f"❌ Error: {e}")

        @self.command(name="ttsref")
        async def ttsref(ctx, mode: str):
            """เปิด/ปิด TTS reference"""
            if mode.lower() not in ["on", "off"]:
                await ctx.send("❌ ใช้: !ttsref on หรือ !ttsref off")
                return
            
            use_ref = (mode.lower() == "on")
            self.orchestrator.tts.set_use_reference(use_ref)
            await ctx.send(f"✅ TTS Reference: {'เปิด' if use_ref else 'ปิด'}")

        @self.command(name="vtsstatus")
        async def vtsstatus(ctx):
            """ดูสถานะ VTS"""
            vts = self.orchestrator.vts
            status = "🟢 เชื่อมต่อ" if vts.ws and not vts.ws.closed else "🔴 ไม่ได้เชื่อมต่อ"
            await ctx.send(f"**VTS Status:** {status}")

        @self.command(name="emotion")
        async def emotion(ctx, emo: str):
            """Trigger emotion"""
            await self.orchestrator.motion.trigger_emotion(emo)
            await ctx.send(f"💫 อารมณ์: {emo}")

        @self.command(name="persona")
        async def persona(ctx, name: str = None):
            """เปลี่ยนหรือดูบุคลิก AI"""
            if not name:
                from src.personality.persona import get_available_personas
                personas = get_available_personas()
                await ctx.send(f"🎭 **Persona ที่มี**: {', '.join(personas)}\nใช้: `!persona <name>`")
                return
            
            try:
                self.orchestrator.llm.set_persona(name)
                await ctx.send(f"✅ เปลี่ยนเป็นบุคลิก: **{name}**")
            except Exception as e:
                await ctx.send(f"❌ ไม่พบบุคลิก '{name}' ลองใช้ `!persona` เพื่อดูรายชื่อ")

    async def _synthesize_speech(self, text: str) -> bytes:
        """สังเคราะห์เสียงจากข้อความ"""
        try:
            self.orchestrator.motion.set_generating(True)

            logger.info(f"🎤 TTS เริ่มสังเคราะห์: {text[:50]}...")
            audio_bytes = self.orchestrator.tts.synthesize(text)

            self.orchestrator.motion.set_generating(False)

            if not audio_bytes:
                logger.error("TTS ไม่ได้คืนค่า audio bytes")
                return None

            logger.info(f"✅ TTS เสร็จ: {len(audio_bytes)} bytes")
            return audio_bytes

        except Exception as e:
            logger.error(f"Synthesize error: {e}", exc_info=True)
            self.orchestrator.motion.set_generating(False)
            return None

    async def _play_audio_and_lipsync(self, audio_bytes: bytes, ctx):
        """เล่นเสียงใน Discord + ลิปซิงก์ VTS"""
        if not audio_bytes:
            logger.error("ไม่มี audio bytes")
            return
        
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                temp_audio.write(audio_bytes)
                temp_path = temp_audio.name
            
            logger.info(f"📂 บันทึกเสียงชั่วคราว: {temp_path}")
            
            lipsync_task = asyncio.create_task(
                self.orchestrator.vts.lipsync_bytes(audio_bytes)
            )
            
            if self.voice_client and self.voice_client.is_connected():
                # แจ้ง MotionController ว่ากำลังพูด เพื่อ bias ท่าทางให้มีชีวิตชีวา
                try:
                    self.orchestrator.motion.set_speaking(True)
                except Exception:
                    pass

                # ตรวจสอบ ffmpeg พร้อมใช้งาน
                ffmpeg_ok = True
                try:
                    subprocess.run(["ffmpeg", "-version"], capture_output=True)
                except Exception:
                    ffmpeg_ok = False
                    logger.warning("⚠️ ไม่พบ ffmpeg ใน PATH — พยายามเล่นต่อ แต่หากเล่นไม่ออกโปรดติดตั้ง ffmpeg")

                audio_source = discord.FFmpegPCMAudio(
                    temp_path,
                    options="-filter:a 'volume=1.0'"
                )
                
                self.voice_client.play(
                    audio_source,
                    after=lambda e: logger.info(f"เล่นเสียงเสร็จ: {e}" if e else "เล่นเสียงเสร็จ")
                )
                # ยืนยันว่าเริ่มเล่นจริงภายใน 2 วินาที
                started = False
                for _ in range(20):
                    if self.voice_client.is_playing():
                        started = True
                        break
                    await asyncio.sleep(0.1)
                if not started:
                    logger.error("❌ ไม่สามารถเริ่มเล่นเสียงใน Discord — ตรวจสอบ ffmpeg/สิทธิ์บอท/การเชื่อมต่อช่องเสียง")
                    try:
                        await ctx.send("❌ เล่นเสียงไม่สำเร็จ (ตรวจสอบ ffmpeg/เชื่อมต่อบอท)")
                    except Exception:
                        pass

                while self.voice_client.is_playing():
                    await asyncio.sleep(0.1)
                
                logger.info("✅ เล่นเสียงใน Discord เสร็จ")
                # ปิดสถานะกำลังพูด
                try:
                    self.orchestrator.motion.set_speaking(False)
                except Exception:
                    pass
            else:
                logger.warning("ไม่ได้เชื่อมต่อช่องเสียง")
            
            await lipsync_task
            
            try:
                os.remove(temp_path)
            except:
                pass
                
        except Exception as e:
            logger.error(f"Play audio error: {e}", exc_info=True)

    async def _record_voice(self, duration: int) -> str:
        """บันทึกเสียงจากช่องเสียง Discord"""
        try:
            from discord import sinks
            
            output_file = tempfile.mktemp(suffix=".wav")
            
            self.voice_client.start_recording(
                sinks.WaveSink(),
                self._recording_callback,
                output_file
            )
            
            self.is_recording = True
            await asyncio.sleep(duration)
            
            self.voice_client.stop_recording()
            self.is_recording = False
            
            await asyncio.sleep(0.5)
            
            return output_file
            
        except ImportError:
            logger.error("ต้องติดตั้ง py-cord สำหรับ recording: pip install py-cord")
            return None
        except Exception as e:
            logger.error(f"Recording error: {e}", exc_info=True)
            return None

    def _recording_callback(self, sink, output_file):
        """Callback เมื่อบันทึกเสร็จ"""
        logger.info(f"Recording saved: {output_file}")

    async def _transcribe_audio(self, audio_file: str) -> str:
        """ถอดเสียงเป็นข้อความด้วย whisper.cpp"""
        try:
            whisper_bin = os.getenv("WHISPER_CPP_BIN_PATH", "whisper.cpp/build/bin/main")
            whisper_model = os.getenv("WHISPER_CPP_MODEL_PATH", "whisper.cpp/models/ggml-base.bin")
            lang = os.getenv("WHISPER_CPP_LANG", "th")
            
            if not os.path.exists(whisper_bin):
                logger.error(f"ไม่พบ whisper.cpp: {whisper_bin}")
                return None
            
            cmd = [
                whisper_bin,
                "-m", whisper_model,
                "-l", lang,
                "-f", audio_file,
                "--no-timestamps"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                text = result.stdout.strip()
                logger.info(f"✅ STT: {text}")
                return text
            else:
                logger.error(f"Whisper error: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Transcribe error: {e}", exc_info=True)
            return None

    async def start_bot(self, token: str):
        """เริ่ม Discord bot"""
        try:
            await self.start(token)
        except Exception as e:
            logger.error(f"Discord bot error: {e}", exc_info=True)