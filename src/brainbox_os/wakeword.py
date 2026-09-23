from __future__ import annotations
from pathlib import Path
from typing import Any

class WakeWordDetector:
    """Local wake word gate for the Brainbox microphone stream."""
    def __init__(self, model_path: str | Path, threshold: float = 0.85, patience: int = 2):
        try:
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError("openWakeWord is not installed. Run: pip install -e '.[voice]'") from exc
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"Wake word model not found: {path}")
        self.model = Model(wakeword_models=[str(path)])
        self.threshold = threshold
        self.patience = max(1, patience)
        self._hits = 0

    def predict(self, pcm16_16khz: bytes) -> float:
        import numpy as np
        scores: dict[str, Any] = self.model.predict(np.frombuffer(pcm16_16khz, dtype=np.int16))
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
