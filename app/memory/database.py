from __future__ import annotations

from app.db import DatabaseManager


class MemoryDatabase(DatabaseManager):
    """SQLite-backed memory store for durable user context."""

    def __init__(self, config=None) -> None:
        super().__init__(config=config)
