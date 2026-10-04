from app.agent import AgentLoop
from app.computer.windows import WindowsController
from app.computer.browser import BrowserController
from app.opencode.client import OpenCodeClient
from app.permissions.policy import PermissionPolicy
from app.tooling import ToolRegistry
from pathlib import Path


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


def test_browser_session_navigates_reads_interacts_and_closes(tmp_path):
    class Locator:
        def __init__(self, page, selector):
            self.page = page
            self.selector = selector

        def count(self):
            return 1

        def click(self, **_kwargs):
            self.page.actions.append(("click", self.selector))

        def fill(self, text, **_kwargs):
            self.page.actions.append(("fill", self.selector, text))

        def inner_text(self, **_kwargs):
            return "Example page body"

    class Page:
        def __init__(self):
            self.url = ""
            self.actions = []

        def set_default_timeout(self, _timeout):
            pass

        def goto(self, url, **_kwargs):
            self.url = url
            return type("Response", (), {"status": 200})()

        def title(self):
            return "Example"

        def locator(self, selector):
            return Locator(self, selector)

        def screenshot(self, path, **_kwargs):
            from pathlib import Path
            Path(path).write_bytes(b"fake png")

    class Browser:
        def __init__(self):
            self.page = Page()
            self.closed = False

        def new_page(self):
            return self.page

        def close(self):
            self.closed = True

    class Playwright:
        def __init__(self):
            self.chromium = self
            self.browser = Browser()
            self.launches = []

        def start(self):
            return self

        def launch(self, **options):
            self.launches.append(options)
            return self.browser

        def stop(self):
            pass

    playwright = Playwright()
    controller = BrowserController(playwright_factory=lambda: playwright)
    opened = controller.open_browser("https://example.com")
    navigated = controller.navigate_browser("https://example.org")
    clicked = controller.click_browser_element("button.submit")
    typed = controller.type_browser("input[name=q]", "Jarvis")
    page = controller.read_page()
    screenshot_path = tmp_path / "browser-test.png"
    screenshot = controller.take_browser_screenshot(str(screenshot_path))
    closed = controller.close_browser()

    assert opened["success"] and opened["status"] == 200
    assert navigated["url"] == "https://example.org"
    assert clicked["success"] and typed["characters_typed"] == 6
    assert page["text"] == "Example page body"
    assert screenshot["image_path"].endswith("browser-test.png")
    assert closed["closed"] is True and playwright.browser.closed is True
    assert screenshot_path.exists()


def test_browser_rejects_non_web_urls_before_launching():
    class NeverStarted:
        def __call__(self):
            raise AssertionError("Invalid URL must not launch a browser.")

    result = BrowserController(playwright_factory=NeverStarted()).open_browser("file:///C:/secrets.txt")
    assert result["success"] is False
    assert "http:// or https://" in result["error"]


def test_desktop_screenshot_is_attached_for_vision_model_analysis(tmp_path, monkeypatch):
    import json
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from app.agent import OpenAICompatibleModelAdapter

    screenshot_path = tmp_path / "screen.png"
    image = QImage(2, 2, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.blue)
    assert image.save(str(screenshot_path), "PNG")

    api = FakeDesktopAPI()
    api.take_screenshot = lambda _path: {"path": str(screenshot_path), "image_path": str(screenshot_path), "format": "png"}
    registry = ToolRegistry(desktop_controller=WindowsController(api=api))
    client = OpenCodeClient(base_url="https://provider.example/v1")
    payloads = []

    def fake_post(_endpoint, payload):
        payloads.append(payload)
        if len(payloads) == 1:
            return {"choices": [{"message": {"tool_calls": [{"function": {
                "name": "take_screenshot", "arguments": json.dumps({"path": str(screenshot_path)}),
            }}]}}]}
        vision_message = payload["messages"][-1]
        assert vision_message["role"] == "user"
        assert vision_message["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        return {"choices": [{"message": {"content": "The screen is mostly blue."}}]}

    monkeypatch.setattr(client, "_post_json", fake_post)
    agent = AgentLoop(registry=registry, model_adapter=OpenAICompatibleModelAdapter(registry, client, "vision-model"))
    result = agent.process_request("Describe my screen", confirm_tool=lambda *_args: True)

    assert result["success"] is True
    assert result["summary"] == "The screen is mostly blue."
    assert len(payloads) == 2
