from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass
class Transcript:
    text: str
    confidence: float | None = None


class WhisperSTT:
    """Local Whisper speech recognizer using faster-whisper."""

    def __init__(self, model_size: str = "base.en", device: str = "cpu", compute_type: str = "int8") -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper is not installed. Re-run PC setup.") from exc
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_16k: np.ndarray) -> Transcript:
        segments, info = self.model.transcribe(
            audio_16k.astype(np.float32),
            language="en",
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        parts = [segment.text.strip() for segment in segments if segment.text.strip()]
        text = " ".join(parts).strip()
        confidence = None
        if parts:
            confidence = float(max(0.0, min(1.0, getattr(info, "language_probability", 0.0))))
        return Transcript(text=text, confidence=confidence)


def resample_mono(audio: np.ndarray, source_rate: int, target_rate: int = 16000) -> np.ndarray:
    """Convert mono float audio to target rate without requiring scipy."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if source_rate == target_rate:
        return audio
    if not len(audio):
        return np.empty(0, dtype=np.float32)
    duration = len(audio) / float(source_rate)
    target_len = max(1, round(duration * target_rate))
    old_x = np.linspace(0.0, duration, len(audio), endpoint=False)
    new_x = np.linspace(0.0, duration, target_len, endpoint=False)
    return np.interp(new_x, old_x, audio).astype(np.float32)
