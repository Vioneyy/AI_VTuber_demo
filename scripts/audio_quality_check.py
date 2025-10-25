from __future__ import annotations
import sys
from pathlib import Path
import io
import wave
import numpy as np


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), 'rb') as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        pcm = w.readframes(n)
    if sw != 2:
        raise ValueError(f"Only 16-bit PCM supported, got {sw*8} bits")
    x = np.frombuffer(pcm, dtype=np.int16)
    if ch == 2:
        x = x.reshape(-1, 2).mean(axis=1).astype(np.int16)
    return x, sr


def rms_dbfs(x: np.ndarray) -> float:
    # Avoid log(0)
    rms = np.sqrt(np.mean((x.astype(np.float64) / 32768.0) ** 2) + 1e-12)
    return 20.0 * np.log10(rms)


def peak_dbfs(x: np.ndarray) -> float:
    peak = np.max(np.abs(x.astype(np.float64)) / 32768.0)
    return 20.0 * np.log10(peak + 1e-12)


def clipping_percent(x: np.ndarray) -> float:
    return 100.0 * (np.sum(np.abs(x) >= 32767) / x.size)


def zero_crossing_rate(x: np.ndarray) -> float:
    x_f = x.astype(np.float64)
    return float(np.mean(np.abs(np.diff(np.sign(x_f))) > 0))


def spectral_centroid(x: np.ndarray, sr: int) -> float:
    # Simple centroid on magnitude spectrum
    N = 2048
    if x.size < N:
        N = int(2 ** np.floor(np.log2(max(256, x.size))))
    window = np.hanning(N)
    seg = x[:N].astype(np.float64) * window
    X = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(N, d=1.0/sr)
    num = np.sum(freqs * X)
    den = np.sum(X) + 1e-12
    return float(num / den)


def duration_seconds(x: np.ndarray, sr: int) -> float:
    return float(x.size) / float(sr)


def summarize(path: Path) -> dict:
    x, sr = read_wav(path)
    return {
        "path": str(path),
        "sr": sr,
        "duration_sec": duration_seconds(x, sr),
        "rms_dbfs": rms_dbfs(x),
        "peak_dbfs": peak_dbfs(x),
        "clipping_percent": clipping_percent(x),
        "zcr": zero_crossing_rate(x),
        "spectral_centroid_hz": spectral_centroid(x, sr),
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/audio_quality_check.py <raw.wav> <processed.wav>")
        sys.exit(1)
    raw = Path(sys.argv[1])
    proc = Path(sys.argv[2])
    if not raw.exists() or not proc.exists():
        print("Input files not found")
        sys.exit(1)

    s1 = summarize(raw)
    s2 = summarize(proc)

    out_dir = Path(__file__).resolve().parents[1] / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "qa_report.md"

    def fmt(d: dict) -> str:
        return (f"- path: {d['path']}\n"
                f"- sr: {d['sr']}\n"
                f"- duration_sec: {d['duration_sec']:.3f}\n"
                f"- rms_dbfs: {d['rms_dbfs']:.2f}\n"
                f"- peak_dbfs: {d['peak_dbfs']:.2f}\n"
                f"- clipping_percent: {d['clipping_percent']:.4f}%\n"
                f"- zero_crossing_rate: {d['zcr']:.4f}\n"
                f"- spectral_centroid_hz: {d['spectral_centroid_hz']:.1f}\n")

    loud_diff = s2['rms_dbfs'] - s1['rms_dbfs']
    cent_diff = s2['spectral_centroid_hz'] - s1['spectral_centroid_hz']

    md = (
        "# Audio QA Report\n\n"
        "## Before (RAW)\n" + fmt(s1) + "\n"
        "## After (Processed/RVC)\n" + fmt(s2) + "\n"
        "## Summary\n"
        f"- loudness_change_db: {loud_diff:.2f}\n"
        f"- spectral_centroid_change_hz: {cent_diff:.1f}\n"
        f"- clipping_change_percent: {(s2['clipping_percent'] - s1['clipping_percent']):.4f}%\n"
    )

    report.write_text(md, encoding="utf-8")
    print(f"QA report generated: {report}")


if __name__ == "__main__":
    main()