from typing import Any, Protocol

class ReflexModel(Protocol):
    def decide(self, text: str, tools: list[dict[str, Any]]) -> dict[str, Any]: ...

class PlaceholderReflex:
    """Temporary interface until the first local model adapter is installed."""
    def decide(self, text: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "intent": "unknown",
            "tool_calls": [],
            "confidence": 0.0,
            "needs_reasoner": True,
        }
