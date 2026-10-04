from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import AppConfig


class SessionManager:
    def __init__(self, config: AppConfig | str | None = None, database_path: str | None = None) -> None:
        if isinstance(config, str):
            self.config = AppConfig(data_dir=str(Path(config).parent))
            self.database_path = str(Path(config))
        else:
            self.config = config or AppConfig()
            self.database_path = database_path or str(self.config.database_path)

        self.database_path = str(Path(self.database_path))
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                model_name TEXT,
                project_path TEXT
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
            )
            """
        )
        self.connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_conversation(self, title: str = "New Chat", model_name: str | None = None, project_path: str | None = None) -> dict[str, Any]:
        conversation_id = uuid.uuid4().hex
        now = self._now()
        self.connection.execute(
            "INSERT INTO conversations(id, title, created_at, updated_at, model_name, project_path) VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, title, now, now, model_name, project_path),
        )
        self.connection.commit()
        return {
            "id": conversation_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "model_name": model_name,
            "project_path": project_path,
        }

    def save_message(self, conversation_id: str, role: str, content: str) -> dict[str, Any]:
        message_id = uuid.uuid4().hex
        created_at = self._now()
        self.connection.execute(
            "INSERT INTO messages(id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, conversation_id, role, content, created_at),
        )
        self.connection.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (created_at, conversation_id),
        )
        self.connection.commit()
        return {"id": message_id, "conversation_id": conversation_id, "role": role, "content": content, "created_at": created_at}

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT id, conversation_id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_conversations(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT id, title, created_at, updated_at, model_name, project_path FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
