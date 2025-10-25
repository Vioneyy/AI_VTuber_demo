# การตั้งค่าและการทดสอบภายในเครื่อง (Local Setup)

เอกสารนี้อธิบายขั้นตอนการตั้งค่าโทเคน, สร้างเสียงตัวอย่าง, ตรวจคุณภาพเสียง และการทำงานร่วมกับโมดูลต่าง ๆ (ตัดเว็บเดโม่ออกแล้ว)

## 1) เตรียมสภาพแวดล้อม
- ติดตั้งไลบรารี: `pip install -r requirements.txt`
- สร้างไฟล์ `.env` (ตัวอย่างมีใน `.env.example`)
- ตั้งค่าโทเคน Hugging Face ใน `.env` (รองรับสองตัวแปร):
  - `HF_TOKEN=<your_token>`
  - `HUGGINGFACE_HUB_TOKEN=<your_token>`

> โปรเจกต์โหลด ENV ผ่าน `python-dotenv` ตั้งแต่เริ่มรัน

## 2) ล็อกอิน Hugging Face CLI (ทางเลือก)
- ใช้คำสั่งแบบไม่โต้ตอบ: `hf auth login --token <your_token>`
- ตรวจสอบผู้ใช้ปัจจุบัน: `hf auth whoami`

> ในโค้ด TTS จะตั้ง `HUGGINGFACE_HUB_TOKEN` อัตโนมัติหากพบโทเคนใน ENV

## 3) สร้างเสียงตัวอย่างและ RVC
- สคริปต์: `scripts/generate_sample.py`
- ผลลัพธ์:
  - `output/sample_sawasdee_raw.wav` (ก่อน RVC)
  - `output/sample_sawasdee.wav` (หลัง RVC ตามพรีเซ็ตใน `.env`)
- ตั้งค่าที่เกี่ยวข้องใน `.env`:
  - `TTS_ENGINE=f5_tts_thai` (ใช้เฉพาะ f5-tts-th)
  - `ENABLE_RVC=true|false`
  - `VOICE_PRESET=anime_girl|deep_male|narrator|neutral`
  - `TTS_REFERENCE_WAV=<path_to_speaker_ref.wav>` (ถ้ามี)
  - แนะนำ `F5_TTS_TIMEOUT_MS≈3000ms`, `RVC_TIMEOUT_MS=2000ms` ให้เป็นไปตามงบเวลา

## 4) ตรวจคุณภาพเสียง (QA)
- สคริปต์: `scripts/audio_quality_check.py`
- ตัวอย่างการใช้:
  - `python scripts/audio_quality_check.py output/sample_sawasdee_raw.wav output/sample_sawasdee.wav`
- รายงานจะถูกบันทึกที่: `output/qa_report.md`
- เมตริกที่วัด:
  - sample rate, duration
  - RMS/Peak (dBFS), clipping %, zero-crossing rate
  - spectral centroid (Hz) และการเปลี่ยนแปลงก่อน-หลัง

## 5) ทำงานร่วมกับ RVC จริง (อนาคต)
- ปัจจุบัน `audio/rvc_v2.py` เป็นพรีเซ็ตจำลอง (สคาฟโฟลด์)
- เมื่อพร้อมเชื่อม RVC v2 จริง ให้แทนที่ฟังก์ชัน `convert()` ด้วยการเรียกโมเดล/เซิร์ฟเวอร์จริง
- รักษาอินเตอร์เฟซ: `convert(audio_bytes: bytes, preset: str) -> bytes`

## 6) ทำงานร่วมกับ LLM (ChatGPT API)
- ตั้งค่าใน `.env`: `OPENAI_API_KEY`, `LLM_MODEL`
- โค้ดเชื่อมต่ออยู่ใน `src/llm/chatgpt_client.py`
- ระบบโหลด `LLM_MODEL` ผ่าน `get_settings()` เพื่อรองรับสลับโมเดลในอนาคต

## 7) เวิร์กโฟลว์แนะนำ (End-to-End)
1. ตั้งค่า `.env` โทเคนและพารามิเตอร์ TTS/RVC
2. รัน `python scripts/generate_sample.py` เพื่อสร้างไฟล์ตัวอย่าง RAW/RVC (มี RVC timeout)
3. รัน `python scripts/audio_quality_check.py output/sample_sawasdee_raw.wav output/sample_sawasdee.wav`
4. ปรับค่า `F5_TTS_*`, `RVC_TIMEOUT_MS`, `VOICE_PRESET` ให้ผ่านงบเวลาและคุณภาพที่ต้องการ

## 8) ข้อควรทราบ
- หากพบ 401 Unauthorized ในการโหลดโมเดฝ ให้ตรวจสอบว่าได้ตั้งค่าโทเคนและยอมรับเงื่อนไขโมเดฝบน Hugging Face แล้ว
- การวัด QA เป็นเชิงสถิติเบื้องต้น เหมาะกับการตรวจสอบความสม่ำเสมอของสัญญาณและไม่มี clipping
- หากแก้ `.env` แล้ว ควรรีสตาร์ทโปรเซสที่เกี่ยวข้องกัชน (เช่น สคริปต์) เพื่อโหลดค่าใหม่
- ถ้าโมดูล TTS ใช้เวลานานในการตอบครั้งแรก ให้เพิ่ม `F5_TTS_TIMEOUT_MS` เพื่อหลีกเลี่ยงการค้าง และใช้ผลลัพธ์ fallback ระหว่าง