from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


class MemoryStore:
    """Small local SQLite memory for durable Brainbox experience retrieval."""

    def __init__(self, path: str | Path | None = None) -> None:
        default = os.getenv("BRAINBOX_MEMORY_DB", "~/.brainbox/memory.db")
        self.path = Path(path or default).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init(self) -> None:
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    kind TEXT NOT NULL,
                    user_text TEXT NOT NULL DEFAULT '',
                    assistant_text TEXT NOT NULL DEFAULT '',
                    context TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_memories_ts ON memories(ts DESC)")
            try:
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(user_text, assistant_text, context, content='memories', content_rowid='id')")
                db.execute("""
                    CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                      INSERT INTO memories_fts(rowid,user_text,assistant_text,context) VALUES (new.id,new.user_text,new.assistant_text,new.context);
                    END
                """)
                db.execute("""
                    CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                      INSERT INTO memories_fts(memories_fts,rowid,user_text,assistant_text,context) VALUES ('delete',old.id,old.user_text,old.assistant_text,old.context);
                    END
                """)
            except sqlite3.OperationalError:
                pass

    def remember(
        self,
        user_text: str,
        assistant_text: str = "",
        *,
        kind: str = "conversation",
        context: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self._connect() as db:
            cur = db.execute(
                "INSERT INTO memories(ts,kind,user_text,assistant_text,context,metadata) VALUES(?,?,?,?,?,?)",
                (time.time(), kind, user_text[:12000], assistant_text[:12000], context[:12000], json.dumps(metadata or {}, ensure_ascii=False, default=str)),
            )
            return int(cur.lastrowid)

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query = " ".join(query.split()).strip()
        if not query:
            return []
        limit = max(1, min(int(limit), 20))
        with self._connect() as db:
            try:
                terms = " OR ".join('"' + token.replace('"', '') + '"' for token in query.split()[:12] if token)
                rows = db.execute(
                    """SELECT m.id,m.ts,m.kind,m.user_text,m.assistant_text,m.context
                       FROM memories_fts f JOIN memories m ON m.id=f.rowid
                       WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?""",
                    (terms, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = db.execute(
                    """SELECT id,ts,kind,user_text,assistant_text,context FROM memories
                       WHERE user_text LIKE ? OR assistant_text LIKE ? OR context LIKE ?
                       ORDER BY ts DESC LIMIT ?""",
                    (f"%{query}%", f"%{query}%", f"%{query}%", limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def recent(self, limit: int = 5) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id,ts,kind,user_text,assistant_text,context FROM memories ORDER BY ts DESC LIMIT ?",
                (max(1, min(int(limit), 20)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def context_for(self, query: str, limit: int = 5) -> str:
        rows = self.search(query, limit=limit)
        if not rows:
            return ""
        parts = []
        for row in rows:
            parts.append(
                f"Previous memory: user={row['user_text'][:700]} | assistant={row['assistant_text'][:700]}"
                + (f" | context={row['context'][:700]}" if row["context"] else "")
            )
        return "\n".join(parts)
