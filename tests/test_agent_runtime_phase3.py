from app.agent import AgentLoop
from app.permissions.policy import PermissionPolicy
from app.tooling import ToolRegistry


def test_tool_registry_lists_common_tools():
    registry = ToolRegistry()
    names = registry.list_tools()
    assert "read_file" in names
    assert "run_powershell" in names
    assert "open_application" in names


def test_permission_policy_enforces_confirmation_for_sensitive_actions():
    policy = PermissionPolicy()
    assert policy.allows("read_file", "safe") is True
    assert policy.allows("write_file", "moderate") is False
    assert policy.allows("write_file", "moderate", confirm=True) is True
    assert policy.allows("run_powershell", "dangerous") is False
    assert policy.allows("run_powershell", "dangerous", confirm=True) is True


def test_agent_loop_executes_tool_request_and_returns_result(tmp_path):
    registry = ToolRegistry()
    target = tmp_path / "notes.txt"
    loop = AgentLoop(registry=registry, permission_policy=PermissionPolicy())

    result = loop.process_request(
        "Write hello to notes.txt and read it back.",
        project_path=str(tmp_path),
        allow_confirmation=True,
    )

    assert result["success"] is True
    assert "hello" in target.read_text(encoding="utf-8") or "hello" in result["summary"].lower()
    assert result["tool_calls"]


def test_agent_loop_stops_when_cancel_requested():
    registry = ToolRegistry()
    loop = AgentLoop(registry=registry, permission_policy=PermissionPolicy())
    loop.cancel()

    result = loop.process_request("Open Notepad.", project_path=".", allow_confirmation=True)
    assert result["success"] is False
    assert result["cancelled"] is True


def test_registry_supports_core_phase3_file_tools(tmp_path):
    registry = ToolRegistry()
    target_dir = tmp_path / "project"
    create_result = registry.execute("create_directory", str(target_dir), {})
    assert create_result["ok"] is True
    assert create_result["success"] is True
    assert target_dir.exists()

    file_path = target_dir / "notes.txt"
    write_result = registry.execute("write_file", str(file_path), {"content": "hello"})
    assert write_result["ok"] is True
    assert write_result["success"] is True
    assert file_path.read_text(encoding="utf-8") == "hello"


def test_task_manager_supports_confirmation_state():
    manager = __import__("app.tasks", fromlist=["TaskManager"]).TaskManager()
    task = manager.create_task("Needs approval")
    manager.start(task.id)
    manager.mark_waiting_confirmation(task.id)
    assert manager.get_task(task.id).status == "waiting_confirmation"
