from __future__ import annotations

import os
from pathlib import Path
from typing import Any

MAX_TEXT_BYTES = 2_000_000


def _path(value: str) -> Path:
    value = os.path.expandvars(os.path.expanduser(value.strip()))
    if not value:
        raise ValueError("Path cannot be empty")
    return Path(value).resolve()


def read_file(path: str, max_bytes: int = MAX_TEXT_BYTES) -> dict[str, Any]:
    target = _path(path)
    if not target.is_file():
        raise FileNotFoundError(str(target))
    data = target.read_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"File is larger than the {max_bytes} byte limit")
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("File is not UTF-8 text") from exc
    return {"path": str(target), "bytes": len(data), "content": content}


def write_file(path: str, content: str, create_parents: bool = True) -> dict[str, Any]:
    target = _path(path)
    if create_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": str(target), "bytes": len(content.encode("utf-8")), "written": True}


def list_directory(path: str = ".") -> dict[str, Any]:
    target = _path(path)
    if not target.is_dir():
        raise NotADirectoryError(str(target))
    entries = []
    for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
        entries.append({
            "name": item.name,
            "path": str(item),
            "type": "directory" if item.is_dir() else "file",
            "size": item.stat().st_size if item.is_file() else None,
        })
    return {"path": str(target), "entries": entries}


def search_files(query: str, path: str = ".", max_results: int = 50) -> dict[str, Any]:
    query = query.strip().casefold()
    if not query:
        raise ValueError("Search query cannot be empty")
    root = _path(path)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    results = []
    for item in root.rglob("*"):
        if len(results) >= max_results:
            break
        if item.is_file() and query in item.name.casefold():
            results.append(str(item))
    return {"query": query, "path": str(root), "results": results}
