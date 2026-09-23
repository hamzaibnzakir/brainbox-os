from __future__ import annotations

import os
import queue
import threading
from collections import deque

import numpy as np


class WasapiEchoCapture:
    """Continuous Windows mic capture with a WASAPI speaker reference and WebRTC AEC3.

    The capture clocks run continuously. The cleaned microphone stream is kept
    deliberately shallow so Brainbox never consumes stale audio from a previous
    turn after the reasoner has finished.
    """

    def __init__(self, source_rate: int, block: int, *, delay_ms: int = 0):
        if os.name != "nt":
            raise RuntimeError("WASAPI echo capture is Windows-only")

        import soundcard as sc
        from pywebrtc_audio import AudioProcessor

        self.source_rate = int(source_rate)
        self.block = int(block)
        self.delay_ms = max(0, int(delay_ms))
        self._stop = threading.Event()
        self._condition = threading.Condition()
        self._mic_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=8)
        self._far_chunks: deque[np.ndarray] = deque()
        self._far_samples = 0
        self._output_queue: deque[np.ndarray] = deque()
        self._output_samples = 0
        self._error: Exception | None = None

        mic = sc.default_microphone()
        speaker = sc.default_speaker()
        loopback = sc.get_microphone(speaker.id, include_loopback=True)

        # Windows/WASAPI SoundCard is known to behave better with both channels
        # requested. We downmix to mono before AEC.
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

        self._mic_thread = threading.Thread(
            target=self._mic_worker,
            name="brainbox-aec-mic",
            daemon=True,
        )
        self._far_thread = threading.Thread(
            target=self._far_worker,
            name="brainbox-aec-loopback",
            daemon=True,
        )
        self._processor_thread = threading.Thread(
            target=self._processor_worker,
            name="brainbox-aec-processor",
            daemon=True,
        )

        self._mic_thread.start()
        self._far_thread.start()
        self._processor_thread.start()

        print(
            '{"event":"audio.aec.ready","backend":"webrtc-aec3",'
            '"reference":"wasapi-loopback","mode":"parallel-capture",'
            f'"sample_rate":{self.source_rate},"delay_ms":{self.delay_ms}}}',
            flush=True,
        )

    @staticmethod
    def _mono(data: np.ndarray) -> np.ndarray:
        data = np.asarray(data, dtype=np.float32)
        if data.ndim > 1:
            return data.mean(axis=1).astype(np.float32)
        return data.reshape(-1).astype(np.float32)

    def _fail(self, exc: Exception) -> None:
        self._error = exc
        self._stop.set()
        with self._condition:
            self._condition.notify_all()

    def _mic_worker(self) -> None:
        try:
            while not self._stop.is_set():
                data = self._mono(self._mic_recorder.record(numframes=self.block))
                if len(data) == 0:
                    continue
                try:
                    self._mic_queue.put(data, timeout=0.02)
                except queue.Full:
                    # Never let latency grow. Drop the oldest capture frame.
                    try:
                        self._mic_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self._mic_queue.put_nowait(data)
                    except queue.Full:
                        pass
        except Exception as exc:
            self._fail(exc)

    def _far_worker(self) -> None:
        try:
            while not self._stop.is_set():
                data = self._mono(self._loop_recorder.record(numframes=self.block))
                if len(data) == 0:
                    continue
                with self._condition:
                    self._far_chunks.append(data)
                    self._far_samples += len(data)
                    max_samples = max(self.source_rate // 2, self.block * 30)
                    while self._far_samples > max_samples and len(self._far_chunks) > 1:
                        self._far_samples -= len(self._far_chunks.popleft())
                    self._condition.notify_all()
        except Exception as exc:
            self._fail(exc)

    def _reference_for(self, count: int) -> np.ndarray:
        delay = int(self.source_rate * self.delay_ms / 1000)
        with self._condition:
            if self._far_samples - delay < count:
                return np.zeros(count, dtype=np.float32)

            # Take the render samples that correspond to the capture frame.
            target_end = self._far_samples - delay
            remaining = count
            selected: list[np.ndarray] = []
            cursor = self._far_samples

            for chunk in reversed(self._far_chunks):
                chunk_end = cursor
                chunk_start = chunk_end - len(chunk)
                cursor = chunk_start

                end = min(chunk_end, target_end)
                start = max(chunk_start, end - remaining)
                if end > start:
                    selected.append(chunk[start - chunk_start:end - chunk_start])
                    remaining -= end - start
                if remaining <= 0:
                    break

            if remaining:
                return np.zeros(count, dtype=np.float32)

            return np.concatenate(list(reversed(selected))).astype(np.float32, copy=False)

    def _append_output(self, audio: np.ndarray) -> None:
        with self._condition:
            self._output_queue.append(audio)
            self._output_samples += len(audio)
            # Keep at most 100 ms queued. A voice assistant should never trade
            # freshness for buffering.
            max_samples = max(int(self.source_rate * 0.10), self.block * 4)
            while self._output_samples > max_samples and len(self._output_queue) > 1:
                self._output_samples -= len(self._output_queue.popleft())
            self._condition.notify_all()

    def _processor_worker(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    near = self._mic_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                far = self._reference_for(len(near))
                cleaned = self._processor.process(near, far)
                self._append_output(
                    np.asarray(cleaned, dtype=np.float32).reshape(-1)
                )
        except Exception as exc:
            self._fail(exc)

    def flush(self) -> None:
        """Drop queued audio captured while Brainbox was thinking or speaking."""
        with self._condition:
            self._output_queue.clear()
            self._output_samples = 0
            while True:
                try:
                    self._mic_queue.get_nowait()
                except queue.Empty:
                    break
            self._condition.notify_all()

    def _take(self, count: int) -> np.ndarray:
        count = int(count)
        with self._condition:
            while (
                self._output_samples < count
                and not self._error
                and not self._stop.is_set()
            ):
                self._condition.wait(timeout=0.02)

            if self._error is not None:
                raise RuntimeError(f"AEC capture failed: {self._error}") from self._error

            parts: list[np.ndarray] = []
            remaining = count
            while remaining and self._output_queue:
                chunk = self._output_queue[0]
                take = min(remaining, len(chunk))
                parts.append(chunk[:take])
                remaining -= take
                self._output_samples -= take
                if take == len(chunk):
                    self._output_queue.popleft()
                else:
                    self._output_queue[0] = chunk[take:]

            if remaining:
                parts.append(np.zeros(remaining, dtype=np.float32))
            return np.concatenate(parts).astype(np.float32, copy=False)

    def read(self, frames: int):
        return self._take(int(frames)).reshape(-1, 1), False

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

        for thread in (self._mic_thread, self._far_thread, self._processor_thread):
            try:
                thread.join(timeout=1.0)
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
