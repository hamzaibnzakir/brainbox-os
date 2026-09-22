from __future__ import annotations

import platform
from typing import Any

from .execution import ToolRegistry, ToolSpec
from .policy import Risk


def register_desktop_tools(registry: ToolRegistry) -> None:
    """Register local desktop capabilities. These execute on the user's PC."""
    if platform.system() == "Windows":
        from .windows_tools import open_application, execute_shell_command

        registry.register(ToolSpec(
            name="open_application",
            function=open_application,
            risk=Risk.READ,
            description="Open a Windows desktop application by name, executable, path, URL, or shell target.",
            input_schema={
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Application name such as Chrome, Discord, VS Code, or Calculator."}
                },
                "required": ["app_name"],
            },
        ))

        registry.register(ToolSpec(
            name="execute_shell_command",
            function=execute_shell_command,
            risk=Risk.WRITE,
            description="Execute a PowerShell command on the Brainbox Windows host. Use this to inspect the PC, manage files, run programs, install software, automate workflows, or perform other requested local computer tasks.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "PowerShell command to execute."},
                    "cwd": {"type": "string", "description": "Optional working directory."},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 300, "description": "Timeout in seconds."},
                },
                "required": ["command"],
            },
        ))
