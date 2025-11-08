import asyncio
from pathlib import Path
import numpy as np
import soundfile as sf
import argparse

import sys
sys.path.append(str(Path(__file__).resolve().parents[1] / 'src'))

from core.config import config
from audio.tts_rvc_handler import tts_rvc_handler


def ensure_len(audio: np.ndarray, sr: int, seconds: float = 5.0) -> np.ndarray:
    """ตัด/เติมให้ยาวตรงตาม seconds"""
    target_samples = int(seconds * sr)
    if audio.size > target_samples:
        return audio[:target_samples]
    if audio.size < target_samples:
        pad = np.zeros(target_samples - audio.size, dtype=audio.dtype)
        return np.concatenate([audio, pad])
    return audio


def process_for_discord(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """
    จำลองกระบวนการเดียวกับ NumpyAudioSource ก่อนส่งให้ Discord:
    - Resample เป็น 48k
    - Normalize 0.95 peak
    - Fade in/out 10ms
    - แปลงเป็น int16 และเติม tail pad ~40ms
    คืนค่าเป็น numpy int16 mono @ 48k
    """
    # Resample → 48k
    target_sr = 48000
    if sample_rate != target_sr:
        try:
            from scipy.signal import resample_poly
            audio = resample_poly(audio, target_sr, sample_rate).astype(np.float32)
        except Exception:
            new_len = int(len(audio) * target_sr / sample_rate)
            x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
            x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
            audio = np.interp(x_new, x_old, audio).astype(np.float32)

    # Normalize peak → 0.95
    max_val = float(np.abs(audio).max())
    if max_val > 0:
        audio = (audio / max_val) * 0.95

    # Fade in/out 10ms
    fade_samples = int(0.01 * target_sr)
    if fade_samples > 0 and audio.size > (2 * fade_samples):
        ramp_in = np.linspace(0.0, 1.0, fade_samples, endpoint=False, dtype=np.float32)
        ramp_out = np.linspace(1.0, 0.0, fade_samples, endpoint=False, dtype=np.float32)
        audio[:fade_samples] *= ramp_in
        audio[-fade_samples:] *= ramp_out

    # Convert → int16
    audio = np.clip(audio, -1.0, 1.0)
    pcm16 = (audio * 32767.0).astype(np.int16)

    # Tail pad ~40ms เพื่อช่วยให้ Opus flush
    pad_samples = int(target_sr * 0.040)
    if pad_samples > 0:
        pcm16 = np.concatenate([pcm16, np.zeros(pad_samples, dtype=np.int16)])

    return pcm16


async def gen_tts_example(text: str, out_path: Path):
    """สร้างเสียงด้วย TTS (ผ่าน tts_rvc_handler) ความยาวสุดท้าย 5 วิ แล้ว process แบบ Discord"""
    audio, tmp = await tts_rvc_handler.generate_speech(text)
    if audio is None:
        # fallback เงียบเพื่อไม่ให้พัง
        sr = config.tts.sample_rate
        audio = np.zeros(int(5.0 * sr), dtype=np.float32)
    sr = config.tts.sample_rate

    # noise reduce / normalize ตาม config (ใช้เมธอดใน handler เพื่อให้เหมือนกัน)
    try:
        if config.tts.noise_reduction:
            audio = tts_rvc_handler._reduce_noise(audio)
        if config.tts.normalize_audio:
            audio = tts_rvc_handler._normalize_audio(audio)
    except Exception:
        pass

    audio = ensure_len(audio, sr, 5.0)
    pcm16 = process_for_discord(audio, sr)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), pcm16, 48000)
    return out_path


def gen_sine_sweep(seconds: float = 5.0) -> np.ndarray:
    sr = config.tts.sample_rate
    t = np.linspace(0.0, seconds, int(sr * seconds), endpoint=False)
    f0, f1 = 200.0, 2000.0
    f = f0 + (f1 - f0) * (t / seconds)
    audio = 0.4 * np.sin(2 * np.pi * f * t).astype(np.float32)
    return audio


def gen_enveloped_noise(seconds: float = 5.0) -> np.ndarray:
    sr = config.tts.sample_rate
    n = int(sr * seconds)
    noise = np.random.randn(n).astype(np.float32)
    # สร้าง envelope ให้ขึ้นลงนุ่มนวล
    env = np.hanning(n)
    # ลดระดับเพื่อหลีกเลี่ยง clipping
    audio = (noise / max(1.0, np.max(np.abs(noise)))) * 0.3
    audio *= env
    return audio.astype(np.float32)


async def main(include_sine_noise: bool = False):
    base = Path(__file__).resolve().parents[1]
    out_dir = base / 'temp' / 'audio_examples'
    out_dir.mkdir(parents=True, exist_ok=True)

    print('Config TTS sample_rate:', config.tts.sample_rate)
    print('TTS/RVC stats:', tts_rvc_handler.get_stats())

    # ตัวอย่าง 1-2: TTS
    texts = [
        "สวัสดีค่ะ ขณะนี้กำลังทดสอบระบบเสียงของเจี๊ดนะคะ",
        "นี่เป็นตัวอย่างเสียงเพื่อทดสอบคุณภาพและตรวจสอบความผิดปกติค่ะ"
    ]
    for i, text in enumerate(texts, start=1):
        path = out_dir / f"example_tts_{i}.wav"
        p = await gen_tts_example(text, path)
        print('✅ Saved', p)

    if include_sine_noise:
        # ตัวอย่าง 3: sine sweep
        sine = gen_sine_sweep(5.0)
        sine = ensure_len(sine, config.tts.sample_rate, 5.0)
        sine_pcm = process_for_discord(sine, config.tts.sample_rate)
        sf.write(str(out_dir / 'example_sine_sweep.wav'), sine_pcm, 48000)
        print('✅ Saved', out_dir / 'example_sine_sweep.wav')

        # ตัวอย่าง 4: noise พร้อม envelope
        noise = gen_enveloped_noise(5.0)
        noise = ensure_len(noise, config.tts.sample_rate, 5.0)
        noise_pcm = process_for_discord(noise, config.tts.sample_rate)
        sf.write(str(out_dir / 'example_noise_enveloped.wav'), noise_pcm, 48000)
        print('✅ Saved', out_dir / 'example_noise_enveloped.wav')
    else:
        print('⏭️ ข้ามการสร้าง sine sweep และ noise (ค่าเริ่มต้น)')

    print('\n🎧 ตัวอย่างทั้งหมดถูกบันทึกที่:', out_dir)
    print('เปิดและฟังเพื่อเช็คว่ามีเสียงแตก คลิก หรือช็อตไหม')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate audio examples')
    parser.add_argument('--include-sine-noise', action='store_true', help='สร้างตัวอย่าง sine sweep และ noise ด้วย')
    args = parser.parse_args()
    asyncio.run(main(include_sine_noise=args.include_sine_noise))