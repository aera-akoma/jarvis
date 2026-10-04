from __future__ import annotations


class PermissionPolicy:
    def __init__(self) -> None:
        self.levels = {
            "safe": {"screenshot", "read_file", "list_directory", "open_app", "read_app_state", "search_files"},
            "moderate": {"edit_file", "create_file", "launch_browser", "send_message", "install_software", "write_file"},
            "dangerous": {"delete_file", "format_drive", "run_command", "change_security_settings", "financial_transaction", "run_powershell"},
        }

    def confirm_required(self, action: str, level: str) -> bool:
        if level == "safe":
            return False
        return action in self.levels.get(level, set())

    def allows(self, action: str, level: str, *, confirm: bool = False) -> bool:
        if level not in self.levels:
            return False
        if action not in self.levels[level]:
            return False
        if level == "safe":
            return True
        return bool(confirm)
