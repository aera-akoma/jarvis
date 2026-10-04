from __future__ import annotations


class PermissionPolicy:
    def __init__(self) -> None:
        self.levels = {
            "safe": {"screenshot", "read_file", "open_app", "read_app_state", "search_files"},
            "moderate": {"edit_file", "create_file", "launch_browser", "send_message", "install_software"},
            "dangerous": {"delete_file", "format_drive", "run_command", "change_security_settings", "financial_transaction"},
        }

    def allows(self, action: str, level: str, *, confirm: bool = False) -> bool:
        if level == "safe":
            return action in self.levels["safe"]
        if level == "moderate":
            return action in self.levels["moderate"] or (confirm and action in self.levels["moderate"])
        if level == "dangerous":
            return confirm and action in self.levels["dangerous"]
        return False
