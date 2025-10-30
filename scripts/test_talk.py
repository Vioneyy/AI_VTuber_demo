import os
import sys
import asyncio
import logging
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Ensure project root on sys.path to import src/* when running directly
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import using src package paths
from src.adapters.vts.vts_client import VTSClient
from src.adapters.vts.motion_controller import create_motion_controller
from src.adapters.tts.f5_tts_thai import create_tts_engine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_talk")


async def main():
    vts_host = os.getenv("VTS_HOST", "127.0.0.1")
    vts_port = int(os.getenv("VTS_PORT", "8001"))
    demo_text = os.getenv("DEMO_TEXT", "สวัสดีค่ะ ฉันพร้อมพูดคุยแล้ว")

    vts = VTSClient(host=vts_host, port=vts_port)
    await vts.connect()
    if not vts._is_connected():
        logger.error("VTS connect failed")
        return

    motion = create_motion_controller(vts, os.environ)
    await motion.start()

    # Build TTS and synthesize
    tts = create_tts_engine()
    audio_bytes = None
    try:
        if hasattr(tts, "synthesize"):
            audio_bytes = await asyncio.to_thread(tts.synthesize, demo_text)
        elif hasattr(tts, "speak"):
            audio_bytes = await asyncio.to_thread(tts.speak, demo_text)
    except Exception as e:
        logger.error(f"TTS synth failed: {e}", exc_info=True)

    if not audio_bytes:
        logger.error("No audio bytes generated from TTS")
    else:
        # Feed mouth envelope to motion
        try:
            series, interval_sec = await vts.compute_mouth_envelope(audio_bytes)
            if series:
                motion.set_mouth_envelope(series, interval_sec)
                # wait until envelope finishes
                await asyncio.sleep(len(series) * interval_sec + 1.0)
        except Exception as e:
            logger.error(f"Compute/Set mouth envelope failed: {e}", exc_info=True)

    # Graceful stop
    try:
        await motion.stop()
    except Exception:
        pass
    await vts.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 ยกเลิกการทดสอบด้วย Ctrl+C")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)