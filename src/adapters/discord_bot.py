"""
Discord Bot Adapter (Fixed Audio System)
"""
import discord
from discord.ext import commands
import asyncio
import logging
import os
import tempfile
import subprocess
from io import BytesIO
import time

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
        self.current_audio_source = None
        
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
                try:
                    self.voice_client = await channel.connect()
                    await ctx.send(f"✅ เข้า {channel.name} แล้วนะ!")
                    logger.info(f"Joined voice channel: {channel.name}")
                except Exception as e:
                    await ctx.send(f"❌ ไม่สามารถเข้าช่องเสียงได้: {e}")
                    logger.error(f"Join error: {e}")
            
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
            
            if len(text) > 200:
                await ctx.send("❌ ข้อความยาวเกินไป (จำกัด 200 ตัวอักษร)")
                return
            
            await ctx.send(f"💬 กำลังพูด: {text[:50]}...")
            
            try:
                logger.info(f"[SAY] สังเคราะห์เสียง: {text}")
                
                # สังเคราะห์เสียง
                audio_bytes = await self._synthesize_speech(text)
                
                if not audio_bytes:
                    await ctx.send("❌ ไม่สามารถสังเคราะห์เสียงได้")
                    return
                
                # เล่นเสียง
                success = await self._play_audio(audio_bytes, ctx)
                
                if success:
                    await ctx.send("✅ พูดเสร็จแล้ว!")
                    logger.info("[SAY] เสร็จสิ้น")
                else:
                    await ctx.send("❌ ไม่สามารถเล่นเสียงได้")
                
            except Exception as e:
                logger.error(f"Say command error: {e}", exc_info=True)
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

        @self.command(name="ask")
        async def ask(ctx, *, question: str):
            """ถามคำถามแล้วให้ AI ตอบ"""
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ ต้อง !join ก่อนนะ")
                return
            
            if len(question) > 200:
                await ctx.send("❌ คำถามยาวเกินไป (จำกัด 200 ตัวอักษร)")
                return
            
            await ctx.send(f"🤔 คำถาม: {question[:50]}...")
            
            try:
                logger.info(f"[ASK] คำถาม: {question}")
                
                # ส่งให้ LLM ตอบ
                answer = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    self.orchestrator.llm.generate_response, 
                    question
                )
                
                if not answer:
                    await ctx.send("❌ ไม่ได้รับคำตอบจาก AI")
                    return
                
                await ctx.send(f"💡 ตอบ: {answer}")
                
                # สังเคราะห์และเล่นเสียง
                audio_bytes = await self._synthesize_speech(answer)
                if audio_bytes:
                    success = await self._play_audio(audio_bytes, ctx)
                    if not success:
                        await ctx.send("⚠️ พูดไม่สำเร็จแต่ส่งข้อความแล้ว")
                else:
                    await ctx.send("❌ สังเคราะห์เสียงไม่สำเร็จ")
                
            except Exception as e:
                logger.error(f"Ask command error: {e}", exc_info=True)
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

        @self.command(name="test")
        async def test(ctx):
            """ทดสอบระบบเสียง"""
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ ต้อง !join ก่อนนะ")
                return
            
            await ctx.send("🔊 ทดสอบระบบเสียง...")
            
            try:
                test_text = "สวัสดีค่ะ นี่คือการทดสอบระบบเสียง"
                audio_bytes = await self._synthesize_speech(test_text)
                
                if audio_bytes:
                    success = await self._play_audio(audio_bytes, ctx)
                    if success:
                        await ctx.send("✅ ทดสอบเสียงสำเร็จ!")
                    else:
                        await ctx.send("❌ เล่นเสียงไม่สำเร็จ")
                else:
                    await ctx.send("❌ สังเคราะห์เสียงไม่สำเร็จ")
                    
            except Exception as e:
                logger.error(f"Test error: {e}", exc_info=True)
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

        @self.command(name="motion")
        async def motion(ctx):
            """ทดสอบการเคลื่อนไหว"""
            try:
                await self.orchestrator.motion.trigger_emotion("happy")
                await ctx.send("💫 ทดสอบการเคลื่อนไหวแล้ว")
            except Exception as e:
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")

    async def _synthesize_speech(self, text: str) -> bytes:
        """สังเคราะห์เสียงจากข้อความ"""
        try:
            # แจ้งระบบว่ากำลังสร้างเสียง
            self.orchestrator.motion.set_generating(True)

            logger.info(f"🎤 TTS เริ่มสังเคราะห์: {text[:50]}...")
            
            # เรียก TTS (รันใน thread แยกเพื่อไม่บล็อก event loop)
            audio_bytes = await asyncio.get_event_loop().run_in_executor(
                None,
                self.orchestrator.tts.synthesize,
                text
            )

            self.orchestrator.motion.set_generating(False)

            if not audio_bytes:
                logger.error("TTS ไม่ได้คืนค่า audio bytes")
                return None

            # ตรวจสอบว่า audio_bytes ไม่ว่าง
            if len(audio_bytes) < 100:
                logger.error(f"Audio bytes สั้นเกินไป: {len(audio_bytes)} bytes")
                return None

            logger.info(f"✅ TTS เสร็จ: {len(audio_bytes)} bytes")
            return audio_bytes

        except Exception as e:
            logger.error(f"Synthesize error: {e}", exc_info=True)
            self.orchestrator.motion.set_generating(False)
            return None

    async def _play_audio(self, audio_bytes: bytes, ctx) -> bool:
        """เล่นเสียงใน Discord"""
        if not audio_bytes or len(audio_bytes) < 100:
            logger.error("ไม่มี audio bytes ที่ใช้ได้")
            return False
        
        temp_path = None
        
        try:
            # สร้างไฟล์ชั่วคราว
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                temp_audio.write(audio_bytes)
                temp_path = temp_audio.name
            
            logger.info(f"📂 บันทึกเสียงชั่วคราว: {temp_path} ({len(audio_bytes)} bytes)")
            
            # ตรวจสอบ ffmpeg
            if not await self._check_ffmpeg():
                await ctx.send("❌ ไม่พบ ffmpeg ในระบบ โปรดติดตั้ง ffmpeg")
                return False
            
            # แจ้ง MotionController ว่ากำลังพูด
            self.orchestrator.motion.set_speaking(True)
            # เริ่มลิปซิงก์ควบคู่ไปกับการเล่นเสียง
            lipsync_task = None
            try:
                if self.orchestrator.vts and self.orchestrator.vts._is_connected():
                    self.orchestrator.motion.set_lipsyncing(True)
                    lipsync_task = asyncio.create_task(self.orchestrator.vts.lipsync_bytes(audio_bytes))
            except Exception:
                lipsync_task = None
            
            # สร้าง audio source
            audio_source = discord.FFmpegPCMAudio(
                temp_path,
                before_options="-loglevel quiet",
                options="-filter:a volume=1.0"
            )
            
            # เล่นเสียง
            play_success = await self._play_audio_source(audio_source, ctx)
            
            # ปิดสถานะกำลังพูด
            self.orchestrator.motion.set_speaking(False)
            # รอให้ลิปซิงก์เสร็จ และปิดสถานะลิปซิงก์
            if lipsync_task:
                try:
                    await lipsync_task
                except Exception:
                    pass
            try:
                self.orchestrator.motion.set_lipsyncing(False)
            except Exception:
                pass
            
            return play_success
            
        except Exception as e:
            logger.error(f"Play audio error: {e}", exc_info=True)
            self.orchestrator.motion.set_speaking(False)
            return False
        finally:
            # ลบไฟล์ชั่วคราว
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    logger.warning(f"ไม่สามารถลบไฟล์ชั่วคราว: {e}")

    async def _check_ffmpeg(self) -> bool:
        """ตรวจสอบว่า ffmpeg พร้อมใช้งาน"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], 
                capture_output=True, 
                text=True,
                timeout=5.0
            )
            if result.returncode == 0:
                logger.info("✅ FFmpeg พร้อมใช้งาน")
                return True
            else:
                logger.error("❌ FFmpeg ไม่พร้อมใช้งาน")
                return False
        except FileNotFoundError:
            logger.error("❌ ไม่พบ FFmpeg ใน PATH")
            return False
        except Exception as e:
            logger.error(f"❌ ตรวจสอบ FFmpeg ไม่สำเร็จ: {e}")
            return False

    async def _play_audio_source(self, audio_source, ctx) -> bool:
        """เล่น audio source และตรวจสอบว่ามีเสียงออกมาจริงๆ"""
        if not self.voice_client or not self.voice_client.is_connected():
            logger.error("Voice client ไม่ได้เชื่อมต่อ")
            await ctx.send("❌ ไม่ได้เชื่อมต่อช่องเสียง")
            return False
        
        try:
            # เริ่มเล่น
            self.voice_client.play(audio_source)
            
            # รอให้เริ่มเล่นจริงๆ
            start_time = time.time()
            while not self.voice_client.is_playing():
                if time.time() - start_time > 5.0:
                    logger.error("Timeout รอการเริ่มเล่นเสียง")
                    await ctx.send("❌ ไม่สามารถเริ่มเล่นเสียงได้ (timeout)")
                    return False
                await asyncio.sleep(0.1)
            
            logger.info("🔊 เริ่มเล่นเสียงแล้ว")
            await ctx.send("🔊 กำลังพูด...")
            
            # รอให้เล่นเสร็จ
            while self.voice_client.is_playing():
                await asyncio.sleep(0.1)
            
            logger.info("✅ เล่นเสียงเสร็จสิ้น")
            return True
            
        except Exception as e:
            logger.error(f"Audio playback error: {e}", exc_info=True)
            await ctx.send(f"❌ เกิดข้อผิดพลาดขณะเล่นเสียง: {e}")
            return False

    async def start_bot(self, token: str):
        """เริ่ม Discord bot"""
        try:
            logger.info("🚀 กำลังเริ่ม Discord bot...")
            await self.start(token)
        except Exception as e:
            logger.error(f"Discord bot error: {e}", exc_info=True)