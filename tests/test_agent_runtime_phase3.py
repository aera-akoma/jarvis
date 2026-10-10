import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.agent import AgentLoop, OpenAICompatibleModelAdapter
from app.config import AppConfig
from app.opencode.client import OpenCodeClient
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
    class MockModel:
        def __init__(self):
            self.calls = 0

        def decide(self, request, *, context=None):
            self.calls += 1
            if self.calls == 1:
                return {"tool": "write_file", "arguments": {"path": str(target), "content": "hello"}}
            assert context["agent_messages"][-1]["role"] == "tool"
            return {"final_response": "Created the file after checking the tool result."}

    loop = AgentLoop(registry=registry, permission_policy=PermissionPolicy(), model_adapter=MockModel())

    result = loop.process_request(
        "Write hello to notes.txt and read it back.",
        project_path=str(tmp_path),
        allow_confirmation=True,
    )

    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "hello"
    assert result["summary"] == "Created the file after checking the tool result."
    assert result["tool_calls"]


def test_agent_loop_without_model_does_not_guess_or_execute_tools(tmp_path):
    target = tmp_path / "notes.txt"
    result = AgentLoop(registry=ToolRegistry()).process_request(
        "Write hello to notes.txt", project_path=str(tmp_path), allow_confirmation=True
    )
    assert result["success"] is True
    assert not target.exists()
    assert "No tool-calling model" in result["summary"]


def test_model_adapter_sends_registered_tools_and_parses_model_tool_call(monkeypatch):
    captured = {}

    client = OpenCodeClient(base_url="https://provider.example/v1")
    def fake_post(endpoint, payload):
        captured["url"] = endpoint
        captured["payload"] = payload
        return {"choices": [{"message": {"tool_calls": [{"function": {
            "name": "list_directory", "arguments": '{"path":"C:/work"}',
        }}]}}]}

    monkeypatch.setattr(client, "_post_json", fake_post)
    decision = client.request_tool_decision(
        request="List my project files", model_name="cloud-model",
        tools=ToolRegistry().model_definitions(), messages=[], system_prompt="Use tools.",
    )
    assert decision == {"tool": "list_directory", "arguments": {"path": "C:/work"}}
    assert captured["payload"]["model"] == "cloud-model"
    assert any(tool["function"]["name"] == "list_directory" for tool in captured["payload"]["tools"])


def test_model_adapter_forwards_stop_to_provider_client():
    class Client:
        cancelled = False

        def cancel_current_request(self):
            self.cancelled = True

    registry = ToolRegistry()
    client = Client()
    adapter = OpenAICompatibleModelAdapter(registry, client, "model")
    adapter.cancel()
    assert adapter.cancelled is True
    assert client.cancelled is True


def test_provider_client_closes_active_socket_on_stop():
    class Socket:
        shutdown_called = False
        close_called = False

        def shutdown(self, _how):
            self.shutdown_called = True

        def close(self):
            self.close_called = True

    class Connection:
        def __init__(self):
            self.sock = Socket()
            self.close_called = False

        def close(self):
            self.close_called = True

    client = OpenCodeClient(base_url="https://provider.example/v1")
    connection = Connection()
    client._active_connection = connection
    client.cancel_current_request()
    assert connection.sock.shutdown_called and connection.sock.close_called
    assert connection.close_called


def test_model_client_loads_key_from_secure_credential_store(monkeypatch):
    class StoredCredentials:
        def get(self, name):
            assert name == "OpenAI"
            return "stored-provider-key"

    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("app.opencode.client.CredentialStore", StoredCredentials)
    client = OpenCodeClient(base_url="https://provider.example/v1")
    assert client.headers()["Authorization"] == "Bearer stored-provider-key"


def test_stop_terminates_active_powershell_process():
    registry = ToolRegistry()

    class Process:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return -15

    process = Process()
    registry._active_process = process
    registry.cancel_running()
    assert process.terminated is True
    assert registry._cancel_requested.is_set()


