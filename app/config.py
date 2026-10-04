from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class AppConfig:
    app_name: str = "Jarvis"
    theme: Literal["dark", "light"] = "dark"
    data_dir: str = field(
        default_factory=lambda: str(Path.home() / "AppData" / "Roaming" / "Jarvis")
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
