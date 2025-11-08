# AI VTuber Demo

โปรเจกต์ตัวอย่างเพื่อสาธิตการเชื่อมต่อ LLM, TTS, และ VTube Studio พร้อมอะแดปเตอร์สำหรับ Discord และ YouTube Live (ปรับใหม่ให้ใช้ Edge-TTS + Faster-Whisper)
รองรับการแปลงเสียงผ่าน RVC แบบทางเลือกด้วยเซิร์ฟเวอร์ภายนอก

## โครงสร้าง
```
AI_VTuber_demo/
  ├─ README.md
  ├─ requirements.txt
  ├─ .env.example
  └─ src/
     ├─ main.py
     ├─ core/
     │  ├─ __init__.py
     │  ├─ config.py          # การตั้งค่าระบบ/ENV
     │  ├─ types.py           # dataclasses สำหรับข้อความ/อารมณ์/แหล่งข้อมูล
     │  ├─ scheduler.py       # คิวจัดลำดับความสำคัญและเวลาตอบภายใน 10วินาที
     │  └─ policy.py          # นโยบายตอบสนองและความเป็นส่วนตัว
     ├─ personality/
     │  ├─ __init__.py
     │  ├─ personality.py     # โหลด/จัดการบุคลิกภาพพื้นฐาน
     │  └─ persona.json       # ไฟล์กำหนดบุคลิกภาพ
     ├─ llm/
     │  ├─ __init__.py
     │  ├─ chatgpt_client.py  # ตัวเชื่อม API สมองหลัก
     │  └─ prompts/
     │     └─ system_prompt.txt
     ├─ adapters/
     │  ├─ __init__.py
     │  ├─ discord_bot.py     # รับข้อความ, เข้าห้องเสียง, เล่นเสียง
     │  ├─ youtube_live.py    # อ่านแชท YouTube แบบเรียงลำดับ
     │  └─ vts/
     ├─ audio/
     │  ├─ __init__.py
     │  ├─ edge_tts_handler.py        # TTS ด้วย Microsoft Edge (เร็ว/คุณภาพดี)
     │  ├─ rvc_adapter.py            # ตัวแปลงเสียงผ่าน RVC REST server (ทางเลือก)
     │  └─ faster_whisper_stt.py     # STT ด้วย Faster-Whisper (เร็ว/เสถียร)
     ├─ main.py
```

## การตั้งค่าและติดตั้ง
1) สร้าง virtual environment (Windows PowerShell):
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
2) ติดตั้งไลบรารี:
```
pip install -r requirements.txt
```
3) สร้างไฟล์ `.env` โดยอ้างอิงจาก `.env.example`

ตัวอย่างตัวแปรสำคัญที่ต้องตั้งค่า:
- `DISCORD_BOT_TOKEN` โทเคนบอท Discord
- `OPENAI_API_KEY` คีย์สำหรับสมองหลัก
- `YOUTUBE_STREAM_ID` ไอดีสตรีม YouTube Live
- `VTS_PLUGIN_NAME` ชื่อปลั๊กอิน VTS
- `VTS_PLUGIN_TOKEN` โทเคนสำหรับ VTS
- `LLM_MODEL` ชื่อโมเดลที่ใช้
- `LLM_TEMPERATURE` ความสุ่มของคำตอบ (แนะนำ 0.2–0.4 เพื่อให้กระชับ)
- `LLM_MAX_TOKENS` จำกัดความยาวคำตอบ (แนะนำ 128 เพื่อความเร็ว)
- `RESPONSE_TIMEOUT` ค่าเริ่มต้น 10 วินาที

### STT (Faster-Whisper)
- ไม่ต้อง build อะไรเพิ่ม ติดตั้งผ่าน `pip install faster-whisper`
- ตั้งค่าภาษาที่ต้องการใน `.env` เช่น `WHISPER_LANG=th`
- รองรับ GPU อัตโนมัติผ่าน CTranslate2 (ขึ้นกับไลบรารีที่ติดตั้งโดยแพ็กเกจ)

### TTS (Edge-TTS)
- ใช้ Microsoft Edge-TTS (ฟรี/เร็ว/เสียงธรรมชาติ)
- ติดตั้ง `pip install edge-tts`
- สามารถเลือกเสียงไทย เช่น `th-TH-PremwadeeNeural`, `th-TH-NiwatNeural`

## การรัน (โหมดสาธิต)
```
python src/main.py
```

