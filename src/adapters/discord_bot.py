"""
Discord Bot สำหรับ AI VTuber
ตำแหน่ง: src/adapters/discord_bot.py (แก้ไขทั้งไฟล์)
"""

import asyncio
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
import io
import wave
from typing import Optional

import sys
sys.path.append('..')
from core.config import config
from core.queue_manager import queue_manager, Message, MessageSource, MessagePriority
from audio.stt_handler import stt_handler

class DiscordBot(commands.Bot):
    """Discord Bot หลัก"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        super().__init__(
            command_prefix=config.discord.command_prefix,
            intents=intents
        )
        
        self.voice_client: Optional[discord.VoiceClient] = None
        self.recording = False
        self.audio_buffer = []
        
        # เพิ่มคำสั่ง
        self.add_commands()
    
    def add_commands(self):
        """เพิ่มคำสั่งต่างๆ"""
        
        @self.command(name='join')
        async def join(ctx):
            """เข้าห้องเสียง"""
            if ctx.author.voice is None:
                await ctx.send("❌ คุณต้องอยู่ในห้องเสียงก่อน!")
                return
            
            channel = ctx.author.voice.channel
            
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.move_to(channel)
            else:
                self.voice_client = await channel.connect()
            
            await ctx.send(f"✅ เข้าห้อง {channel.name} แล้วจ้า~")
        
        @self.command(name='leave')
        async def leave(ctx):
            """ออกจากห้องเสียง"""
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect()
                self.voice_client = None
                await ctx.send("👋 บ๊ายบาย~")
            else:
                await ctx.send("❌ หนูไม่ได้อยู่ในห้องเสียงนะ")
        
        @self.command(name='stt')
        async def stt_command(ctx, duration: int = 5):
            """บันทึกเสียงและถอดความ"""
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send("❌ หนูต้องอยู่ในห้องเสียงก่อน! ใช้ `!join`")
                return
            
            if duration > config.discord.max_record_duration:
                duration = config.discord.max_record_duration
            
            await ctx.send(f"🎤 กำลังบันทึกเสียง {duration} วินาที...")
            
            # บันทึกเสียง
            audio_data = await self._record_audio(duration)
            
            if audio_data:
                # ถอดความ
                text = await stt_handler.transcribe_audio(audio_data)
                
                if text:
                    await ctx.send(f"✅ ได้ยินว่า: **{text}**")
                    
                    # เพิ่มเข้าคิว
                    message = Message(
                        content=text,
                        source=MessageSource.DISCORD_VOICE,
                        priority=MessagePriority.HIGH,
                        user_id=str(ctx.author.id),
                        user_name=ctx.author.name,
                        channel_id=str(ctx.channel.id)
                    )
                    await queue_manager.add_message(message)
                else:
                    await ctx.send("❌ ถอดความไม่สำเร็จ ลองใหม่นะ")
            else:
                await ctx.send("❌ บันทึกเสียงล้มเหลว")
        
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
    
    async def _record_audio(self, duration: int) -> Optional[bytes]:
        """บันทึกเสียงจาก voice channel"""
        try:
            if not self.voice_client:
                return None
            
            # เตรียม buffer
            self.audio_buffer = []
            self.recording = True
            
            # สร้าง sink สำหรับบันทึก
            class AudioSink(discord.sinks.WaveSink):
                def __init__(self, bot_instance):
                    super().__init__()
                    self.bot = bot_instance
                
                def write(self, data):
                    if self.bot.recording:
                        self.bot.audio_buffer.append(data)
            
            sink = AudioSink(self)
            
            # เริ่มบันทึก
            self.voice_client.start_recording(
                sink,
                lambda *args: None,
                ctx=None
            )
            
            # รอตามเวลาที่กำหนด
            await asyncio.sleep(duration)
            
            # หยุดบันทึก
            self.recording = False
            self.voice_client.stop_recording()
            
            # รวมข้อมูลเสียง
            if self.audio_buffer:
                audio_data = b''.join(self.audio_buffer)
                return audio_data
            
            return None
            
        except Exception as e:
            print(f"❌ Record Error: {e}")
            return None
    
    async def play_audio(self, audio_path: str, channel_id: Optional[str] = None):
        """เล่นเสียงในห้อง"""
        try:
            if not self.voice_client or not self.voice_client.is_connected():
                print("⚠️ ไม่ได้เชื่อมต่อห้องเสียง")
                return
            
            # รอให้เสียงเดิมเล่นเสร็จ
            while self.voice_client.is_playing():
                await asyncio.sleep(0.1)
            
            # เล่นเสียงใหม่
            audio_source = FFmpegPCMAudio(audio_path)
            self.voice_client.play(audio_source)
            
            print(f"🔊 เล่นเสียง: {audio_path}")
            
        except Exception as e:
            print(f"❌ Play Audio Error: {e}")
    
    async def on_ready(self):
        """เมื่อ bot พร้อม"""
        print(f"✅ Discord Bot พร้อมแล้ว: {self.user}")
    
    async def on_message(self, message: discord.Message):
        """เมื่อมีข้อความใหม่"""
        # ไม่สนใจข้อความจากตัวเอง
        if message.author == self.user:
            return
        
        # ประมวลผลคำสั่ง
        await self.process_commands(message)
        
        # ถ้าไม่ใช่คำสั่ง ให้เพิ่มเข้าคิว
        if not message.content.startswith(self.command_prefix):
            msg = Message(
                content=message.content,
                source=MessageSource.DISCORD_TEXT,
                priority=MessagePriority.NORMAL,
                user_id=str(message.author.id),
                user_name=message.author.name,
                channel_id=str(message.channel.id)
            )
            await queue_manager.add_message(msg)
    
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

async def run_discord_bot():
    """รัน Discord bot"""
    try:
        await discord_bot.start(config.discord.token)
    except Exception as e:
        print(f"❌ Discord Bot Error: {e}")