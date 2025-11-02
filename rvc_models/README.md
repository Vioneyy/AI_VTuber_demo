# RVC Models

ไฟล์โมเดลสำหรับ RVC ให้จัดวางดังนี้:

- `jeed_anime.pth` (น้ำหนักโมเดลหลัก)
- `jeed_anime.index` (index สำหรับการค้นคุณลักษณะเสียง)

หมายเหตุ:
- `jeed_anime.index` มีขนาดเกิน 100MB จึงไม่ได้อัปโหลดขึ้น GitHub ใน repository นี้ หากต้องการใช้งาน โปรดวางไฟล์ `.index` ในโฟลเดอร์นี้ให้ตรงกับค่า `RVC_INDEX_PATH` ใน `.env`
- สามารถแก้ไขพาธใน `.env` เช่น `RVC_MODEL_PATH=rvc_models/jeed_anime.pth` และ `RVC_INDEX_PATH=rvc_models/jeed_anime.index`