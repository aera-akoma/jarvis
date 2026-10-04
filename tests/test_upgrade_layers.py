from app.computer.windows import WindowsController
from app.opencode.client import OpenCodeClient
from app.startup import StartupManager


def test_opencode_client_uses_env_and_builds_request(monkeypatch):
    monkeypatch.setenv("OPENCODE_API_KEY", "demo-key")
    monkeypatch.setenv("JARVIS_OPENAI_BASE_URL", "https://example.com/v1")

    client = OpenCodeClient()
    payload = client.build_request("hello there", "custom-model")

    assert payload["model"] == "custom-model"
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"] == "hello there"
    assert client.headers()["Authorization"] == "Bearer demo-key"


def test_startup_manager_creates_cmd_file(tmp_path):
    manager = StartupManager(startup_dir=str(tmp_path))
    manager.enable_startup()
    assert (tmp_path / "Jarvis-startup.cmd").exists()

    manager.disable_startup()
    assert not (tmp_path / "Jarvis-startup.cmd").exists()


def test_windows_controller_opens_application(monkeypatch):
    calls = []

    def fake_startfile(path):
        calls.append(path)

    monkeypatch.setattr("os.startfile", fake_startfile, raising=False)
    controller = WindowsController()

    assert controller.open_application("notepad.exe") is True
    assert calls == ["notepad.exe"]


def test_opencode_client_reports_runtime_unavailable_when_not_configured(monkeypatch):
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCODE_BASE_URL", raising=False)

    client = OpenCodeClient()
    response = client.respond("Hello Jarvis", model_name="OpenCode Zen")

    assert "runtime unavailable" in response.lower()
    assert "I’ve received your request" not in response


def test_opencode_client_discovers_models_from_runtime(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return __import__("json").dumps(self.payload).encode("utf-8")

    def fake_urlopen(req, timeout=15):
        captured["url"] = req.full_url
        payload = {"data": [{"id": "gpt-4o-mini"}, {"id": "claude-3-5-sonnet"}]}
        return FakeResponse(payload)

    monkeypatch.setenv("JARVIS_OPENAI_BASE_URL", "https://example.com")
    monkeypatch.setattr("app.opencode.client.request.urlopen", fake_urlopen)

    client = OpenCodeClient()
    models = client.available_models()

    assert models == ["gpt-4o-mini", "claude-3-5-sonnet"]
    assert "example.com" in captured["url"]
