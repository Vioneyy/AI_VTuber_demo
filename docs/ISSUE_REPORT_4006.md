# รายงานปัญหา: Discord Voice invalid session (4006)

## สรุปปัญหา
- ระบบ AI VTuber เริ่มทำงานครบทุกคอมโพเนนต์ (PersonalityManager, ChatGPT Client, VTS Client, Motion Controller, TTS Engine) แล้ว
- ขณะบอทพยายามเชื่อมต่อเข้า voice channel เกิดข้อผิดพลาดจาก Discord: `ClientException` โดย WebSocket ปิดด้วยรหัส `4006` (invalid session)
- ระบบมีการจัดการข้อผิดพลาด: ทำการ cleanup voice client และแจ้งว่า “❌ Voice invalid session (4006) — cleaned up. Will retry later.”
- บอทถูกตัดการเชื่อมต่อจาก voice channel และหยุดการทำงานของ process เพื่อหลีกเลี่ยงสภาวะค้าง

## สภาพแวดล้อมและการตั้งค่า
- ระบบปฏิบัติการ: Windows
- ไลบรารีหลัก: Discord bot, VTube Studio client, TTS F5-TTS-Thai
- ค่าที่เกี่ยวข้องใน `.env` (ไม่มีการใส่ token จริงในรายงานนี้):
  - `DISCORD_BOT_TOKEN=<set in local .env>`
  - `DISCORD_AUTO_JOIN=false`
  - `DISCORD_VOICE_STT_ENABLED=true`
  - `VTS_HOST=127.0.0.1`, `VTS_PORT=8001`
  - `TTS_ENGINE=f5_tts_thai`

## ขั้นตอนทำซ้ำ (Reproduction Steps)
- รันคำสั่งเริ่มระบบ:
  - `python -m src.ai_vtuber`
- ตรวจสอบใน Discord ให้บอทออนไลน์และพยายามเข้าห้องเสียง (เช่น Lobby)
- สังเกต log ใน Terminal และข้อความแจ้งเตือนใน Discord

## Log ที่เกี่ยวข้อง (จาก Terminal)
```
[Startup] PersonalityManager ✅
[Startup] ChatGPT Client ✅
[Startup] VTS Client connected (host=127.0.0.1, port=8001) ✅
[Startup] Motion Controller started ✅
[Startup] TTS Engine: f5_tts_thai ✅
[Startup] Loading TTS model and vocoder...

[Discord] Bot logged in ✅
[Discord] Attempting to connect voice to channel: Lobby
[Discord] ClientException: Voice WebSocket closed with code 4006 (invalid session)
[Discord] Cleanup voice client
❌ Voice invalid session (4006) — cleaned up. Will retry later.
[Discord] Bot disconnected from voice channel
```

### Terminal Snapshot #1–8 (ตามที่ผู้ใช้ระบุ)
```
PS D:\AI_VTuber_demo> & d:/AI_VTuber_demo/.venv/Scripts/Activate.ps1
(.venv) PS D:\AI_VTuber_demo> & d:/AI_VTuber_demo/.venv/Scripts/python.exe d:/AI_VTuber_demo/src/ai_vtuber.py
(.venv) PS D:\AI_VTuber_demo> & d:/AI_VTuber_demo/.venv/Scripts/python.exe d:/AI_VTuber_demo/src/ai_vtuber.py
(.venv) PS D:\AI_VTuber_demo>
```
หมายเหตุ: บรรทัดที่ 8 คือ prompt ที่ว่าง (idle) หลังรันคำสั่ง

## ข้อความแจ้งเตือนใน Discord (ตัวอย่าง)
- `Voice invalid session (4006). โปรดตรวจ firewall/UDP และลองใหม่`

## การจัดการข้อผิดพลาดในระบบ (ยืนยันแล้วว่าทำงาน)
- ระบบทำการบันทึกและแสดงข้อความชัดเจนเมื่อพบ `4006`
- ตั้งค่าและบันทึกสถานะ เช่น `last_voice_close_code=4006`, `last_voice_error`
- ทำการ cleanup voice client เพื่อให้ระบบไม่ค้าง
- แนะนำให้สั่งคำสั่งช่วยตรวจสอบ: `!voicelog` และลอง `!join` อีกครั้งหลังตรวจสภาพแวดล้อม

## สมมติฐานสาเหตุที่เป็นไปได้
- การสื่อสาร UDP ถูกบล็อก (Firewall/Antivirus/Network Policy)
- NAT/Router ไม่อนุญาตหรือแปลพอร์ต UDP ของ Discord อย่างถูกต้อง
- ปัญหา region ของ Discord voice server หรือการสลับ region ระหว่างเชื่อมต่อ
- การตั้งค่าหรือสิทธิ์ของบอทในเซิร์ฟเวอร์ Discord ไม่ครบสำหรับ voice
- ความไม่เข้ากันระหว่างเวอร์ชันของไลบรารี voice ที่ใช้ (เช่น discord.py เวอร์ชัน voice)
- การ reconnect/heartbeat timing mismatch ทำให้ session invalid

## ขั้นตอนแนะนำในการวินิจฉัย
- ใช้คำสั่งบอท:
  - `!voicelog` เพื่อตรวจสอบสาเหตุล่าสุดและรายละเอียด voice connection
  - `!join` เพื่อทดสอบการเข้าห้องใหม่หลังแก้ไขเครือข่าย
- ตรวจสอบ Firewall/Antivirus บน Windows ให้อนุญาต UDP สำหรับ Discord
- ทดสอบเปลี่ยน voice region ของช่องใน Discord (ถ้าตั้งค่าได้)
- ตรวจสอบสิทธิ์ของบอทในเซิร์ฟเวอร์ (เช่น Connect, Speak, Use Voice Activity)
- ทดสอบบนเครือข่ายอื่น (เช่น hotspot) เพื่อตัดปัจจัย firewall ภายนอก

## คำสั่งและเครื่องมือที่อาจช่วยได้
- รันระบบ: `python -m src.ai_vtuber`
- ตรวจสอบบันทึก: ใช้ `!voicelog` ในช่องข้อความ
- ทดสอบ join: ใช้ `!join <voice-channel>`
- Windows Firewall (ตัวอย่างเพิ่ม rule — ปรับให้เหมาะสม):
  - `netsh advfirewall firewall add rule name="Discord UDP" dir=out action=allow protocol=UDP localport=1-65535`

## สถานะล่าสุด
- ระบบยืนยันและจัดการกรณี `4006` ได้อย่างถูกต้อง (cleanup และแจ้งเตือน)
- ปัญหาการเชื่อมต่อ voice ยังขึ้นกับสภาพเครือข่าย/Firewall/UDP
- พร้อมสำหรับการปรึกษาภายนอก โดยไฟล์นี้รวบรวมบริบทและ log ที่จำเป็น