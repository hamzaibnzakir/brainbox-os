from __future__ import annotations

import os
import threading
from collections import deque

import numpy as np


class WasapiEchoCapture:
    """Continuous Windows mic capture with WASAPI speaker reference and WebRTC AEC3."""

    def __init__(self, source_rate: int, block: int, *, delay_ms: int = 50):
        if os.name != "nt":
            raise RuntimeError("WASAPI echo capture is Windows-only")

        import soundcard as sc
        from pywebrtc_audio import AudioProcessor

        self.source_rate = int(source_rate)
        self.block = int(block)
        self.delay_ms = max(0, int(delay_ms))
        self._stop = threading.Event()
        self._condition = threading.Condition()
        self._queue: deque[np.ndarray] = deque()
        self._queued_samples = 0
        self._error: Exception | None = None
        self._echo_active = False
        self._max_queue_samples = max(self.source_rate, self.block * 100)

        mic = sc.default_microphone()
        speaker = sc.default_speaker()
        loopback = sc.get_microphone(speaker.id, include_loopback=True)

        self._mic_recorder = mic.recorder(
            samplerate=self.source_rate,
            blocksize=self.block,
            channels=2,
        )
        self._loop_recorder = loopback.recorder(
            samplerate=self.source_rate,
            blocksize=self.block,
            channels=2,
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

        self._thread = threading.Thread(
            target=self._capture_worker,
            name="brainbox-aec-capture",
            daemon=True,
        )
        self._thread.start()

        print(
            '{"event":"audio.aec.ready","backend":"webrtc-aec3",'
            '"reference":"wasapi-loopback","mode":"continuous",'
            f'"sample_rate":{self.source_rate},"delay_ms":{self.delay_ms},"channels":2' + '}',
            flush=True,
        )

    @staticmethod
    def _mono(data: np.ndarray) -> np.ndarray:
        data = np.asarray(data, dtype=np.float32)
        if data.ndim > 1:
            return data.mean(axis=1).astype(np.float32)
        return data.reshape(-1).astype(np.float32)

    def _capture_worker(self) -> None:
        try:
            while not self._stop.is_set():
                # Keep BOTH devices flowing continuously. This prevents mic-buffer
                # buildup while Brainbox is speaking and gives AEC3 synchronized
                # near/far frames instead of trying to reconstruct them afterwards.
                near = self._mono(self._mic_recorder.record(numframes=self.block))
                far = self._mono(self._loop_recorder.record(numframes=self.block))
                if len(near) == 0:
                    continue

                if self._echo_active:
                    cleaned = self._processor.process(near, far)
                else:
                    cleaned = near

                cleaned = np.asarray(cleaned, dtype=np.float32).reshape(-1)
                with self._condition:
                    self._queue.append(cleaned.copy())
                    self._queued_samples += len(cleaned)
                    while self._queued_samples > self._max_queue_samples and len(self._queue) > 1:
                        old = self._queue.popleft()
                        self._queued_samples -= len(old)
                    self._condition.notify_all()
        except Exception as exc:
            self._error = exc
            with self._condition:
                self._condition.notify_all()

    def _take(self, count: int) -> np.ndarray:
        count = int(count)
        if count <= 0:
            return np.empty(0, dtype=np.float32)

        with self._condition:
            while (
                self._queued_samples < count
                and not self._error
                and not self._stop.is_set()
            ):
                self._condition.wait(timeout=0.05)

            if self._error is not None:
                raise RuntimeError(f"AEC capture failed: {self._error}") from self._error

            parts: list[np.ndarray] = []
            remaining = count
            while remaining and self._queue:
                chunk = self._queue[0]
                take = min(remaining, len(chunk))
                parts.append(chunk[:take])
                remaining -= take
                self._queued_samples -= take
                if take == len(chunk):
                    self._queue.popleft()
                else:
                    self._queue[0] = chunk[take:]

            if remaining:
                parts.append(np.zeros(remaining, dtype=np.float32))
            return np.concatenate(parts).astype(np.float32, copy=False)

    def set_echo_active(self, active: bool) -> None:
        active = bool(active)
        if active == self._echo_active:
            return

        self._echo_active = active
        if not active:
            # Reset the adaptive filter and discard audio captured while Brainbox
            # was speaking. The next read starts from a clean acoustic state.
            self._processor.reset()
            with self._condition:
                self._queue.clear()
                self._queued_samples = 0
                self._condition.notify_all()

    def read(self, frames: int):
        audio = self._take(int(frames))
        return audio.reshape(-1, 1), False

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
