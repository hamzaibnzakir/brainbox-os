from __future__ import annotations

from pathlib import Path
from typing import Any


class WakeWordDetector:
    """Local wake word gate for the Brainbox microphone stream."""

    def __init__(self, model_path: str | Path):
        try:
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError("openWakeWord is not installed. Run: pip install -e '.[voice]'") from exc
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"Wake word model not found: {path}")
        self.model = Model(wakeword_models=[str(path)])

    def predict(self, pcm16_16khz: bytes) -> float:
        import numpy as np
        scores: dict[str, Any] = self.model.predict(np.frombuffer(pcm16_16khz, dtype=np.int16))
        return max((float(v) for v in scores.values()), default=0.0)

    def detected(self, pcm16_16khz: bytes, threshold: float = 0.60) -> bool:
        return self.predict(pcm16_16khz) >= threshold
