#!/usr/bin/env python3
import asyncio
import sys
from typing import List
from pathlib import Path

# ทำให้ Python มองเห็นแพ็กเกจในโฟลเดอร์ src
SRC_PATH = str(Path(__file__).parent / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

# ใช้ VTSClient จากโปรเจกต์เพื่อทดสอบการเชื่อมต่อ/รายการ hotkeys/ยิง hotkey
try:
    from adapters.vts.vts_client import VTSClient
    from core.config import get_settings
except Exception as e:
    print("Import error:", e)
    print("Run this script from project root: python test_vts_connection.py")
    sys.exit(1)

async def run_test(hotkeys: List[str] | None = None, duration: float = 60.0):
    settings = get_settings()
    vts = VTSClient()
    print("[TEST] Connecting to VTS ...")
    await vts.connect()
    # รอให้การเชื่อมต่อคงที่/รีเชื่อมต่อสำเร็จภายในช่วงเวลาที่กำหนด แทนที่จะออกทันที
    ok = False
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < 20.0:  # รอสูงสุด 20 วินาที
        if hasattr(vts, "_ws") and vts._ws is not None and getattr(vts._ws, "open", False):
            ok = True
            break
        await asyncio.sleep(0.1)
    if not ok:
        print("[TEST] Connection still unstable after 20s; continuing and will wait in-loop.")

    print("[TEST] Connected. Listing available hotkeys...")
    names = []
    try:
        hk = await vts.list_model_hotkeys()
        names = [str(h.get("name", "")) for h in hk if str(h.get("name", ""))]
        print(f"[TEST] Available hotkeys ({len(names)}):", names)
    except Exception as e:
        print("[TEST] Failed to list hotkeys:", e)

    if not names:
        print("[TEST] No hotkeys available from the current model. Please open a model in VTube Studio and ensure it has hotkeys.")
        # ลองใช้ชื่อจาก argument/ENV ถ้ามีเพื่อทดสอบการทริกเกอร์โดยตรง
        if hotkeys:
            names = hotkeys
    else:
        # เลือกจากพารามิเตอร์หรือใช้ตัวแรก
        chosen = hotkeys or names[:3]
        names = chosen
        print(f"[TEST] Will trigger hotkeys: {names}")
    
    # ยิง hotkey ทีละตัว และรอ
    t_end = asyncio.get_event_loop().time() + duration
    idx = 0
    while asyncio.get_event_loop().time() < t_end:
        # ถ้า connection หลุดระหว่างทดสอบ ให้รอจนกลับมา
        if not (hasattr(vts, "_ws") and vts._ws is not None and getattr(vts._ws, "open", False)):
            print("[TEST] Connection dropped. Waiting to reconnect...")
            wait_start = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - wait_start < 20.0:
                if hasattr(vts, "_ws") and vts._ws is not None and getattr(vts._ws, "open", False):
                    print("[TEST] Reconnected.")
                    break
                await asyncio.sleep(0.2)
        if names:
            name = names[idx % len(names)]
            try:
                print(f"[TEST] Trigger: {name}")
                await vts.trigger_hotkey_by_name(name)
            except Exception as e:
                print("[TEST] trigger failed:", e)
            idx += 1
        # คั่นด้วยการ recv loop ทำงานเอง, เราแค่รอ
        await asyncio.sleep(float(getattr(settings, "SAFE_HOTKEY_INTERVAL", 6.0)))

    print("[TEST] Done. Closing connection.")
    try:
        await vts.stop_all_motions()
    except Exception:
        pass

if __name__ == "__main__":
    # hotkeys จาก arg หรือ ENV SAFE_HOTKEY_NAMES
    hk_arg = None
    if len(sys.argv) > 1:
        hk_arg = [p.strip() for p in " ".join(sys.argv[1:]).split(",") if p.strip()]
    else:
        try:
            s = get_settings()
            if getattr(s, "SAFE_HOTKEY_NAMES", None):
                hk_arg = [p.strip() for p in str(s.SAFE_HOTKEY_NAMES).split(",") if p.strip()]
        except Exception:
            hk_arg = None
    asyncio.run(run_test(hotkeys=hk_arg))