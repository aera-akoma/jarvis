from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WorkflowManager:
    def __init__(self, database_path: str | None = None) -> None:
        if database_path is None:
            database_path = str(Path.home() / "AppData" / "Roaming" / "Jarvis" / "workflows.db")
        self.database_path = str(Path(database_path))
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                steps TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_workflow(self, name: str, steps: list[str]) -> dict[str, Any]:
        workflow_id = uuid.uuid4().hex
        now = self._now()
        self.connection.execute(
            "INSERT INTO workflows(id, name, steps, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (workflow_id, name, "|".join(steps), now, now),
        )
        self.connection.commit()
        return {"id": workflow_id, "name": name, "steps": list(steps), "created_at": now, "updated_at": now}

    def list_workflows(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT id, name, steps, created_at, updated_at FROM workflows ORDER BY updated_at DESC"
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append({
                "id": row["id"],
                "name": row["name"],
                "steps": row["steps"].split("|") if row["steps"] else [],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })
        return result