def test_pyside_chat_runs_approved_tool_and_persists_model_reply(tmp_path, monkeypatch):
    import json
    import time
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.ui.main_window import MainWindow

    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr("app.ui.main_window.OpenCodeClient.available_models", lambda _self: ["test-model"])
    window = MainWindow(AppConfig(data_dir=str(tmp_path / "jarvis-data")))
    deadline = time.monotonic() + 3
    while window._models_loading and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)
    assert window.model_selector.isEnabled()
    target = tmp_path / "created-through-ui.txt"
    model_replies = iter([
        {"tool": "write_file", "arguments": {"path": str(target), "content": "from the UI tool flow"}},
        {"final_response": "The file was written through the approved agent loop."},
    ])
    window.runtime.request_tool_decision = lambda **_kwargs: next(model_replies)
    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes)
    window.prompt_input.setText("Hi Jarvis")

    window.send_message()
    worker = window.agent_worker
    assert worker is not None
    deadline = time.monotonic() + 3
    while worker.isRunning() and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)
    application.processEvents()
    assert not worker.isRunning()

    messages = window.session_manager.get_messages(window.active_conversation["id"])
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "The file was written through the approved agent loop."
    assert target.read_text(encoding="utf-8") == "from the UI tool flow"
    assert window.task_manager.get_task(window.current_task.id).status == "completed"
    action_log = tmp_path / "jarvis-data" / "logs" / "action_log.jsonl"
    assert json.loads(action_log.read_text(encoding="utf-8").splitlines()[0])["tool"] == "write_file"
    window.close()


def test_provider_to_tool_to_provider_round_trip_and_approval(tmp_path, monkeypatch):
    target = tmp_path / "agent-created.txt"
    registry = ToolRegistry()
    client = OpenCodeClient(base_url="https://provider.example/v1")
    payloads = []

    def fake_post(_endpoint, payload):
        payloads.append(payload)
        if len(payloads) == 1:
            return {"choices": [{"message": {"tool_calls": [{"function": {
                "name": "write_file",
                "arguments": __import__("json").dumps({"path": str(target), "content": "model selected this"}),
            }}]}}]}
        assert payload["messages"][-1]["role"] == "tool"
        assert "model selected this" in payload["messages"][-1]["content"]
        return {"choices": [{"message": {"content": "The file was written and verified."}}]}

    monkeypatch.setattr(client, "_post_json", fake_post)
    approvals = []
    logged = []
    agent = AgentLoop(
        registry=registry,
        model_adapter=OpenAICompatibleModelAdapter(registry, client, "cloud-model"),
        action_logger=logged.append,
    )
    result = agent.process_request(
        "Create a file", project_path=str(tmp_path),
        confirm_tool=lambda name, args, level: approvals.append((name, args, level)) or True,
    )

    assert result["success"] is True
    assert result["summary"] == "The file was written and verified."
    assert target.read_text(encoding="utf-8") == "model selected this"
    assert approvals[0][0] == "write_file" and approvals[0][2] == "moderate"
    assert len(logged) == 1 and logged[0]["result"]["success"] is True
    assert len(payloads) == 2


def test_stop_cancels_an_in_flight_model_request():
    import threading

    entered = threading.Event()

    class CancellableModel:
        def __init__(self):
            self.cancelled = False

        def decide(self, _request, *, context=None):
            entered.set()
            while not self.cancelled:
                threading.Event().wait(0.01)
            return {"final_response": "cancelled"}

        def cancel(self):
            self.cancelled = True

    model = CancellableModel()
    agent = AgentLoop(model_adapter=model)
    completed = threading.Event()
    result_holder = []

    def run():
        result_holder.append(agent.process_request("Do work"))
        completed.set()

    worker = threading.Thread(target=run)
    worker.start()
    assert entered.wait(2)
    agent.cancel()
    assert completed.wait(2)
    worker.join()
    assert result_holder[0]["cancelled"] is True


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
