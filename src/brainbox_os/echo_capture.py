from __future__ import annotations

import os
import threading
import time
from collections import deque

import numpy as np


class WasapiEchoCapture:
    """Windows microphone capture with a WASAPI speaker reference and WebRTC AEC3."""

    def __init__(self, source_rate: int, block: int, *, delay_ms: int = 80):
        if os.name != "nt":
            raise RuntimeError("WASAPI echo capture is Windows-only")

        import soundcard as sc
        from pywebrtc_audio import AudioProcessor

        self.source_rate = int(source_rate)
        self.block = int(block)
        self.delay_ms = max(0, int(delay_ms))
        self._stop = threading.Event()
        self._condition = threading.Condition()
        self._far_chunks: deque[np.ndarray] = deque()
        self._far_samples = 0
        self._error: Exception | None = None

        mic = sc.default_microphone()
        speaker = sc.default_speaker()
        loopback = sc.get_microphone(speaker.id, include_loopback=True)

        self._mic_recorder = mic.recorder(
            samplerate=self.source_rate,
            blocksize=self.block,
            channels=1,
        )
        self._loop_recorder = loopback.recorder(
            samplerate=self.source_rate,
            blocksize=self.block,
            channels=1,
        )

        self._processor = AudioProcessor(
            sample_rate=self.source_rate,
            num_channels=1,
            echo_cancellation=True,
            noise_suppression=True,
            auto_gain_control=False,
            stream_delay_ms=self.delay_ms,
        )

        self._mic_recorder.__enter__()
        try:
            self._loop_recorder.__enter__()
        except Exception:
            self._mic_recorder.__exit__(None, None, None)
            raise

        self._target_history = max(
            self.block,
            int(self.source_rate * self.delay_ms / 1000) + self.block * 2,
        )
        self._thread = threading.Thread(
            target=self._loopback_worker,
            name="brainbox-wasapi-loopback",
            daemon=True,
        )
        self._thread.start()

        deadline = time.monotonic() + 0.25
        with self._condition:
            while (
                self._far_samples < self._target_history
                and not self._error
                and time.monotonic() < deadline
            ):
                self._condition.wait(timeout=0.02)

        print(
            '{"event":"audio.aec.ready","backend":"webrtc-aec3","reference":"wasapi-loopback",'
            f'"sample_rate":{self.source_rate},"delay_ms":{self.delay_ms}' + '}',
            flush=True,
        )

    def _loopback_worker(self) -> None:
        try:
            while not self._stop.is_set():
                data = np.asarray(
                    self._loop_recorder.record(numframes=self.block),
                    dtype=np.float32,
                )
                if data.ndim > 1:
                    data = data.mean(axis=1)
                else:
                    data = data.reshape(-1)
                if len(data) == 0:
                    continue
                with self._condition:
                    self._far_chunks.append(data.copy())
                    self._far_samples += len(data)
                    max_buffer = max(
                        self._target_history + self.block * 8,
                        self.source_rate,
                    )
                    while self._far_samples > max_buffer and len(self._far_chunks) > 1:
                        old = self._far_chunks.popleft()
                        self._far_samples -= len(old)
                    self._condition.notify_all()
        except Exception as exc:
            self._error = exc
            with self._condition:
                self._condition.notify_all()

    def _take_reference(self, count: int) -> np.ndarray:
        with self._condition:
            deadline = time.monotonic() + 0.12
            while (
                self._far_samples < self._target_history + count
                and not self._error
                and not self._stop.is_set()
                and time.monotonic() < deadline
            ):
                self._condition.wait(timeout=0.01)

            target = max(count, int(self.source_rate * self.delay_ms / 1000))
            while self._far_samples > target + count and len(self._far_chunks) > 1:
                old = self._far_chunks.popleft()
                self._far_samples -= len(old)

            parts: list[np.ndarray] = []
            remaining = count
            while remaining > 0 and self._far_chunks:
                chunk = self._far_chunks[0]
                take = min(remaining, len(chunk))
                parts.append(chunk[:take])
                remaining -= take
                self._far_samples -= take
                if take == len(chunk):
                    self._far_chunks.popleft()
                else:
                    self._far_chunks[0] = chunk[take:]
            if remaining:
                parts.append(np.zeros(remaining, dtype=np.float32))
            return np.concatenate(parts)

    def read(self, frames: int):
        near = np.asarray(
            self._mic_recorder.record(numframes=int(frames)),
            dtype=np.float32,
        )
        if near.ndim > 1:
            near = near.mean(axis=1)
        else:
            near = near.reshape(-1)

        far = self._take_reference(len(near))
        cleaned = self._processor.process(near, far)
        return np.asarray(cleaned, dtype=np.float32).reshape(-1, 1), False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def reset_aec(self) -> None:
        self._processor.reset()

    def close(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        try:
            self._thread.join(timeout=1.0)
        except Exception:
            pass
        try:
            self._loop_recorder.__exit__(None, None, None)
        except Exception:
            pass
        try:
            self._mic_recorder.__exit__(None, None, None)
        except Exception:
            pass
