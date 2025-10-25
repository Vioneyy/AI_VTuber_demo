# Whisper.cpp (Windows) – ขั้นตอนการเตรียมและ build

เอกสารนี้อธิบายวิธีเตรียม `main.exe` ของ whisper.cpp บน Windows ให้ใช้งานได้กับ GPU (CUDA) หรือ CPU และจับคู่กับค่าที่ตั้งใน `.env` ของโปรเจกต์นี้

## 1) ติดตั้งเครื่องมือที่จำเป็น
- Visual Studio Build Tools (เลือก C++ Build Tools และ CMake integration)
- CMake (ล่าสุด) และ Git
- NVIDIA CUDA Toolkit 12.x (สำหรับโหมด GPU – cuBLAS)
- ทางเลือก: OpenCL (ถ้าต้องการใช้แทน CUDA)

ตรวจสอบให้ `cmake`, `git`, และเครื่องมือคอมไพล์อยู่ใน PATH ของ PowerShell

## 2) เตรียมโครงสร้างโฟลเดอร์ตาม `.env`
ค่าใน `.env` ตั้งเป็น:
- `WHISPER_CPP_BIN_PATH=D:\tools\whisper.cpp\main.exe`
- `WHISPER_CPP_MODEL_PATH=D:\tools\whisper.cpp\models\ggml-small.bin`

สร้างโฟลเดอร์และดาวน์โหลดโมเดล:
```powershell
# สร้างโฟลเดอร์
New-Item -ItemType Directory -Force -Path "D:\tools\whisper.cpp\models" | Out-Null

# ดาวน์โหลดโมเดลขนาดเล็กเพื่อทดสอบเร็ว
Invoke-WebRequest -Uri "https://huggingface.co/datasets/ggerganov/whisper.cpp/resolve/main/ggml-small.bin" -OutFile "D:\tools\whisper.cpp\models\ggml-small.bin"
```

## 3) สร้าง main.exe (CUDA GPU)
```powershell
# รับซอร์สโค้ด
cd $env:TEMP
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp

# สร้างด้วย CUDA
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=1 -DWHISPER_BUILD_EXAMPLES=OFF
cmake --build build --config Release -j 8

# ผลลัพธ์มักอยู่ที่ build\bin หรือ build\bin\Release
# คัดลอกไปตามพาธใน .env
Copy-Item -Path (Resolve-Path "build\bin\Release\main.exe" -ErrorAction SilentlyContinue) -Destination "D:\tools\whisper.cpp\main.exe" -Force
Copy-Item -Path (Resolve-Path "build\bin\main.exe" -ErrorAction SilentlyContinue) -Destination "D:\tools\whisper.cpp\main.exe" -Force
```
หมายเหตุ:
- ถ้าใช้ Generator VS อาจมีพาธ `build\bin\Release\main.exe`
- ถ้าใช้ Ninja/MinGW อาจเป็น `build\bin\main.exe`

## 4) สร้าง main.exe (CPU เท่านั้น – ทางเลือก)
หากยังไม่มี CUDA/OpenCL ให้สร้าง CPU binary ก่อน:
```powershell
cd $env:TEMP\whisper.cpp
cmake -B build_cpu -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=0 -DGGML_OPENCL=0 -DWHISPER_BUILD_EXAMPLES=OFF
cmake --build build_cpu --config Release -j 8
Copy-Item -Path (Resolve-Path "build_cpu\bin\Release\main.exe" -ErrorAction SilentlyContinue) -Destination "D:\tools\whisper.cpp\main.exe" -Force
Copy-Item -Path (Resolve-Path "build_cpu\bin\main.exe" -ErrorAction SilentlyContinue) -Destination "D:\tools\whisper.cpp\main.exe" -Force
```
และตั้งใน `.env`:
- `WHISPER_CPP_NGL=0` (ปิดการ offload ไป GPU)

## 5) ทดสอบ main.exe แบบตรงๆ
```powershell
& "D:\tools\whisper.cpp\main.exe" -m "D:\tools\whisper.cpp\models\ggml-small.bin" -f "D:\AI_VTuber_demo\output\sample_sawasdee.wav" -l th -otxt -of "D:\AI_VTuber_demo\output\stt_test.txt" -t 4 -ngl 35
# ถ้าเป็น CPU main.exe ให้ใช้ -ngl 0
```

## 6) ทดสอบผ่านโปรเจกต์นี้
เปิด venv แล้วรัน:
```powershell
.\.venv\Scripts\Activate.ps1
python scripts\test_stt_whispercpp.py
```
หากเห็นข้อความถอดความ แสดงว่าการตั้งค่าและพาธถูกต้อง

## 7) ปรับแต่งประสิทธิภาพ
- `WHISPER_CPP_THREADS`: ปรับตามจำนวน CPU cores
- `WHISPER_CPP_NGL`: จำนวนเลเยอร์ที่ offload ไป GPU (ต้องเป็น binary แบบ CUDA/OpenCL); ถ้า CPU ใช้ 0
- โมเดลที่ใหญ่ขึ้น เช่น `base`, `medium`, `large` ให้ใช้พลังงานมากขึ้นและจำเป็นต้องมี VRAM เพียงพอ

## 8) ปัญหาที่พบบ่อย
- main.exe หาไม่เจอ: ตรวจพาธใน `.env` และสิทธิ์ไฟล์
- CUDA build ล้มเหลว: ตรวจว่า CUDA Toolkit ติดตั้งและ CMake หาได้ (`find_package(CUDAToolkit)`)
- เปิดไฟล์ wav ไม่ได้: ตรวจว่าไฟล์มีรูปแบบ PCM 16-bit และพาธถูกต้อง