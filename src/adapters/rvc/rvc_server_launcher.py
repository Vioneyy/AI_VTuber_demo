"""
RVC WebUI server launcher
- ตรวจสอบว่า RVC WebUI เปิดอยู่หรือไม่
- หากยังไม่เปิดและ RVC_ENABLED=true จะพยายามเปิด infer-web.py โดยใช้พาธใน .env:RVC_WEBUI_DIR
- รองรับ Windows
"""

import os
import sys
import time
import logging
import subprocess
from urllib.parse import urlparse
from pathlib import Path

import requests
try:
    # โหลด .env จากรากโปรเจกต์เพื่อให้ os.getenv ใช้ค่าในไฟล์นี้ได้
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parents[3]
    ENV_PATH = BASE_DIR / ".env"
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=str(ENV_PATH), override=False)
    else:
        load_dotenv()
except Exception:
    # ถ้าไม่มี dotenv ก็ข้ามไป (จะใช้ค่า env ที่มีอยู่ในระบบ)
    pass

logger = logging.getLogger(__name__)


def _is_server_up(url: str, timeout: float = 1.5) -> bool:
    try:
        resp = requests.get(url.rstrip('/'), timeout=timeout)
        return resp.status_code < 500
    except Exception:
        return False


def ensure_server_running() -> bool:
    """พยายามให้ RVC WebUI เปิดทำงาน ถ้าพร้อมแล้วคืน True"""
    if os.getenv("RVC_ENABLED", "false").lower() != "true":
        logger.debug("RVC not enabled; skip server launch")
        return False

    server_url = os.getenv("RVC_SERVER_URL", "http://localhost:7865").strip()
    webui_dir = os.getenv("RVC_WEBUI_DIR", "").strip()
    # หากไม่ได้ตั้งค่า RVC_WEBUI_DIR ลองเดาค่า default ที่พบบ่อย
    if not webui_dir:
        candidates = [
            str(Path(server_url).anchor) if hasattr(Path(server_url), 'anchor') else "",
            str(Path(__file__).resolve().parents[3] / "Retrieval-based-Voice-Conversion-WebUI"),
            r"d:\\Retrieval-based-Voice-Conversion-WebUI",
            r"D:\\Retrieval-based-Voice-Conversion-WebUI",
        ]
        for c in candidates:
            if c and os.path.isdir(c):
                webui_dir = c
                break

    # เช็คว่ามีเซิร์ฟเวอร์อยู่แล้วหรือไม่
    if _is_server_up(server_url):
        logger.info(f"✅ พบ RVC WebUI แล้วที่ {server_url}")
        return True

    # หากไม่พบ ลองเปิดใหม่ถ้าระบุ path ไว้
    if not webui_dir:
        logger.warning("⚠️ RVC WebUI ไม่ได้เปิดและไม่ได้ตั้งค่า RVC_WEBUI_DIR ใน .env — ข้ามการเปิดอัตโนมัติ")
        return False

    infer_py = os.path.join(webui_dir, "infer-web.py")
    if not os.path.isfile(infer_py):
        logger.warning(f"⚠️ ไม่พบ infer-web.py ที่ {infer_py}; ตรวจสอบ RVC_WEBUI_DIR")
        return False

    # หา port จาก URL
    parsed = urlparse(server_url)
    port = parsed.port or (7865 if parsed.scheme == 'http' else 443)

    # เลือก Python ที่จะใช้รัน infer-web.py
    # 1) อนุญาตให้ตั้งค่าเองผ่านตัวแปร RVC_PYTHON
    # 2) ถ้ามี venv ภายในโฟลเดอร์ RVC ให้ใช้ตัวนั้น
    # 3) ถ้าไม่พบ ใช้ Python ปัจจุบัน (sys.executable)
    python_exec = os.getenv("RVC_PYTHON", "").strip()
    if not python_exec:
        candidates = [
            os.path.join(webui_dir, ".venv", "Scripts", "python.exe"),
            os.path.join(webui_dir, "venv", "Scripts", "python.exe"),
            os.path.join(webui_dir, "env", "Scripts", "python.exe"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                python_exec = p
                break
    if not python_exec:
        python_exec = sys.executable

    # สร้างคำสั่งเปิดเซิร์ฟเวอร์
    cmd = [python_exec, infer_py, "--port", str(port)]
    extra_args = os.getenv("RVC_WEBUI_ARGS", "").strip()
    if extra_args:
        cmd.extend(extra_args.split())

    try:
        logger.info(f"🚀 กำลังเปิด RVC WebUI: {' '.join(cmd)} (cwd={webui_dir})")
        # เปิดเป็น background process
        creationflags = 0
        if sys.platform.startswith('win'):
            # ไม่ต้องเปิด console ใหม่
            creationflags = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(
            cmd,
            cwd=webui_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        # รอจนกว่าจะพร้อม
        deadline = time.time() + 60
        while time.time() < deadline:
            if _is_server_up(server_url, timeout=1.5):
                logger.info(f"✅ RVC WebUI พร้อมแล้วที่ {server_url}")
                return True
            time.sleep(2)
        logger.warning("⚠️ เปิด RVC WebUI ไม่สำเร็จภายในเวลาที่กำหนด")
        return False
    except Exception as e:
        logger.warning(f"⚠️ เปิด RVC WebUI ล้มเหลว: {e}")
        return False


if __name__ == "__main__":
    # ตั้งค่า logging ให้เห็นบน console ทันที
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    # เรียกตรวจ/เปิด RVC WebUI โดยตรงเมื่อรันไฟล์นี้
    ok = ensure_server_running()
    if ok:
        print("✅ RVC WebUI พร้อมใช้งานหรือเปิดสำเร็จแล้ว")
        sys.exit(0)
    else:
        # หมายเหตุ: หาก RVC_ENABLED=false หรือไม่พบ infer-web.py จะมองเป็นสถานะไม่พร้อมใช้งาน
        print("⚠️ RVC WebUI ยังไม่พร้อมใช้งานหรือเปิดไม่สำเร็จ")
        sys.exit(1)