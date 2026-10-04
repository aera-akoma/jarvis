from __future__ import annotations


class PermissionPolicy:
    _ALIASES = {
        "open_application": "open_app",
        "open_app": "open_app",
        "run_powershell": "run_command",
        "run_command": "run_command",
        "search_files": "search_files",
        "read_file": "read_file",
        "write_file": "write_file",
        "create_file": "create_file",
        "create_directory": "create_directory",
        "edit_file": "edit_file",
        "rename_file": "rename_file",
        "move_file": "move_file",
        "list_directory": "list_directory",
    }

    def __init__(self) -> None:
        self.levels = {
            "safe": {"screenshot", "read_file", "list_directory", "open_app", "read_app_state", "search_files"},
            "moderate": {"edit_file", "create_file", "create_directory", "rename_file", "move_file", "launch_browser", "send_message", "install_software", "write_file"},
            "dangerous": {"delete_file", "format_drive", "run_command", "change_security_settings", "financial_transaction", "run_powershell"},
        }

    def _normalize_action(self, action: str) -> str:
        return self._ALIASES.get(action, action)

    def confirm_required(self, action: str, level: str) -> bool:
        if level == "safe":
            return False
        action = self._normalize_action(action)
        return action in self.levels.get(level, set())

    def allows(self, action: str, level: str, *, confirm: bool = False) -> bool:
        if level not in self.levels:
            return False
        action = self._normalize_action(action)
        if action not in self.levels[level]:
            return False
        if level == "safe":
            return True
        return bool(confirm)
