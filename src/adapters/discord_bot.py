"""
Discord Bot สำหรับ AI VTuber (แก้ !join ซ้ำซ้อนและเพิ่ม !listen)
ตำแหน่ง: src/adapters/discord_bot.py (แทนที่ทั้งหมด)
"""

import asyncio
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio, PCMVolumeTransformer
from typing import Optional
import os

import sys
sys.path.append('..')
from core.config import config
from core.scheduler import Message, MessageSource, MessagePriority, scheduler
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
        self.joining = False  # Flag เพื่อป้องกัน join ซ้ำ
        
        self.add_commands()
    
    def add_commands(self):
        """เพิ่มคำสั่งต่างๆ"""
        
        @self.command(name='join')
        async def join(ctx):
            """เข้าห้องเสียง"""
            # ป้องกัน join ซ้ำ
            if self.joining:
                await ctx.send("⏳ กำลังเชื่อมต่อ... รอสักครู่นะ")
                return
            
            try:
                self.joining = True
                
                if not ctx.author.voice:
                    await ctx.send("❌ คุณต้องอยู่ในห้องเสียงก่อน!")
                    return
                
                channel = ctx.author.voice.channel
                
                # ถ้ามี voice client แล้ว
                if self.voice_client:
                    if self.voice_client.is_connected():
                        # ถ้าอยู่ห้องเดียวกัน
                        if self.voice_client.channel == channel:
                            await ctx.send("✅ หนูอยู่ห้องนี้อยู่แล้วนะ~")
                            return
                        
                        # ย้ายห้อง
                        await self.voice_client.move_to(channel)
                        await ctx.send(f"✅ ย้ายมาห้อง {channel.name} แล้วจ้า~")
                        return
                    else:
                        # cleanup voice client เก่า
                        self.voice_client = None
                
                # เชื่อมต่อใหม่
                self.voice_client = await channel.connect(timeout=10.0)
                await ctx.send(f"✅ เข้าห้อง {channel.name} แล้วจ้า~")
                print(f"✅ เข้าห้องเสียง: {channel.name}")
                
            except asyncio.TimeoutError:
                await ctx.send("❌ หมดเวลาเชื่อมต่อ ลองใหม่นะ")
            except Exception as e:
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {str(e)[:100]}")
                print(f"Join Error: {e}")
            finally:
                self.joining = False
        
        @self.command(name='leave')
        async def leave(ctx):
            """ออกจากห้องเสียง"""
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
                self.voice_client = None
                await ctx.send("👋 บ๊ายบาย~")
                print("👋 ออกจากห้องเสียง")
            else:
                await ctx.send("❌ หนูไม่ได้อยู่ในห้องเสียงนะ")
        
        @self.command(name='listen')
        async def listen(ctx, duration: int = 5):
            """บันทึกเสียงและถอดความ (เปลี่ยนจาก !stt เป็น !listen)"""
            if not config.discord.stt_enabled:
                await ctx.send("⚠️ ฟีเจอร์ STT ถูกปิดใช้งาน")
                return
            
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ หนูต้องอยู่ในห้องเสียงก่อน! ใช้ `!join`")
                return
            
            if duration > config.discord.max_record_duration:
                duration = config.discord.max_record_duration
            
            await ctx.send(f"🎤 กำลังบันทึกเสียง {duration} วินาที...")
            
            # TODO: Implement voice recording + STT
            # สำหรับตอนนี้แจ้งว่ายังไม่พร้อม
            await ctx.send("⚠️ ฟีเจอร์บันทึกเสียงยังอยู่ระหว่างพัฒนา\nกรุณาพิมพ์ข้อความแทนนะ~")
        
        @self.command(name='test')
        async def test(ctx):
            """ทดสอบการทำงาน"""
            status = ["✅ บอททำงานปกติ!"]
            
            if self.voice_client and self.voice_client.is_connected():
                status.append(f"🔊 อยู่ในห้อง: {self.voice_client.channel.name}")
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
            
            # รอให้เสียงเดิมเล่นเสร็จ
            max_wait = 10
            elapsed = 0
            while self.voice_client.is_playing() and elapsed < max_wait:
                await asyncio.sleep(0.1)
                elapsed += 0.1
            
            if self.voice_client.is_playing():
                self.voice_client.stop()
                await asyncio.sleep(0.2)
            
            # เล่นเสียง
            audio_source = FFmpegPCMAudio(audio_path, options='-loglevel panic')
            audio_source = PCMVolumeTransformer(audio_source, volume=1.0)
            
            self.voice_client.play(audio_source)
            print(f"🔊 เล่นเสียง: {audio_path}")
            
        except Exception as e:
            print(f"❌ Play Audio Error: {e}")
    
    async def on_ready(self):
        """เมื่อ bot พร้อม"""
        self.is_ready = True
        print(f"✅ Discord Bot พร้อมแล้ว: {self.user}")
        
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
            if before.channel and not after.channel:
                self.voice_client = None
                print("👋 ถูก disconnect จากห้องเสียง")
    
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