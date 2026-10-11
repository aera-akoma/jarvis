"""Tests for the Mark-LV-adapted undo stack, the undo tool, and self-describing skills."""
from pathlib import Path

import pytest

from app.permissions.policy import PermissionPolicy
from app.tool_loader import discover_skills
from app.tooling import ToolRegistry
from app.undo import UndoManager
from app.computer.windows import WindowsController


class FakeDesktopAPI:
    def __init__(self):
        self.actions = []
        self.windows = [{"handle": 1, "title": "Notepad", "x": 10, "y": 20, "width": 800, "height": 600}]

    def get_windows(self):
        return list(self.windows)

    def set_window_bounds(self, title, x, y, width, height):
        self.actions.append(("bounds", title, x, y, width, height))
        for window in self.windows:
            if title.casefold() in window["title"].casefold():
                window.update(x=x, y=y, width=width, height=height)
        return {"title": title, "x": x, "y": y, "width": width, "height": height}


# ---- UndoManager -----------------------------------------------------------


def test_undo_manager_lifo_and_clear():
    manager = UndoManager()
    assert manager.count() == 0
    assert manager.peek_label() is None
    manager.push("first", lambda: None)
    manager.push("second", lambda: None)
    assert manager.count() == 2
    assert manager.peek_label() == "second"
    entry = manager.pop()
    assert entry.label == "second"
    assert manager.pop().label == "first"
    assert manager.pop() is None
    manager.push("only", lambda: None)
    manager.clear()
    assert manager.count() == 0


def test_undo_manager_bounds_stack_size():
    manager = UndoManager(max_entries=3)
    for index in range(5):
        manager.push(f"entry-{index}", lambda: None)
    assert manager.count() == 3
    assert manager.peek_label() == "entry-4"


def test_undo_manager_rejects_empty_labels():
    manager = UndoManager()
    manager.push("", lambda: None)
    assert manager.count() == 0


# ---- Undo through the registry ---------------------------------------------


def test_write_file_undo_restores_previous_content(tmp_path):
    registry = ToolRegistry()
    target = tmp_path / "notes.txt"

    result = registry.execute("write_file", str(target), {"content": "hello"})
    assert result["ok"] is True

    result = registry.execute("undo", params={})
    assert result["ok"] is True
    assert result["undone"] == "restore the previous file content"
    assert not target.exists()

    target.write_text("original", encoding="utf-8")
    registry.execute("write_file", str(target), {"content": "changed"})
    assert target.read_text(encoding="utf-8") == "changed"
    registry.execute("undo", params={})
    assert target.read_text(encoding="utf-8") == "original"


def test_create_file_undo_deletes_the_created_file(tmp_path):
    registry = ToolRegistry()
    target = tmp_path / "new.txt"

    result = registry.execute("create_file", str(target), {"content": "data"})
    assert result["ok"] is True
    assert target.exists()

    result = registry.execute("undo", params={})
    assert result["ok"] is True
    assert result["undone"] == "delete the created file"
    assert not target.exists()


def test_create_directory_undo_removes_empty_directory(tmp_path):
    registry = ToolRegistry()
    directory = tmp_path / "made"

    result = registry.execute("create_directory", str(directory))
    assert result["ok"] is True and directory.exists()

    result = registry.execute("undo", params={})
    assert result["ok"] is True
    assert not directory.exists()


def test_create_directory_undo_fails_when_no_longer_empty(tmp_path):
    registry = ToolRegistry()
    directory = tmp_path / "made"
    registry.execute("create_directory", str(directory))
    (directory / "user-file.txt").write_text("kept", encoding="utf-8")

    result = registry.execute("undo", params={})
    assert result["ok"] is False
    assert "no longer empty" in result["error"]
    # The failed undo entry is pushed back so it can be retried.
    assert registry.undo_manager.count() == 1
    assert (directory / "user-file.txt").exists()


def test_window_move_undo_restores_geometry():
    api = FakeDesktopAPI()
    registry = ToolRegistry(desktop_controller=WindowsController(api=api))

    result = registry.execute("move_window", params={"title": "Notepad", "x": 200, "y": 300})
    assert result["ok"] is True

    result = registry.execute("undo", params={})
    assert result["ok"] is True
    assert api.actions[-1] == ("bounds", "Notepad", 10, 20, 800, 600)


