from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


RECORDABLE_WORKFLOW_TOOLS = frozenset({
    "open_application", "open_browser", "navigate_browser", "focus_window",
    "list_directory", "search_files", "create_directory",
})


class WorkflowManager:
    """Stores approved workflows and learns repeated, low-risk action sequences."""

    def __init__(self, database_path: str | None = None) -> None:
        if database_path is None:
            database_path = str(Path.home() / "AppData" / "Roaming" / "Jarvis" / "jarvis.db")
        self.database_path = str(Path(database_path))
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, steps TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS workflow_observations (
                id TEXT PRIMARY KEY, sequence_key TEXT NOT NULL, steps TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_workflow_observation_key ON workflow_observations(sequence_key)")
        self.connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _serialize_steps(steps: list[Any]) -> str:
        return json.dumps(steps, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _deserialize_steps(value: str) -> list[Any]:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (TypeError, ValueError):
            pass
        # Backward compatibility with the original pipe-delimited schema.
        return value.split("|") if value else []

    def save_workflow(self, name: str, steps: list[Any]) -> dict[str, Any]:
        name = (name or "").strip()
        if not name:
            raise ValueError("Workflow name cannot be empty.")
        if not steps or len(steps) > 20:
            raise ValueError("A workflow must contain between 1 and 20 steps.")
        normalized = []
        for step in steps:
            if isinstance(step, str):
                normalized.append({"tool": step, "arguments": {}})
            elif isinstance(step, dict) and step.get("tool") and isinstance(step.get("arguments", {}), dict):
                normalized.append({"tool": str(step["tool"]), "arguments": dict(step.get("arguments", {}))})
            else:
                raise ValueError("Each workflow step must have a tool and object arguments.")
        workflow_id = uuid.uuid4().hex
        now = self._now()
        self.connection.execute(
            "INSERT INTO workflows(id, name, steps, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (workflow_id, name, self._serialize_steps(normalized), now, now),
        )
        self.connection.commit()
        return {"id": workflow_id, "name": name, "steps": normalized, "created_at": now, "updated_at": now}

    def _workflow_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "name": row["name"], "steps": self._deserialize_steps(row["steps"]),
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list_workflows(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT id, name, steps, created_at, updated_at FROM workflows ORDER BY updated_at DESC").fetchall()
        return [self._workflow_from_row(row) for row in rows]

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT id, name, steps, created_at, updated_at FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        return self._workflow_from_row(row) if row else None

    def delete_workflow(self, workflow_id: str) -> bool:
        cursor = self.connection.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
        self.connection.commit()
        return cursor.rowcount > 0

    def record_observation(self, actions: list[dict[str, Any]]) -> bool:
        """Store a successful in-session sequence only for narrowly allowed tools."""
        steps = []
        for action in actions:
            tool = action.get("name") or action.get("tool")
            result = action.get("result") or {}
            if tool not in RECORDABLE_WORKFLOW_TOOLS or not result.get("success", result.get("ok", False)):
                continue
            arguments = action.get("arguments") or {}
            if not isinstance(arguments, dict):
                continue
            # Keep only the declared action inputs; never capture tool output or page/file contents.
            steps.append({"tool": tool, "arguments": arguments})
        if len(steps) < 2 or len(steps) > 20:
            return False
        canonical = self._serialize_steps(steps)
        sequence_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.connection.execute(
            "INSERT INTO workflow_observations(id, sequence_key, steps, created_at) VALUES (?, ?, ?, ?)",
            (uuid.uuid4().hex, sequence_key, canonical, self._now()),
        )
        self.connection.commit()
        return True

    def workflow_suggestions(self, min_occurrences: int = 2) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT sequence_key, steps, COUNT(*) AS occurrences, MAX(created_at) AS last_seen "
            "FROM workflow_observations GROUP BY sequence_key HAVING COUNT(*) >= ? ORDER BY last_seen DESC",
            (max(2, min_occurrences),),
        ).fetchall()
        saved = {self._serialize_steps(workflow["steps"]) for workflow in self.list_workflows()}
        suggestions = []
        for row in rows:
            steps = self._deserialize_steps(row["steps"])
            if self._serialize_steps(steps) in saved:
                continue
            tool_names = [step["tool"] for step in steps if isinstance(step, dict)]
            app_labels = []
            for step in steps:
                args = step.get("arguments", {}) if isinstance(step, dict) else {}
                label = args.get("path") or args.get("url") or args.get("title")
                if label:
                    app_labels.append(str(label))
            default_name = " → ".join(app_labels[:3]) or "Repeated desktop routine"
            suggestions.append({"steps": steps, "occurrences": row["occurrences"], "last_seen": row["last_seen"],
                                "suggested_name": default_name[:80], "tools": tool_names})
        return suggestions

    def execute_workflow(self, workflow_id: str, *, registry: Any, permission_policy: Any,
                         confirm_step: Callable[[str, dict[str, Any], str], bool] | None = None,
                         should_cancel: Callable[[], bool] | None = None) -> dict[str, Any]:
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            return {"success": False, "error": "Saved workflow was not found.", "steps": []}
        results = []
        for index, step in enumerate(workflow["steps"], start=1):
            if should_cancel and should_cancel():
                return {"success": False, "cancelled": True, "error": f"Workflow stopped before step {index}.", "steps": results}
            if isinstance(step, str):
                return {"success": False, "error": "This legacy workflow has no saved arguments and cannot be executed safely. Edit and resave it first.", "steps": results}
            tool_name = step.get("tool", "")
            arguments = step.get("arguments", {})
            if tool_name not in RECORDABLE_WORKFLOW_TOOLS:
                return {"success": False, "error": f"Workflow step {index} uses a tool that is not approved for workflow replay: {tool_name}", "steps": results}
            definition = registry.get(tool_name)
            if definition is None:
                return {"success": False, "error": f"Workflow step {index} references unavailable tool: {tool_name}", "steps": results}
            if permission_policy.confirm_required(tool_name, definition.permission_level):
                if confirm_step is None or not confirm_step(tool_name, arguments, definition.permission_level):
                    return {"success": False, "cancelled": True, "error": f"Workflow stopped at step {index}; approval was not granted.", "steps": results}
            if not permission_policy.allows(tool_name, definition.permission_level, confirm=bool(confirm_step)):
                return {"success": False, "error": f"Permission denied at workflow step {index}.", "steps": results}
            result = registry.execute(tool_name, params=arguments)
            results.append({"step": index, "tool": tool_name, "arguments": arguments, "result": result})
            if not result.get("success", result.get("ok", False)):
                return {"success": False, "error": f"Workflow stopped because step {index} failed.", "steps": results}
        return {"success": True, "workflow": workflow["name"], "steps": results}
