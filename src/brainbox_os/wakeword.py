from __future__ import annotations

from pathlib import Path
from typing import Any


class WakeWordDetector:
    """Local wake word gate with correctly framed openWakeWord inference."""

    FRAME_SAMPLES = 1280  # 80 ms @ 16 kHz, openWakeWord's native streaming frame.

    def __init__(
        self,
        model_path: str | Path,
        threshold: float = 0.65,
        patience: int = 1,
        verifier_path: str | Path | None = None,
        verifier_threshold: float = 0.30,
        vad_threshold: float | None = 0.0,
    ):
        try:
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError("openWakeWord is not installed. Run: pip install -e '.[voice]'") from exc

        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"Wake word model not found: {path}")

        verifier = Path(verifier_path) if verifier_path else None
        if verifier and not verifier.exists():
            raise FileNotFoundError(f"Wake word verifier not found: {verifier}")

        kwargs: dict[str, Any] = {"wakeword_models": [str(path)]}
        if vad_threshold is not None and vad_threshold > 0:
            kwargs["vad_threshold"] = vad_threshold
        if verifier:
            model_name = path.stem
            kwargs["custom_verifier_models"] = {model_name: str(verifier)}
            kwargs["custom_verifier_threshold"] = verifier_threshold

        self.model = Model(**kwargs)
        self.threshold = threshold
        self.patience = max(1, patience)
        self._hits = 0
        self._buffer = bytearray()

    def predict(self, pcm16_16khz: bytes) -> float:
        import numpy as np

        samples = np.frombuffer(pcm16_16khz, dtype=np.int16)
        if len(samples) != self.FRAME_SAMPLES:
            raise ValueError(
                f"openWakeWord expects {self.FRAME_SAMPLES} samples per frame, got {len(samples)}"
            )
        scores: dict[str, Any] = self.model.predict(samples)
        return max((float(v) for v in scores.values()), default=0.0)

    def detected(self, pcm16_16khz: bytes) -> bool:
        # The microphone runtime uses ~30 ms audio blocks, while openWakeWord's
        # streaming models are designed around 80 ms / 1280 sample frames.
        # Accumulate here so every inference receives a correctly sized frame.
        self._buffer.extend(pcm16_16khz)
        frame_bytes = self.FRAME_SAMPLES * 2
        detected = False

        while len(self._buffer) >= frame_bytes:
            frame = bytes(self._buffer[:frame_bytes])
            del self._buffer[:frame_bytes]
            score = self.predict(frame)

            if score >= self.threshold:
                self._hits += 1
            else:
                self._hits = 0

            if self._hits >= self.patience:
                self._hits = 0
                detected = True
                print(
                    f'{{"event":"wake.score","score":{score:.4f},"threshold":{self.threshold:.4f}}}',
                    flush=True,
                )
                break

        return detected

    def reset(self) -> None:
        self._hits = 0
        self._buffer.clear()
        self.model.reset()
