from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class WakeWordDetector:
    """Local wake word gate with optional VAD and speaker-specific verification."""

    def __init__(
        self,
        model_path: str | Path,
        threshold: float = 0.85,
        patience: int = 2,
        verifier_path: str | Path | None = None,
        verifier_threshold: float = 0.30,
        vad_threshold: float | None = 0.50,
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

        # VAD is enabled by default to reject non-speech noise before activation.
        # A verifier is optional because it must be trained on the user's own voice.
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

    def predict(self, pcm16_16khz: bytes) -> float:
        import numpy as np

        scores: dict[str, Any] = self.model.predict(
            np.frombuffer(pcm16_16khz, dtype=np.int16)
        )
        return max((float(v) for v in scores.values()), default=0.0)

    def detected(self, pcm16_16khz: bytes) -> bool:
        score = self.predict(pcm16_16khz)
        self._hits = self._hits + 1 if score >= self.threshold else 0
        if self._hits >= self.patience:
            self._hits = 0
            return True
        return False

    def reset(self) -> None:
        self._hits = 0
        self.model.reset()
