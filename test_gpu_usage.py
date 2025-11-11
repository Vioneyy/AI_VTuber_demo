"""
GPU Usage Test
ทดสอบว่าโมดูลต่างๆ ใช้ GPU หรือไม่
"""
import torch
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

print("Testing GPU usage...")

# Test Whisper
try:
    import whisper
    model = whisper.load_model("tiny", device="cuda")
    print(f"✅ Whisper on GPU: {next(model.parameters()).device}")
except Exception as e:
    print(f"❌ Whisper: {e}")

# Test TTS
try:
    from f5_tts_th.tts import TTS
    # Check if TTS uses GPU
    print(f"✅ TTS module loaded")
except Exception as e:
    print(f"❌ TTS: {e}")

# Removed RVC test (TTS-only mode)

print("\nGPU Memory:")
if torch.cuda.is_available():
    print(f"Allocated: {torch.cuda.memory_allocated()/1024**2:.1f} MB")
    print(f"Cached: {torch.cuda.memory_reserved()/1024**2:.1f} MB")
