from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import sys
from typing import Literal


@dataclass
class AppConfig:
    app_name: str = "Jarvis"
    theme: Literal["dark", "light"] = "dark"
    data_dir: str = field(
        default_factory=lambda: str(_default_data_dir())
    )
    db_name: str = "jarvis.db"

    def __post_init__(self) -> None:
        self.data_dir = str(Path(self.data_dir).expanduser())
        self.data_dir_path = Path(self.data_dir)
        self.data_dir_path.mkdir(parents=True, exist_ok=True)
        (self.data_dir_path / "logs").mkdir(exist_ok=True)
        (self.data_dir_path / "attachments").mkdir(exist_ok=True)
        (self.data_dir_path / "exports").mkdir(exist_ok=True)
        self.database_path = self.data_dir_path / self.db_name

    def default_model(self) -> str:
        return "OpenCode Zen"


def _default_data_dir() -> Path:
    """Return a stable per-user data path independent of the install location."""
    if os.name == "nt":
        roaming = os.getenv("APPDATA")
        if roaming:
            return Path(roaming) / "Jarvis"
        return Path.home() / "AppData" / "Roaming" / "Jarvis"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Jarvis"
    return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "Jarvis"
