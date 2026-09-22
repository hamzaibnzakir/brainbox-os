from __future__ import annotations

import os
import platform
import subprocess
from typing import Any


def _require_windows() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Windows desktop tools can only execute on the Brainbox host PC.")


def open_application(name: str) -> dict[str, Any]:
    """Open a Windows application by its Start Menu name, executable, path, URL, or shell target.

    Args:
        name: Application name such as Chrome, VS Code, Discord, Spotify, or Calculator.
    """
    _require_windows()
    target = name.strip()
    if not target:
        raise ValueError("Application name cannot be empty")

    # Prefer Start Menu app registrations so friendly names like "Google Chrome" work.
    ps = (
        "$q = [Console]::In.ReadToEnd().Trim(); "
        "$apps = Get-StartApps | Where-Object { $_.Name -like ('*' + $q + '*') }; "
        "$apps | Select-Object -First 10 | ConvertTo-Json -Compress"
    )
    lookup = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        input=target,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    matches: list[dict[str, str]] = []
    if lookup.returncode == 0 and lookup.stdout.strip():
        import json
        value = json.loads(lookup.stdout)
        if isinstance(value, dict):
            value = [value]
        matches = value or []

    chosen = next((x for x in matches if x.get("Name", "").casefold() == target.casefold()), None)
    if chosen is None and matches:
        chosen = matches[0]

    if chosen:
        app_id = chosen["AppID"]
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"opened": True, "name": chosen["Name"], "app_id": app_id, "match": "start_menu"}

    # Fall back to a path, URL, executable or shell registered target.
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Start-Process -FilePath $args[0]", target],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"opened": True, "name": target, "match": "shell_fallback"}
