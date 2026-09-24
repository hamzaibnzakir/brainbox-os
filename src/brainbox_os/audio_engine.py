from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class AudioEngineConfig:
    """Configuration for the single-owner microphone/speaker audio engine."""

    sample_rate: int = 48000
    channels: int = 1
    block_ms: int = 10
    queue_ms: int = 300
    stream_delay_ms: int = 0
    enable_aec: bool = True
    enable_noise_suppression: bool = True


class AudioEngine:
    """Own the microphone and speaker reference for the entire voice session.

    The engine deliberately has one reader for the microphone and one reader for
    the WASAPI speaker loopback. Runtime code consumes cleaned microphone frames
    through read(). It must never create a second reader for the same microphone.

    pywebrtc-audio supplies WebRTC AEC3. SoundCard supplies Windows WASAPI
    microphone and speaker-loopback capture. If the optional AEC stack is not
    installed, the engine can run in raw-mic mode instead of silently pretending
    that echo cancellation is active.
    """

    def __init__(
        self,
        config: AudioEngineConfig | None = None,
        event_callback: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.config = config or AudioEngineConfig()
        self.event_callback = event_callback
        self._mic = None
        self._far = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._near_queue: deque[np.ndarray] = deque()
        self._far_queue: deque[np.ndarray] = deque()
        self._near_samples = 0
        self._far_samples = 0
        self._started = False
        self._aec = None
        self._aec_available = False
        self._last_far_rms = 0.0
        self._last_near_rms = 0.0
        self._last_clean_rms = 0.0
        self._dropped_blocks = 0
        self._data_ready = threading.Condition(self._lock)

    @property
    def aec_available(self) -> bool:
        return self._aec_available

    @property
    def block_samples(self) -> int:
        return max(1, int(self.config.sample_rate * self.config.block_ms / 1000))

    def _emit(self, event: str, **payload) -> None:
        if self.event_callback:
            self.event_callback(event, payload)

    @staticmethod
    def _mono(data: np.ndarray) -> np.ndarray:
        array = np.asarray(data, dtype=np.float32)
        if array.ndim == 1:
            return array
        return array.mean(axis=1).astype(np.float32, copy=False)

    @staticmethod
    def _rms(data: np.ndarray) -> float:
        if data.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(data), dtype=np.float64)))

    def _append_bounded(self, queue: deque[np.ndarray], samples_name: str, data: np.ndarray) -> None:
        samples = len(data)
        queue.append(data)
        current = getattr(self, samples_name) + samples
        limit = max(self.block_samples, int(self.config.sample_rate * self.config.queue_ms / 1000))
        while current > limit and queue:
            current -= len(queue.popleft())
            self._dropped_blocks += 1
        setattr(self, samples_name, current)

    def _take(self, queue: deque[np.ndarray], samples_name: str, count: int) -> np.ndarray:
        parts: list[np.ndarray] = []
        remaining = count
        current = getattr(self, samples_name)
        while remaining > 0 and queue:
            head = queue[0]
            take = min(remaining, len(head))
            parts.append(head[:take])
            remaining -= take
            if take == len(head):
                queue.popleft()
            else:
                queue[0] = head[take:]
            current -= take
        setattr(self, samples_name, max(0, current))
        if remaining:
            parts.append(np.zeros(remaining, dtype=np.float32))
        return np.concatenate(parts) if len(parts) > 1 else parts[0]

    def _capture_stream(self, recorder, queue: deque[np.ndarray], samples_name: str, rms_name: str) -> None:
        block = self.block_samples
        while not self._stop.is_set():
            try:
                data = self._mono(recorder.record(numframes=block))
                if len(data) != block:
                    data = np.pad(data, (0, max(0, block - len(data))))[:block]
                with self._data_ready:
                    self._append_bounded(queue, samples_name, data)
                    setattr(self, rms_name, self._rms(data))
                    self._data_ready.notify_all()
            except Exception as exc:
                self._emit("audio.error", error=str(exc), stage=samples_name)
                time.sleep(0.01)

    def _capture_loop(self) -> None:
        self._near_thread = threading.Thread(
            target=self._capture_stream,
            args=(self._mic, self._near_queue, "_near_samples", "_last_near_rms"),
            name="brainbox-mic-capture",
            daemon=True,
        )
        self._far_thread = threading.Thread(
            target=self._capture_stream,
            args=(self._far, self._far_queue, "_far_samples", "_last_far_rms"),
            name="brainbox-speaker-loopback",
            daemon=True,
        )
        self._near_thread.start()
        self._far_thread.start()
        while not self._stop.is_set():
            with self._data_ready:
                self._data_ready.wait(timeout=0.05)
    def _build_aec(self) -> None:
        if not self.config.enable_aec:
            return
        try:
            from pywebrtc_audio import AudioProcessor

            self._aec = AudioProcessor(
                sample_rate=self.config.sample_rate,
                num_channels=1,
                echo_cancellation=True,
                noise_suppression=self.config.enable_noise_suppression,
                auto_gain_control=False,
                stream_delay_ms=self.config.stream_delay_ms,
            )
            self._aec_available = True
            self._emit(
                "audio.aec.ready",
                sample_rate=self.config.sample_rate,
                block_ms=self.config.block_ms,
            )
        except ImportError:
            self._emit("audio.aec.unavailable", reason="pywebrtc-audio not installed")
        except Exception as exc:
            self._emit("audio.aec.unavailable", reason=str(exc))

    def start(self) -> None:
        if self._started:
            return
        if os.name != "nt":
            raise RuntimeError("AudioEngine currently requires Windows WASAPI loopback.")

        try:
            import soundcard as sc
        except ImportError as exc:
            raise RuntimeError("soundcard is required for the Windows audio engine") from exc

        self._mic = sc.default_microphone()
        speaker = sc.default_speaker()
        self._far = sc.get_microphone(speaker.id, include_loopback=True)

        self._build_aec()

        block = self.block_samples
        self._stop.clear()
        self._mic_recorder = self._mic.recorder(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            blocksize=block,
        )
        self._far_recorder = self._far.recorder(
            samplerate=self.config.sample_rate,
            channels=2,
            blocksize=block,
        )
        self._mic_recorder.__enter__()
        self._far_recorder.__enter__()
        self._mic = self._mic_recorder
        self._far = self._far_recorder
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="brainbox-audio-engine",
            daemon=True,
        )
        self._thread.start()
        self._started = True
        self._emit("audio.mic.started", sample_rate=self.config.sample_rate)

    def read(self, frames: int | None = None) -> np.ndarray:
        """Return exactly frames of cleaned mono float32 microphone audio."""
        if not self._started:
            raise RuntimeError("AudioEngine is not started")
        count = frames or self.block_samples
        deadline = time.monotonic() + 2.0
        with self._data_ready:
            while self._near_samples < count and not self._stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._data_ready.wait(timeout=min(remaining, 0.05))
            near = self._take(self._near_queue, "_near_samples", count)
            far = self._take(self._far_queue, "_far_samples", count)

        if self._aec_available and self._aec is not None:
            try:
                clean = np.asarray(self._aec.process(near, far), dtype=np.float32)
            except Exception as exc:
                self._emit("audio.error", error=str(exc), stage="aec")
                clean = near
        else:
            clean = near

        self._last_clean_rms = self._rms(clean)
        return clean

    def read_seconds(self, seconds: float) -> np.ndarray:
        count = max(self.block_samples, int(self.config.sample_rate * seconds))
        chunks = []
        remaining = count
        while remaining:
            take = min(self.block_samples, remaining)
            chunks.append(self.read(take))
            remaining -= take
        return np.concatenate(chunks)

    def reset(self) -> None:
        if self._aec is not None:
            try:
                self._aec.reset()
            except Exception:
                pass
        with self._data_ready:
            self._near_queue.clear()
            self._far_queue.clear()
            self._near_samples = 0
            self._far_samples = 0
            self._data_ready.notify_all()
        self._emit("audio.aec.reset")

    def flush(self) -> None:
        with self._data_ready:
            self._near_queue.clear()
            self._far_queue.clear()
            self._near_samples = 0
            self._far_samples = 0
            self._data_ready.notify_all()

    def diagnostics(self) -> dict:
        with self._lock:
            return {
                "started": self._started,
                "aec_available": self._aec_available,
                "sample_rate": self.config.sample_rate,
                "block_ms": self.config.block_ms,
                "near_queue_ms": round(self._near_samples * 1000 / self.config.sample_rate, 1),
                "far_queue_ms": round(self._far_samples * 1000 / self.config.sample_rate, 1),
                "near_rms": round(self._last_near_rms, 6),
                "far_rms": round(self._last_far_rms, 6),
                "clean_rms": round(self._last_clean_rms, 6),
                "dropped_blocks": self._dropped_blocks,
            }

    def close(self) -> None:
        if not self._started:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        for recorder_name in ("_far_recorder", "_mic_recorder"):
            recorder = getattr(self, recorder_name, None)
            if recorder is not None:
                try:
                    recorder.__exit__(None, None, None)
                except Exception:
                    pass
        self._thread = None
        self._started = False
        self._emit("audio.mic.stopped")

    def __enter__(self) -> "AudioEngine":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
