from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.permissions.policy import PermissionPolicy
from app.tooling import ToolRegistry


class AgentLoop:
    """Small tool-driven agent loop for local desktop tasks."""

    def __init__(self, registry: ToolRegistry | None = None, permission_policy: PermissionPolicy | None = None) -> None:
        self.registry = registry or ToolRegistry()
        self.permission_policy = permission_policy or PermissionPolicy()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def process_request(self, request: str, *, project_path: str | None = None, allow_confirmation: bool = False) -> dict[str, Any]:
        if self.cancelled:
            return {
                "success": False,
                "cancelled": True,
                "summary": "The task was cancelled before execution.",
                "tool_calls": [],
            }

        request_text = (request or "").strip()
        if not request_text:
            return {
                "success": False,
                "cancelled": False,
                "summary": "No request was provided.",
                "tool_calls": [],
            }

        workspace = Path(project_path) if project_path else Path.cwd()
        tool_calls: list[dict[str, Any]] = []
        result: dict[str, Any] | None = None

        lower = request_text.lower()
        if any(pattern in lower for pattern in ("write ", "create ", "save ", "overwrite ")) and ("file" in lower or ".txt" in lower or ".md" in lower or ".json" in lower):
            target = self._resolve_target_path(request_text, workspace)
            content = self._extract_write_content(request_text)
            if target is None:
                return {"success": False, "cancelled": False, "summary": "No file target could be determined from the request.", "tool_calls": []}
            invocation = self._execute_tool("write_file", target=str(target), params={"content": content}, allow_confirmation=allow_confirmation)
            tool_calls.append({"name": "write_file", "target": str(target), "result": invocation})
            result = invocation
            if not invocation.get("ok"):
                return {"success": False, "cancelled": False, "summary": invocation.get("error", "Write failed."), "tool_calls": tool_calls}

        if "read" in lower or "open" in lower and ("file" in lower or ".txt" in lower or ".md" in lower or ".json" in lower):
            target = self._resolve_target_path(request_text, workspace)
            if target is not None:
                invocation = self._execute_tool("read_file", target=str(target), params={}, allow_confirmation=allow_confirmation)
                tool_calls.append({"name": "read_file", "target": str(target), "result": invocation})
                if not invocation.get("ok"):
                    return {"success": False, "cancelled": False, "summary": invocation.get("error", "Read failed."), "tool_calls": tool_calls}
                result = invocation

        if result is None:
            if "list" in lower or "directory" in lower or "folder" in lower:
                target = self._resolve_directory_path(request_text, workspace)
                invocation = self._execute_tool("list_directory", target=str(target or workspace), params={}, allow_confirmation=allow_confirmation)
                tool_calls.append({"name": "list_directory", "target": str(target or workspace), "result": invocation})
                result = invocation
            elif "search" in lower and ("file" in lower or "directory" in lower or "folder" in lower):
                target = self._resolve_directory_path(request_text, workspace)
                invocation = self._execute_tool("search_files", target=str(target or workspace), params={"pattern": "*"}, allow_confirmation=allow_confirmation)
                tool_calls.append({"name": "search_files", "target": str(target or workspace), "result": invocation})
                result = invocation
            elif "notepad" in lower or "open application" in lower or "open app" in lower:
                target = "notepad.exe" if "notepad" in lower else (str(workspace) if workspace.exists() else ".")
                invocation = self._execute_tool("open_application", target=target, params={}, allow_confirmation=allow_confirmation)
                tool_calls.append({"name": "open_application", "target": target, "result": invocation})
                result = invocation
            elif "powershell" in lower or "run command" in lower or "terminal" in lower:
                command = self._extract_command(request_text)
                invocation = self._execute_tool("run_powershell", target=None, params={"command": command}, allow_confirmation=allow_confirmation)
                tool_calls.append({"name": "run_powershell", "target": None, "result": invocation})
                result = invocation
            else:
                return {
                    "success": False,
                    "cancelled": False,
                    "summary": "The request did not require a tool or could not be mapped to a supported action.",
                    "tool_calls": [],
                }

        if not isinstance(result, dict):
            result = {"ok": True, "result": result}

        if not result.get("ok"):
            return {
                "success": False,
                "cancelled": False,
                "summary": result.get("error", "The tool execution failed."),
                "tool_calls": tool_calls,
            }

        summary = self._summarize_result(request_text, result)
        return {
            "success": True,
            "cancelled": False,
            "summary": summary,
            "tool_calls": tool_calls,
        }

    def _execute_tool(self, name: str, *, target: str | None = None, params: dict[str, Any] | None = None, allow_confirmation: bool) -> dict[str, Any]:
        tool = self.registry.tools.get(name)
        if tool is None:
            return {"ok": False, "error": f"Tool {name} is not registered."}
        if not self.permission_policy.allows(name, tool.permission_level, confirm=allow_confirmation):
            return {
                "ok": False,
                "error": f"Permission denied for {name} ({tool.permission_level}).",
                "requires_confirmation": self.permission_policy.confirm_required(name, tool.permission_level),
            }
        return self.registry.execute(name, target=target, params=params)

    def _resolve_target_path(self, request: str, workspace: Path) -> Path | None:
        patterns = [
            r"(?:to|at|in|for)\s+([A-Za-z0-9_./\\-]+(?:\.[A-Za-z0-9]+)?)",
            r"(?:write|read|open)\s+(?:the\s+)?([A-Za-z0-9_./\\-]+(?:\.[A-Za-z0-9]+)?)",
            r"([A-Za-z0-9_./\\-]+(?:\.[A-Za-z0-9]+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, request, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip().strip('"\'')
                if candidate.lower() in {"file", "directory", "folder", "document", "notes"}:
                    continue
                path = Path(candidate)
                if not path.is_absolute():
                    path = workspace / candidate
                return path
        return None

    def _resolve_directory_path(self, request: str, workspace: Path) -> Path | None:
        for token in ("directory", "folder", "path"):
            match = re.search(rf"(?:in|for|at|to)\s+([A-Za-z0-9_./\\-]+)", request, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip('"\'')
                path = Path(candidate)
                if not path.is_absolute():
                    path = workspace / candidate
                return path
        return workspace

    def _extract_write_content(self, request: str) -> str:
        match = re.search(r"(?:write|create|save|overwrite)\s+(?:the\s+)?(?:file\s+)?(?:(?:to|at|in)\s+.*?\s+)?(?:(?:with|content|text)\s+)?(.+)$", request, flags=re.IGNORECASE)
        if match:
            content = match.group(1).strip()
            if content:
                return content
        # Common default when the user includes an explicit text phrase.
        if "hello" in request.lower():
            return "hello"
        return ""

    def _extract_command(self, request: str) -> str:
        match = re.search(r"(?:powershell|run command|terminal)\s+(.*)$", request, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return "Get-ChildItem" if "powershell" in request.lower() else "echo hello"

    def _summarize_result(self, request: str, result: dict[str, Any]) -> str:
        if "write_file" in request.lower() and result.get("path"):
            return f"Wrote the requested content to {result.get('path')}"
        if result.get("content") is not None:
            return f"Read file content: {result.get('content')[:200]}"
        if result.get("entries"):
            return f"Directory listing returned {len(result.get('entries', []))} items."
        if result.get("matches"):
            return f"Found {len(result.get('matches', []))} matches."
        if result.get("stdout"):
            return result["stdout"].strip() or "Command completed successfully."
        return "The requested action completed successfully."
