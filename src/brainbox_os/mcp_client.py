from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MCPServerConfig:
    """Connection definition for one MCP server."""
    name: str
    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    default_risk: str = "external"

    def target(self) -> Any:
        if self.url:
            return self.url
        if self.command:
            from mcp import StdioServerParameters
            return StdioServerParameters(command=self.command, args=list(self.args), env=self.env or None)
        raise ValueError(f"MCP server {self.name!r} needs url or command")


class MCPToolBridge:
    """Discover and execute MCP tools through the central ToolRegistry boundary."""

    def __init__(self, config: MCPServerConfig):
        self.config = config

    @staticmethod
    def _run(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError("MCP sync bridge cannot run inside an active asyncio loop")

    async def _list_tools_async(self) -> list[dict[str, Any]]:
        from mcp import Client
        async with Client(self.config.target()) as client:
            page = await client.list_tools()
            tools = []
            cursor = page.next_cursor
            tools.extend(page.tools)
            while cursor is not None:
                page = await client.list_tools(cursor=cursor)
                tools.extend(page.tools)
                cursor = page.next_cursor
            return [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.input_schema,
                    "risk": self.config.default_risk,
                    "mcp_server": self.config.name,
                }
                for tool in tools
            ]

    def discover(self) -> list[dict[str, Any]]:
        return self._run(self._list_tools_async())

    async def _call_async(self, name: str, arguments: dict[str, Any]) -> Any:
        from mcp import Client
        async with Client(self.config.target()) as client:
            result = await client.call_tool(name, arguments)
            if result.is_error:
                messages = []
                for item in result.content:
                    text = getattr(item, "text", None)
                    if text:
                        messages.append(text)
                raise RuntimeError("; ".join(messages) or f"MCP tool {name} failed")
            if result.structured_content is not None:
                return result.structured_content
            output = []
            for item in result.content:
                text = getattr(item, "text", None)
                if text is not None:
                    output.append(text)
            return "\n".join(output)

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        return self._run(self._call_async(name, arguments))
