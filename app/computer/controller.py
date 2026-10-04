from __future__ import annotations

from typing import Any


class ComputerController:
    def __init__(self) -> None:
        self.action_log: list[str] = []

    def log_action(self, message: str) -> None:
        self.action_log.append(message)

    def take_action(self, operation: str, *, confirm: bool = False, level: str = "safe") -> bool:
        from app.permissions.policy import PermissionPolicy

        policy = PermissionPolicy()
        if not policy.allows(operation, level, confirm=confirm):
            return False
        self.log_action(f"{operation}: allowed")
        return True
