from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MemoryManager:
    def __init__(self, database_path: str | None = None) -> None:
        if database_path is None:
            database_path = str(Path.home() / "AppData" / "Roaming" / "Jarvis" / "jarvis.db")
        self.database_path = str(Path(database_path))
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT
            )
            """
        )
        self.connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_memory(self, category: str, content: str, source: str | None = None) -> dict[str, Any]:
        memory_id = uuid.uuid4().hex
        now = self._now()
        self.connection.execute(
            "INSERT INTO memory(id, category, content, created_at, updated_at, source) VALUES (?, ?, ?, ?, ?, ?)",
            (memory_id, category, content, now, now, source),
        )
        self.connection.commit()
        return {"id": memory_id, "category": category, "content": content, "created_at": now, "updated_at": now, "source": source}

    def search(self, term: str) -> list[dict[str, Any]]:
        query = f"%{term.lower()}%"
        rows = self.connection.execute(
            "SELECT id, category, content, created_at, updated_at, source FROM memory WHERE LOWER(content) LIKE ? OR LOWER(category) LIKE ? ORDER BY updated_at DESC",
            (query, query),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_memories(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT id, category, content, created_at, updated_at, source FROM memory ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_memory(self, memory_id: str) -> None:
        self.connection.execute("DELETE FROM memory WHERE id = ?", (memory_id,))
        self.connection.commit()
