from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any


class KokoroSynthesizer:
    """Warm, local Kokoro ONNX synthesizer for low-latency Brainbox speech."""

    def __init__(self, model_path: str, voices_path: str, voice: str = "bm_lewis", lang: str = "en-gb", speed: float = 1.04) -> None:
        self.model_path = Path(os.path.expandvars(os.path.expanduser(model_path))).resolve()
        self.voices_path = Path(os.path.expandvars(os.path.expanduser(voices_path))).resolve()
        self.voice = voice
        self.lang = lang
        self.speed = max(0.75, min(float(speed), 1.35))
        self._engine: Any | None = None
        self._lock = threading.Lock()

    @staticmethod
    def clean_text(text: str) -> str:
        text = re.sub(r"```.*?```", " ", text, flags=re.S)
        text = re.sub(r"`([^`]*)`", r"\1", text)
        text = re.sub(r"[*_~]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:4000]

    def _load(self) -> Any:
        if self._engine is not None:
            return self._engine
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Kokoro model not found: {self.model_path}")
        if not self.voices_path.is_file():
            raise FileNotFoundError(f"Kokoro voices not found: {self.voices_path}")
        from kokoro_onnx import Kokoro
        self._engine = Kokoro(str(self.model_path), str(self.voices_path))
        return self._engine

    def speak(self, text: str) -> None:
        clean = self.clean_text(text)
        if not clean:
            return
        import sounddevice as sd
        with self._lock:
            engine = self._load()
            samples, sample_rate = engine.create(clean, voice=self.voice, speed=self.speed, lang=self.lang)
            sd.play(samples, sample_rate, blocking=True)
            sd.stop()

    def warm(self) -> None:
        self._load()


def create_kokoro_from_env() -> KokoroSynthesizer:
    return KokoroSynthesizer(
        model_path=os.getenv("BRAINBOX_KOKORO_MODEL", "models/tts/kokoro-v1.0.int8.onnx"),
        voices_path=os.getenv("BRAINBOX_KOKORO_VOICES", "models/tts/voices-v1.0.bin"),
        voice=os.getenv("BRAINBOX_KOKORO_VOICE", "bm_lewis"),
        lang=os.getenv("BRAINBOX_KOKORO_LANG", "en-gb"),
        speed=float(os.getenv("BRAINBOX_KOKORO_SPEED", "1.04")),
    )
