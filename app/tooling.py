from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class ToolDefinition:
    name: str
    description: str
    permission_level: str = "safe"
    parameters: dict[str, str] = field(default_factory=dict)
    handler: Callable[..., dict[str, Any]] | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self.tools: dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        self.register(
            ToolDefinition(
                name="read_file",
                description="Read a text file from disk.",
                permission_level="safe",
                parameters={"path": "file path"},
                handler=self._read_file,
            )
        )
        self.register(
            ToolDefinition(
                name="write_file",
                description="Write or overwrite a text file.",
                permission_level="moderate",
                parameters={"path": "file path", "content": "file contents"},
                handler=self._write_file,
            )
        )
        self.register(
            ToolDefinition(
                name="create_file",
                description="Create a new file with content.",
                permission_level="moderate",
                parameters={"path": "file path", "content": "file contents"},
                handler=self._create_file,
            )
        )
        self.register(
            ToolDefinition(
                name="create_directory",
                description="Create a directory tree.",
                permission_level="moderate",
                parameters={"path": "directory path"},
                handler=self._create_directory,
            )
        )
        self.register(
            ToolDefinition(
                name="list_directory",
                description="List files in a directory.",
                permission_level="safe",
                parameters={"path": "directory path"},
                handler=self._list_directory,
            )
        )
        self.register(
            ToolDefinition(
                name="search_files",
                description="Search for files under a directory.",
                permission_level="safe",
                parameters={"path": "directory path", "pattern": "file pattern"},
                handler=self._search_files,
            )
        )
        self.register(
            ToolDefinition(
                name="open_application",
                description="Open an application or document on Windows.",
                permission_level="safe",
                parameters={"path": "application or document path"},
                handler=self._open_application,
            )
        )
        self.register(
            ToolDefinition(
                name="run_powershell",
                description="Run a PowerShell command.",
                permission_level="dangerous",
                parameters={"command": "PowerShell command"},
                handler=self._run_powershell,
            )
        )

    def register(self, tool: ToolDefinition) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self.tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self.tools.keys())

    def model_definitions(self) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        for name in sorted(self.tools):
            tool = self.tools[name]
            definitions.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "permission_level": tool.permission_level,
                }
            )
        return definitions

    def execute(self, name: str, target: str | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            return {"ok": False, "success": False, "error": f"Unknown tool: {name}"}

        payload = dict(params or {})
        if target is not None and "path" not in payload and "target" not in payload:
            payload["path"] = target
        if tool.handler is None:
            return {"ok": False, "success": False, "error": f"Tool {name} has no handler"}
        result = tool.handler(**payload)
        if isinstance(result, dict):
            result.setdefault("success", result.get("ok", False))
            result.setdefault("ok", result.get("success", False))
            return result
        return {"ok": True, "success": True, "result": result}

    def _read_file(self, path: str) -> dict[str, Any]:
        file_path = Path(path)
        if not file_path.exists():
            return {"ok": False, "success": False, "error": f"File not found: {path}"}
        return {"ok": True, "success": True, "path": str(file_path), "content": file_path.read_text(encoding="utf-8")}

    def _write_file(self, path: str, content: str = "") -> dict[str, Any]:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"ok": True, "success": True, "path": str(file_path), "content": content}

    def _create_file(self, path: str, content: str = "") -> dict[str, Any]:
        file_path = Path(path)
        if file_path.exists():
            return {"ok": False, "success": False, "error": f"File already exists: {path}"}
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"ok": True, "success": True, "path": str(file_path), "content": content}

    def _create_directory(self, path: str) -> dict[str, Any]:
        directory = Path(path)
        if directory.exists():
            return {"ok": True, "success": True, "path": str(directory), "created": False}
        directory.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "success": True, "path": str(directory), "created": True}

    def _list_directory(self, path: str) -> dict[str, Any]:
        directory = Path(path)
        if not directory.exists():
            return {"ok": False, "success": False, "error": f"Directory not found: {path}"}
        entries = sorted(p.name for p in directory.iterdir())
        return {"ok": True, "success": True, "path": str(directory), "entries": entries}

    def _search_files(self, path: str, pattern: str = "*") -> dict[str, Any]:
        directory = Path(path)
        if not directory.exists():
            return {"ok": False, "success": False, "error": f"Directory not found: {path}"}
        matches = sorted(str(p) for p in directory.rglob(pattern) if p.is_file())
        return {"ok": True, "success": True, "path": str(directory), "matches": matches}

    def _open_application(self, path: str) -> dict[str, Any]:
        if not hasattr(os, "startfile"):
            return {"ok": False, "success": False, "error": "Windows startfile is not available."}
        try:
            os.startfile(path)
            return {"ok": True, "success": True, "path": path}
        except OSError as exc:
            return {"ok": False, "success": False, "error": str(exc)}

    def _run_powershell(self, command: str) -> dict[str, Any]:
        try:
            completed = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, check=False)
            return {
                "ok": completed.returncode == 0,
                "success": completed.returncode == 0,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        except FileNotFoundError:
            return {"ok": False, "success": False, "error": "PowerShell is not available."}
