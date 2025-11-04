"""
Discord Bot สำหรับ AI VTuber (แก้ทุกปัญหา)
ตำแหน่ง: src/adapters/discord_bot.py
"""

import asyncio
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio, PCMVolumeTransformer
from typing import Optional
import os
import tempfile

import sys
sys.path.append('..')
from core.config import config
from core.scheduler import scheduler, Message, MessageSource, MessagePriority
from audio.stt_handler import stt_handler

class DiscordBot(commands.Bot):
    """Discord Bot หลัก"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        intents.guild_messages = True
        
        super().__init__(
            command_prefix=config.discord.command_prefix,
            intents=intents,
            help_command=None
        )
        
        self.voice_client: Optional[discord.VoiceClient] = None
        self.is_ready = False
        self.joining = False
        self._actual_channel = None  # เก็บห้องจริงๆ
        self._has_ever_connected = False  # เคยเชื่อมต่อห้องเสียงจริงหรือยัง
        # กด suppress event ตอนบูต เพื่อไม่ให้ spam disconnect
        import time
        self._suppress_voice_events_until = time.time() + 5.0
        
        self.add_commands()

    def get_current_voice_client(self, guild: discord.Guild) -> Optional[discord.VoiceClient]:
        """ดึง VoiceClient ปัจจุบันจาก self หรือ guild และซิงค์สถานะภายใน
        คืนค่า VoiceClient ที่เชื่อมต่อแล้ว หรือ None หากยังไม่พร้อม
        """
        vc = self.voice_client
        # 1) ใช้ self.voice_client หากพร้อม
        if vc and vc.is_connected():
            return vc
        # 2) ใช้ guild.voice_client หากพร้อม
        try:
            gvc = guild.voice_client
            if gvc and gvc.is_connected():
                self.voice_client = gvc
                try:
                    self._actual_channel = gvc.channel
                    self._has_ever_connected = True
                except Exception:
                    pass
                return gvc
        except Exception:
            pass
        # 3) หาในรายการ voice_clients ของบอท
        try:
            from discord.utils import get as dget
            existing = dget(self.voice_clients, guild=guild)
            if existing and existing.is_connected():
                self.voice_client = existing
                try:
                    self._actual_channel = existing.channel
                    self._has_ever_connected = True
                except Exception:
                    pass
                return existing
        except Exception:
            pass
        # 4) ถ้าบอทอยู่ในห้อง (จาก Member.voice) ให้รอสั้นๆ เพื่อให้ VC โผล่
        try:
            bot_vs = guild.me.voice
        except Exception:
            bot_vs = None
        if bot_vs and bot_vs.channel:
            # ฟังก์ชันนี้เป็น sync จึงไม่รอจริง
            # ผู้เรียกควรใช้ await_current_voice_client หากต้องการรอให้ VC โผล่
            return None

    async def await_current_voice_client(self, guild: discord.Guild, wait_seconds: float = 2.0) -> Optional[discord.VoiceClient]:
        """รอให้ VoiceClient ปรากฏและซิงค์สถานะ ภายในช่วง wait_seconds"""
        # ลองดึงก่อนหนึ่งครั้ง
        vc = self.get_current_voice_client(guild)
        if vc:
            return vc
        # ถ้าบอทอยู่ในห้อง ให้รอ VC
        try:
            bot_vs = guild.me.voice
        except Exception:
            bot_vs = None
        if not (bot_vs and bot_vs.channel):
            return None
        # poll
        tries = max(1, int(wait_seconds / 0.1))
        from discord.utils import get as dget
        for _ in range(tries):
            try:
                gvc = guild.voice_client
                if gvc and gvc.is_connected():
                    self.voice_client = gvc
                    try:
                        self._actual_channel = gvc.channel
                        self._has_ever_connected = True
                    except Exception:
                        pass
                    return gvc
                existing = dget(self.voice_clients, guild=guild)
                if existing and existing.is_connected():
                    self.voice_client = existing
                    try:
                        self._actual_channel = existing.channel
                        self._has_ever_connected = True
                    except Exception:
                        pass
                    return existing
            except Exception:
                pass
            await asyncio.sleep(0.1)
        return None

    async def ensure_voice_client(self, guild: discord.Guild, wait_seconds: float = 2.0) -> Optional[discord.VoiceClient]:
        """พยายามให้มี VoiceClient พร้อมใช้งานด้วยการดึง/รอ/เชื่อม (กรณีอยู่ในห้องแล้ว)
        - ดึงจาก self/guild
        - รอสั้นๆ หากบอทอยู่ในห้องแต่ VC ยังไม่มาทัน
        - เชื่อมเข้าห้องของบอทเอง หากยังไม่มี VC แต่รายงานว่าอยู่ในห้อง
        """
        vc = self.get_current_voice_client(guild)
        if vc:
            return vc
        vc = await self.await_current_voice_client(guild, wait_seconds=wait_seconds)
        if vc:
            return vc
        # ถ้ายังไม่มี vc แต่บอทอยู่ในห้อง ลองเชื่อมเข้าห้องนั้นอีกครั้ง (จะจับ Already connected)
        try:
            bot_vs = guild.me.voice
        except Exception:
            bot_vs = None
        if bot_vs and bot_vs.channel:
            try:
                self.voice_client = await bot_vs.channel.connect(timeout=5.0, reconnect=True)
                try:
                    self._actual_channel = bot_vs.channel
                    self._has_ever_connected = True
                except Exception:
                    pass
                return self.voice_client
            except Exception as e:
                if "Already connected" in str(e):
                    # ดึงจาก guild อีกครั้ง
                    try:
                        gvc = guild.voice_client
                        if gvc and gvc.is_connected():
                            self.voice_client = gvc
                            try:
                                self._actual_channel = gvc.channel
                                self._has_ever_connected = True
                            except Exception:
                                pass
                            return gvc
                    except Exception:
                        pass
                # อื่นๆ ปล่อยผ่าน
        return None
    
    def add_commands(self):
        """เพิ่มคำสั่งต่างๆ"""
        
        @self.command(name='join')
        async def join(ctx):
            """เข้าห้องเสียง"""
            if self.joining:
                await ctx.send("⏳ กำลังเชื่อมต่อ... รอสักครู่นะ")
                return
            
            try:
                self.joining = True
                
                if not ctx.author.voice:
                    await ctx.send("❌ คุณต้องอยู่ในห้องเสียงก่อน!")
                    return
                
                channel = ctx.author.voice.channel
                guild = ctx.guild
                # ตรวจสิทธิ์การเชื่อมต่อ/พูด
                perms = channel.permissions_for(guild.me)
                if not perms.connect or not perms.speak:
                    await ctx.send("❌ บอทไม่มีสิทธิ์ Connect/Speak ในห้องนี้")
                    return
                
                # ตรวจสอบว่ามี voice client และอยู่ห้องเดียวกัน
                # ใช้ voice_client จาก guild ถ้ามี เพื่อกัน state หลุด
                if guild.voice_client:
                    self.voice_client = guild.voice_client
                
                if self.voice_client and self.voice_client.is_connected():
                    if self._actual_channel == channel:
                        await ctx.send("✅ หนูอยู่ห้องนี้อยู่แล้วนะ~")
                        return
                    
                    # ย้ายห้อง
                    try:
                        await self.voice_client.move_to(channel)
                        self._actual_channel = channel
                        await ctx.send(f"✅ ย้ายมาห้อง {channel.name} แล้วจ้า~")
                        return
                    except:
                        # ถ้าย้ายไม่ได้ ให้ disconnect แล้วเชื่อมใหม่
                        await self.voice_client.disconnect(force=True)
                        self.voice_client = None
                        self._actual_channel = None
                        await asyncio.sleep(0.5)
                
                # เชื่อมต่อใหม่
                self.voice_client = await channel.connect(timeout=10.0, reconnect=True)
                self._actual_channel = channel
                
                # รอให้สถานะเชื่อมต่อจริง (บางครั้ง lib คืน VoiceClient ก่อน ready)
                ok, waited = False, 0.0
                for _ in range(30):  # ขยายระยะรอเล็กน้อย
                    vc = guild.voice_client
                    # ยอมรับสองกรณี: guild.voice_client พร้อม หรือ self.voice_client พร้อม
                    if (vc and vc.is_connected()) or (self.voice_client and self.voice_client.is_connected()):
                        # หาก guild.voice_client มี ให้ใช้เป็น source หลักเพื่อกัน state หลุด
                        if vc and vc.is_connected():
                            self.voice_client = vc
                        ok = True
                        break
                    await asyncio.sleep(0.1)
                    waited += 0.1
                
                if ok:
                    await ctx.send(f"✅ เข้าห้อง {channel.name} แล้วจ้า~")
                    print(f"✅ เข้าห้องเสียง: {channel.name} (ready in {waited:.1f}s)")
                    # เคยเชื่อมต่อสำเร็จแล้ว
                    self._has_ever_connected = True
                else:
                    await ctx.send("⚠️ เชื่อมต่อยังไม่เสถียร ลอง !join อีกครั้ง หรือเปลี่ยนห้อง")
                    print("⚠️ VoiceClient ยังไม่พร้อมหลัง connect")
                
            except asyncio.TimeoutError:
                await ctx.send("❌ หมดเวลาเชื่อมต่อ ลองใหม่นะ")
            except Exception as e:
                # กรณีเชื่อมแล้ว แต่ lib รายงานว่าเชื่อมอยู่แล้ว ให้ถือว่าสำเร็จและซิงค์สถานะ
                msg = str(e)
                if "Already connected to a voice channel" in msg:
                    try:
                        # พยายาม ensure VC อีกครั้งแบบรอสั้นๆ
                        evc = await self.ensure_voice_client(ctx.guild, wait_seconds=1.5)
                        if evc and evc.is_connected():
                            self.voice_client = evc
                            try:
                                self._actual_channel = evc.channel
                            except Exception:
                                pass
                            self._has_ever_connected = True
                            await ctx.send(f"✅ หนูอยู่ในห้อง {getattr(evc.channel, 'name', 'ไม่ทราบชื่อ')} แล้วจ้า~")
                            print("Join Info: Already connected, ensured and synced")
                            return
                        # พยายามซิงค์จากหลายแหล่ง
                        gvc = ctx.guild.voice_client
                        if not (gvc and gvc.is_connected()):
                            from discord.utils import get as dget
                            gvc = dget(self.voice_clients, guild=ctx.guild)
                        if gvc and gvc.is_connected():
                            self.voice_client = gvc
                            try:
                                self._actual_channel = gvc.channel
                            except Exception:
                                pass
                            self._has_ever_connected = True
                            await ctx.send(f"✅ หนูอยู่ในห้อง {getattr(gvc.channel, 'name', 'ไม่ทราบชื่อ')} แล้วจ้า~")
                            print("Join Info: Already connected, state synced")
                            return
                        # ถ้า VC ยังไม่พร้อม แต่บอทอยู่ในห้อง ให้ประกาศสำเร็จแบบซิงค์
                        try:
                            bot_vs = ctx.guild.me.voice
                        except Exception:
                            bot_vs = None
                        if bot_vs and bot_vs.channel:
                            self._actual_channel = bot_vs.channel
                            self._has_ever_connected = True
                            await ctx.send(f"✅ หนูอยู่ในห้อง {bot_vs.channel.name} แล้วจ้า~ (sync)")
                            print("Join Info: Already connected, synced by Member.voice")
                            return
                        # fallback: ใช้ห้องของผู้สั่งคำสั่งเป็นตัวอ้าง
                        if ctx.author.voice and ctx.author.voice.channel:
                            self._actual_channel = ctx.author.voice.channel
                            self._has_ever_connected = True
                            await ctx.send(f"✅ หนูอยู่ในห้อง {ctx.author.voice.channel.name} แล้วจ้า~ (assumed)")
                            print("Join Info: Already connected, assumed by author channel")
                            return
                    except Exception:
                        pass
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {msg[:100]}")
                print(f"Join Error: {e}")
            finally:
                self.joining = False
        
        @self.command(name='leave')
        async def leave(ctx):
            """ออกจากห้องเสียง"""
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
                self.voice_client = None
                self._actual_channel = None
                await ctx.send("👋 บ๊ายบาย~")
                print("👋 ออกจากห้องเสียง")
            else:
                await ctx.send("❌ หนูไม่ได้อยู่ในห้องเสียงนะ")
        
        @self.command(name='listen')
        async def listen(ctx, duration: int = 5):
            """บันทึกเสียงและถอดความ (แทน !stt)"""
            if not config.discord.stt_enabled:
                await ctx.send("⚠️ ฟีเจอร์ STT ถูกปิดใช้งาน")
                return
            
            # ดึง/รอ/เชื่อม ให้มี VoiceClient พร้อมใช้งาน (รอนานขึ้นเล็กน้อย)
            vc = await self.ensure_voice_client(ctx.guild, wait_seconds=3.0)
            # หากยังไม่มี vc แต่บอทรายงานว่าอยู่ในห้อง ให้ถือว่าเชื่อมจริงและแนะนำให้ !join เพื่อซิงค์
            if not (vc and vc.is_connected()):
                try:
                    bot_vs = ctx.guild.me.voice
                except Exception:
                    bot_vs = None
                if bot_vs and bot_vs.channel:
                    # พยายามซิงค์อีกครั้งแบบรอสั้นๆ
                    await ctx.send("⚠️ เชื่อมต่อยังไม่เสถียร กำลังซิงค์กับห้อง...")
                    self._actual_channel = bot_vs.channel
                    self._has_ever_connected = True
                    vc = await self.ensure_voice_client(ctx.guild, wait_seconds=2.0)
                    if not (vc and vc.is_connected()):
                        await ctx.send("❌ หนูต้องอยู่ในห้องเสียงก่อน! ใช้ `!join` เพื่อซิงค์อีกครั้ง")
                        return
                await ctx.send("❌ หนูต้องอยู่ในห้องเสียงก่อน! ใช้ `!join`")
                return
            
            if duration > config.discord.max_record_duration:
                duration = config.discord.max_record_duration
            
            await ctx.send(f"🎤 กำลังเตรียมบันทึกเสียง {duration} วินาที...")

            # พยายามใช้ PyCord sinks ถ้ามี
            has_sinks = hasattr(discord, 'sinks')
            if has_sinks:
                try:
                    sinks = discord.sinks
                    sink = sinks.WaveSink()  # บันทึกเป็น WAV

                    async def finished_callback(sink_obj, channel, *args):
                        try:
                            # เลือกเสียงของผู้ใช้ที่สั่งคำสั่งก่อน ถ้าไม่มี เลือกตัวแรก
                            audio_map = getattr(sink_obj, 'audio_data', {})
                            user_id_str = str(ctx.author.id)
                            target = None
                            if user_id_str in audio_map:
                                target = audio_map[user_id_str]
                            elif len(audio_map) > 0:
                                target = list(audio_map.values())[0]
                            
                            if not target:
                                await ctx.send("⚠️ ไม่พบเสียงที่บันทึกได้ ลองใหม่อีกครั้งนะ")
                                return
                            
                            # อ่านไฟล์ WAV bytes จาก sink แล้วบันทึกชั่วคราว
                            tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                            tmp.write(target.file.getvalue())
                            tmp_path = tmp.name
                            tmp.close()
                            
                            # ถอดความ
                            text = await stt_handler.transcribe_file(tmp_path)
                            try:
                                os.unlink(tmp_path)
                            except:
                                pass
                            
                            if text:
                                await ctx.send(f"📝 ผลการถอดความ:\n{text}")
                                # ส่งเข้าคิวให้ตอบกลับด้วยเสียงทันที
                                msg = Message(
                                    content=text,
                                    source=MessageSource.DISCORD_VOICE,
                                    priority=MessagePriority.HIGH,
                                    user_id=str(ctx.author.id),
                                    user_name=ctx.author.display_name,
                                    channel_id=str(ctx.channel.id)
                                )
                                await scheduler.add_message(msg)
                            else:
                                await ctx.send("❌ ถอดความไม่สำเร็จ ลองพูดให้ชัดขึ้นหรือแนบไฟล์เสียงแทน")
                        except Exception as e:
                            await ctx.send(f"❌ เกิดข้อผิดพลาดในการประมวลผลเสียง: {str(e)[:120]}")

                    # เริ่มบันทึก
                    await ctx.send(f"🎧 เริ่มบันทึก {duration} วินาที... พูดได้เลย!")
                    self.voice_client.start_recording(sink, finished_callback, ctx.channel)
                    await asyncio.sleep(duration)
                    self.voice_client.stop_recording()
                    return
                except Exception as e:
                    # ถ้า sinks มีแต่ใช้ไม่ได้ ตกไปใช้ไฟล์แนบ
                    await ctx.send(f"⚠️ โหมดบันทึกจากห้องใช้ไม่ได้: {str(e)[:100]}\nโปรดแนบไฟล์เสียง (.wav/.mp3/.m4a) แล้วพิมพ์ !listen อีกครั้ง")
                    # ไม่ return เพื่อให้ไป fallback ไฟล์แนบ

            # Fallback: ถอดความจากไฟล์แนบเสียงในข้อความ
            attachments = getattr(ctx.message, 'attachments', [])
            if attachments:
                try:
                    a = attachments[0]
                    filename = a.filename.lower()
                    if not any(filename.endswith(ext) for ext in ['.wav', '.mp3', '.m4a', '.ogg']):
                        await ctx.send("⚠️ รองรับเฉพาะไฟล์เสียง .wav/.mp3/.m4a/.ogg")
                        return
                    
                    data = await a.read()
                    tmp = tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1], delete=False)
                    tmp.write(data)
                    tmp_path = tmp.name
                    tmp.close()
                    
                    await ctx.send("🔎 กำลังถอดความไฟล์เสียงที่แนบมา...")
                    text = await stt_handler.transcribe_file(tmp_path)
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
                    
                    if text:
                        await ctx.send(f"📝 ผลการถอดความ:\n{text}")
                        # ส่งเข้าคิวให้ตอบกลับด้วยเสียงทันที
                        msg = Message(
                            content=text,
                            source=MessageSource.DISCORD_VOICE,
                            priority=MessagePriority.HIGH,
                            user_id=str(ctx.author.id),
                            user_name=ctx.author.display_name,
                            channel_id=str(ctx.channel.id)
                        )
                        await scheduler.add_message(msg)
                    else:
                        await ctx.send("❌ ถอดความไม่สำเร็จ ลองแนบไฟล์เสียงที่ชัดขึ้นหรือยาวกว่านี้")
                except Exception as e:
                    await ctx.send(f"❌ อ่านไฟล์แนบไม่สำเร็จ: {str(e)[:100]}")
                return
            
            # หากไม่มี sinks และไม่มีไฟล์แนบ
            await ctx.send(
                "⚠️ โหมดบันทึกจากห้องยังไม่พร้อมในสภาพแวดล้อมนี้\n"
                "โปรดแนบไฟล์เสียง (.wav/.mp3/.m4a/.ogg) แล้วพิมพ์ !listen อีกครั้ง"
            )
        
        @self.command(name='test')
        async def test(ctx):
            """ทดสอบการทำงาน"""
            status = ["✅ บอททำงานปกติ!"]
            
            # ใช้ตัวช่วยดึง VoiceClient ปัจจุบัน
            vc = self.get_current_voice_client(ctx.guild)
            bot_vs = None
            try:
                bot_vs = ctx.guild.me.voice  # voice state ของบอทเอง
            except Exception:
                bot_vs = None

            # ตัดสินว่าบอทอยู่ในห้องหรือไม่: ถ้ามี vc เชื่อมต่อ หรืออย่างน้อย bot_vs.channel มีค่า
            is_in_voice = bool((vc and vc.is_connected()) or (bot_vs and bot_vs.channel))
            if is_in_voice:
                # อัพเดตชื่อห้องล่าสุด
                try:
                    cname = (
                        (vc.channel.name if vc and vc.channel else None)
                        or (bot_vs.channel.name if bot_vs and bot_vs.channel else None)
                        or (self._actual_channel.name if self._actual_channel else "ไม่ทราบชื่อ")
                    )
                except Exception:
                    cname = self._actual_channel.name if self._actual_channel else "ไม่ทราบชื่อ"
                # ซิงค์สถานะภายในให้สอดคล้องกับ voice state ของบอท
                if bot_vs and bot_vs.channel:
                    self._actual_channel = bot_vs.channel
                    self._has_ever_connected = True
                status.append(f"🔊 อยู่ในห้อง: {cname}")
            else:
                status.append("⚠️ ไม่ได้อยู่ในห้องเสียง")
            
            await ctx.send(" ".join(status))
        
        @self.command(name='ping')
        async def ping(ctx):
            """ตรวจสอบ latency"""
            latency = round(self.latency * 1000)
            await ctx.send(f"🏓 Pong! Latency: {latency}ms")
        
        @self.command(name='collab')
        async def collab(ctx, mode: str = "on"):
            """เปิด/ปิดโหมดคอแลป"""
            enabled = mode.lower() in ["on", "enable", "true", "1"]
            scheduler.set_collab_mode(enabled)
            status = "เปิด" if enabled else "ปิด"
            await ctx.send(f"🎤 โหมดคอแลป: {status}")
        
        @self.command(name='youtube')
        async def youtube_toggle(ctx, mode: str = "on"):
            """เปิด/ปิดคอมเม้น YouTube"""
            enabled = mode.lower() in ["on", "enable", "true", "1"]
            scheduler.set_youtube_enabled(enabled)
            status = "เปิด" if enabled else "ปิด"
            await ctx.send(f"📺 YouTube Comments: {status}")
        
        @self.command(name='clear')
        async def clear_queue(ctx):
            """ล้างคิวคำถาม"""
            scheduler.clear_queue()
            await ctx.send("🗑️ ล้างคิวแล้ว")
        
        @self.command(name='stats')
        async def show_stats(ctx):
            """แสดงสถิติ"""
            stats = scheduler.get_stats()
            msg = f"""📊 **สถิติระบบ**
