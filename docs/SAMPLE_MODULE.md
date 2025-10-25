# โมดูลสร้างเสียงตัวอย่าง (Sample Voice Module)

โมดูลนี้ช่วยให้ระบบ AI VTuber สร้างเสียงตัวอย่างที่ปรับแต่งได้ และเชื่อมต่อกับส่วนอื่น ๆ ในโปรเจกต์ได้ทั้งแบบเรียกฟังก์ชันโดยตรงและผ่าน API

## คุณสมบัติหลัก
- เรียกใช้โดยตรงผ่านคลาส `SampleVoiceService` (Python)
- ปรับพารามิเตอร์ต่อคำเรียก: `speed`, `gain_db`, `emotion`
- รองรับการแปลงเสียงด้วย RVC (สคาฟโฟลด์) ผ่านพรีเซ็ต `voice_preset`

- สคริปต์ทดสอบการทำงานร่วมกัน: `scripts/integration_test.py` สร้างเสียงและรัน QA อัตโนมัติ

## การใช้งานแบบฟังก์ชัน (Python)

ตัวอย่าง:

```python
from src.audio.sample_generator import SampleVoiceService, SampleOptions

svc = SampleVoiceService()
audio = svc.generate(
    "สวัสดีจากโมดูลตัวอย่าง",
    SampleOptions(speed=1.1, gain_db=2.0, emotion="neutral", apply_rvc=True, voice_preset="anime_girl")
)
paths = svc.save_files("output", audio, raw_name="sample_raw.wav", proc_name="sample_rvc.wav")
print(paths)
```

ผลลัพธ์:
- `output/sample_raw.wav` (ก่อน RVC)
- `output/sample_rvc.wav` (หลัง RVC)



## ทดสอบการทำงานร่วมกัน (Integration Test)

ใช้สคริปต์:

```
python scripts/integration_test.py
```

ฟังก์ชันนี้จะ:
- ใช้ LLM (ถ้ามี `OPENAI_API_KEY`) เพื่อสร้างข้อความทักทาย
- สร้างเสียงตัวอย่างด้วย `SampleVoiceService`
- บันทึกไฟล์ `output/integration_raw.wav` และ `output/integration_rvc.wav`
- รัน `scripts/audio_quality_check.py` เพื่อสร้าง `output/qa_report.md`

## การตั้งค่าเกี่ยวข้อง (.env)

- `TTS_ENGINE=f5_tts_thai`
- `F5_TTS_SPEED=1.0` (ค่าเริ่มต้น, สามารถ override ต่อคำเรียกด้วย `options.speed`)
- `ENABLE_RVC=true|false`
- `VOICE_PRESET=anime_girl|deep_male|narrator|neutral`
- `TTS_REFERENCE_WAV=<path_to_speaker_ref.wav>` (ถ้ามี)

## แนวทางการปรับคุณภาพเสียง

- ปรับ `speed` เพื่อควบคุมจังหวะการพูด (0.8–1.2 แนะนำ)
- ปรับ `gain_db` เพื่อเพิ่ม/ลดระดับเสียงโดยรวม (–6 ถึง +6 dB)
- เลือก `voice_preset` ให้เหมาะกับบุคลิก VTuber; เมื่อเชื่อม RVC จริง สามารถขยายพรีเซ็ตเพิ่มเติม
- ใช้รายงานจาก `audio_quality_check.py` เพื่อสอบทาน RMS/Peak, clipping และสเปกตรัม