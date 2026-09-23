from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .memory import _redact


class ExperienceStore:
    """Durable execution experience used to identify repeat failures and improvement targets."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or "~/.brainbox/experience.db").expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                kind TEXT NOT NULL,
                task TEXT NOT NULL,
                tool TEXT,
                success INTEGER NOT NULL,
                detail TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_experience_tool ON experiences(tool, success)")

    def record(self, kind: str, task: str, success: bool, tool: str | None = None, detail: Any = None) -> None:
        payload = _redact(detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False, default=str), 8000)
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO experiences(ts,kind,task,tool,success,detail) VALUES(?,?,?,?,?,?)",
                       (time.time(), kind, task[:2000], tool, int(success), payload))

    def recent_failures(self, limit: int = 20) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT ts,kind,task,tool,detail FROM experiences WHERE success=0 ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"ts": r[0], "kind": r[1], "task": r[2], "tool": r[3], "detail": r[4]} for r in rows]
