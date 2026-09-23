from __future__ import annotations

import os
import platform
import subprocess
from difflib import SequenceMatcher
import re
from typing import Any


def _require_windows() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Windows desktop tools can only execute on the Brainbox host PC.")


def _normalize_app_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _choose_start_menu_app(target: str, matches: list[dict[str, str]]) -> tuple[dict[str, str] | None, str, float]:
    if not matches:
        return None, "none", 0.0
    target_norm = _normalize_app_name(target)
    exact = next((x for x in matches if _normalize_app_name(x.get("Name", "")) == target_norm), None)
    if exact:
        return exact, "normalized_exact", 1.0

    scored = []
    for app in matches:
        name = app.get("Name", "")
        score = SequenceMatcher(None, target_norm, _normalize_app_name(name)).ratio()
        scored.append((score, name.casefold(), app))
    scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
    score, _, chosen = scored[0]
    if score >= 0.76:
        return chosen, "fuzzy", score
    return None, "ambiguous", score


def resolve_application_name(target: str) -> tuple[str | None, float, str]:
    _require_windows()
    target = target.strip()
    if not target:
        return None, 0.0, "empty"
    ps = "$apps = Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
    lookup = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        text=True, capture_output=True, timeout=8, check=False,
    )
    if lookup.returncode != 0 or not lookup.stdout.strip():
        return None, 0.0, "lookup_failed"
    import json
    value = json.loads(lookup.stdout)
    if isinstance(value, dict):
        value = [value]
    chosen, kind, score = _choose_start_menu_app(target, value or [])
    return (chosen.get("Name") if chosen else None), score, kind


def open_application(app_name: str) -> dict[str, Any]:
    _require_windows()
    target = app_name.strip()
    if not target:
        raise ValueError("Application name cannot be empty")

    ps = (
        "$q = [Console]::In.ReadToEnd().Trim(); "
        "$apps = Get-StartApps | Where-Object { $_.Name -like ('*' + $q + '*') }; "
        "$apps | Select-Object -First 10 | ConvertTo-Json -Compress"
    )
    lookup = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        input=target, text=True, capture_output=True, timeout=5, check=False,
    )

    matches: list[dict[str, str]] = []
    if lookup.returncode == 0 and lookup.stdout.strip():
        import json
        value = json.loads(lookup.stdout)
        if isinstance(value, dict):
            value = [value]
        matches = value or []

    chosen, match_type, match_score = _choose_start_menu_app(target, matches)

    if chosen:
        app_id = chosen["AppID"]
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return {"opened": True, "name": chosen["Name"], "app_id": app_id,
                "match": match_type, "match_score": round(match_score, 3)}

    explicit_target = target.startswith(("http://", "https://", "file://")) or any(
        ch in target for ch in ("\\", "/", ":")
    ) or target.lower().endswith((".exe", ".lnk", ".url"))
    if not explicit_target and matches:
        raise ValueError(f"No confident Start Menu match for '{target}'. Best match score: {match_score:.2f}")

    os.startfile(target)  # type: ignore[attr-defined]
    return {"opened": True, "name": target, "match": "shell_fallback"}


def execute_shell_command(command: str, cwd: str | None = None, timeout: int = 30) -> dict[str, Any]:
    """Execute a PowerShell command on the Brainbox Windows host and return stdout/stderr."""
    _require_windows()
    command = command.strip()
    if not command:
        raise ValueError("Command cannot be empty")
    timeout = max(1, min(int(timeout), 300))
    workdir = os.path.expandvars(os.path.expanduser(cwd)) if cwd else os.getcwd()
    if not os.path.isdir(workdir):
        raise ValueError(f"Working directory does not exist: {workdir}")

    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
            cwd=workdir,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": None,
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "",
            "cwd": workdir,
            "timed_out": True,
        }
    return {
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "cwd": workdir,
        "timed_out": False,
    }
