"""
ไฟล์หลัก AI VTuber - Jeed (แก้ Event Loop ให้ถูกต้อง)
ตำแหน่ง: src/main.py
"""

import asyncio
import sys
import time
from pathlib import Path

# โหลด .env ให้แน่ใจว่าอ่านจากไฟล์จริงที่รากโปรเจกต์
try:
    from dotenv import load_dotenv
    # รากโปรเจกต์ = พ่อของโฟลเดอร์ src
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

# เพิ่ม path
sys.path.append(str(Path(__file__).parent))

# Import ทุกอย่าง
from core.config import config
from core.queue_manager import queue_manager
from core.safety_filter import safety_filter, FilterResult
from personality.jeed_persona import jeed_persona, JeedPersona
from llm.llm_handler import llm_handler
from audio.stt_handler import stt_handler
from audio.tts_rvc_handler import tts_rvc_handler
from adapters.discord_bot import discord_bot
from adapters.vts.vtube_controller import vtube_controller, AnimationState

class JeedAIVTuber:
    """คลาสหลักของ AI VTuber"""
    
    def __init__(self):
        self.running = False
        self.processing_task = None
        self.discord_task = None
        
    async def start(self):
        """เริ่มระบบทั้งหมด"""
        print("\n" + "="*60)
        print("🎮 Jeed AI VTuber Starting...")
        print("="*60)
        
        # ตรวจสอบ config
        if not config.validate():
            print("❌ การตั้งค่าไม่ถูกต้อง!")
            return False
        
        config.print_config()
        
        # เชื่อมต่อ VTube Studio
        print("\n📡 เชื่อมต่อ VTube Studio...")
        vts_connected = await vtube_controller.connect()
        if not vts_connected:
            print("⚠️ เชื่อมต่อ VTube Studio ล้มเหลว")
        
        # เริ่ม Discord Bot (ใน background task)
        print("\n🤖 เริ่ม Discord Bot...")
        self.discord_task = asyncio.create_task(self._run_discord_bot())
        
        # รอให้ Discord Bot พร้อม
        await asyncio.sleep(3)
        
        # เริ่ม processing loop
        self.running = True
        self.processing_task = asyncio.create_task(self._processing_loop())
        
        print("\n" + "="*60)
        print("✅ Jeed AI VTuber พร้อมแล้ว!")
        print("="*60)
        print("คำสั่ง Discord Bot:")
        print("  !join      - เข้าห้องเสียง")
        print("  !leave     - ออกจากห้องเสียง")
        print("  !test      - ทดสอบบอท")
        print("  !ping      - ตรวจสอบ latency")
        print("  !stats     - แสดงสถิติ")
        print("  !clear     - ล้างคิว")
        print("="*60 + "\n")
        
        return True
    
    async def _run_discord_bot(self):
        """รัน Discord bot แยก task"""
        try:
            if not config.discord.token:
                print("❌ ไม่พบ DISCORD_BOT_TOKEN")
                return
            
            await discord_bot.start(config.discord.token)
            
        except Exception as e:
            print(f"❌ Discord Bot Error: {e}")
            import traceback
            traceback.print_exc()
    
    async def _processing_loop(self):
        """Loop หลักประมวลผลคำถาม"""
        print("🔄 เริ่ม Processing Loop")
        
        while self.running:
            try:
                # ดึงข้อความถัดไป
                message = await queue_manager.process_next()
                
                if message is None:
                    await asyncio.sleep(0.5)
                    continue
                
                # ประมวลผลข้อความ
                await self._process_message(message)
                
                # เสร็จสิ้น
                queue_manager.finish_processing()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ Processing Error: {e}")
                import traceback
                traceback.print_exc()
                queue_manager.finish_processing()
                await asyncio.sleep(1)
        
        print("🛑 Processing Loop หยุดทำงาน")
    
    async def _process_message(self, message):
        """ประมวลผลข้อความ"""
        start_time = time.time()
        
        try:
            print(f"\n{'='*60}")
            print(f"📨 ประมวลผล: {message.source.value}")
            print(f"   User: {message.user_name}")
            print(f"   Message: {message.content[:100]}")
            print(f"{'='*60}")
            
            # 1. กรองเนื้อหา
            filter_result, reason = safety_filter.check_content(message.content)
            
            if filter_result == FilterResult.BLOCK:
                print(f"🚫 บล็อกเนื้อหา: {reason}")
                response = safety_filter.create_safe_response(filter_result, reason)
                
                if message.channel_id and discord_bot.is_ready:
                    await discord_bot.send_message(message.channel_id, response)
                
                return
            
            elif filter_result == FilterResult.REQUIRE_PERMISSION:
                print(f"🔐 ต้องขออนุญาต: {reason}")
                response = safety_filter.create_safe_response(filter_result, reason)
                
                if message.channel_id and discord_bot.is_ready:
                    await discord_bot.send_message(message.channel_id, response)
                
                return
            
            # 2. เปลี่ยนสถานะเป็น THINKING
            if vtube_controller.running:
                await vtube_controller.set_state(AnimationState.THINKING)
            
            # 3. สร้างคำตอบจาก LLM
            response = await llm_handler.generate_response(message.content)
            
            if not response:
                print("❌ LLM ไม่สามารถสร้างคำตอบได้")
                return
            
            print(f"💬 คำตอบ: {response}")
            
            # 4. ส่งข้อความกลับ
            if message.channel_id and discord_bot.is_ready:
                await discord_bot.send_message(message.channel_id, response)
            
            # 5. สร้างเสียง TTS + RVC
            if vtube_controller.running:
                await vtube_controller.start_speaking(response)
            
            audio_data, audio_path = await tts_rvc_handler.generate_speech(response)
            
            if audio_path:
                # 6. เล่นเสียง
                if discord_bot.voice_client and discord_bot.voice_client.is_connected():
                    await discord_bot.play_audio(audio_path, message.channel_id)
                    
                    # รอให้เล่นเสร็จ
                    duration = tts_rvc_handler.estimate_duration(response)
                    await asyncio.sleep(duration + 0.5)
                else:
                    print("⚠️ ไม่ได้เชื่อมต่อห้องเสียง (ใช้ !join เพื่อเข้าห้อง)")
                
                # ลบไฟล์ชั่วคราว
                try:
                    Path(audio_path).unlink()
                except:
                    pass
            
            # 7. หยุดพูด
            if vtube_controller.running:
                await vtube_controller.stop_speaking()
            
            # แสดงเวลาประมวลผล
            elapsed = time.time() - start_time
            print(f"\n✅ ประมวลผลเสร็จ ({elapsed:.2f}s)")
            
            if elapsed > config.system.max_processing_time:
                print(f"⚠️ ใช้เวลานานเกินไป! ({elapsed:.2f}s > {config.system.max_processing_time}s)")
            
        except Exception as e:
            print(f"❌ Process Message Error: {e}")
            import traceback
            traceback.print_exc()
    
    async def stop(self):
        """หยุดระบบ"""
        print("\n🛑 กำลังหยุดระบบ...")
        
        self.running = False
        
        # หยุด processing loop
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        
        # ตัดการเชื่อมต่อ VTube Studio
        if vtube_controller.running:
            await vtube_controller.disconnect()
        
        # ปิด Discord bot
        if discord_bot.is_ready:
            await discord_bot.close()
        
        # หยุด Discord task
        if self.discord_task:
            self.discord_task.cancel()
            try:
                await self.discord_task
            except asyncio.CancelledError:
                pass
        
        print("👋 ระบบหยุดแล้ว")

async def main():
    """ฟังก์ชันหลัก"""
    jeed = JeedAIVTuber()
    
    try:
        # เริ่มระบบ
        success = await jeed.start()
        
        if not success:
            return
        
        # รอจนกว่าจะถูกหยุด (Ctrl+C)
        while True:
            await asyncio.sleep(1)
            
            # ตรวจสอบว่า tasks ยังทำงานอยู่หรือไม่
            if jeed.discord_task and jeed.discord_task.done():
                print("⚠️ Discord Bot หยุดทำงาน")
                break
            
            if jeed.processing_task and jeed.processing_task.done():
                print("⚠️ Processing Loop หยุดทำงาน")
                break
            
    except KeyboardInterrupt:
        print("\n\n⚠️ ได้รับสัญญาณหยุด (Ctrl+C)")
    
    except Exception as e:
        print(f"\n❌ Fatal Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await jeed.stop()

if __name__ == "__main__":
    try:
        # ใช้ asyncio.run() เพื่อสร้าง event loop เดียว
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 บ๊ายบาย~")
    except Exception as e:
        print(f"\n❌ Startup Error: {e}")
        import traceback
        traceback.print_exc()