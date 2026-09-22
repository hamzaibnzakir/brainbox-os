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
    input_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class ToolRegistry:
    """Local execution boundary. MCP adapters can register the same interface."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def schemas(self) -> list[dict[str, Any]]:
        schemas = []
        for s in self._tools.values():
            schema = {"name": s.name, "description": s.description, "risk": s.risk.value}
            if s.input_schema is not None:
                schema["parameters"] = s.input_schema
            if s.metadata:
                schema.update(s.metadata)
            schemas.append(schema)
        return schemas

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

    def register_mcp_server(self, bridge: Any) -> list[str]:
        """Discover one MCP server and register its tools behind this execution boundary."""
        from .policy import Risk

        risk_map = {risk.value: risk for risk in Risk}
        registered: list[str] = []
        for schema in bridge.discover():
            name = schema["name"]
            if name in self._tools:
                raise ValueError(f"Tool already registered: {name}")
            risk = risk_map.get(schema.get("risk", Risk.EXTERNAL.value), Risk.EXTERNAL)
            self.register(ToolSpec(
                name=name,
                function=lambda _name=name, **kwargs: bridge.call(_name, kwargs),
                risk=risk,
                description=schema.get("description", ""),
                input_schema=schema.get("input_schema"),
                metadata={"mcp_server": schema.get("mcp_server", bridge.config.name)},
            ))
            registered.append(name)
        return registered
