from __future__ import annotations
from pathlib import Path
import sys
import os
import json
import subprocess

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from src.core.config import get_settings
from src.audio.sample_generator import SampleVoiceService, SampleOptions


def maybe_generate_text() -> str:
    settings = get_settings()
    prompt = "เขียนประโยคทักทายสั้นๆ เป็นภาษาไทย น้ำเสียงเป็นมิตร"
    if settings.OPENAI_API_KEY:
        try:
            from src.llm.chatgpt_client import ChatGPTClient
            llm = ChatGPTClient()
            msg = type("Msg", (), {"text": prompt})
            resp = llm.generate_reply(msg.text, system_prompt="", persona={})
            return resp.text.strip() or "สวัสดีจากโมดูลทดสอบ"
        except Exception as e:
            print(f"LLM generation failed: {e}")
    return "สวัสดีจากระบบตัวอย่าง AI VTuber"


def run_audio_qa(raw_path: Path, proc_path: Path) -> Path:
    qa_script = BASE_DIR / "scripts" / "audio_quality_check.py"
    out_dir = BASE_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    if qa_script.exists():
        subprocess.run([sys.executable, str(qa_script), str(raw_path), str(proc_path)], check=False)
    return out_dir / "qa_report.md"


def main():
    settings = get_settings()
    text = maybe_generate_text()
    print(f"[LLM] ข้อความทดสอบ: {text}")

    svc = SampleVoiceService()
    opts = SampleOptions(
        speed=float(settings.F5_TTS_SPEED),
        gain_db=0.0,
        emotion=settings.TTS_EMOTION_DEFAULT,
        apply_rvc=settings.ENABLE_RVC,
        voice_preset=settings.VOICE_PRESET,
    )
    audio = svc.generate(text, opts)
    out = svc.save_files(str(BASE_DIR / "output"), audio, raw_name="integration_raw.wav", proc_name="integration_rvc.wav")
    print(json.dumps({"saved": out}, ensure_ascii=False))

    report = run_audio_qa(Path(out["raw"]), Path(out["processed"]))
    if report.exists():
        print(f"[QA] รายงานคุณภาพเสียง: {report}")
    else:
        print("[QA] ไม่พบไฟล์รายงาน (audio_quality_check.py อาจไม่ทำงาน)")


if __name__ == "__main__":
    main()