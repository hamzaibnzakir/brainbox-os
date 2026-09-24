from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Protocol
import json
import os
import subprocess
import tempfile
import wave

import numpy as np


@dataclass
class Transcript:
    text: str
    confidence: float | None = None
    rejected: bool = False
    reason: str | None = None


def _load_speech_dictionary() -> dict[str, str]:
    """Load conservative ASR corrections from BRAINBOX_STT_DICTIONARY.

    Format: "canonical: alias, alias; another canonical: misheard, other"
    """
    raw = os.getenv("BRAINBOX_STT_DICTIONARY", "").strip()
    if not raw:
        return {}
    mapping: dict[str, str] = {}
    for entry in raw.split(";"):
        if ":" not in entry:
            continue
        canonical, aliases = entry.split(":", 1)
        canonical = canonical.strip()
        if not canonical:
            continue
        for alias in aliases.split(","):
            alias = alias.strip()
            if alias and alias.casefold() != canonical.casefold():
                mapping[alias] = canonical
    return mapping


def _apply_speech_dictionary(text: str, mapping: dict[str, str] | None = None) -> str:
    """Apply only explicit user supplied ASR corrections."""
    mapping = _load_speech_dictionary() if mapping is None else mapping
    if not mapping or not text:
        return text
    ordered = sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True)
    for alias, canonical in ordered:
        pattern = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.IGNORECASE)
        text = pattern.sub(canonical, text)
    return text


_HALLUCINATION_PATTERNS = (
    r"\bthanks? for watching\b",
    r"\bthank you for watching\b",
    r"\bsee you (?:next time|in the next video)\b",
    r"\bthanks? for (?:watching|listening)\b",
    r"\blike and subscribe\b",
    r"\bdon't forget to subscribe\b",
    r"\bsubscribe to (?:the )?channel\b",
)


def _looks_like_hallucination(text: str, segments: list[Any], audio_seconds: float) -> tuple[bool, str | None]:
    normalized = re.sub(r"\s+", " ", text.casefold()).strip()
    if not normalized:
        return True, "empty"

    if any(re.search(pattern, normalized) for pattern in _HALLUCINATION_PATTERNS):
        return True, "known_hallucination_phrase"

    words = normalized.split()
    if len(words) >= 4:
        for width in (2, 3, 4, 5):
            if len(words) >= width * 2 and words[-width:] == words[-2 * width:-width]:
                return True, "repeated_phrase"

    if audio_seconds < 1.0 and len(words) > 12:
        return True, "speech_audio_length_mismatch"

    if segments:
        no_speech = [float(getattr(s, "no_speech_prob", 0.0)) for s in segments]
        log_probs = [float(getattr(s, "avg_logprob", 0.0)) for s in segments]
        compression = [float(getattr(s, "compression_ratio", 0.0)) for s in segments]
        if no_speech and max(no_speech) >= 0.72:
            return True, "high_no_speech_probability"
        if log_probs and min(log_probs) < -1.55 and max(no_speech or [0.0]) >= 0.45:
            return True, "weak_log_probability"
        if compression and max(compression) >= 3.0:
            return True, "high_compression_ratio"

    return False, None


class ASRBackend(Protocol):
    """Common contract for local Brainbox speech recognition backends."""

    def transcribe(self, audio_16k: np.ndarray) -> Transcript:
        ...


