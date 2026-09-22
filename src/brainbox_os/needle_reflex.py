from __future__ import annotations

from pathlib import Path
from typing import Any


class NeedleReflex:
    """Local Needle 3 reflex layer.

    Needle proposes structured calls. Brainbox Harness remains the authority that
    decides whether a proposed call is allowed to execute.
    """

    def __init__(self, tools: list[Any] | None = None, weights: str | Path | None = None, system: str | None = None):
        try:
            import needle
        except ImportError as exc:
            raise RuntimeError("Needle is not installed. Run: pip install -e '.[needle]'") from exc

        self._needle = needle
        self._tools = tools or []
        self._weights = Path(weights or __import__("os").getenv("BRAINBOX_NEEDLE_MODEL", "models/needle3.cact"))
        self._system = system
        if not self._weights.exists():
            raise FileNotFoundError(f"Needle weights not found: {self._weights}")
        self.agent = self._new_agent()

    def _new_agent(self):
        kwargs: dict[str, Any] = {"tools": self._tools, "weights": str(self._weights)}
        if self._system:
            kwargs["system"] = self._system
        return self._needle.Needle(**kwargs)

    def decide(self, text: str, tools: list[Any] | None = None) -> dict[str, Any]:
        if tools is not None and tools != self._tools:
            self._tools = tools
            self.agent = self._new_agent()
        return self.agent.complete(text)

    def decide_audio(self, audio: bytes, audio_format: str = "wav", sample_rate: int = 0, channels: int = 1) -> dict[str, Any]:
        return self.agent.complete(audio=audio, audio_format=audio_format, sample_rate=sample_rate, channels=channels)

    def reset(self) -> None:
        self.agent.reset()
