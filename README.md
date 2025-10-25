# AI VTuber Demo

โปรเจกต์ตัวอย่างเพื่อสาธิตการเชื่อมต่อ LLM, TTS, และ VTube Studio พร้อมอะแดปเตอร์สำหรับ Discord และ YouTube Live

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
     │  ├─ discord_bot.py     # รับข้อความ, เข้าห้องเสียง, STT Whisper.cpp
     │  ├─ youtube_live.py    # อ่านแชท YouTube แบบเรียงลำดับ
     │  ├─ tts/
     │  └─ vts/
     ├─ audio/
     │  ├─ __init__.py
     │  ├─ rvc_v2.py          # RVC v2 (สคาฟโฟลด์)
     │  └─ stt_whispercpp.py  # ตัวห่อเรียก whisper.cpp ด้วย GPU
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

ตัวอย่าตต้องตั้งค่า:
- `DISCORD_BOT_TOKEN` โทเคนบอท Discord
- `OPENAI_API_KEY` คีย์สำหรับสมองหลัก
- `YOUTUBE_STREAM_ID` ไอดีสตรีม YouTube Live
- `VTS_PLUGIN_NAME` ชื่อปลั๊กอิน VTS
- `VTS_PLUGIN_TOKEN` โทเคนสำหรับ VTS
- `LLM_MODEL` ชื่อโมเดลที่ใช้
- `RESPONSE_TIMEOUT` ค่าเริ่มต้น 10 วินาที
- `TTS_ENGINE` ตั้งค่าเป็น `f5_tts_thai` เพื่อใช้ F5-TTS-THAI
- `TTS_REFERENCE_WAV` ไฟล์อ้างอิงเสียงผู้พูด (ช่วยกำหนดโทน)
- `ENABLE_RVC` เปิด/ปิดตัวแปลงเสียง RVC v2 (สคาฟโฟลด์)
- `VOICE_PRESET` พรีเซ็ตเสียง เช่น `anime_girl`, `deep_male`, `narrator`

### เพิ่มสำหรับ STT (Whisper.cpp)
- `WHISPER_CPP_BIN_PATH` พาธไปที่ `main.exe` ของ whisper.cpp
- `WHISPER_CPP_MODEL_PATH` พาธไปที่ไฟล์โมเดล ggml เช่น `ggml-small.bin`
- `WHISPER_CPP_LANG` ภาษาถอดความ (เช่น `th`)
- `WHISPER_CPP_THREADS` จำนวน threads (เช่น 4)
- `WHISPER_CPP_NGL` จำนวนเลเยอร์ offload ไป GPU (เช่น 35)
- `WHISPER_CPP_TIMEOUT_MS` เวลารอในมิลลิวินาที (เช่น 5000)
- `DISCORD_VOICE_STT_ENABLED` เปิด/ปิดคำสั่ง STT สำหรับเสียง

> หมายเหตุ: ต้อง build whisper.cpp ด้วย CUDA/cuBLAS หรือ OpenCL เพื่อให้ `-ngl` ใช้งาน GPU ได้

## การรัน (โหมดสาธิต)
```
python src/main.py
```

## ใช้ STT ใน Discord
- คำสั่ง `!join` ให้บอทเข้าห้องเสียง
- คำสั่ง `!stt <seconds>` บันทึกเสียงช่วงสั้น ๆ (ดีฟอลต์ 5 วินาที) แล้วถอดความด้วย Whisper.cpp
- คำสั่ง `!leave` ออกจากห้องเสียง

ข้อความที่ถอดความจะถูกส่งเข้า `PriorityScheduler` และประมวลผลเหมือนข้อความแชทปกติ (ส่งต่อเข้า LLM, สร้าง TTS, ฯลฯ)

## หมายเหตุเกี่ยวกับ RVC
- ฟีเจอร์ตัวอย่างเสียงและสคริปต์ทดสอบถูกถอดออกเพื่อความสะอาดของโปรเจกต์
- โปรเจกต์ยังรองรับ RVC ผ่านการตั้งค่าใน `.env`: `ENABLE_RVC` และ `VOICE_PRESET`
- การใช้งานจริงจะถูกเรียกผ่าน workflow หลักใน `src/main.py` เมื่อ TTS สร้างเสียงสำเร็จ