from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from typing import Any


VALID_STATUSES = {
    "pending",
    "running",
    "waiting_confirmation",
    "paused",
    "completed",
    "failed",
    "cancelled",
}


@dataclass
class JarvisTask:
    title: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    project_path: str | None = None
    selected_model: str | None = None
    current_step: str | None = None
    status: str = "pending"
    cancelled: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_running(self) -> None:
        self.status = "running"
        self.cancelled = False
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def request_stop(self) -> None:
        self.cancelled = True
        self.status = "cancelled"
        self.updated_at = datetime.now(timezone.utc).isoformat()


class EmergencyStopController:
    def __init__(self) -> None:
        self.triggered = False

    def stop(self) -> bool:
        self.triggered = True
        return True

    def clear(self) -> None:
        self.triggered = False


class TaskManager:
    def __init__(self) -> None:
        self.tasks: dict[str, JarvisTask] = {}
        self.emergency_stop = EmergencyStopController()

    def create_task(self, title: str, *, project_path: str | None = None, selected_model: str | None = None) -> JarvisTask:
        task = JarvisTask(title=title, project_path=project_path, selected_model=selected_model)
        self.tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> JarvisTask:
        if task_id not in self.tasks:
            raise KeyError(f"Task {task_id} not found")
        return self.tasks[task_id]

    def start(self, task_id: str) -> JarvisTask:
        task = self.get_task(task_id)
        task.mark_running()
        return task

    def request_stop(self, task_id: str) -> JarvisTask:
        task = self.get_task(task_id)
        task.request_stop()
        self.emergency_stop.stop()
        return task

    def list_tasks(self) -> list[JarvisTask]:
        return list(self.tasks.values())

    def mark_completed(self, task_id: str) -> JarvisTask:
        task = self.get_task(task_id)
        task.status = "completed"
        task.updated_at = datetime.now(timezone.utc).isoformat()
        return task

    def mark_failed(self, task_id: str, reason: str) -> JarvisTask:
        task = self.get_task(task_id)
        task.status = "failed"
        task.metadata["error"] = reason
        task.updated_at = datetime.now(timezone.utc).isoformat()
        return task
