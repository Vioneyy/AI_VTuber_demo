#Requires -Version 5.1
param(
    [string]$WhisperRoot = "D:\tools\whisper.cpp",
    [string]$ModelName = "ggml-small.bin",
    [switch]$CpuOnly
)

$ErrorActionPreference = 'Stop'

Write-Host "[setup] เตรียมโครงสร้างโฟลเดอร์และดาวน์โหลดโมเดลสำหรับ whisper.cpp" -ForegroundColor Cyan

# 1) สร้างโฟลเดอร์หลักและ models
New-Item -ItemType Directory -Force -Path $WhisperRoot | Out-Null
$ModelsDir = Join-Path $WhisperRoot 'models'
New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null

# 2) ดาวน์โหลดโมเดลถ้ายังไม่มี
$ModelPath = Join-Path $ModelsDir $ModelName
if (-not (Test-Path $ModelPath)) {
    $Uri = "https://huggingface.co/datasets/ggerganov/whisper.cpp/resolve/main/$ModelName"
    Write-Host "[setup] ดาวน์โหลดโมเดล: $ModelName" -ForegroundColor Yellow
    Invoke-WebRequest -Uri $Uri -OutFile $ModelPath -UseBasicParsing
} else {
    Write-Host "[setup] พบโมเดลอยู่แล้ว: $ModelPath" -ForegroundColor Green
}

# 3) ตรวจ main.exe ตาม .env path ที่เราตั้งไว้
$ExpectedBin = Join-Path $WhisperRoot 'main.exe'
if (-not (Test-Path $ExpectedBin)) {
    Write-Host "[setup] ยังไม่พบ main.exe ที่ $ExpectedBin" -ForegroundColor Yellow
    Write-Host "[setup] ขั้นตอนถัดไป: คอมไพล์ whisper.cpp ด้วย CMake" -ForegroundColor Yellow
    Write-Host ""; Write-Host "ตัวอย่างคำสั่ง (CUDA):" -ForegroundColor Cyan
    Write-Host "  git clone https://github.com/ggml-org/whisper.cpp.git"
    Write-Host "  cd whisper.cpp"
    Write-Host "  cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=1 -DWHISPER_BUILD_EXAMPLES=OFF"
    Write-Host "  cmake --build build --config Release -j 8"
    Write-Host "  Copy-Item build\\bin\\Release\\main.exe '$ExpectedBin' -Force"
    Write-Host ""; Write-Host "ตัวอย่างคำสั่ง (CPU):" -ForegroundColor Cyan
    Write-Host "  cmake -B build_cpu -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=0 -DGGML_OPENCL=0 -DWHISPER_BUILD_EXAMPLES=OFF"
    Write-Host "  cmake --build build_cpu --config Release -j 8"
    Write-Host "  Copy-Item build_cpu\\bin\\Release\\main.exe '$ExpectedBin' -Force"
    if ($CpuOnly) {
        Write-Host "[setup] โหมด CPU เท่านั้น: โปรดตั้งค่า WHISPER_CPP_NGL=0 ใน .env" -ForegroundColor Magenta
    }
} else {
    Write-Host "[setup] พบ main.exe แล้ว: $ExpectedBin" -ForegroundColor Green
}

Write-Host "[setup] สรุปพาธที่สำคัญ:" -ForegroundColor Cyan
Write-Host "  WHISPER_CPP_BIN_PATH=$ExpectedBin"
Write-Host "  WHISPER_CPP_MODEL_PATH=$ModelPath"
Write-Host "[setup] เอกสารเพิ่มเติม: docs\\WHISPERCPP_WINDOWS.md" -ForegroundColor Cyan