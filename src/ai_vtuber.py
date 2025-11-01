import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

async def process_message(self, message: dict):
    """ประมวลผล message แต่ละอัน"""
    source = message['source']
    content = message['content']
    metadata = message.get('metadata', {})
    
    logger.info(f"▶️ Processing:  [{source}] {content}")
    
    try:
        # 1. สร้าง response
        response_text = await self.response_gen.generate_response(content)
        logger.info(f"💬 Response generated: {response_text}")
        
        # 2. สร้างเสียง TTS
        logger.info("🎤 กำลังสร้างเสียง...")
        audio_file = await self.tts.generate(response_text)
        
        if not audio_file:
            logger.error("❌ ไม่สามารถสร้างเสียงได้")
            return
        
        logger.info(f"✅ สร้างเสียงสำเร็จ: {audio_file}")
        
        # 3. อ่านไฟล์เสียง
        try:
            with open(audio_file, 'rb') as f:
                audio_data = f.read()
            logger.info(f"📁 อ่านไฟล์เสียงแล้ว: {len(audio_data)} bytes")
        except Exception as e:
            logger.error(f"❌ ไม่สามารถอ่านไฟล์เสียงได้: {e}")
            return
        
        # 4. เล่นเสียงตาม source
        if source == 'discord_text':
            voice_client = metadata.get('voice_client')
            ctx = metadata.get('ctx')
            
            if voice_client and voice_client.is_connected():
                logger.info("🔊 กำลังเล่นเสียงใน Discord...")
                
                # แปลง audio_data เป็น PCM format สำหรับ Discord
                try:
                    import io
                    from pydub import AudioSegment
                    
                    # โหลดไฟล์เสียง
                    audio = AudioSegment.from_file(io.BytesIO(audio_data))
                    
                    # แปลงเป็น PCM format ที่ Discord ต้องการ
                    # 48kHz, 16-bit, 2 channels (stereo)
                    audio = audio.set_frame_rate(48000).set_channels(2).set_sample_width(2)
                    
                    # Export เป็น raw PCM
                    pcm_audio = io.BytesIO()
                    audio.export(pcm_audio, format='s16le', codec='pcm_s16le')
                    pcm_audio.seek(0)
                    
                    # เล่นใน Discord
                    success = await self.discord_bot.play_audio(pcm_audio.read(), voice_client)
                    
                    if success:
                        logger.info("✅ เล่นเสียงใน Discord สำเร็จ")
                        if ctx:
                            await ctx.send(f"✅ **ตอบ:** {response_text}")
                    else:
                        logger.error("❌ เล่นเสียงใน Discord ไม่สำเร็จ")
                        if ctx:
                            await ctx.send(f"⚠️ เล่นเสียงไม่สำเร็จ แต่ตอบว่า: {response_text}")
                
                except ImportError:
                    logger.error("❌ ต้องติดตั้ง pydub: pip install pydub")
                    if ctx:
                        await ctx.send("❌ ต้องติดตั้ง pydub ก่อน")
                except Exception as e:
                    logger.error(f"❌ แปลงเสียงผิดพลาด: {e}", exc_info=True)
                    if ctx:
                        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")
            else:
                logger.warning("⚠️ Voice client ไม่ได้เชื่อมต่อ")
                if ctx:
                    await ctx.send("⚠️ ไม่ได้เชื่อมต่อ voice channel")
        
        else:
            # เล่นแบบปกติ (local)
            logger.info("🔊 เล่นเสียงแบบ local...")
            await self.audio_player.play(audio_file)
        
        # 5. Motion (ถ้ามี)
        await self.motion_controller.trigger_motion("talking")
        
        logger.info("✅ ประมวลผลเสร็จสิ้น")
        
    except Exception as e:
        logger.error(f"❌ Process message error: {e}", exc_info=True)
        raise


# --- Standalone entrypoint ---
def _ensure_project_root_on_path():
    """ทำให้สามารถ import โมดูลจากแพ็กเกจ src ได้เมื่อรันไฟล์นี้โดยตรง"""
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def _import_run():
    """พยายาม import ฟังก์ชัน run_vts_demo จาก main โดยรองรับทั้งแพ็กเกจและสคริปต์"""
    try:
        # เมื่อมีโครงสร้างแพ็กเกจ src
        from src.main import run_vts_demo
        return run_vts_demo
    except ModuleNotFoundError:
        # เมื่อรันจากในโฟลเดอร์ src โดยตรง
        from main import run_vts_demo
        return run_vts_demo


if __name__ == "__main__":
    _ensure_project_root_on_path()
    run_vts_demo = _import_run()

    import argparse
    parser = argparse.ArgumentParser(description="Run AI VTuber demo standalone")
    parser.add_argument("--duration", type=float, default=25.0, help="เวลารัน motion (วินาที), 0 = ต่อเนื่อง")
    args = parser.parse_args()

    logger.info("🚀 เริ่มรัน AI VTuber demo แบบเดี่ยวผ่าน ai_vtuber.py")
    try:
        asyncio.run(run_vts_demo(duration_sec=args.duration))
    except KeyboardInterrupt:
        logger.info("🛑 หยุดโดยผู้ใช้ (Ctrl+C)")
    except Exception as e:
        logger.exception(f"เกิดข้อผิดพลาดระหว่างการรัน: {e}")