class WhisperCppBackend:
    """Adapter for the official whisper.cpp CLI.

    The binary and model stay local to the PC. No audio is uploaded anywhere.
    """

    def __init__(
        self,
        binary: str | None = None,
        model: str | None = None,
        use_gpu: bool = True,
        timeout: int = 30,
    ) -> None:
        self.binary = binary or os.getenv("BRAINBOX_WHISPER_CPP_BIN", "whisper-cli")
        self.model = model or os.getenv("BRAINBOX_WHISPER_CPP_MODEL", "")
        self.use_gpu = use_gpu
        self.timeout = max(5, timeout)
        if not self.model:
            raise RuntimeError("Set BRAINBOX_WHISPER_CPP_MODEL to a local ggml model path.")

    def transcribe(self, audio_16k: np.ndarray) -> Transcript:
        audio = preprocess_audio(audio_16k)
        if audio.size == 0:
            return Transcript("", rejected=True, reason="empty_audio")

        with tempfile.TemporaryDirectory(prefix="brainbox-stt-") as tmp:
            wav_path = os.path.join(tmp, "input.wav")
            out_base = os.path.join(tmp, "result")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                pcm = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
                wf.writeframes(pcm.tobytes())

            command = [
                self.binary, "-m", self.model, "-f", wav_path,
                "-oj", "-of", out_base, "-np", "-nt", "-l", "en",
                "-t", str(max(1, min(8, os.cpu_count() or 4))),
            ]
            if not self.use_gpu:
                command.append("-ng")
            try:
                completed = subprocess.run(
                    command, capture_output=True, text=True, timeout=self.timeout, check=False
                )
            except FileNotFoundError as exc:
                raise RuntimeError(f"whisper.cpp binary not found: {self.binary}") from exc
            except subprocess.TimeoutExpired:
                return Transcript("", rejected=True, reason="backend_timeout")

            json_path = out_base + ".json"
            if not os.path.exists(json_path):
                detail = (completed.stderr or completed.stdout).strip()[-500:]
                return Transcript("", rejected=True, reason=f"backend_failed:{detail}")

            try:
                payload = json.loads(open(json_path, encoding="utf-8").read())
                text = " ".join(
                    str(item.get("text", "")).strip()
                    for item in payload.get("transcription", [])
                    if str(item.get("text", "")).strip()
                ).strip()
            except (OSError, json.JSONDecodeError) as exc:
                return Transcript("", rejected=True, reason=f"invalid_backend_output:{exc}")

        rejected, reason = _looks_like_hallucination(text, [], len(audio) / 16000.0)
        if rejected:
            return Transcript("", rejected=True, reason=reason)
        if not text:
            return Transcript("", rejected=True, reason="no_transcript")
        return Transcript(text=_apply_speech_dictionary(text), confidence=0.75)


class ParakeetSTT:
    """Optional local Parakeet TDT backend via sherpa-onnx."""

    def __init__(self, model_dir: str | None = None, provider: str | None = None, num_threads: int | None = None) -> None:
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise RuntimeError(
                "sherpa-onnx is required for BRAINBOX_STT_BACKEND=parakeet."
            ) from exc

        self.model_dir = os.path.abspath(
            model_dir or os.getenv(
                "BRAINBOX_PARAKEET_MODEL_DIR",
                os.path.join("models", "stt", "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"),
            )
        )
        self.provider = provider or os.getenv("BRAINBOX_PARAKEET_PROVIDER", "cpu")
        self.num_threads = max(1, int(num_threads or os.getenv("BRAINBOX_PARAKEET_THREADS", "4")))
        self.hotwords_file = os.getenv("BRAINBOX_PARAKEET_HOTWORDS_FILE", "").strip()
        self.hotwords_score = float(os.getenv("BRAINBOX_PARAKEET_HOTWORDS_SCORE", "1.5"))
        self.decoding_method = os.getenv("BRAINBOX_PARAKEET_DECODING", "modified_beam_search").strip()

        self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=os.path.join(self.model_dir, "encoder.int8.onnx"),
            decoder=os.path.join(self.model_dir, "decoder.int8.onnx"),
            joiner=os.path.join(self.model_dir, "joiner.int8.onnx"),
            tokens=os.path.join(self.model_dir, "tokens.txt"),
            num_threads=self.num_threads,
            sample_rate=16000,
            feature_dim=128,
            decoding_method=self.decoding_method,
            max_active_paths=int(os.getenv("BRAINBOX_PARAKEET_MAX_ACTIVE_PATHS", "4")),
            hotwords_file=self.hotwords_file,
            hotwords_score=self.hotwords_score,
            modeling_unit=os.getenv("BRAINBOX_PARAKEET_MODELING_UNIT", "bpe"),
            bpe_vocab=os.getenv("BRAINBOX_PARAKEET_BPE_VOCAB", ""),
            model_type="nemo_transducer",
            provider=self.provider,
        )

    def transcribe(self, audio_16k: np.ndarray) -> Transcript:
        audio = preprocess_audio(audio_16k)
        if audio.size == 0:
            return Transcript("", rejected=True, reason="empty_audio")
        stream = self._recognizer.create_stream()
        stream.accept_waveform(16000, audio)
        self._recognizer.decode_stream(stream)
        text = _apply_speech_dictionary(str(stream.result.text or "").strip())
        if not text:
            return Transcript("", rejected=True, reason="no_transcript")
        rejected, reason = _looks_like_hallucination(text, [], len(audio) / 16000.0)
        if rejected:
            return Transcript("", rejected=True, reason=reason)
        return Transcript(text=text, confidence=0.90)


