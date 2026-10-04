from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app.permissions.policy import PermissionPolicy


class WindowsController:
    def __init__(self, permission_policy: PermissionPolicy | None = None) -> None:
        self.permission_policy = permission_policy or PermissionPolicy()
        self.action_log: list[str] = []

    def log_action(self, message: str) -> None:
        self.action_log.append(message)

    def open_application(self, app_name: str, *, confirm: bool = False) -> bool:
        if not app_name:
            return False
        if not self.permission_policy.allows("open_app", "safe", confirm=confirm):
            return False
        if not hasattr(os, "startfile"):
            return False
        try:
            os.startfile(app_name)
            self.log_action(f"Opened application: {app_name}")
            return True
        except (AttributeError, OSError):
            return False

    def open_file(self, file_path: str, *, confirm: bool = False) -> bool:
        if not self.permission_policy.allows("open_app", "safe", confirm=confirm):
            return False
        path = Path(file_path)
        if not path.exists():
            return False
        if not hasattr(os, "startfile"):
            return False
        try:
            os.startfile(str(path))
            self.log_action(f"Opened file: {path}")
            return True
        except (AttributeError, OSError):
            return False

    def run_powershell(self, command: str, *, confirm: bool = False) -> bool:
        if not self.permission_policy.allows("run_command", "dangerous", confirm=confirm):
            return False
        try:
            subprocess.run(["powershell", "-Command", command], check=False)
            self.log_action(f"Ran command: {command}")
            return True
        except (FileNotFoundError, OSError):
            return False
