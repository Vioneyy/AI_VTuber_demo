#Requires -Version 5.1
param(
  [string]$SourceDir = "$env:TEMP\whisper.cpp",
  [string]$TargetExe = "D:\\tools\\whisper.cpp\\main.exe"
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $SourceDir)) {
  git clone https://github.com/ggml-org/whisper.cpp.git $SourceDir
}

Set-Location $SourceDir
cmake --version
git --version

cmake -B build_cpu -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=0 -DGGML_OPENCL=0 -DWHISPER_BUILD_EXAMPLES=OFF
cmake --build build_cpu --config Release -j 8

$binCandidates = @(
  "build_cpu\\bin\\Release\\main.exe",
  "build_cpu\\bin\\main.exe",
  "build_cpu\\bin\\x64\\Release\\main.exe"
)
$srcbin = $null
foreach ($c in $binCandidates) {
  if (Test-Path $c) { $srcbin = (Resolve-Path $c).Path; break }
}

if ($null -ne $srcbin) {
  Copy-Item -Path $srcbin -Destination $TargetExe -Force
  Write-Host "[build] copied to $TargetExe"
} else {
  Write-Error "main.exe not found in build_cpu paths."
}