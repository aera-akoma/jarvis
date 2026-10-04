from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from app.permissions.policy import PermissionPolicy
from app.tooling import ToolRegistry


class DefaultModelAdapter:
    """Fallback planner used when a real model adapter is not supplied."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def decide(self, request: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        request_text = (request or "").strip()
        if not request_text:
            return {"final_response": "Please provide a request."}

        lower = request_text.lower()
        project_path = (context or {}).get("project_path") or str(Path.cwd())
        workspace = Path(project_path)
        last_result = (context or {}).get("last_tool_result")

        if last_result and isinstance(last_result, dict) and last_result.get("success"):
            if "read" in lower or "summary" in lower or "what" in lower:
                return {"final_response": self._summarize_tool_result(last_result)}

        if any(token in lower for token in ("write", "create", "save", "overwrite")) or "hello" in lower:
            target = self._guess_file_target(request_text, workspace)
            content = self._guess_content(request_text)
            return {"tool": "write_file", "arguments": {"path": str(target), "content": content}}

        if any(token in lower for token in ("read ", "readme", "open file")) or re.search(r"\.txt|\.md|\.json", lower):
            target = self._guess_file_target(request_text, workspace)
            if target:
                return {"tool": "read_file", "arguments": {"path": str(target)}}
            return {"tool": "list_directory", "arguments": {"path": str(workspace)}}

        if any(token in lower for token in ("list files", "list directory", "show files", "directory", "folder")):
            return {"tool": "list_directory", "arguments": {"path": str(workspace)}}

        if any(token in lower for token in ("search", "find file")):
            return {"tool": "search_files", "arguments": {"path": str(workspace), "pattern": "*"}}

        if any(token in lower for token in ("notepad", "open app", "open application")):
            return {"tool": "open_application", "arguments": {"path": "notepad.exe"}}

        if any(token in lower for token in ("power shell", "powershell", "run command", "terminal")):
            command = "Get-ChildItem" if "list" in lower or "files" in lower else "python --version"
            return {"tool": "run_powershell", "arguments": {"command": command}}

        return {"final_response": "I can help with file operations, directory listing, and Windows application launches."}

    def _guess_file_target(self, request: str, workspace: Path) -> Path | None:
        patterns = [
            r"(?:for|to|at|in)\s+([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)",
            r"(?:file\s+(?:called|named)|named|called)\s+([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)",
            r"([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, request, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip('"\'')
                path = Path(candidate)
                if not path.is_absolute():
                    path = workspace / candidate
                return path
        return workspace / "notes.txt"

    def _guess_content(self, request: str) -> str:
        lower = request.lower()
        if "hello" in lower:
            return "hello"
        if "jarvis" in lower:
            return "Hello Jarvis"
        if "containing" in lower:
            remainder = request.split("containing", 1)[1].strip()
            if remainder:
                return remainder.strip('"\'')
        return "hello"

    def _summarize_tool_result(self, result: dict[str, Any]) -> str:
        if result.get("content") is not None:
            return f"The file contents were read successfully: {result.get('content', '')[:200]}"
        if result.get("entries"):
            return f"Directory listing returned {len(result.get('entries', []))} entries."
        if result.get("matches"):
            return f"Found {len(result.get('matches', []))} matches."
        if result.get("stdout"):
            return result.get("stdout", "Command completed successfully.").strip() or "Command completed successfully."
        if result.get("path"):
            return f"Completed successfully at {result.get('path')}"
        return "The tool completed successfully."


class AgentLoop:
    """Model-driven tool loop for the Jarvis desktop agent."""

    def __init__(self, registry: ToolRegistry | None = None, permission_policy: PermissionPolicy | None = None, model_adapter: Any | None = None, max_tool_iterations: int = 20) -> None:
        self.registry = registry or ToolRegistry()
        self.permission_policy = permission_policy or PermissionPolicy()
        self.model_adapter = model_adapter or DefaultModelAdapter(self.registry)
        self.max_tool_iterations = max_tool_iterations
        self.cancelled = False
        self.last_context: dict[str, Any] = {}

    def cancel(self) -> None:
        self.cancelled = True

    def format_context(self, *, request: str, project_path: str | None = None, conversation: list[dict[str, Any]] | None = None, memory: list[dict[str, Any]] | None = None, available_tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        context = {
            "request": request,
            "project_path": project_path or str(Path.cwd()),
            "conversation": conversation or [],
            "memory": memory or [],
            "available_tools": available_tools or self.registry.model_definitions(),
        }
        self.last_context = context
        return context

    def build_agent_prompt(self, *, request: str, project_path: str | None = None, conversation: list[dict[str, Any]] | None = None, memory: list[dict[str, Any]] | None = None) -> str:
        tool_docs = ", ".join(f"{tool['name']}({tool['permission_level']})" for tool in self.registry.model_definitions())
        convo = "\n".join(f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in (conversation or [])[-8:])
        memory_text = "\n".join(f"- {item.get('content', '')}" for item in (memory or [])[:4])
        return (
            "You are Jarvis, a Windows desktop AI agent. "
            f"Project path: {project_path or Path.cwd()}. "
            f"Available tools: {tool_docs}. "
            f"Conversation:\n{convo or 'No earlier messages.'}\n"
            f"Relevant memory:\n{memory_text or 'No relevant memory.'}\n"
            "Use tools when needed. Never claim a tool succeeded without a tool result. Ask the user when required information is missing."
        )

    def _model_decision(self, request: str, *, context: dict[str, Any]) -> dict[str, Any]:
        if hasattr(self.model_adapter, "decide"):
            return self.model_adapter.decide(request, context=context)
        if hasattr(self.model_adapter, "plan"):
            return self.model_adapter.plan(request, context=context)
        if callable(self.model_adapter):
            return self.model_adapter(request, context=context)
        return {"final_response": "I can help with file, directory, and application tasks."}

    def _normalize_tool_call(self, tool_call: Any) -> dict[str, Any]:
        if isinstance(tool_call, dict):
            name = tool_call.get("tool") or tool_call.get("name")
            args = tool_call.get("arguments") or tool_call.get("args") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (TypeError, ValueError):
                    args = {} if not args else {"value": args}
            if name:
                return {"tool": name, "arguments": args or {}}
        if isinstance(tool_call, str):
            return {"tool": tool_call, "arguments": {}}
        return {"tool": "", "arguments": {}}

    def _execute_tool_call(self, tool_name: str, arguments: dict[str, Any], *, allow_confirmation: bool) -> dict[str, Any]:
        tool_def = self.registry.get(tool_name)
        if tool_def is None:
            return {"success": False, "tool": tool_name, "error": f"Unknown tool: {tool_name}"}
        if not self.permission_policy.allows(tool_name, tool_def.permission_level, confirm=allow_confirmation):
            return {
                "success": False,
                "tool": tool_name,
                "error": f"Permission denied for {tool_name} ({tool_def.permission_level}).",
                "requires_confirmation": self.permission_policy.confirm_required(tool_name, tool_def.permission_level),
            }
        result = self.registry.execute(tool_name, params=arguments)
        result.setdefault("tool", tool_name)
        result.setdefault("success", result.get("ok", False))
        return result

    def process_request(self, request: str, *, project_path: str | None = None, allow_confirmation: bool = False, conversation: list[dict[str, Any]] | None = None, memory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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

        context = self.format_context(request=request_text, project_path=project_path, conversation=conversation, memory=memory)
        tool_calls: list[dict[str, Any]] = []
        iteration = 0

        while iteration < self.max_tool_iterations:
            iteration += 1
            if self.cancelled:
                return {"success": False, "cancelled": True, "summary": "The task was cancelled.", "tool_calls": tool_calls}

            decision = self._model_decision(request_text, context=context)
            if isinstance(decision, dict) and "tool" in decision and "arguments" in decision:
                tool_call = decision
            else:
                tool_call = self._normalize_tool_call(decision.get("tool_call") or decision.get("tool") or decision)
            if tool_call.get("tool"):
                tool = tool_call["tool"]
                args = tool_call.get("arguments", {}) or {}
                result = self._execute_tool_call(tool, args, allow_confirmation=allow_confirmation)
                tool_calls.append({"name": tool, "arguments": args, "result": result})
                context["last_tool_result"] = result
                if not result.get("success", False):
                    return {
                        "success": False,
                        "cancelled": False,
                        "summary": result.get("error", "Tool execution failed."),
                        "tool_calls": tool_calls,
                    }
                if decision.get("final_response"):
                    return {"success": True, "cancelled": False, "summary": decision["final_response"], "tool_calls": tool_calls}
                continue

            if decision.get("final_response"):
                return {
                    "success": True,
                    "cancelled": False,
                    "summary": decision["final_response"],
                    "tool_calls": tool_calls,
                }

            break

        return {
            "success": False,
            "cancelled": False,
            "summary": "Jarvis stopped because the maximum tool iteration limit was reached.",
            "tool_calls": tool_calls,
        }

    def _resolve_target_path(self, request: str, workspace: Path) -> Path | None:
        return DefaultModelAdapter(self.registry)._guess_file_target(request, workspace)

    def _extract_write_content(self, request: str) -> str:
        return DefaultModelAdapter(self.registry)._guess_content(request)

    def _extract_command(self, request: str) -> str:
        return "Get-ChildItem" if "list" in request.lower() or "files" in request.lower() else "python --version"

    def _summarize_result(self, request: str, result: dict[str, Any]) -> str:
        if result.get("content") is not None:
            return f"Read file content: {result.get('content')[:200]}"
        if result.get("entries"):
            return f"Directory listing returned {len(result.get('entries', []))} items."
        if result.get("matches"):
            return f"Found {len(result.get('matches', []))} matches."
        if result.get("stdout"):
            return result["stdout"].strip() or "Command completed successfully."
        if result.get("path"):
            return f"Action completed at {result.get('path')}"
        return "The requested action completed successfully."
