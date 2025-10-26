#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

# ให้ Python มองเห็นแพ็กเกจในโฟลเดอร์ src
SRC_PATH = str(Path(__file__).parent / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

try:
    from adapters.vts.vts_client import VTSClient
    from core.config import get_settings
except Exception as e:
    print("Import error:", e)
    print("Run this script from project root: python run_vts_motion.py")
    raise

async def run_motion(duration: float = 120.0):
    settings = get_settings()
    vts = VTSClient(host="127.0.0.1", port=8001)
    print("[MOTION] Connecting to VTS ...")
    ok = await vts.connect()
    if not ok or not vts.authenticated or not vts.ws or getattr(vts.ws, "closed", True):
        print("[MOTION] ❌ ไม่สามารถเชื่อมต่อ/Authenticate กับ VTS ได้ — โปรดเปิด VTube Studio และ Allow plugin ที่พอร์ต 8001")
        return

    # เริ่มลูปการขยับพื้นฐานแบบ context-aware
    await vts.start_idle_loop()

    async def simulate_moods():
        moods = ["neutral", "thinking", "happy", "sad"]
        while True:
            vts.set_context_mood(random.choice(moods))
            await asyncio.sleep(random.uniform(8, 16))

    async def simulate_speaking():
        while True:
            vts.set_speaking(True)
            for _ in range(random.randint(30, 80)):
                amp = max(0.0, min(1.0, random.random()))
                vts.update_speech_amplitude(amp)
                await asyncio.sleep(0.05)
            vts.set_speaking(False)
            await asyncio.sleep(random.uniform(6, 14))

    mood_task = asyncio.create_task(simulate_moods())
    speak_task = asyncio.create_task(simulate_speaking())

    # วนรอให้การขยับทำงานต่อเนื่อง พร้อมรอการ reconnect หากหลุด
    t_end = asyncio.get_event_loop().time() + duration
    while asyncio.get_event_loop().time() < t_end:
        await asyncio.sleep(1.0)

    print("[MOTION] Done. Stopping motions and closing.")
    for t in (mood_task, speak_task):
        try:
            t.cancel()
        except Exception:
            pass
    try:
        await vts.stop_idle_loop()
    except Exception:
        pass

if __name__ == "__main__":
    import random
    asyncio.run(run_motion())