from __future__ import annotations

import os
import threading
from collections import deque

import numpy as np


class WasapiEchoCapture:
    """Windows microphone capture with WASAPI speaker reference and WebRTC AEC3."""

    def __init__(self, source_rate: int, block: int, *, delay_ms: int = 60):
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

        # SoundCard documents a Windows/WASAPI single-channel capture issue.
        # Capture stereo and downmix ourselves.
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

        self._max_far_samples = max(self.source_rate // 2, self.block * 20)
        self._thread = threading.Thread(
            target=self._loopback_worker,
            name="brainbox-wasapi-loopback",
            daemon=True,
        )
        self._thread.start()

        print(
            '{"event":"audio.aec.ready","backend":"webrtc-aec3","reference":"wasapi-loopback",'
            f'"sample_rate":{self.source_rate},"delay_ms":{self.delay_ms},"channels":2}}',
            flush=True,
        )

    @staticmethod
    def _mono(data: np.ndarray) -> np.ndarray:
        data = np.asarray(data, dtype=np.float32)
        if data.ndim > 1:
            return data.mean(axis=1).astype(np.float32)
        return data.reshape(-1).astype(np.float32)

    def _loopback_worker(self) -> None:
        try:
            while not self._stop.is_set():
                data = self._mono(self._loop_recorder.record(numframes=self.block))
                if len(data) == 0:
                    continue
                with self._condition:
                    self._far_chunks.append(data.copy())
                    self._far_samples += len(data)
                    while self._far_samples > self._max_far_samples and len(self._far_chunks) > 1:
                        old = self._far_chunks.popleft()
                        self._far_samples -= len(old)
                    self._condition.notify_all()
        except Exception as exc:
            self._error = exc
            with self._condition:
                self._condition.notify_all()

    def _latest_reference(self, count: int) -> np.ndarray:
        """Return the newest render samples without waiting on the render clock."""
        count = int(count)
        if count <= 0:
            return np.empty(0, dtype=np.float32)

        with self._condition:
            if self._far_samples < count:
                return np.zeros(count, dtype=np.float32)

            remaining = count
            parts: list[np.ndarray] = []
            for chunk in reversed(self._far_chunks):
                take = min(remaining, len(chunk))
                if take:
                    parts.append(chunk[-take:])
                    remaining -= take
                if remaining <= 0:
                    break

            if remaining:
                return np.zeros(count, dtype=np.float32)

            return np.concatenate(list(reversed(parts))).astype(np.float32, copy=False)

    def read(self, frames: int):
        near = self._mono(self._mic_recorder.record(numframes=int(frames)))
        if len(near) == 0:
            return np.zeros((0, 1), dtype=np.float32), False

        far = self._latest_reference(len(near))
        far_rms = float(np.sqrt(np.mean(np.square(far)))) if far.size else 0.0

        # Do not run AEC against an empty render reference. It can attenuate
        # the user's voice even though there is no speaker echo to remove.
        if far_rms < 0.001:
            cleaned = near
        else:
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
