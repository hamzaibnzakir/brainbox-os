from __future__ import annotations

from dataclasses import dataclass
import re

import numpy as np


@dataclass
class Transcript:
    text: str
    confidence: float | None = None


_HALLUCINATION_PATTERNS = (
    r"\bthanks? for watching\b",
    r"\bthank you for watching\b",
    r"\bsee you (?:next time|in the next video)\b",
    r"\bthanks? for (?:watching|listening)\b",
    r"\blike and subscribe\b",
    r"\bdon't forget to subscribe\b",
    r"\bsubscribe to (?:the )?channel\b",
)


def _looks_like_hallucination(text: str, segments: list[object], audio_seconds: float) -> bool:
    normalized = re.sub(r"\s+", " ", text.casefold()).strip()
    if not normalized:
        return True

    # Whisper commonly invents outro language when given silence or weak/noisy audio.
    if any(re.search(pattern, normalized) for pattern in _HALLUCINATION_PATTERNS):
        return True

    # Repeated phrases are a strong signal of the classic Whisper looping failure.
    words = normalized.split()
    if len(words) >= 8:
        for width in (3, 4, 5):
            if len(words) >= width * 2:
                a = words[-width:]
                b = words[-2 * width:-width]
                if a == b:
                    return True

    if audio_seconds < 1.0 and len(words) > 12:
        return True

    if segments:
        no_speech = [float(getattr(s, "no_speech_prob", 0.0)) for s in segments]
        log_probs = [float(getattr(s, "avg_logprob", 0.0)) for s in segments]
        compression = [float(getattr(s, "compression_ratio", 0.0)) for s in segments]
        if no_speech and max(no_speech) >= 0.72:
            return True
        if log_probs and min(log_probs) < -1.55 and max(no_speech or [0.0]) >= 0.45:
            return True
        if compression and max(compression) >= 3.0:
            return True

    return False


class WhisperSTT:
    """Local Whisper recognizer tuned for short voice commands."""

    def __init__(
        self,
        model_size: str = "base.en",
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

        segments_iter, info = self.model.transcribe(
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
            initial_prompt=(
                "Brainbox, open, launch, start, Chrome, Calculator, Discord, VS Code, "
                "PowerShell, terminal, Shopify, GitHub, browser, VPS."
            ),
        )

        # faster-whisper returns a lazy generator, so consume it once and retain
        # segment-level confidence signals before constructing the transcript.
        segments = list(segments_iter)
        parts = [segment.text.strip() for segment in segments if segment.text.strip()]
        text = " ".join(parts).strip()

        audio_seconds = len(audio) / 16000.0
        if _looks_like_hallucination(text, segments, audio_seconds):
            return Transcript("")

        confidence = None
        if parts:
            no_speech = [float(getattr(s, "no_speech_prob", 0.0)) for s in segments]
            log_probs = [float(getattr(s, "avg_logprob", -2.0)) for s in segments]
            speech_conf = 1.0 - max(no_speech or [0.0])
            log_conf = max(0.0, min(1.0, (sum(log_probs) / len(log_probs) + 2.0) / 2.0))
            language_conf = float(max(0.0, min(1.0, getattr(info, "language_probability", 0.0))))
            confidence = round(max(0.0, min(1.0, speech_conf * 0.5 + log_conf * 0.35 + language_conf * 0.15)), 3)

        return Transcript(text=text, confidence=confidence)


def preprocess_audio(audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """Clean microphone audio before Whisper without adding another runtime dependency."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size < 160:
        return audio
    audio = audio - float(np.mean(audio))

    try:
        from scipy.signal import butter, sosfiltfilt
        sos = butter(4, [70, min(7600, sample_rate // 2 - 100)], btype="bandpass", fs=sample_rate, output="sos")
        audio = sosfiltfilt(sos, audio).astype(np.float32)
    except Exception:
        pass

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
