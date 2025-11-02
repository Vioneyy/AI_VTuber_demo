"""
ไฟล์หลัก AI VTuber - Jeed
ตำแหน่ง: src/main.py (เขียนใหม่ทั้งหมด)
"""

import asyncio
import sys
import time
from pathlib import Path

# โหลด .env ให้เร็วที่สุดก่อน import config
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# เพิ่ม path
sys.path.append(str(Path(__file__).parent))

# Import ทุกอย่าง
from core.config import config
from core.queue_manager import queue_manager, Message, MessageSource
from core.safety_filter import safety_filter, FilterResult
from personality.jeed_persona import jeed_persona, JeedPersona
from llm.llm_handler import llm_handler
from audio.stt_handler import stt_handler
from audio.tts_rvc_handler import tts_rvc_handler
from adapters.discord_bot import discord_bot, run_discord_bot
from adapters.vts.vtube_controller import vtube_controller, AnimationState

class JeedAIVTuber:
    """คลาสหลักของ AI VTuber"""
    
    def __init__(self):
        self.running = False
        self.processing_task = None
        
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
            print("⚠️ เชื่อมต่อ VTube Studio ล้มเหลว (ข้ามไป)")
        
        # เริ่ม Discord Bot
        print("\n🤖 เริ่ม Discord Bot...")
        asyncio.create_task(run_discord_bot())
        
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
        print("  !stt [วินาที] - บันทึกเสียงและถอดความ")
        print("  !collab on/off - เปิด/ปิดโหมดคอแลป")
        print("  !youtube on/off - เปิด/ปิดคอมเม้น YouTube")
        print("  !stats     - แสดงสถิติ")
        print("  !clear     - ล้างคิว")
        print("="*60 + "\n")
        
        return True
    
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
                
            except Exception as e:
                print(f"❌ Processing Error: {e}")
                queue_manager.finish_processing()
                await asyncio.sleep(1)
    
    async def _process_message(self, message: Message):
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
                
                # ส่งคำตอบกลับ (ไม่พูดออกเสียง)
                if message.channel_id:
                    await discord_bot.send_message(message.channel_id, response)
                
                return
            
            elif filter_result == FilterResult.REQUIRE_PERMISSION:
                print(f"🔐 ต้องขออนุญาต: {reason}")
                response = safety_filter.create_safe_response(filter_result, reason)
                
                if message.channel_id:
                    await discord_bot.send_message(message.channel_id, response)
                
                # TODO: รอการอนุญาต
                return
            
            # 2. เปลี่ยนสถานะเป็น THINKING
            await vtube_controller.set_state(AnimationState.THINKING)
            
            # 3. สร้างคำตอบจาก LLM
            response = await llm_handler.generate_response(message.content)
            
            if not response:
                print("❌ LLM ไม่สามารถสร้างคำตอบได้")
                return
            
            print(f"💬 คำตอบ: {response}")
            
            # 4. ส่งข้อความกลับ (ถ้าเป็น text)
            if message.source == MessageSource.DISCORD_TEXT:
                await discord_bot.send_message(message.channel_id, response)
            
            # 5. สร้างเสียง TTS + RVC
            await vtube_controller.start_speaking(response)
            
            audio_data, audio_path = await tts_rvc_handler.generate_speech(response)
            
            if audio_path:
                # 6. เล่นเสียง
                await discord_bot.play_audio(audio_path, message.channel_id)
                
                # รอให้พูดเสร็จ
                duration = tts_rvc_handler.estimate_duration(response)
                await asyncio.sleep(duration)
                
                # ลบไฟล์ชั่วคราว
                try:
                    Path(audio_path).unlink()
                except:
                    pass
            
            # 7. หยุดพูด
            await vtube_controller.stop_speaking()
            
            # แสดงเวลาประมวลผล
            elapsed = time.time() - start_time
            print(f"\n✅ ประมวลผลเสร็จ ({elapsed:.2f}s)")
            
            # ตรวจสอบว่าเกิน 10 วินาทีหรือไม่
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
        
        if self.processing_task:
            self.processing_task.cancel()
        
        await vtube_controller.disconnect()
        await discord_bot.close()
        
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
            
    except KeyboardInterrupt:
        print("\n\n⚠️ ได้รับสัญญาณหยุด (Ctrl+C)")
        await jeed.stop()
    
    except Exception as e:
        print(f"\n❌ Fatal Error: {e}")
        import traceback
        traceback.print_exc()
        await jeed.stop()

if __name__ == "__main__":
    # รัน async main
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 บ๊ายบาย~")