from __future__ import annotations

from pathlib import Path
from typing import Any


class NeedleReflex:
    """Needle 3 local reflex model for fast tool selection and structured actions."""

    def __init__(self, tools: list[Any] | None = None, weights: str | Path | None = None):
        try:
            import needle
        except ImportError as exc:
            raise RuntimeError(
                "Needle is not installed. Run: pip install -e '.[needle]'"
            ) from exc

        self._needle = needle
        self._tools = tools or []
        model_path = Path(weights) if weights else Path("models/needle3.cact")
        self._weights = model_path if model_path.exists() else None
        kwargs: dict[str, Any] = {"tools": self._tools}
        if self._weights:
            kwargs["weights"] = str(self._weights)
        self.agent = needle.Needle(**kwargs)

    def decide(self, text: str, tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Turn a user utterance into structured tool calls using Needle 3."""
        if tools is not None and tools != self._tools:
            self._tools = tools
            self.agent = self._needle.Needle(tools=tools, **({"weights": str(self._weights)} if self._weights else {}))

        result = self.agent.complete(text)
        return result

    def run(self, text: str, max_steps: int = 8) -> dict[str, Any]:
        """Run Needle's tool loop. The harness remains responsible for policy and permissions."""
        return self.agent.run(text, max_steps=max_steps, strict=True)
