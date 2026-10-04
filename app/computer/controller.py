from __future__ import annotations

from typing import Any

from app.permissions.policy import PermissionPolicy


class ComputerController:
    def __init__(self, permission_policy: PermissionPolicy | None = None) -> None:
        self.permission_policy = permission_policy or PermissionPolicy()
        self.action_log: list[str] = []

    def log_action(self, message: str) -> None:
        self.action_log.append(message)

    def confirm_required(self, operation: str, level: str = "safe") -> bool:
        return self.permission_policy.confirm_required(operation, level)

    def take_action(self, operation: str, *, confirm: bool = False, level: str = "safe") -> bool:
        if not self.permission_policy.allows(operation, level, confirm=confirm):
            return False
        self.log_action(f"{operation}: allowed")
        return True
