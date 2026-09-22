from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .policy import Risk


@dataclass(frozen=True)
class ToolSpec:
    name: str
    function: Callable[..., Any]
    risk: Risk = Risk.READ
    description: str = ""


class ToolRegistry:
    """Local execution boundary. MCP adapters can register the same interface."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {"name": s.name, "description": s.description, "risk": s.risk.value}
            for s in self._tools.values()
        ]

    def names(self) -> set[str]:
        return set(self._tools)

    def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name].function(**arguments)

    def risk(self, name: str) -> Risk:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name].risk