## ใช้บอทใน Discord
- คำสั่ง `!join` ให้บอทเข้าห้องเสียง
- พูดในห้องเสียง บอทจะถอดความด้วย Faster-Whisper และตอบเสียงด้วย Edge-TTS
- คำสั่ง `!leave` ออกจากห้องเสียง

หมายเหตุ:
- บอทจะถอดความและพูดตอบโดยอัตโนมัติโดยใช้ Edge-TTS เป็นฐานเสียง
- หากตั้งค่า `ENABLE_RVC=true` และมีเซิร์ฟเวอร์ RVC พร้อมใช้งาน ระบบจะส่งเสียงไปแปลงผ่าน RVC แล้วเล่นใน Discord
- ข้อความที่ถอดความจะถูกส่งเข้า `QueueManager` และประมวลผลเหมือนข้อความแชทปกติ (ส่งต่อเข้า LLM, สร้าง TTS, ฯลฯ)

### RVC (ทางเลือก)
- ตั้งค่าใน `.env`:
  - `ENABLE_RVC=true`
  - `RVC_MODEL_PATH` ชี้ไปที่โมเดลใน `d:\AI_VTuber_demo\rvc_models\...`
  - `RVC_SERVER_URL` URL ของ REST endpoint สำหรับแปลงเสียง เช่น `http://localhost:7860/api/convert`
- รันเซิร์ฟเวอร์ RVC ที่รองรับการรับไฟล์เสียงและคืนไฟล์เสียงที่แปลงแล้ว (ตัวอย่างเช่น Mangio-RVC-WebUI ที่เพิ่ม REST API)
- หากการแปลงล้มเหลว ระบบจะ fallback เป็นเสียงจาก Edge-TTS ตามเดิม

## การปรับ Motion เพื่อความเสถียร
- ปรับการเร่ง/หน่วง (acceleration/deceleration) ให้เริ่ม-หยุดนุ่มนวลขึ้นผ่านการปรับโค้ง interpolation ในตัวควบคุมการเคลื่อนไหว
- ลดมุมเอียงศีรษะ (roll) ให้ไม่เกิน ~15° โดยลดค่าการเอียงใน action และเพิ่มการ clamp ระหว่างรันไทม์
- ลดการสั่นในแกน Y ระหว่าง idle เพื่อลดอาการเวียนหัว
- เพิ่มความสม่ำเสมอของรอยยิ้ม โดยคง base smile สูงและลด randomness
- ลด threshold การส่งมุมไปยัง VTS (epsilon) เพื่อให้การอัปเดตย่อย ๆ ไม่ถูกตัดทิ้งและการเคลื่อนไหวไม่สะดุด

### ตัวแปรสภาพแวดล้อมที่เกี่ยวข้อง
- `VTS_MOVEMENT_SMOOTHING` ค่าคุมความนุ่มนวลโดยรวม (ตัวอย่างจาก `.env` คือ 0.85)
- `VTS_UPDATE_DT` ช่วงเวลาอัปเดตเป็นวินาที
- `VTS_MOTION_INTENSITY` สเกลความแรงของ action
- `VTS_SEND_MIN_INTERVAL_MS` ควบคุมอัตราการส่งให้ VTS; ลดค่านี้เพื่อเพิ่มความถี่
- `VTS_SMOOTHNESS_GUARD` และ `VTS_SMOOTH_MAX_DELTA_*` ป้องกันการเปลี่ยนแปลงที่ฉับพลัน

### หมายเหตุการจูนเพิ่มเติม
- ค่ามาตรฐานใน `.env` ใช้งานได้ดี ไม่จำเป็นต้องแก้ หากต้องการเคลื่อนไหวเนียนขึ้น ให้ลองปรับ `VTS_MOVEMENT_SMOOTHING` ไปช่วง 0.88–0.92
- หากยังเอียงมากไป สามารถลดสเกล `FaceAngleZ` เพิ่มเติม หรือปรับช่วง clamp ใน `src/adapters/vts/motion_controller.py`
- ไม่มีหน้า Web UI สำหรับดูพฤติกรรม motion ในโปรเจกต์นี้ ขณะทดสอบให้สังเกตผลผ่านหน้าจอ VTube Studio โดยตรง

## หมายเหตุการล้างไฟล์เก่า
- โค้ด/สคริปต์ที่เกี่ยวกับ RVC และ whisper.cpp ถูกลบออกจากโปรเจกต์เพื่อความเรียบง่าย
- หากต้องการกลับไปใช้ whisper.cpp หรือ RVC สามารถดู commit เดิมใน Git history