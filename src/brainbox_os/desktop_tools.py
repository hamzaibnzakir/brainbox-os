from __future__ import annotations

import platform
from typing import Any

from .execution import ToolRegistry, ToolSpec
from .policy import Risk


def register_desktop_tools(registry: ToolRegistry) -> None:
    """Register local desktop capabilities. These execute on the user's PC, not the VPS."""
    if platform.system() == "Windows":
        from .windows_tools import open_application
        registry.register(ToolSpec(
            name="open_application",
            function=open_application,
            risk=Risk.READ,
            description="Open a Windows desktop application by name, executable, path, URL, or shell target.",
        ))
