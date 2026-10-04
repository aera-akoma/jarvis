from pathlib import Path

from app.permissions.policy import PermissionPolicy
from app.tasks import JarvisTask, TaskManager
from app.tooling import ToolRegistry


def test_permission_policy_requires_confirmation_for_sensitive_actions():
    policy = PermissionPolicy()

    assert policy.allows("read_file", "safe")
    assert policy.allows("edit_file", "moderate") is False
    assert policy.allows("edit_file", "moderate", confirm=True) is True
    assert policy.allows("delete_file", "dangerous") is False
    assert policy.allows("delete_file", "dangerous", confirm=True) is True
    assert policy.confirm_required("delete_file", "dangerous") is True


def test_tool_registry_runs_real_file_tools(tmp_path):
    registry = ToolRegistry()
    target = tmp_path / "demo.txt"

    result = registry.execute("write_file", str(target), {"content": "hello"})
    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "hello"

    read_result = registry.execute("read_file", str(target), {})
    assert read_result["ok"] is True
    assert read_result["content"] == "hello"


def test_task_manager_tracks_progress_and_stop():
    manager = TaskManager()
    task = manager.create_task("Demo task", project_path="C:/Projects/demo")

    manager.start(task.id)
    assert manager.get_task(task.id).status == "running"

    manager.request_stop(task.id)
    assert manager.get_task(task.id).status == "cancelled"
    assert manager.get_task(task.id).cancelled is True


def test_task_object_has_expected_statuses():
    task = JarvisTask(title="Status test")
    assert task.status == "pending"
    assert task.cancelled is False
    task.status = "completed"
    assert task.status == "completed"
