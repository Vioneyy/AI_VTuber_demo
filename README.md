# AI VTuber Demo

โปรเจกต์ตัวอย่างเพื่อสาธิตการเชื่อมต่อ LLM, TTS, และ VTube Studio พร้อมอะแดปเตอร์สำหรับ Discord และ YouTube Live (ปรับใหม่ให้ใช้ F5-TTS-Thai + Faster-Whisper)
โหมดปัจจุบัน: TTS-only (ลบ RVC ออกทั้งหมด)

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
     │  ├─ f5_tts_handler.py         # TTS ด้วย F5-TTS-Thai (คุณภาพเสียงธรรมชาติ)
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

### สวิตช์เปิด/ปิดโมดูล
- `DISCORD_ENABLED=true|false` เปิด/ปิดการทำงานของบอท Discord (ถ้าปิด ไม่จำเป็นต้องตั้ง `DISCORD_BOT_TOKEN`)
- `VTS_ENABLED=true|false` เปิด/ปิดการเชื่อมต่อ VTube Studio (ถ้าปิดจะข้ามการเชื่อมต่อและลูปแอนิเมชัน)

### STT (Faster-Whisper)
- ไม่ต้อง build อะไรเพิ่ม ติดตั้งผ่าน `pip install faster-whisper`
- ตั้งค่าภาษาที่ต้องการใน `.env` เช่น `WHISPER_LANG=th`
- รองรับ GPU อัตโนมัติผ่าน CTranslate2 (ขึ้นกับไลบรารีที่ติดตั้งโดยแพ็กเกจ)

### TTS (F5-TTS-Thai)
- ใช้ F5-TTS-Thai สำหรับสังเคราะห์เสียงภาษาไทยจากข้อความ
- ติดตั้ง `pip install f5-tts-th`
- แนะนำให้ตั้งค่าไฟล์อ้างอิงเสียงและข้อความอ้างอิงเพื่อให้เสียงคงเส้นคงวา

โหมดบังคับใช้เฉพาะ F5-TTS-Thai (ไม่ fallback):
- ตั้งค่าใน `.env`: `TTS_STRICT_ONLY=true`
- เมื่อเปิดโหมดนี้ หาก F5-TTS ใช้งานไม่ได้หรือเรียก API ไม่ถูกต้อง ระบบจะยกเลิกทันทีและไม่สลับไปใช้ Edge-TTS หรือเสียงเงียบ
- ค่าเริ่มต้นคือ `false` (อนุญาตให้ fallback เพื่อความสะดวกในการทดสอบ)

ตัวแปรที่เกี่ยวข้องใน `.env` (ตัวอย่าง):
- `TTS_ENGINE=f5_tts_thai`
- `TTS_DEVICE=cuda` หรือ `cpu`
- `TTS_REFERENCE_WAV=reference_audio/jeed_voice.wav`
- `F5_TTS_REF_AUDIO=reference_audio/jeed_voice.wav`
- `F5_TTS_REF_TEXT=สวัสดีค่ะ ฉันชื่อจีด`
- `F5_TTS_SPEED=1.0` (ปรับความเร็ว)
- `F5_TTS_STEPS=32` (จำนวนสเต็ป)
- `F5_TTS_CFG_STRENGTH=2.0` (ความแรงของ CFG)
- `F5_TTS_SAMPLE_RATE=24000` (ค่าเริ่มต้นของเสียงที่สังเคราะห์)
 - `TTS_STRICT_ONLY=true|false` (เปิด/ปิดโหมดไม่ fallback)

## การรัน (โหมดสาธิต)
```
python src/main.py
```

## ใช้บอทใน Discord
- คำสั่ง `!join` ให้บอทเข้าห้องเสียง
- พูดในห้องเสียง บอทจะถอดความด้วย Faster-Whisper และตอบเสียงด้วย F5-TTS-Thai
- คำสั่ง `!leave` ออกจากห้องเสียง

หมายเหตุ:
- บอทจะถอดความและพูดตอบโดยอัตโนมัติโดยใช้ F5-TTS-Thai เป็นฐานเสียง
- ข้อความที่ถอดความจะถูกส่งเข้า `QueueManager` และประมวลผลเหมือนข้อความแชทปกติ (ส่งต่อเข้า LLM, สร้าง TTS, ฯลฯ)

### RVC Server (Optional)
โปรเจกต์นี้ลบ RVC ภายในออกเพื่อความเรียบง่าย แต่หากต้องการใช้ voice conversion ภายนอก สามารถตั้งค่าเซิร์ฟเวอร์ RVC แยกต่างหากได้:
- เลือกใช้เครื่องมืออย่าง "RVC WebUI" หรือ "so-vits-svc"
- เตรียมโมเดลในโฟลเดอร์ `rvc_models/` (ไฟล์ที่มีอยู่เป็นตัวอย่างจากเวอร์ชันก่อนหน้า)
- รันเซิร์ฟเวอร์ RVC ให้รับ HTTP/WS บนเครื่องทดสอบ (เช่น `http://localhost:7865`)
- บอทนี้ไม่ได้เชื่อมต่อ RVC โดยตรง หากต้องการผสานเสียง ให้ประมวลผลไฟล์ที่ได้จาก TTS ด้วยเซิร์ฟเวอร์ RVC ภายนอก แล้วนำไฟล์ที่แปลงแล้วไปเล่นในระบบเสียงของคุณ

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
- โค้ด/สคริปต์ที่เกี่ยวกับ RVC ถูกลบออกจากโปรเจกต์เพื่อความเรียบง่าย
- หากต้องการกลับไปใช้ RVC สามารถดู commit เดิมใน Git history