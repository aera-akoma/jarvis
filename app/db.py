from __future__ import annotations

import sqlite3
from typing import Any

from app.config import AppConfig


class DatabaseManager:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig()
        self.connection = sqlite3.connect(self.config.database_path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
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

    def set_setting(self, key: str, value: Any) -> None:
        self.connection.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        self.connection.commit()

    def get_setting(self, key: str, default: Any | None = None) -> Any:
        row = self.connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return default
        return row["value"]