```
Queue Size: {stats['queue_size']}
Total Processed: {stats['total_processed']}
Collab Mode: {stats['collab_mode']}
YouTube Enabled: {stats['youtube_enabled']}
```"""
            await ctx.send(msg)
        
        @self.command(name='help')
        async def help_command(ctx):
            """แสดงคำสั่งทั้งหมด"""
            help_text = """📖 **คำสั่งที่ใช้ได้**
```
!join           - เข้าห้องเสียง
!leave          - ออกจากห้องเสียง
!listen [วินาที] - บันทึกเสียงและถอดความ
!test           - ทดสอบบอท
!ping           - ตรวจสอบ latency
!collab on/off  - เปิด/ปิดโหมดคอแลป
!youtube on/off - เปิด/ปิดคอมเม้น YouTube
!stats          - แสดงสถิติ
!clear          - ล้างคิว
!help           - แสดงคำสั่งนี้
```
💬 พิมพ์ข้อความธรรมดาเพื่อคุยกับหนู~"""
            await ctx.send(help_text)
    
    async def play_audio(self, audio_path: str, channel_id: Optional[str] = None):
        """เล่นเสียงในห้อง"""
        try:
            if not os.path.exists(audio_path):
                print(f"❌ ไม่พบไฟล์เสียง: {audio_path}")
                return
            
            if not self.voice_client or not self.voice_client.is_connected():
                print("⚠️ ไม่ได้เชื่อมต่อห้องเสียง (ใช้ !join เพื่อเข้าห้อง)")
                return
            
            max_wait = 10
            elapsed = 0
            while self.voice_client.is_playing() and elapsed < max_wait:
                await asyncio.sleep(0.1)
                elapsed += 0.1
            
            if self.voice_client.is_playing():
                self.voice_client.stop()
                await asyncio.sleep(0.2)
            
            audio_source = FFmpegPCMAudio(audio_path, options='-loglevel panic')
            audio_source = PCMVolumeTransformer(audio_source, volume=1.0)
            
            self.voice_client.play(audio_source)
            print(f"🔊 เล่นเสียง: {audio_path}")
            
        except Exception as e:
            print(f"❌ Play Audio Error: {e}")
    
    async def on_ready(self):
        """เมื่อ bot พร้อม"""
        self.is_ready = True
        # เปิดรับ voice events หลังบูต
        import time
        self._suppress_voice_events_until = time.time()
        print(f"✅ Discord Bot พร้อมแล้ว: {self.user}")
        # เปิดดีบัก event ชั่วคราว 15 วินาที เพื่อไล่ปัญหา disconnect ที่บูต
        self._debug_voice_events_until = time.time() + 15.0
        
        try:
            await self.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name="!help | พิมพ์คุยได้เลย~"
                )
            )
        except:
            pass
    
    async def on_message(self, message: discord.Message):
        """เมื่อมีข้อความใหม่"""
        if message.author == self.user or message.author.bot:
            return
        
        await self.process_commands(message)
        
        if not message.content.startswith(self.command_prefix):
            msg = Message(
                content=message.content,
                source=MessageSource.DISCORD_TEXT,
                priority=MessagePriority.NORMAL,
                user_id=str(message.author.id),
                user_name=message.author.display_name,
                channel_id=str(message.channel.id)
            )
            
            success = await scheduler.add_message(msg)
            if success:
                try:
                    await message.add_reaction("✅")
                except:
                    pass
    
    async def on_command_error(self, ctx, error):
        """จัดการ error"""
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ ขาดพารามิเตอร์: {error.param.name}")
        elif isinstance(error, commands.CommandInvokeError):
            print(f"Command Error: {error.original}")
            await ctx.send("❌ เกิดข้อผิดพลาดในการใช้คำสั่ง")
        else:
            print(f"Unhandled Error: {error}")
    
    async def on_voice_state_update(self, member, before, after):
        """เมื่อมีการเปลี่ยนแปลง voice state"""
        if member == self.user:
            # บางครั้งตอนบูตจะมี event แปลกๆ ให้ข้ามในช่วงแรก
            import time
            if time.time() < self._suppress_voice_events_until:
                return
            # log ดีบักช่วงแรกเพื่อวิเคราะห์สาเหตุจริง
            if hasattr(self, '_debug_voice_events_until') and time.time() < self._debug_voice_events_until:
                try:
                    bname = before.channel.name if (before and before.channel) else None
                    aname = after.channel.name if (after and after.channel) else None
                    vc_connected = (self.voice_client.is_connected() if self.voice_client else None)
                    acname = self._actual_channel.name if self._actual_channel else None
                    print(f"[DEBUG] voice_state_update(bot): before={bname}, after={aname}, vc_connected={vc_connected}, actual={acname}, has_connected={self._has_ever_connected}")
                except Exception:
                    pass
            # อัพเดต state เมื่อย้ายช่องโดยสมัครใจ
            if after and after.channel:
                # ซิงค์ voice_client จาก guild และจำห้องล่าสุด
                try:
                    vc = after.channel.guild.voice_client
                    # อนุญาตอัพเดตเฉพาะกรณีที่มี voice_client จริงและเชื่อมต่ออยู่
                    if vc and vc.is_connected():
                        self.voice_client = vc
                        self._actual_channel = after.channel
                        self._has_ever_connected = True
                    else:
                        # กรณี event หลอน (after.channel มีแต่ไม่มี voice_client)
                        # ไม่อัพเดต state เพื่อหลีกเลี่ยง false positive ช่วงบูต/รีสตาร์ท
                        return
                except Exception:
                    pass
                return

            # ถูกเตะ/หลุดออกจากช่องเสียง — ตรวจสอบแบบหน่วงเวลาเพื่อกัน false positive
            if before and before.channel and not after.channel:
                async def verify_then_clear():
                    # หน่วงเวลาเล็กน้อยเพื่อรอให้ voice_client/guild state ซิงค์
                    await asyncio.sleep(0.7)
                    # ถ้าระหว่างหน่วงเวลา บอทย้ายไปห้องอื่นแล้ว ไม่เคลียร์
                    try:
                        if self._actual_channel and self._actual_channel != before.channel:
                            return
                    except Exception:
                        pass
                    try:
                        gvc = before.channel.guild.voice_client
                        # ถ้ายังมี VC เชื่อมต่ออยู่ ถือว่ายังไม่หลุดจริง
                        if gvc and gvc.is_connected():
                            return
                    except Exception:
                        pass

                    # ตรวจสอบ Member.voice ของบอทอีกครั้ง
                    try:
                        bot_vs = before.channel.guild.me.voice
                    except Exception:
                        bot_vs = None
                    if bot_vs and bot_vs.channel:
                        # ยังอยู่ในห้อง — ไม่เคลียร์
                        return

                    # เคลียร์ state เฉพาะกรณีเคยเชื่อมจริง และห้องก่อนหน้าตรงกับที่จำไว้
                    if self._has_ever_connected and (self._actual_channel is None or self._actual_channel == before.channel):
                        print("👋 ถูก disconnect จากห้องเสียง (verified)")
                        self.voice_client = None
                        self._actual_channel = None
                try:
                    asyncio.create_task(verify_then_clear())
                except Exception:
                    pass
    
    async def send_message(self, channel_id: str, content: str):
        """ส่งข้อความไปยัง channel"""
        try:
            channel = self.get_channel(int(channel_id))
            if channel:
                await channel.send(content)
        except Exception as e:
            print(f"❌ Send Message Error: {e}")

# Global bot instance
discord_bot = DiscordBot()