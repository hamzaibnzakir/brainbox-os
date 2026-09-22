from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Transcript:
    text: str
    confidence: float | None = None


class WhisperSTT:
    """Local Whisper recognizer tuned for short voice commands."""

    def __init__(
        self,
        model_size: str = "small.en",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper is not installed. Re-run PC setup.") from exc
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_16k: np.ndarray) -> Transcript:
        audio = preprocess_audio(audio_16k)
        if audio.size == 0:
            return Transcript("")
        segments, info = self.model.transcribe(
            audio,
            language="en",
            beam_size=5,
            best_of=5,
            temperature=0.0,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 350, "speech_pad_ms": 120},
            condition_on_previous_text=False,
            no_speech_threshold=0.55,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )
        parts = [segment.text.strip() for segment in segments if segment.text.strip()]
        text = " ".join(parts).strip()
        confidence = None
        if parts:
            confidence = float(max(0.0, min(1.0, getattr(info, "language_probability", 0.0))))
        return Transcript(text=text, confidence=confidence)


def preprocess_audio(audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Clean microphone audio before Whisper without adding another runtime dependency."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size < 160:
        return audio
    audio = audio - float(np.mean(audio))

    # Remove very low frequency rumble/DC while preserving speech.
    try:
        from scipy.signal import butter, sosfiltfilt
        sos = butter(4, [70, min(7600, sample_rate // 2 - 100)], btype="bandpass", fs=sample_rate, output="sos")
        audio = sosfiltfilt(sos, audio).astype(np.float32)
    except Exception:
        pass

    # Gentle peak normalization only when the recording is genuinely quiet.
    rms = float(np.sqrt(np.mean(np.square(audio))))
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if 0.004 < rms < 0.045 and peak > 1e-5:
        gain = min(2.5, 0.08 / rms)
        audio = np.clip(audio * gain, -1.0, 1.0)
    return audio.astype(np.float32)


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
