from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ExportImportManager:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root) if root is not None else Path.home() / "AppData" / "Roaming" / "Jarvis"
        self.root.mkdir(parents=True, exist_ok=True)

    def export_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        exported = json.loads(json.dumps(payload))
        file_path = self.root / "jarvis_memory_package.json"
        file_path.write_text(json.dumps(exported, indent=2), encoding="utf-8")
        return exported

    def import_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(payload))
