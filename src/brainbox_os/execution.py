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
    """Small local registry used by the harness. MCP will plug into this boundary."""

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

    def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name].function(**arguments)

    def risk(self, name: str) -> Risk:
        return self._tools[name].risk
