from __future__ import annotations

from app.config import AppConfig
from app.db import DatabaseManager


class SettingsManager:
    def __init__(self, config: AppConfig | DatabaseManager | None = None) -> None:
        if isinstance(config, DatabaseManager):
            self.db = config
        else:
            self.db = DatabaseManager(config)

    def set(self, key: str, value: str) -> None:
        self.db.set_setting(key, value)

    def get(self, key: str, default: str | None = None) -> str | None:
        value = self.db.get_setting(key, default)
        return default if value is None else str(value)
