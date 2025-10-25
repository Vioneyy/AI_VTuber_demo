from __future__ import annotations
import asyncio
from typing import Optional
from pathlib import Path

import discord
from discord.ext import commands
# รองรับกรณีไม่มีโมดูล sinks ในบางเวอร์ชันของ discord.py
try:
    from discord.sinks import WaveSink  # type: ignore
except Exception:  # pragma: no cover
    WaveSink = None  # type: ignore

from core.types import Message, Source
from core.config import get_settings
from core.policy import PolicyGuard
from personality.personality import Personality
from audio.rvc_v2 import convert as rvc_convert

class DiscordAdapter:
    def __init__(self, scheduler, llm_client, tts_engine=None, vts_client=None) -> None:
        self.settings = get_settings()
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.scheduler = scheduler
        self.llm_client = llm_client
        self.tts_engine = tts_engine
        self.vts_client = vts_client
        self.policy = PolicyGuard(allow_mild_profanity=True)
        self.persona = Personality.load()

        @self.bot.event
        async def on_ready():
            print(f"Discord bot ready as {self.bot.user}")

        @self.bot.event
        async def on_message(message: discord.Message):
            if message.author == self.bot.user:
                return
            text = message.content or ""
            # ให้คำสั่ง prefix ทำงานเสมอ และไม่ส่งเข้าคิว
            if text.strip().startswith("!"):
                await self.bot.process_commands(message)
                return
            ok, reason = self.policy.check_message_ok(Message(text=text, source=Source.DISCORD, author=str(message.author)))
            if not ok:
                # ข้ามตามนโยบาย
                return
            is_question = any(q in text for q in ("?", "ไหม", "หรือเปล่า", "ได้ไหม"))
            msg = Message(
                text=text,
                source=Source.DISCORD,
                author=str(message.author),
                is_question=is_question,
                priority=self.settings.DISCORD_PRIORITY,
            )
            await self.scheduler.enqueue(msg)

        @self.bot.command(name="join")
        async def join(ctx: commands.Context):
            # เข้าร่วมห้องเสียงเพื่อรับข้อมูล
            if ctx.author.voice and ctx.author.voice.channel:
                channel = ctx.author.voice.channel
                if ctx.voice_client:
                    try:
                        await ctx.send("อยู่ในห้องเสียงแล้ว")
                    except Exception:
                        print("อยู่ในห้องเสียงแล้ว (ไม่สามารถส่งข้อความได้)")
                else:
                    try:
                        await channel.connect()
                        try:
                            await ctx.send("เข้าร่วมห้องเสียงแล้ว พร้อมบันทึกเสียง")
                        except Exception:
                            print("เข้าร่วมห้องเสียงแล้ว พร้อมบันทึกเสียง (ไม่สามารถส่งข้อความได้)")
                    except Exception as e:
                        print(f"เข้าห้องเสียงไม่สำเร็จ: {e}")
                        try:
                            await ctx.send(f"เข้าห้องเสียงไม่สำเร็จ: {e}. ตรวจสิทธิ์ Connect/Speak ของบอทในช่องนี้")
                        except Exception:
                            print("ไม่สามารถส่งข้อความแจ้งข้อผิดพลาดได้")
            else:
                try:
                    await ctx.send("กรุณาเข้าห้องเสียงก่อน")
                except Exception:
                    print("กรุณาเข้าห้องเสียงก่อน (ไม่สามารถส่งข้อความได้)")

        @self.bot.command(name="leave")
        async def leave(ctx: commands.Context):
            if ctx.voice_client:
                try:
                    await ctx.voice_client.disconnect()
                    try:
                        await ctx.send("ออกจากห้องเสียงแล้ว")
                    except Exception:
                        print("ออกจากห้องเสียงแล้ว (ไม่สามารถส่งข้อความได้)")
                except Exception as e:
                    print(f"ออกจากห้องเสียงไม่สำเร็จ: {e}")
                    try:
                        await ctx.send(f"ออกจากห้องเสียงไม่สำเร็จ: {e}")
                    except Exception:
                        print("ไม่สามารถส่งข้อความแจ้งข้อผิดพลาดได้")
            else:
                try:
                    await ctx.send("ไม่ได้อยู่ในห้องเสียง")
                except Exception:
                    print("ไม่ได้อยู่ในห้องเสียง (ไม่สามารถส่งข้อความได้)")

        @self.bot.command(name="stt")
        async def stt(ctx: commands.Context, seconds: Optional[int] = 5):
            """บันทึกเสียงสั้น ๆ และถอดความด้วย Whisper.cpp แล้วตอบผ่าน LLM+TTS"""
            if not self.settings.DISCORD_VOICE_STT_ENABLED:
                await ctx.send("STT ถูกปิดใช้งานใน .env")
                return
            if WaveSink is None:
                await ctx.send("เวอร์ชัน discord.py ปัจจุบันไม่รองรับการบันทึกเสียง (ไม่มี discord.sinks). กรุณาติดตั้ง Py-cord หรือ discord.py ที่มี sinks.")
                return
            if not (ctx.author.voice and ctx.author.voice.channel):
                await ctx.send("กรุณาเข้าห้องเสียงก่อน")
                return
            # เข้าร่วมถ้ายังไม่ได้อยู่
            if not ctx.voice_client:
                await ctx.author.voice.channel.connect()
            vc: discord.VoiceClient = ctx.voice_client  # type: ignore
            sink = WaveSink()

            result_event = asyncio.Event()
            captured_files = {}

            def finished(s: WaveSink, *args):
                nonlocal captured_files
                captured_files = dict(s.audio_files)
                result_event.set()

            vc.start_recording(sink, finished, ctx.channel)
            try:
                await asyncio.sleep(max(1, int(seconds or 5)))
            finally:
                vc.stop_recording()
            await result_event.wait()

            # เลือกไฟล์ของผู้สั่งคำสั่งถ้ามี มิฉะนั้นเลือกไฟล์แรก
            file_path = None
            if captured_files:
                file_path = captured_files.get(ctx.author)
                if not file_path:
                    file_path = list(captured_files.values())[0]
            if not file_path:
                await ctx.send("ไม่พบเสียงที่บันทึก")
                return

            try:
                from audio.stt_whispercpp import WhisperCppSTT
                stt_cli = WhisperCppSTT()
                wav_bytes = Path(file_path).read_bytes()
                text = stt_cli.transcribe_wav_bytes(wav_bytes, language=self.settings.WHISPER_CPP_LANG)
            except Exception as e:
                await ctx.send(f"STT ล้มเหลว: {e}")
                return

            text = (text or "").strip()
            await ctx.send(f"ถอดความ: {text or '(ว่าง)'}")

            # ประมวลผลต่อด้วย LLM และส่งเสียงกลับด้วย TTS หากพร้อม
            try:
                system_prompt = self._load_system_prompt()
                resp = self.llm_client.generate_reply(text, system_prompt, self.persona.data)
                reply_text = self.policy.sanitize_output(resp.text)
                await ctx.send(reply_text or "")

                if self.tts_engine:
                    audio = self.tts_engine.speak(
                        reply_text,
                        voice_id=self.settings.TTS_VOICE_ID,
                        emotion=resp.emotion.value,
                        prosody={"rate": float(self.settings.F5_TTS_SPEED)},
                    )
                    if audio:
                        # Apply RVC processing if enabled
                        if self.settings.ENABLE_RVC:
                            try:
                                audio = rvc_convert(audio, self.settings.VOICE_PRESET)
                            except Exception as e:
                                print(f"RVC conversion failed: {e}")
                        # เล่นในช่องเสียงจาก bytes โดยตรง
                        await self._play_in_voice_bytes(ctx, audio)
            except Exception as e:
                await ctx.send(f"LLM/TTS ล้มเหลว: {e}")

            # ใส่เข้าคิวประมวลผลเหมือนข้อความ (หากยังต้องการ pipeline รวม)
            is_question = any(q in text for q in ("?", "ไหม", "หรือเปล่า", "ได้ไหม"))
            msg = Message(
                text=text,
                source=Source.DISCORD,
                author=str(ctx.author),
                is_question=is_question,
                priority=self.settings.DISCORD_PRIORITY,
            )
            await self.scheduler.enqueue(msg)

        @self.bot.command(name="ask")
        async def ask(ctx: commands.Context, *, text: str):
            """รับข้อความ, ส่งเข้า LLM และส่งเสียงผ่าน TTS กลับ"""
            ok, reason = self.policy.check_message_ok(Message(text=text, source=Source.DISCORD, author=str(ctx.author)))
            if not ok:
                await ctx.send("ข้อความนี้ถูกข้ามตามนโยบาย")
                return
            try:
                system_prompt = self._load_system_prompt()
                resp = self.llm_client.generate_reply(text, system_prompt, self.persona.data)
                reply_text = self.policy.sanitize_output(resp.text)
                await ctx.send(reply_text or "")

                if self.tts_engine:
                    audio = self.tts_engine.speak(
                        reply_text,
                        voice_id=self.settings.TTS_VOICE_ID,
                        emotion=resp.emotion.value,
                        prosody={"rate": float(self.settings.F5_TTS_SPEED)},
                    )
                    if audio:
                        # Apply RVC processing if enabled
                        if self.settings.ENABLE_RVC:
                            try:
                                audio = rvc_convert(audio, self.settings.VOICE_PRESET)
                            except Exception as e:
                                print(f"RVC conversion failed: {e}")
                        # เล่นในช่องเสียงจาก bytes โดยตรง
                        await self._play_in_voice_bytes(ctx, audio)
            except Exception as e:
                await ctx.send(f"LLM/TTS ล้มเหลว: {e}")

        @self.bot.command(name="say")
        async def say(ctx: commands.Context, *, text: str):
            """ให้บอทพูดข้อความที่ระบุโดยตรง (สำหรับทดสอบ TTS)"""
            if not self.tts_engine:
                await ctx.send("TTS engine ไม่พร้อมใช้งาน")
                return
            async with ctx.typing():
                try:
                    audio = self.tts_engine.speak(
                        text,
                        voice_id=self.settings.TTS_VOICE_ID,
                        emotion="neutral",
                        prosody={"rate": float(self.settings.F5_TTS_SPEED)},
                    )
                    if audio:
                        if self.settings.ENABLE_RVC:
                            try:
                                audio = rvc_convert(audio, self.settings.VOICE_PRESET)
                            except Exception as e:
                                print(f"RVC conversion failed: {e}")
                        # เล่นในช่องเสียงจาก bytes โดยตรง
                        await self._play_in_voice_bytes(ctx, audio)
                    else:
                        await ctx.send("ไม่สามารถสร้างเสียงได้")
                except Exception as e:
                    await ctx.send(f"TTS ล้มเหลว: {e}")

        @self.bot.command(name="emotion")
        async def emotion(ctx: commands.Context, emotion_type: str):
            """ทริกเกอร์อีโมทแบบ manual
            
            ใช้งาน: !emotion <ประเภท>
            ประเภทที่รองรับ: thinking, happy, sad, angry, surprised
            """
            if not self.vts_client:
                await ctx.send("VTS client ไม่พร้อมใช้งาน")
                return
                
            valid_emotions = ['thinking', 'happy', 'sad', 'angry', 'surprised']
            emotion_type = emotion_type.lower()
            
            if emotion_type not in valid_emotions:
                await ctx.send(f"อีโมทไม่ถูกต้อง ใช้ได้: {', '.join(valid_emotions)}")
                return
                
            try:
                await self.vts_client.trigger_manual_emotion(emotion_type)
                await ctx.send(f"✅ ทริกเกอร์อีโมท: {emotion_type}")
            except Exception as e:
                await ctx.send(f"ทริกเกอร์อีโมทล้มเหลว: {e}")

        @self.bot.command(name="reset_emotion")
        async def reset_emotion(ctx: commands.Context):
            """รีเซ็ตอีโมทกลับเป็นปกติ"""
            if not self.vts_client:
                await ctx.send("VTS client ไม่พร้อมใช้งาน")
                return
                
            try:
                await self.vts_client.reset_manual_emotion()
                await ctx.send("✅ รีเซ็ตอีโมทเรียบร้อย")
            except Exception as e:
                await ctx.send(f"รีเซ็ตอีโมทล้มเหลว: {e}")

        @self.bot.command(name="thinking")
        async def thinking(ctx: commands.Context):
            """ทริกเกอร์อีโมท 'กำลังคิด' (shortcut)"""
            if self.vts_client:
                try:
                    await self.vts_client.trigger_manual_emotion('thinking')
                    await ctx.send("🤔 กำลังคิด...")
                except Exception as e:
                    await ctx.send(f"ล้มเหลว: {e}")

        @self.bot.command(name="happy")
        async def happy(ctx: commands.Context):
            """ทริกเกอร์อีโมท 'มีความสุข' (shortcut)"""
            if self.vts_client:
                try:
                    await self.vts_client.trigger_manual_emotion('happy')
                    await ctx.send("😊 มีความสุข!")
                except Exception as e:
                    await ctx.send(f"ล้มเหลว: {e}")

        @self.bot.command(name="sad")
        async def sad(ctx: commands.Context):
            """ทริกเกอร์อีโมท 'เศร้า' (shortcut)"""
            if self.vts_client:
                try:
                    await self.vts_client.trigger_manual_emotion('sad')
                    await ctx.send("😢 เศร้า...")
                except Exception as e:
                    await ctx.send(f"ล้มเหลว: {e}")

    def _load_system_prompt(self) -> str:
        # โหลด system prompt เดียวกับ main.py
        try:
            root = Path(__file__).resolve().parents[1]
            p = root / "llm" / "prompts" / "system_prompt.txt"
            return p.read_text(encoding="utf-8") if p.exists() else ""
        except Exception:
            return ""

    async def _play_in_voice(self, ctx: commands.Context, wav_path: str):
        """เล่นไฟล์ WAV ในช่องเสียงด้วย ffmpeg หากพร้อม"""
        import shutil as _shutil
        ffmpeg = _shutil.which("ffmpeg")
        if not ffmpeg:
            await ctx.send("ไม่พบ ffmpeg ใน PATH จึงไม่สามารถเล่นเสียงในช่องได้")
            return
        if not (ctx.author.voice and ctx.author.voice.channel):
            await ctx.send("กรุณาเข้าห้องเสียงก่อน")
            return
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        vc: discord.VoiceClient = ctx.voice_client  # type: ignore
        if vc.is_playing():
            vc.stop()
        source = discord.FFmpegPCMAudio(wav_path, executable=ffmpeg)
        vc.play(source)
        # หากมี VTS client ให้ลิปซิงก์ตามไฟล์เสียงแบบ async
        try:
            vts_client = getattr(self, "vts_client", None)
            if vts_client:
                asyncio.create_task(vts_client.lipsync_wav(wav_path))
        except Exception:
            pass

    async def _play_in_voice_bytes(self, ctx: commands.Context, wav_bytes: bytes):
        """เล่น WAV bytes ในช่องเสียงโดยไม่ต้องบันทึกไฟล์ ด้วย ffmpeg pipe"""
        import shutil as _shutil
        ffmpeg = _shutil.which("ffmpeg")
        if not ffmpeg:
            await ctx.send("ไม่พบ ffmpeg ใน PATH จึงไม่สามารถเล่นเสียงในช่องได้")
            return
        if not (ctx.author.voice and ctx.author.voice.channel):
            await ctx.send("กรุณาเข้าห้องเสียงก่อน")
            return
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        vc: discord.VoiceClient = ctx.voice_client  # type: ignore
        if vc.is_playing():
            vc.stop()
        # ใช้ ffmpeg อ่านจาก stdin แก่วะ แปลงเป็น PCM ให้ Discord
        source = discord.FFmpegPCMAudio(source='pipe:0', executable=ffmpeg, pipe=True)
        vc.play(source)
        # เขียน bytes ลง stdin ของ ffmpeg ใน thread เพื่อไม่บล็อก
        def _writer():
            try:
                if source._process and source._process.stdin:
                    source._process.stdin.write(wav_bytes)
                    try:
                        source._process.stdin.flush()
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                try:
                    if source._process and source._process.stdin:
                        source._process.stdin.close()
                except Exception:
                    pass
        try:
            await asyncio.to_thread(_writer)
        except Exception:
            pass
        # ลิปซิงก์พร้อมกันหากมี VTS client
        try:
            vts_client = getattr(self, "vts_client", None)
            if vts_client:
                asyncio.create_task(vts_client.lipsync_bytes(wav_bytes))
        except Exception:
            pass

    def run(self):
        token = self.settings.DISCORD_BOT_TOKEN
        if not token:
            print("DISCORD_BOT_TOKEN ไม่ถูกตั้งค่าใน .env")
            return
        self.bot.run(token)