def create_stt_backend() -> ASRBackend:
    backend = os.getenv("BRAINBOX_STT_BACKEND", "parakeet").strip().lower()
    if backend in {"parakeet", "parakeet_tdt", "sherpa_parakeet"}:
        return ParakeetSTT()
    if backend in {"whisper_cpp", "whisper.cpp", "cpp"}:
        return WhisperCppBackend(
            binary=os.getenv("BRAINBOX_WHISPER_CPP_BIN", "whisper-cli"),
            model=os.getenv("BRAINBOX_WHISPER_CPP_MODEL", ""),
            use_gpu=os.getenv("BRAINBOX_WHISPER_CPP_GPU", "1") != "0",
        )
    if backend not in {"faster_whisper", "faster-whisper", "whisper"}:
        raise ValueError(f"Unsupported BRAINBOX_STT_BACKEND: {backend}")
    return WhisperSTT(
        model_size=os.getenv("BRAINBOX_WHISPER_MODEL", "base.en"),
        device=os.getenv("BRAINBOX_WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("BRAINBOX_WHISPER_COMPUTE", "int8"),
    )


class WhisperSTT:
    """Whisper-family backend with confidence and hallucination rejection."""

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
            return Transcript("", rejected=True, reason="empty_audio")

        segments_iter, info = self.model.transcribe(
            audio,
            language="en",
            beam_size=1,
            best_of=1,
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

        segments = list(segments_iter)
        parts = [segment.text.strip() for segment in segments if segment.text.strip()]
        text = " ".join(parts).strip()
        audio_seconds = len(audio) / 16000.0

        rejected, reason = _looks_like_hallucination(text, segments, audio_seconds)
        if rejected:
            return Transcript("", rejected=True, reason=reason)

        no_speech = [float(getattr(s, "no_speech_prob", 0.0)) for s in segments]
        log_probs = [float(getattr(s, "avg_logprob", -2.0)) for s in segments]
        speech_conf = 1.0 - max(no_speech or [0.0])
        log_conf = max(0.0, min(1.0, (sum(log_probs) / len(log_probs) + 2.0) / 2.0))
        language_conf = float(max(0.0, min(1.0, getattr(info, "language_probability", 0.0))))
        confidence = round(max(0.0, min(1.0, speech_conf * 0.5 + log_conf * 0.35 + language_conf * 0.15)), 3)

        if not text:
            return Transcript("", confidence=confidence, rejected=True, reason="no_transcript")
        if confidence < 0.40:
            return Transcript("", confidence=confidence, rejected=True, reason="low_confidence")

        return Transcript(text=_apply_speech_dictionary(text), confidence=confidence)


def preprocess_audio(audio: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
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
        audio = np.clip(audio * min(2.5, 0.08 / rms), -1.0, 1.0)
    return audio.astype(np.float32)


def resample_mono(audio: np.ndarray, source_rate: int, target_rate: int = 16000) -> np.ndarray:
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
