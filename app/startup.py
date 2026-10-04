from __future__ import annotations

import sys
import os
from pathlib import Path


class StartupManager:
    def __init__(self, startup_dir: str | None = None) -> None:
        if startup_dir is None:
            roaming = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
            startup_dir = str(roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")
        self.startup_dir = Path(startup_dir)
        self.startup_dir.mkdir(parents=True, exist_ok=True)
        self.startup_file = self.startup_dir / "Jarvis-startup.cmd"

    def is_enabled(self) -> bool:
        return self.startup_file.exists()

    def enable_startup(self) -> None:
        executable = Path(sys.executable).resolve()
        if getattr(sys, "frozen", False):
            command = f'"{executable}"'
        else:
            project_root = Path(__file__).resolve().parent.parent
            command = f'cd /d "{project_root}" && "{executable}" -m app'
        script = "@echo off\r\n" + command + "\r\n"
        self.startup_file.write_text(script, encoding="utf-8")

    def disable_startup(self) -> None:
        if self.startup_file.exists():
            self.startup_file.unlink()
