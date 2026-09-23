from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any


class KokoroSynthesizer:
    """Warm, local Kokoro ONNX synthesizer for low-latency Brainbox speech."""

    def __init__(
        self,
        model_path: str,
        voices_path: str,
        voice: str = "bm_lewis",
        lang: str = "en-gb",
        speed: float = 1.12,
        provider: str = "auto",
    ) -> None:
        self.model_path = Path(os.path.expandvars(os.path.expanduser(model_path))).resolve()
        self.voices_path = Path(os.path.expandvars(os.path.expanduser(voices_path))).resolve()
        self.voice = voice
        self.lang = lang
        self.speed = max(0.75, min(float(speed), 1.35))
        self.provider = provider.strip().lower() or "auto"
        self._engine: Any | None = None
        self._lock = threading.Lock()
        self._active_provider = "CPUExecutionProvider"

    @staticmethod
    def clean_text(text: str) -> str:
        tick = chr(96)
        text = text.replace(tick * 3, " ")
        text = re.sub(tick + r"([^" + tick + r"]*)" + tick, r"\1", text)
        text = re.sub(r"[*_~]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:4000]

    def _select_provider(self) -> str:
        if self.provider in {"cpu", "cpuexecutionprovider"}:
            return "CPUExecutionProvider"
        if self.provider in {"cuda", "cudaexecutionprovider"}:
            return "CUDAExecutionProvider"
        if self.provider in {"directml", "dmlexecutionprovider"}:
            return "DmlExecutionProvider"

        try:
            import onnxruntime as ort
            available = set(ort.get_available_providers())
        except Exception:
            return "CPUExecutionProvider"

        if "CUDAExecutionProvider" in available:
            return "CUDAExecutionProvider"
        if "DmlExecutionProvider" in available:
            return "DmlExecutionProvider"
        return "CPUExecutionProvider"

    def _load(self) -> Any:
        if self._engine is not None:
            return self._engine
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Kokoro model not found: {self.model_path}")
        if not self.voices_path.is_file():
            raise FileNotFoundError(f"Kokoro voices not found: {self.voices_path}")

        import onnxruntime as ort
        from kokoro_onnx import Kokoro

        provider = self._select_provider()
        providers = [provider]
        if provider != "CPUExecutionProvider":
            providers.append("CPUExecutionProvider")

        options = ort.SessionOptions()
        options.intra_op_num_threads = max(
            1, int(os.getenv("BRAINBOX_KOKORO_CPU_THREADS", str(os.cpu_count() or 4)))
        )
        options.inter_op_num_threads = max(1, min(4, options.intra_op_num_threads // 2 or 1))
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        try:
            session = ort.InferenceSession(
                str(self.model_path),
                sess_options=options,
                providers=providers,
            )
            self._engine = Kokoro.from_session(session, str(self.voices_path))
            self._active_provider = session.get_providers()[0]
        except Exception:
            if provider != "CPUExecutionProvider":
                session = ort.InferenceSession(
                    str(self.model_path),
                    sess_options=options,
                    providers=["CPUExecutionProvider"],
                )
                self._engine = Kokoro.from_session(session, str(self.voices_path))
                self._active_provider = "CPUExecutionProvider"
            else:
                raise
        return self._engine

    def speak(self, text: str) -> None:
        clean = self.clean_text(text)
        if not clean:
            return

        import sounddevice as sd

        with self._lock:
            engine = self._load()
            stream = engine.create_stream(
                clean,
                voice=self.voice,
                speed=self.speed,
                lang=self.lang,
            )

            for samples, sample_rate in _run_async_stream(stream):
                if len(samples) == 0:
                    continue
                sd.play(samples, sample_rate, blocking=True)
                sd.stop()

    def warm(self) -> None:
        self._load()

    @property
    def active_provider(self) -> str:
        return self._active_provider


def _run_async_stream(stream: Any):
    import asyncio
    import queue

    q: queue.Queue[Any] = queue.Queue(maxsize=2)
    done = object()

    def producer() -> None:
        async def consume():
            try:
                async for item in stream:
                    q.put(item)
            finally:
                q.put(done)

        asyncio.run(consume())

    threading.Thread(target=producer, daemon=True).start()
    while True:
        item = q.get()
        if item is done:
            break
        yield item


def create_kokoro_from_env() -> KokoroSynthesizer:
    return KokoroSynthesizer(
        model_path=os.getenv("BRAINBOX_KOKORO_MODEL", "models/tts/kokoro-v1.0.int8.onnx"),
        voices_path=os.getenv("BRAINBOX_KOKORO_VOICES", "models/tts/voices-v1.0.bin"),
        voice=os.getenv("BRAINBOX_KOKORO_VOICE", "bm_lewis"),
        lang=os.getenv("BRAINBOX_KOKORO_LANG", "en-gb"),
        speed=float(os.getenv("BRAINBOX_KOKORO_SPEED", "1.12")),
        provider=os.getenv("BRAINBOX_KOKORO_PROVIDER", "auto"),
    )
