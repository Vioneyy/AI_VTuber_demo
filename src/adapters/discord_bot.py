"""
Discord Bot สำหรับ AI VTuber (แก้ให้เล่นเสียงได้)
ตำแหน่ง: src/adapters/discord_bot.py
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
from core.queue_manager import queue_manager, Message, MessageSource, MessagePriority
from audio.stt_handler import stt_handler

class DiscordBot(commands.Bot):
    """Discord Bot หลัก"""
    
    def __init__(self):
        # ตั้งค่า Intents
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
        self.current_guild = None
        
        # เพิ่มคำสั่ง
        self.add_commands()
    
    def add_commands(self):
        """เพิ่มคำสั่งต่างๆ"""
        
        @self.command(name='join')
        async def join(ctx):
            """เข้าห้องเสียง"""
            try:
                # ตรวจสอบว่าผู้ใช้อยู่ในห้องเสียงหรือไม่
                if not ctx.author.voice:
                    await ctx.send("❌ คุณต้องอยู่ในห้องเสียงก่อน!")
                    return
                
                channel = ctx.author.voice.channel
                
                # ตรวจสอบว่ามี voice client อยู่แล้วหรือไม่
                if self.voice_client:
                    # ถ้าอยู่ห้องเดียวกัน
                    if self.voice_client.channel == channel:
                        await ctx.send("✅ หนูอยู่ห้องนี้อยู่แล้วนะ~")
                        return
                    
                    # ถ้าอยู่ห้องต่างกัน ให้ตัดการเชื่อมต่อก่อน
                    try:
                        await self.voice_client.disconnect(force=True)
                    except:
                        pass
                    self.voice_client = None
                    await asyncio.sleep(0.5)
                
                # เชื่อมต่อใหม่
                self.voice_client = await channel.connect(timeout=10.0)
                self.current_guild = ctx.guild
                
                await ctx.send(f"✅ เข้าห้อง {channel.name} แล้วจ้า~")
                print(f"✅ เข้าห้องเสียง: {channel.name} (Guild: {ctx.guild.name})")
                
            except asyncio.TimeoutError:
                await ctx.send("❌ หมดเวลาเชื่อมต่อ ลองใหม่นะ")
            except Exception as e:
                await ctx.send(f"❌ เกิดข้อผิดพลาด: {str(e)[:100]}")
                print(f"Join Error: {e}")
        
        @self.command(name='leave')
        async def leave(ctx):
            """ออกจากห้องเสียง"""
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
                self.voice_client = None
                self.current_guild = None
                await ctx.send("👋 บ๊ายบาย~")
                print("👋 ออกจากห้องเสียง")
            else:
                await ctx.send("❌ หนูไม่ได้อยู่ในห้องเสียงนะ")
        
        @self.command(name='test')
        async def test(ctx):
            """ทดสอบการทำงาน"""
            status = []
            status.append("✅ บอททำงานปกติ!")
            
            if self.voice_client and self.voice_client.is_connected():
                status.append(f"🔊 อยู่ในห้อง: {self.voice_client.channel.name}")
            else:
                status.append("⚠️ ไม่ได้อยู่ในห้องเสียง")
            
            await ctx.send("\n".join(status))
        
        @self.command(name='ping')
        async def ping(ctx):
            """ตรวจสอบ latency"""
            latency = round(self.latency * 1000)
            await ctx.send(f"🏓 Pong! Latency: {latency}ms")
        
        @self.command(name='volume')
        async def volume(ctx, vol: int = None):
            """ปรับระดับเสียง (0-100)"""
            if vol is None:
                await ctx.send("📊 ระดับเสียงปัจจุบัน: 100%")
                return
            
            if vol < 0 or vol > 100:
                await ctx.send("❌ ระดับเสียงต้องอยู่ระหว่าง 0-100")
                return
            
            await ctx.send(f"🔊 ตั้งระดับเสียง: {vol}%")
        
        @self.command(name='collab')
        async def collab(ctx, mode: str = "on"):
            """เปิด/ปิดโหมดคอแลป"""
            enabled = mode.lower() in ["on", "enable", "true", "1"]
            queue_manager.set_collab_mode(enabled)
            status = "เปิด" if enabled else "ปิด"
            await ctx.send(f"🎤 โหมดคอแลป: {status}")
        
        @self.command(name='youtube')
        async def youtube_toggle(ctx, mode: str = "on"):
            """เปิด/ปิดคอมเม้น YouTube"""
            enabled = mode.lower() in ["on", "enable", "true", "1"]
            queue_manager.set_youtube_enabled(enabled)
            status = "เปิด" if enabled else "ปิด"
            await ctx.send(f"📺 YouTube Comments: {status}")
        
        @self.command(name='clear')
        async def clear_queue(ctx):
            """ล้างคิวคำถาม"""
            queue_manager.clear_queue()
            await ctx.send("🗑️ ล้างคิวแล้ว")
        
        @self.command(name='stats')
        async def show_stats(ctx):
            """แสดงสถิติ"""
            stats = queue_manager.get_stats()
            msg = f"""📊 **สถิติระบบ**
