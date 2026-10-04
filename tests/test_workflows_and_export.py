from app.export_import.import_export import ExportImportManager
from app.workflows.workflow_manager import WorkflowManager
from app.permissions.policy import PermissionPolicy
from app.tooling import ToolDefinition, ToolRegistry
from app.agent import AgentLoop


def test_workflow_manager_round_trip(tmp_path):
    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    workflow = manager.save_workflow("Prepare project", ["open_app", "read_files"])
    assert workflow["name"] == "Prepare project"
    assert manager.list_workflows()[0]["name"] == "Prepare project"


def test_repeated_approved_sequences_suggest_and_save_structured_workflow(tmp_path):
    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    sequence = [
        {"name": "open_application", "arguments": {"path": "notepad.exe"}, "result": {"success": True}},
        {"name": "open_browser", "arguments": {"url": "https://example.com"}, "result": {"success": True}},
    ]
    assert manager.record_observation(sequence)
    assert manager.workflow_suggestions() == []
    assert manager.record_observation(sequence)
    suggestion = manager.workflow_suggestions()[0]
    assert suggestion["occurrences"] == 2
    assert suggestion["steps"] == [
        {"tool": "open_application", "arguments": {"path": "notepad.exe"}},
        {"tool": "open_browser", "arguments": {"url": "https://example.com"}},
    ]
    manager.save_workflow("Start work", suggestion["steps"])
    assert manager.workflow_suggestions() == []


def test_workflow_observer_excludes_failed_and_sensitive_actions(tmp_path):
    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    assert not manager.record_observation([
        {"name": "run_powershell", "arguments": {"command": "secret"}, "result": {"success": True}},
        {"name": "open_application", "arguments": {"path": "x"}, "result": {"success": False}},
    ])
    assert manager.workflow_suggestions() == []


def test_workflow_run_requires_start_and_step_approvals(tmp_path):
    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    workflow = manager.save_workflow("Open site", [{"tool": "open_browser", "arguments": {"url": "https://example.com"}}])
    registry = ToolRegistry(workflow_manager=manager)
    calls = []
    registry.register(ToolDefinition("open_browser", "Open URL", "moderate", {"url": "URL"}, lambda url: calls.append(url) or {"success": True, "url": url}))

    class Model:
        def decide(self, _request, *, context=None):
            if not context["agent_messages"]:
                return {"tool": "run_workflow", "arguments": {"workflow_id": workflow["id"]}}
            return {"final_response": "Workflow finished."}

    confirmations = []
    def approve(tool, arguments, level):
        confirmations.append((tool, level))
        return True

    result = AgentLoop(registry=registry, model_adapter=Model(), workflow_manager=manager).process_request("Open my saved workflow", confirm_tool=approve)
    assert result["success"] is True
    assert calls == ["https://example.com"]
    assert confirmations == [("run_workflow", "dangerous"), ("open_browser", "moderate")]


def test_workflow_run_denial_stops_without_executing(tmp_path):
    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    workflow = manager.save_workflow("Open site", [{"tool": "open_browser", "arguments": {"url": "https://example.com"}}])
    registry = ToolRegistry(workflow_manager=manager)
    calls = []
    registry.register(ToolDefinition("open_browser", "Open URL", "moderate", {"url": "URL"}, lambda url: calls.append(url) or {"success": True}))

    result = manager.execute_workflow(workflow["id"], registry=registry, permission_policy=PermissionPolicy(), confirm_step=lambda *_args: False)
    assert result["success"] is False
    assert result["cancelled"] is True
    assert calls == []


def test_workflow_stop_prevents_following_steps(tmp_path):
    from threading import Event

    manager = WorkflowManager(database_path=str(tmp_path / "workflows.db"))
    workflow = manager.save_workflow("Open two sites", [
        {"tool": "open_browser", "arguments": {"url": "https://first.example"}},
        {"tool": "open_browser", "arguments": {"url": "https://second.example"}},
    ])
    registry = ToolRegistry(workflow_manager=manager)
    calls = []
    stopped = Event()

    def open_site(url):
        calls.append(url)
        stopped.set()
        return {"success": True}

    registry.register(ToolDefinition("open_browser", "Open URL", "moderate", {"url": "URL"}, open_site))
    result = manager.execute_workflow(
        workflow["id"], registry=registry, permission_policy=PermissionPolicy(),
        confirm_step=lambda *_args: True, should_cancel=stopped.is_set,
    )
    assert result["success"] is False and result["cancelled"] is True
    assert calls == ["https://first.example"]


def test_export_import_manager(tmp_path):
    manager = ExportImportManager(root=str(tmp_path))
    bundle = manager.export_data({"profile": "A", "preferences": ["dark mode"]})
    assert "profile" in bundle
    restored = manager.import_data(bundle)
    assert restored["preferences"] == ["dark mode"]
