from __future__ import annotations

import os
import re
import threading
from typing import Any


class PocketTTSSynthesizer:
    """Low-latency CPU Pocket TTS backend for Brainbox."""

    def __init__(self, voice: str = "george", speed: float = 1.08, quantize: bool = True) -> None:
        self.voice = voice
        self.speed = max(0.75, min(float(speed), 1.5))
        self.quantize = quantize
        self._model: Any | None = None
        self._voice_state: Any | None = None
        self._lock = threading.Lock()
        self._event_callback = None
        self._sample_rate = 24000

    @staticmethod
    def clean_text(text: str) -> str:
        text = re.sub(r'```.*?```', ' ', text, flags=re.S)
        text = re.sub(r'`([^`]*)`', r'\1', text)
        text = re.sub(r'[*_~]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:4000]

    def set_event_callback(self, callback) -> None:
        self._event_callback = callback

    def _emit(self, event: str, **payload) -> None:
        if self._event_callback is not None:
            try:
                self._event_callback(event, payload)
            except Exception:
                pass

    def _load(self) -> None:
        if self._model is not None and self._voice_state is not None:
            return
        from pocket_tts import TTSModel
        self._model = TTSModel.load_model(
            language=os.getenv('BRAINBOX_POCKET_LANGUAGE', 'english'),
            quantize=self.quantize,
        )
        self._voice_state = self._model.get_state_for_audio_prompt(self.voice)
        self._sample_rate = int(self._model.sample_rate)

    def warm(self) -> None:
        with self._lock:
            self._load()

    def speak(self, text: str) -> None:
        clean = self.clean_text(text)
        if not clean:
            return
        import numpy as np
        import sounddevice as sd
        with self._lock:
            self._load()
            self._emit('tts.synthesis_started', provider='pocket-tts')
            first = True
            for chunk in self._model.generate_audio_stream(self._voice_state, clean, copy_state=True):
                if chunk is None:
                    continue
                samples = chunk.detach().cpu().numpy().astype(np.float32, copy=False)
                if samples.size == 0:
                    continue
                if first:
                    first = False
                    self._emit('tts.first_audio', provider='pocket-tts', sample_rate=self._sample_rate, samples=int(samples.size))
                sd.play(samples, self._sample_rate, blocking=True)
                sd.stop()

    @property
    def active_provider(self) -> str:
        return 'pocket-tts'


def create_pocket_from_env() -> PocketTTSSynthesizer:
    return PocketTTSSynthesizer(
        voice=os.getenv('BRAINBOX_POCKET_VOICE', 'george'),
        speed=float(os.getenv('BRAINBOX_POCKET_SPEED', '1.08')),
        quantize=os.getenv('BRAINBOX_POCKET_QUANTIZE', 'true').lower() == 'true',
    )
