from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.computer.windows import WindowsController


@dataclass
class ToolDefinition:
    name: str
    description: str
    permission_level: str = "safe"
    parameters: dict[str, str] = field(default_factory=dict)
    handler: Callable[..., dict[str, Any]] | None = None


class ToolRegistry:
    def __init__(self, desktop_controller: WindowsController | None = None) -> None:
        self.tools: dict[str, ToolDefinition] = {}
        self.desktop = desktop_controller or WindowsController()
        self._active_process: subprocess.Popen[str] | None = None
        self._process_lock = threading.Lock()
        self._cancel_requested = threading.Event()
        self._register_default_tools()

    def cancel_running(self) -> None:
        self._cancel_requested.set()
        with self._process_lock:
            process = self._active_process
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
        except OSError:
            return
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass

    def _register_default_tools(self) -> None:
        definitions = [
            ToolDefinition("read_file", "Read a text file from disk.", "safe", {"path": "file path"}, self._read_file),
            ToolDefinition("write_file", "Write or overwrite a text file.", "moderate", {"path": "file path", "content": "file contents"}, self._write_file),
            ToolDefinition("create_file", "Create a new file with content.", "moderate", {"path": "file path", "content": "file contents"}, self._create_file),
            ToolDefinition("create_directory", "Create a directory tree.", "moderate", {"path": "directory path"}, self._create_directory),
            ToolDefinition("list_directory", "List files in a directory.", "safe", {"path": "directory path"}, self._list_directory),
            ToolDefinition("search_files", "Search for files under a directory.", "safe", {"path": "directory path", "pattern": "file pattern"}, self._search_files),
            ToolDefinition("open_application", "Open an application or document on Windows.", "safe", {"path": "application or document path"}, self._open_application),
            ToolDefinition("run_powershell", "Run a PowerShell command.", "dangerous", {"command": "PowerShell command"}, self._run_powershell),
        ]
        for definition in definitions:
            self.register(definition)
        self._register_desktop_tools()

    def _register_desktop_tools(self) -> None:
        definitions = [
            ("take_screenshot", "Capture the desktop as a PNG and send the image to the configured model for analysis.", "moderate", {"path": "PNG output file path"}, self.desktop.take_screenshot),
            ("move_mouse", "Move the mouse pointer to screen coordinates.", "moderate", {"x": "horizontal screen coordinate", "y": "vertical screen coordinate"}, self.desktop.move_mouse),
            ("click", "Click a screen coordinate with the left, right, or middle mouse button.", "moderate", {"x": "horizontal screen coordinate", "y": "vertical screen coordinate", "button": "left, right, or middle"}, self.desktop.click),
            ("double_click", "Double click a screen coordinate.", "moderate", {"x": "horizontal screen coordinate", "y": "vertical screen coordinate"}, self.desktop.double_click),
            ("right_click", "Right click a screen coordinate.", "moderate", {"x": "horizontal screen coordinate", "y": "vertical screen coordinate"}, self.desktop.right_click),
            ("type_text", "Type text into the currently focused application.", "moderate", {"text": "text to type"}, self.desktop.type_text),
            ("press_key", "Press one named keyboard key.", "moderate", {"key": "key name such as Enter or Escape"}, self.desktop.press_key),
            ("hotkey", "Press a key combination, for example Ctrl+Shift+S.", "dangerous", {"keys": "keys joined with +"}, self.desktop.hotkey),
            ("get_windows", "List visible desktop windows and their bounds.", "safe", {}, self.desktop.get_windows),
            ("focus_window", "Bring the uniquely matching visible window to the foreground.", "safe", {"title": "visible window title or unique substring"}, self.desktop.focus_window),
            ("move_window", "Move a visible window while preserving its size.", "moderate", {"title": "visible window title", "x": "new horizontal coordinate", "y": "new vertical coordinate"}, self.desktop.move_window),
            ("resize_window", "Resize a visible window while preserving its position.", "moderate", {"title": "visible window title", "width": "new width in pixels", "height": "new height in pixels"}, self.desktop.resize_window),
            ("close_application", "Request that a visible application window close.", "dangerous", {"title": "visible window title"}, self.desktop.close_application),
            ("open_browser", "Open a visible Jarvis-managed browser at an HTTP(S) URL.", "moderate", {"url": "HTTP or HTTPS URL to open"}, self.desktop.open_browser),
            ("navigate_browser", "Navigate the active Jarvis browser tab to an HTTP(S) URL.", "moderate", {"url": "HTTP or HTTPS URL to open"}, self.desktop.navigate_browser),
            ("click_browser_element", "Click one uniquely matched CSS selector in the active page.", "dangerous", {"selector": "CSS selector matching exactly one element"}, self.desktop.click_browser_element),
            ("type_browser", "Fill one uniquely matched form field in the active page.", "dangerous", {"selector": "CSS selector for the field", "text": "text to enter"}, self.desktop.type_browser),
            ("read_page", "Read the active page text; the text is sent to the configured model for assistance.", "dangerous", {}, self.desktop.read_page),
            ("take_browser_screenshot", "Capture the active page; its image is sent to the configured model for analysis.", "moderate", {"path": "PNG output file path"}, self.desktop.take_browser_screenshot),
            ("close_browser", "Close Jarvis's managed browser window and its tabs.", "dangerous", {}, self.desktop.close_browser),
        ]
        for name, description, permission, parameters, handler in definitions:
            self.register(ToolDefinition(name, description, permission, parameters, handler))

    def register(self, tool: ToolDefinition) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self.tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self.tools.keys())

    def model_definitions(self) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        for name in sorted(self.tools):
            tool = self.tools[name]
            definitions.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "permission_level": tool.permission_level,
                }
            )
        return definitions

    def execute(self, name: str, target: str | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            return {"ok": False, "success": False, "error": f"Unknown tool: {name}"}

        payload = dict(params or {})
        if target is not None and "path" not in payload and "target" not in payload:
            payload["path"] = target
        if tool.handler is None:
            return {"ok": False, "success": False, "error": f"Tool {name} has no handler"}
        try:
            result = tool.handler(**payload)
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            return {"ok": False, "success": False, "tool": name, "error": str(exc)}
        if isinstance(result, dict):
            result.setdefault("success", result.get("ok", False))
            result.setdefault("ok", result.get("success", False))
            return result
        return {"ok": True, "success": True, "result": result}

    def _read_file(self, path: str) -> dict[str, Any]:
        file_path = Path(path)
        if not file_path.exists():
            return {"ok": False, "success": False, "error": f"File not found: {path}"}
        return {"ok": True, "success": True, "path": str(file_path), "content": file_path.read_text(encoding="utf-8")}

    def _write_file(self, path: str, content: str = "") -> dict[str, Any]:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"ok": True, "success": True, "path": str(file_path), "content": content}

    def _create_file(self, path: str, content: str = "") -> dict[str, Any]:
        file_path = Path(path)
        if file_path.exists():
            return {"ok": False, "success": False, "error": f"File already exists: {path}"}
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"ok": True, "success": True, "path": str(file_path), "content": content}

    def _create_directory(self, path: str) -> dict[str, Any]:
        directory = Path(path)
        if directory.exists():
            return {"ok": True, "success": True, "path": str(directory), "created": False}
        directory.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "success": True, "path": str(directory), "created": True}

    def _list_directory(self, path: str) -> dict[str, Any]:
        directory = Path(path)
        if not directory.exists():
            return {"ok": False, "success": False, "error": f"Directory not found: {path}"}
        entries = sorted(p.name for p in directory.iterdir())
        return {"ok": True, "success": True, "path": str(directory), "entries": entries}

    def _search_files(self, path: str, pattern: str = "*") -> dict[str, Any]:
        directory = Path(path)
        if not directory.exists():
            return {"ok": False, "success": False, "error": f"Directory not found: {path}"}
        matches = sorted(str(p) for p in directory.rglob(pattern) if p.is_file())
        return {"ok": True, "success": True, "path": str(directory), "matches": matches}

    def _open_application(self, path: str) -> dict[str, Any]:
        if not hasattr(os, "startfile"):
            return {"ok": False, "success": False, "error": "Windows startfile is not available."}
        try:
            os.startfile(path)
            return {"ok": True, "success": True, "path": path}
        except OSError as exc:
            return {"ok": False, "success": False, "error": str(exc)}

    def _run_powershell(self, command: str) -> dict[str, Any]:
        if self._cancel_requested.is_set():
            return {"ok": False, "success": False, "cancelled": True, "error": "PowerShell command cancelled."}
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(["powershell", "-NoProfile", "-Command", command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            with self._process_lock:
                self._active_process = process
            if self._cancel_requested.is_set():
                self.cancel_running()
            stdout, stderr = process.communicate()
            return {
                "ok": process.returncode == 0,
                "success": process.returncode == 0,
                "cancelled": self._cancel_requested.is_set(),
                "returncode": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
        except FileNotFoundError:
            return {"ok": False, "success": False, "error": "PowerShell is not available."}
        finally:
            with self._process_lock:
                if self._active_process is process:
                    self._active_process = None
