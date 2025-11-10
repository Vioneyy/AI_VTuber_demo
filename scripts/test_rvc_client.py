"""
ทดสอบการเชื่อมต่อ RVC Server กับโมเดลใน rvc_models/
- สร้างเสียงจาก F5-TTS-Thai
- ส่งเข้า RVC เพื่อแปลงเสียง
- บันทึกไฟล์ก่อนและหลังแปลงเพื่อเทียบผล

การตั้งค่า:
- ใน .env: ตั้งค่า RVC_ENABLED=true, RVC_SERVER_URL, RVC_MODEL_PTH, RVC_MODEL_INDEX
"""

import os
import sys
import asyncio
from pathlib import Path

import numpy as np
try:
    # โหลด .env จากรากโปรเจกต์เพื่อให้ตัวแปรสิ่งแวดล้อมพร้อมใช้
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# เพิ่ม project root ลงใน sys.path เพื่อให้ import 'src.*' ได้ไม่ว่ารันจากที่ใด
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# โหลด .env ก่อนทำงาน เพื่อให้ RVC_ENABLED/RVC_WEBUI_DIR ถูกอ่านได้
if load_dotenv:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path), override=False)
    else:
        load_dotenv()

async def gen_tts(text: str):
    from src.audio.f5_tts_handler import F5TTSHandler
    tts = F5TTSHandler()
    audio, sr = await tts.generate_speech(text)
    return audio, sr

def save_wav(path: Path, audio: np.ndarray, sr: int):
    import soundfile as sf
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio.astype('float32'), sr)

def run_rvc(audio: np.ndarray, sr: int):
    from src.adapters.rvc.rvc_client import RVCClient
    client = RVCClient()
    return client.convert(audio, sr)

async def main():
    text = "สวัสดีค่ะ ฉันชื่อจีด กำลังทดสอบระบบ RVC"
    # เปิด RVC WebUI อัตโนมัติถ้าตั้งค่า RVC_ENABLED=true และกำหนด RVC_WEBUI_DIR
    try:
        from src.adapters.rvc.rvc_server_launcher import ensure_server_running
        started = ensure_server_running()
        if started:
            print("✅ RVC WebUI พร้อมใช้งาน")
        else:
            # บอกเหตุผลที่เป็นไปได้
            rvc_enabled = os.getenv("RVC_ENABLED", "false").lower() == "true"
            webui_dir = os.getenv("RVC_WEBUI_DIR", "")
            if not rvc_enabled:
                print("ℹ️ ไม่ได้เปิด RVC WebUI อัตโนมัติ (RVC_ENABLED=false)")
            elif not webui_dir:
                print("ℹ️ ไม่ได้เปิด RVC WebUI อัตโนมัติ (ยังไม่ได้ตั้งค่า RVC_WEBUI_DIR)")
            else:
                print("ℹ️ ไม่ได้เปิด RVC WebUI อัตโนมัติ (ตรวจสอบพาธ infer-web.py และพอร์ต)")
    except Exception as e:
        print(f"⚠️ เปิด RVC WebUI อัตโนมัติผิดพลาด: {e}")
    print("🔊 สร้างเสียง TTS...")
    audio, sr = await gen_tts(text)
    if audio is None or len(audio) == 0:
        print("❌ TTS ล้มเหลว")
        return
    save_wav(Path("temp/rvc_test_tts.wav"), audio, sr)
    print(f"✅ บันทึก TTS: temp/rvc_test_tts.wav ({sr} Hz)")

    print("🎚️ ส่งเข้า RVC Server...")
    conv_audio, conv_sr = run_rvc(audio, sr)
    save_wav(Path("temp/rvc_test_converted.wav"), conv_audio, conv_sr)
    print(f"✅ บันทึก RVC: temp/rvc_test_converted.wav ({conv_sr} Hz)")
    print("🎉 เสร็จสิ้น ลองฟังไฟล์เพื่อเทียบผลได้เลย")

if __name__ == "__main__":
    asyncio.run(main())