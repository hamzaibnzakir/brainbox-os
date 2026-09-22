from __future__ import annotations

import argparse
import json
import time
import wave
from pathlib import Path

import numpy as np

from brainbox_os.stt import WhisperSTT, resample_mono


def load_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate()
        channels = wf.getnchannels()
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return resample_mono(audio, rate, 16000)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Brainbox local STT models on recorded WAV files.")
    parser.add_argument("audio_dir", type=Path)
    parser.add_argument("--models", nargs="+", default=["base.en"])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args()

    files = sorted(args.audio_dir.glob("*.wav"))
    if not files:
        raise SystemExit(f"No WAV files found in {args.audio_dir}")

    rows = []
    for model_name in args.models:
        recognizer = WhisperSTT(model_name, args.device, args.compute_type)
        for path in files:
            audio = load_wav(path)
            started = time.perf_counter()
            result = recognizer.transcribe(audio)
            elapsed = time.perf_counter() - started
            duration = len(audio) / 16000.0
            rows.append({
                "model": model_name,
                "file": path.name,
                "audio_seconds": round(duration, 3),
                "latency_seconds": round(elapsed, 3),
                "realtime_factor": round(elapsed / duration, 3) if duration else None,
                "confidence": result.confidence,
                "rejected": result.rejected,
                "reason": result.reason,
                "text": result.text,
            })

    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
