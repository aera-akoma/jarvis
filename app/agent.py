from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from app.permissions.policy import PermissionPolicy
from app.tooling import ToolRegistry


class OpenAICompatibleModelAdapter:
    """Tool-calling adapter for explicitly configured OpenAI-compatible APIs.

    This does not imply that an OpenCode service supports this protocol. The
    configured endpoint must document support for chat completions and tools.
    """

    def __init__(self, registry: ToolRegistry, client: Any, model_name: str) -> None:
        self.registry = registry
        self.client = client
        self.model_name = model_name
        self.cancelled = False

    def decide(self, request: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        if self.cancelled:
            return {"final_response": "The model request was cancelled."}
        reply = self.client.request_tool_decision(
            request=request,
            model_name=self.model_name,
            tools=self.registry.model_definitions(),
            messages=context.get("agent_messages", []),
            system_prompt=context.get("system_prompt", "You are Jarvis, a desktop assistant. Use tools when needed and never claim unverified actions succeeded."),
        )
        return reply

    def cancel(self) -> None:
        self.cancelled = True
        cancel = getattr(self.client, "cancel_current_request", None)
        if cancel:
            cancel()


class AgentLoop:
    """Model-driven tool loop for the Jarvis desktop agent."""

    def __init__(self, registry: ToolRegistry | None = None, permission_policy: PermissionPolicy | None = None, model_adapter: Any | None = None, max_tool_iterations: int = 20, action_logger: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.registry = registry or ToolRegistry()
        self.permission_policy = permission_policy or PermissionPolicy()
        self.model_adapter = model_adapter
        self.max_tool_iterations = max_tool_iterations
        self.cancelled = False
        self.last_context: dict[str, Any] = {}
        self.action_logger = action_logger

    def cancel(self) -> None:
        self.cancelled = True
        cancel_tools = getattr(self.registry, "cancel_running", None)
        if cancel_tools:
            cancel_tools()
        cancel = getattr(self.model_adapter, "cancel", None)
        if cancel:
            cancel()

    def format_context(self, *, request: str, project_path: str | None = None, conversation: list[dict[str, Any]] | None = None, memory: list[dict[str, Any]] | None = None, available_tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        context = {
            "request": request,
            "project_path": project_path or str(Path.cwd()),
            "conversation": conversation or [],
            "memory": memory or [],
            "available_tools": available_tools or self.registry.model_definitions(),
            "agent_messages": [],
            "system_prompt": self.build_agent_prompt(request=request, project_path=project_path, conversation=conversation, memory=memory),
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
        if self.model_adapter is None:
            return {"final_response": "No tool-calling model is configured. Configure a supported model API before asking Jarvis to act."}
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

    def _execute_tool_call(self, tool_name: str, arguments: dict[str, Any], *, allow_confirmation: bool, confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None) -> dict[str, Any]:
        tool_def = self.registry.get(tool_name)
        if tool_def is None:
            return {"success": False, "tool": tool_name, "error": f"Unknown tool: {tool_name}"}
        confirmed = allow_confirmation
        if self.permission_policy.confirm_required(tool_name, tool_def.permission_level) and confirm_tool is not None:
            confirmed = bool(confirm_tool(tool_name, arguments, tool_def.permission_level))
        if not self.permission_policy.allows(tool_name, tool_def.permission_level, confirm=confirmed):
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

    def process_request(self, request: str, *, project_path: str | None = None, allow_confirmation: bool = False, confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None, conversation: list[dict[str, Any]] | None = None, memory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
            if self.cancelled:
                return {"success": False, "cancelled": True, "summary": "The task was cancelled.", "tool_calls": tool_calls}
            if isinstance(decision, dict) and decision.get("error"):
                return {"success": False, "cancelled": False, "summary": str(decision["error"]), "tool_calls": tool_calls}
            if isinstance(decision, dict) and "tool" in decision and "arguments" in decision:
                tool_call = decision
            else:
                tool_call = self._normalize_tool_call(decision.get("tool_call") or decision.get("tool") or decision)
            if tool_call.get("tool"):
                tool = tool_call["tool"]
                args = tool_call.get("arguments", {}) or {}
                result = self._execute_tool_call(tool, args, allow_confirmation=allow_confirmation, confirm_tool=confirm_tool)
                tool_calls.append({"name": tool, "arguments": args, "result": result})
                if self.action_logger:
                    try:
                        self.action_logger({"tool": tool, "arguments": args, "result": result})
                    except OSError as exc:
                        result["action_log_error"] = str(exc)
                context["last_tool_result"] = result
                context.setdefault("agent_messages", []).extend([
                    {"role": "assistant", "tool_call": {"name": tool, "arguments": args}},
                    {"role": "tool", "name": tool, "content": json.dumps(result, ensure_ascii=False)},
                ])
                if decision.get("final_response") and result.get("success", False):
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