```
Queue Size: {stats['queue_size']}
Total Processed: {stats['total_processed']}
Total Dropped: {stats['total_dropped']}
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
!test           - ทดสอบบอท
!ping           - ตรวจสอบ latency
!volume [0-100] - ปรับระดับเสียง
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
            # ตรวจสอบว่าไฟล์มีอยู่จริง
            if not os.path.exists(audio_path):
                print(f"❌ ไม่พบไฟล์เสียง: {audio_path}")
                return
            
            # ตรวจสอบการเชื่อมต่อ
            if not self.voice_client or not self.voice_client.is_connected():
                print("⚠️ ไม่ได้เชื่อมต่อห้องเสียง (ใช้ !join เพื่อเข้าห้อง)")
                return
            
            # รอให้เสียงเดิมเล่นเสร็จ
            max_wait = 10
            elapsed = 0
            while self.voice_client.is_playing() and elapsed < max_wait:
                await asyncio.sleep(0.1)
                elapsed += 0.1
            
            # หยุดเสียงเดิม (ถ้ายังเล่นอยู่)
            if self.voice_client.is_playing():
                self.voice_client.stop()
                await asyncio.sleep(0.2)
            
            # สร้าง audio source
            audio_source = FFmpegPCMAudio(
                audio_path,
                options='-loglevel panic'  # ลด log จาก ffmpeg
            )
            
            # เพิ่ม volume control
            audio_source = PCMVolumeTransformer(audio_source, volume=1.0)
            
            # เล่นเสียง
            def after_playing(error):
                if error:
                    print(f"⚠️ Audio Error: {error}")
            
            self.voice_client.play(audio_source, after=after_playing)
            
            print(f"🔊 เล่นเสียง: {audio_path}")
            
        except Exception as e:
            print(f"❌ Play Audio Error: {e}")
            import traceback
            traceback.print_exc()
    
    async def on_ready(self):
        """เมื่อ bot พร้อม"""
        self.is_ready = True
        print(f"✅ Discord Bot พร้อมแล้ว: {self.user} (ID: {self.user.id})")
        print(f"📊 เชื่อมต่อกับ {len(self.guilds)} servers")
        
        # ตั้งค่า status
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
        # ไม่สนใจข้อความจากตัวเอง
        if message.author == self.user:
            return
        
        # ไม่สนใจข้อความจาก bot อื่น
        if message.author.bot:
            return
        
        # ประมวลผลคำสั่งก่อน
        await self.process_commands(message)
        
        # ถ้าไม่ใช่คำสั่ง ให้เพิ่มเข้าคิว
        if not message.content.startswith(self.command_prefix):
            msg = Message(
                content=message.content,
                source=MessageSource.DISCORD_TEXT,
                priority=MessagePriority.NORMAL,
                user_id=str(message.author.id),
                user_name=message.author.display_name,
                channel_id=str(message.channel.id)
            )
            
            success = await queue_manager.add_message(msg)
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
        # ถ้าบอทถูก disconnect
        if member == self.user:
            if before.channel and not after.channel:
                self.voice_client = None
                self.current_guild = None
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