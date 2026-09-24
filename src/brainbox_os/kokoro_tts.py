from __future__ import annotations

import threading
import time
import warnings
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class KokoroConfig:
    voice: str = "af_heart"
    language: str = "a"
    speed: float = 1.05
    device: str = "auto"
    sample_rate: int = 24000


class KokoroTTS:
    """Local, cancellable, sentence-streaming Kokoro TTS backend.

    Kokoro yields generated audio a segment at a time, so Brainbox can start
    speaking before the whole response has been synthesized. The stop event is
    checked between segments, which gives us a clean cancellation boundary.
    """

    def __init__(
        self,
        config: KokoroConfig | None = None,
        event_callback: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.config = config or KokoroConfig()
        self.event_callback = event_callback
        self._pipeline = None
        self._output = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def _emit(self, event: str, **payload) -> None:
        if self.event_callback:
            self.event_callback(event, payload)

    def _ensure_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="dropout option adds dropout")
            warnings.filterwarnings("ignore", message=".*weight_norm.*deprecated.*")
            warnings.filterwarnings("ignore", message=".*torch.jit.script.*deprecated.*")
            warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
            from kokoro import KPipeline

        device = None if self.config.device in {"", "auto"} else self.config.device
        started = time.perf_counter()
        self._pipeline = KPipeline(lang_code=self.config.language, device=device)
        model_device = getattr(getattr(self._pipeline, "model", None), "device", device)
        # torch.device is not JSON serializable, and the runtime emits telemetry
        # through json.dumps. Normalize the diagnostic value at the boundary.
        self._emit(
            "tts.model.ready",
            backend="kokoro",
            device=str(model_device) if model_device is not None else "auto",
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return self._pipeline

    def _ensure_output(self):
        if self._output is not None:
            return self._output
        import sounddevice as sd

        self._output = sd.OutputStream(
            samplerate=self.config.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=0,
        )
        self._output.start()
        return self._output

    def warm(self) -> None:
        self._ensure_pipeline()
        self._ensure_output()

    def stop(self) -> None:
        self._stop.set()
        self._emit("tts.cancel_requested", backend="kokoro")

    @staticmethod
    def _split_text(text: str, max_chars: int = 120) -> list[str]:
        """Split speech into short natural chunks to reduce first-audio latency."""
        import re

        value = " ".join(str(text or "").split()).strip()
        if not value:
            return []
        sentences = re.split(r"(?<=[.!?])\s+", value)
        chunks: list[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= max_chars:
                chunks.append(sentence)
                continue
            clauses = re.split(r"(?<=[,;:])\s+", sentence)
            current = ""
            for clause in clauses:
                clause = clause.strip()
                if not clause:
                    continue
                candidate = f"{current} {clause}".strip()
                if current and len(candidate) > max_chars:
                    chunks.append(current)
                    current = clause
                else:
                    current = candidate
            if current:
                chunks.append(current)
        return chunks

    def speak(self, text: str) -> None:
        import numpy as np

        self._stop.clear()
        pipeline = self._ensure_pipeline()
        output = self._ensure_output()
        started = time.perf_counter()
        first_audio = True

        try:
            chunks = self._split_text(text)
            self._emit("tts.started", backend="kokoro", chunks=len(chunks))
            for chunk in chunks:
                if self._stop.is_set():
                    break
                for result in pipeline(
                    chunk,
                    voice=self.config.voice,
                    speed=self.config.speed,
                    split_pattern=r"(?<=[.!?])\\s+|\\n+",
                ):
                    if self._stop.is_set():
                        break
                    audio = result.audio
                    if audio is None:
                        continue
                    samples = np.asarray(audio.detach().cpu().numpy() if hasattr(audio, "detach") else audio, dtype=np.float32)
                    if samples.size == 0:
                        continue
                    if first_audio:
                        first_audio = False
                        self._emit(
                            "tts.first_audio",
                            backend="kokoro",
                            latency_ms=round((time.perf_counter() - started) * 1000, 1),
                        )
                    output.write(samples.reshape(-1, 1))
        finally:
            self._emit(
                "tts.completed",
                backend="kokoro",
                cancelled=self._stop.is_set(),
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            self._stop.clear()

    def close(self) -> None:
        with self._lock:
            if self._output is not None:
                try:
                    self._output.stop()
                    self._output.close()
                except Exception:
                    pass
                self._output = None
            self._pipeline = None
