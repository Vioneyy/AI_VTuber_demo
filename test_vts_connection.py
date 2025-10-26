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
    ok = await vts.connect()
    print(f"[TEST] connect() returned: {ok}")
    print(f"[TEST] authenticated: {getattr(vts, 'authenticated', False)}")
    print(f"[TEST] ws present: {vts.ws is not None}")
    print(f"[TEST] ws.closed: {getattr(vts.ws, 'closed', True) if vts.ws else 'n/a'}")
    if vts.ws:
        print(f"[TEST] ws.open: {getattr(vts.ws, 'open', None)}")
        print(f"[TEST] ws.close_code: {getattr(vts.ws, 'close_code', None)}")
        print(f"[TEST] ws.close_reason: {getattr(vts.ws, 'close_reason', None)}")
    if not ok or not vts.authenticated or not vts.ws:
        print("[TEST] Connection failed: not authenticated / websocket object missing")
        return
    print("[TEST] Connected & authenticated. Listing available hotkeys...")
    try:
        hk = await vts.list_model_hotkeys()
    except Exception as e:
        print("[TEST] list_model_hotkeys failed:", e)
        hk = []
    names = [str(h.get("name", "")) for h in hk if str(h.get("name", ""))]
    print(f"[TEST] Available hotkeys ({len(names)}):", names)

    if not names:
        print("[TEST] No hotkeys available from the current model. Please open a model in VTube Studio and ensure it has hotkeys.")
    else:
        # เลือกจากพารามิเตอร์หรือใช้ตัวแรก
        chosen = hotkeys or names[:3]
        print(f"[TEST] Will trigger hotkeys: {chosen}")
    
    # ยิง hotkey ทีละตัว และรอ
    t_end = asyncio.get_event_loop().time() + duration
    idx = 0
    while asyncio.get_event_loop().time() < t_end:
        if names:
            name = chosen[idx % len(chosen)]
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