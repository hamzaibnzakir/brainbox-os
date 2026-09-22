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
    if score >= 0.86:
        return chosen, "fuzzy", score
    return None, "ambiguous", score


def open_application(app_name: str) -> dict[str, Any]:
    """Open a Windows application by its Start Menu name, executable, path, URL, or shell target.

    Args:
        name: Application name such as Chrome, VS Code, Discord, Spotify, or Calculator.
    """
    _require_windows()
    target = app_name.strip()
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

    chosen, match_type, match_score = _choose_start_menu_app(target, matches)

    if chosen:
        app_id = chosen["AppID"]
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"opened": True, "name": chosen["Name"], "app_id": app_id, "match": match_type, "match_score": round(match_score, 3)}

    # Only use shell fallback when the user supplied an explicit path, URL, or executable.
    explicit_target = target.startswith(("http://", "https://", "file://")) or any(ch in target for ch in ("\\", "/", ":")) or target.lower().endswith((".exe", ".lnk", ".url"))
    if not explicit_target and matches:
        raise ValueError(f"No confident Start Menu match for '{target}'. Best match score: {match_score:.2f}")

    # Fall back to a path, URL, executable or shell registered target.
    os.startfile(target)  # type: ignore[attr-defined]
    return {"opened": True, "name": target, "match": "shell_fallback"}