def test_undo_with_empty_stack_reports_clearly():
    registry = ToolRegistry()
    registry.undo_manager.clear()
    result = registry.execute("undo", params={})
    assert result["ok"] is False
    assert result["error"] == "Nothing to undo."


def test_undo_permission_is_moderate():
    policy = PermissionPolicy()
    assert policy.confirm_required("undo", "moderate") is True
    assert policy.allows("undo", "moderate") is False
    assert policy.allows("undo", "moderate", confirm=True) is True


def test_undo_agent_prompt_mentions_undo():
    from app.agent import AgentLoop

    loop = AgentLoop()
    prompt = loop.build_agent_prompt(request="undo my last change")
    assert "undo" in prompt


# ---- Self-describing skills ------------------------------------------------


def test_skill_module_is_converted_to_tool(tmp_path):
    module_path = tmp_path / "greet.py"
    module_path.write_text(
        'TOOL = {"name": "greet", "description": "Say hello.", "permission_level": "safe",'
        ' "parameters": {"name": "who to greet"}}\n'
        "def handler(name: str = \"world\") -> dict:\n"
        '    return {"ok": True, "greeting": f"Hello, {name}"}\n',
        encoding="utf-8",
    )
    tools = discover_skills(tmp_path)
    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == "greet"
    assert tool.permission_level == "safe"
    assert tool.parameters == {"name": "who to greet"}

    registry = ToolRegistry()
    registry.register(tool)
    result = registry.execute("greet", params={"name": "Ada"})
    assert result["greeting"] == "Hello, Ada"


def test_invalid_skill_modules_are_skipped(tmp_path):
    (tmp_path / "no_tool.py").write_text("VALUE = 42\n", encoding="utf-8")
    (tmp_path / "bad_name.py").write_text(
        'TOOL = {"name": "Not Valid!", "description": "bad"}\n',
        encoding="utf-8",
    )
    (tmp_path / "no_handler.py").write_text(
        'TOOL = {"name": "ghost", "description": "no handler"}\n',
        encoding="utf-8",
    )
    (tmp_path / "bad_level.py").write_text(
        'TOOL = {"name": "wild", "description": "x", "permission_level": "extreme"}\n'
        "def handler() -> dict:\n return {}\n",
        encoding="utf-8",
    )
    # Hidden files are excluded from discovery.
    (tmp_path / "_template.py").write_text(
        'TOOL = {"name": "template", "description": "hidden"}\n',
        encoding="utf-8",
    )
    assert discover_skills(tmp_path) == []


def test_broken_skill_module_does_not_break_discovery(tmp_path):
    (tmp_path / "broken.py").write_text("this is not python !!!\n", encoding="utf-8")
    assert discover_skills(tmp_path) == []


def test_bundled_skills_are_auto_registered():
    registry = ToolRegistry()
    disk_free = registry.get("disk_free")
    uptime = registry.get("uptime")
    assert disk_free is not None
    assert disk_free.permission_level == "safe"
    assert uptime is not None

    result = registry.execute("disk_free", params={})
    assert result["ok"] is True
    assert result["free_bytes"] > 0


def test_shipped_skill_template_is_not_discovered():
    # app/skills/_template.py is a developer authoring aid; the leading
    # underscore must keep it out of discovery so its example "hello" tool
    # never reaches the registry.
    names = {tool.name for tool in discover_skills()}
    assert "hello" not in names
    assert {"disk_free", "uptime"} <= names


def test_skill_that_collides_with_builtin_is_skipped(tmp_path, monkeypatch):
    module_path = tmp_path / "read_file.py"
    module_path.write_text(
        'TOOL = {"name": "read_file", "description": "shadow", "permission_level": "safe"}\n'
        "def handler() -> dict:\n    return {}\n",
        encoding="utf-8",
    )
    shadow = discover_skills(tmp_path)
    assert len(shadow) == 1 and shadow[0].name == "read_file"

    import app.tooling

    monkeypatch.setattr(app.tooling, "discover_skills", lambda directory=None: shadow)
    registry = ToolRegistry()
    assert registry.get("read_file").description != "shadow"