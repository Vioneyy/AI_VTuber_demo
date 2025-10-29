"""
VTuber Human-Like Motion Controller for VTube Studio (entry script)
รันสคริปต์นี้เพื่อเริ่ม motion โดยโหลดโมดูลจาก src/adapters/vts/motion_controller
"""

import asyncio
import os
import sys

# ให้ Python มองเห็นรากโปรเจกต์เพื่อ import "src.*"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.adapters.vts.motion_controller import run_motion


async def main():
    await run_motion()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Shutdown by user")