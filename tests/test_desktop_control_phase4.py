from app.agent import AgentLoop
from app.computer.windows import WindowsController
from app.opencode.client import OpenCodeClient
from app.permissions.policy import PermissionPolicy
from app.tooling import ToolRegistry


class FakeDesktopAPI:
    def __init__(self):
        self.actions = []

    def click(self, x, y, button="left", clicks=1):
        self.actions.append(("click", x, y, button, clicks))
        return {"x": x, "y": y, "button": button, "clicks": clicks}

    def move_mouse(self, x, y):
        self.actions.append(("move_mouse", x, y))
        return {"x": x, "y": y}

    def get_windows(self):
        return [{"handle": 1, "title": "Notepad", "x": 10, "y": 20, "width": 800, "height": 600}]

    def focus_window(self, title):
        self.actions.append(("focus_window", title))
        return {"title": title}

    def set_window_bounds(self, title, x, y, width, height):
        self.actions.append(("bounds", title, x, y, width, height))
        return {"title": title, "x": x, "y": y, "width": width, "height": height}

    def close_window(self, title):
        self.actions.append(("close", title))
        return {"title": title}

    def type_text(self, text):
        self.actions.append(("type", text))
        return {"characters_typed": len(text)}

    def press_key(self, key):
        self.actions.append(("key", key))
        return {"key": key}

    def hotkey(self, keys):
        self.actions.append(("hotkey", keys))
        return {"keys": keys}

    def take_screenshot(self, path):
        self.actions.append(("screenshot", path))
        return {"path": path, "format": "png"}


def test_phase4_tools_are_registered_with_guarded_permissions():
    api = FakeDesktopAPI()
    registry = ToolRegistry(desktop_controller=WindowsController(api=api))
    policy = PermissionPolicy()

    assert {"take_screenshot", "move_mouse", "click", "double_click", "right_click",
            "type_text", "press_key", "hotkey", "get_windows", "focus_window",
            "move_window", "resize_window", "close_application"}.issubset(registry.list_tools())
    assert policy.allows("get_windows", "safe")
    assert policy.allows("click", "moderate") is False
    assert policy.allows("click", "moderate", confirm=True)
    assert policy.allows("close_application", "dangerous") is False
    assert policy.allows("close_application", "dangerous", confirm=True)


def test_desktop_tool_is_not_executed_when_user_denies_confirmation():
    api = FakeDesktopAPI()
    registry = ToolRegistry(desktop_controller=WindowsController(api=api))

    class Model:
        calls = 0

        def decide(self, _request, *, context=None):
            self.calls += 1
            if self.calls == 1:
                return {"tool": "click", "arguments": {"x": 50, "y": 80, "button": "left"}}
            assert context["agent_messages"][-1]["role"] == "tool"
            return {"final_response": "I did not click because you denied approval."}

    result = AgentLoop(registry=registry, model_adapter=Model()).process_request(
        "Click the button", confirm_tool=lambda *_args: False,
    )

    assert result["success"] is True
    assert api.actions == []
    assert result["tool_calls"][0]["result"]["requires_confirmation"] is True


def test_desktop_window_tools_use_visible_window_bounds():
    api = FakeDesktopAPI()
    desktop = WindowsController(api=api)
    moved = desktop.move_window("Notepad", 100, 120)
    resized = desktop.resize_window("Notepad", 640, 480)

    assert moved["x"] == 100 and moved["y"] == 120
    assert resized["width"] == 640 and resized["height"] == 480
    assert api.actions == [
        ("bounds", "Notepad", 100, 120, 800, 600),
        ("bounds", "Notepad", 10, 20, 640, 480),
    ]


def test_model_schema_exposes_desktop_coordinates_as_integers(monkeypatch):
    registry = ToolRegistry(desktop_controller=WindowsController(api=FakeDesktopAPI()))
    client = OpenCodeClient(base_url="https://provider.example/v1")
    captured = {}

    def fake_post(_endpoint, payload):
        captured.update(payload)
        return {"choices": [{"message": {"content": "Ready."}}]}

    monkeypatch.setattr(client, "_post_json", fake_post)
    client.request_tool_decision(
        request="Click", model_name="model", tools=registry.model_definitions(),
        messages=[], system_prompt="Use tools.",
    )
    click = next(item["function"] for item in captured["tools"] if item["function"]["name"] == "click")
    assert click["parameters"]["properties"]["x"]["type"] == "integer"
    assert click["parameters"]["properties"]["y"]["type"] == "integer"
