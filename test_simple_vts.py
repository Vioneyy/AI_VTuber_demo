#!/usr/bin/env python3
"""
Simple VTS Connection Test
ทดสอบการเชื่อมต่อ VTS แบบง่าย
"""

import asyncio
import sys
from pathlib import Path

# เพิ่ม src path
SRC_PATH = str(Path(__file__).parent / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

try:
    from adapters.vts.motion_controller import VTSHumanMotionController
except Exception as e:
    print("Import error:", e)
    sys.exit(1)

async def simple_test():
    """ทดสอบการเชื่อมต่อแบบง่าย (โครงสร้างใหม่: motion_controller)"""
    print("🔄 กำลังทดสอบการเชื่อมต่อ VTube Studio ด้วย VTSHumanMotionController...")

    ctrl = VTSHumanMotionController()

    try:
        print("1. กำลังเชื่อมต่อ...")
        await ctrl.connect()

        print("2. กำลังยืนยันตัวตน...")
        ok = await ctrl.authenticate()
        if not ok:
            print("❌ การยืนยันตัวตนล้มเหลว")
            return

        print("✅ เชื่อมต่อและยืนยันตัวตนสำเร็จ!")
        print(f"3. WebSocket อยู่: {ctrl.ws is not None}")

        # ดึงและแมป parameters ของโมเดล
        print("4. กำลังดึงพารามิเตอร์ของโมเดล...")
        await ctrl._resolve_param_map()
        mapped = {k: v for k, v in ctrl.param_map.items() if v}
        print(f"5. แมปพารามิเตอร์สำเร็จ: {len(mapped)}/{len(ctrl.param_map)} รายการ")
        for k, v in mapped.items():
            print(f"   - {k} → {v}")

        # รอสักครู่เพื่อทดสอบ keepalive
        print("6. รอ 3 วินาที เพื่อทดสอบ keepalive...")
        await asyncio.sleep(3)
        closed_status = getattr(ctrl.ws, 'closed', 'unknown') if ctrl.ws else 'unknown'
        print(f"7. สถานะ WebSocket หลัง 3 วินาที: {closed_status}")

        print("✅ การทดสอบเสร็จสิ้น")

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {e}")
        import traceback
        traceback.print_exc()

    finally:
        try:
            await ctrl.disconnect()
            print("🔌 ปิดการเชื่อมต่อแล้ว")
        except Exception as e:
            print(f"⚠️ ปิดการเชื่อมต่อล้มเหลว: {e}")

if __name__ == "__main__":
    asyncio.run(simple_test())