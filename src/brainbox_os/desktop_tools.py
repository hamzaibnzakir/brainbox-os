from __future__ import annotations

import platform

from .execution import ToolRegistry, ToolSpec
from .policy import Risk


def register_desktop_tools(registry: ToolRegistry) -> None:
    """Register local desktop capabilities. These execute on the user's PC."""
    if platform.system() == "Windows":
        from .windows_tools import open_application, execute_shell_command
        from .filesystem_tools import read_file, write_file, list_directory, search_files

        registry.register(ToolSpec(
            name="open_application",
            function=open_application,
            risk=Risk.READ,
            description="Open a Windows desktop application by name, executable, path, URL, or shell target.",
            input_schema={"type":"object","properties":{"app_name":{"type":"string","description":"Application name such as Chrome, Discord, VS Code, or Calculator."}},"required":["app_name"]},
        ))

        registry.register(ToolSpec(
            name="execute_shell_command",
            function=execute_shell_command,
            risk=Risk.WRITE,
            description="Execute a PowerShell command on the Brainbox Windows host.",
            input_schema={"type":"object","properties":{
                "command":{"type":"string","description":"PowerShell command to execute."},
                "cwd":{"type":"string","description":"Optional working directory."},
                "timeout":{"type":"integer","minimum":1,"maximum":300,"description":"Timeout in seconds."},
            },"required":["command"]},
        ))

        registry.register(ToolSpec(
            name="read_file",
            function=read_file,
            risk=Risk.READ,
            description="Read a UTF-8 text file from the Windows host.",
            input_schema={"type":"object","properties":{
                "path":{"type":"string","description":"Absolute or user-relative file path."},
                "max_bytes":{"type":"integer","minimum":1,"maximum":2000000},
            },"required":["path"]},
        ))

        registry.register(ToolSpec(
            name="write_file",
            function=write_file,
            risk=Risk.WRITE,
            description="Create or replace a UTF-8 text file on the Windows host.",
            input_schema={"type":"object","properties":{
                "path":{"type":"string","description":"File path."},
                "content":{"type":"string","description":"Complete UTF-8 file contents."},
                "create_parents":{"type":"boolean"},
            },"required":["path","content"]},
        ))

        registry.register(ToolSpec(
            name="list_directory",
            function=list_directory,
            risk=Risk.READ,
            description="List files and directories on the Windows host.",
            input_schema={"type":"object","properties":{"path":{"type":"string","description":"Directory path."}}},
        ))

        registry.register(ToolSpec(
            name="search_files",
            function=search_files,
            risk=Risk.READ,
            description="Find files by name recursively under a directory.",
            input_schema={"type":"object","properties":{
                "query":{"type":"string"},
                "path":{"type":"string"},
                "max_results":{"type":"integer","minimum":1,"maximum":200},
            },"required":["query"]},
        ))
