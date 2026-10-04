from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
from pathlib import Path
from typing import Any


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.wintypes.DWORD),
        ("biWidth", ctypes.wintypes.LONG),
        ("biHeight", ctypes.wintypes.LONG),
        ("biPlanes", ctypes.wintypes.WORD),
        ("biBitCount", ctypes.wintypes.WORD),
        ("biCompression", ctypes.wintypes.DWORD),
        ("biSizeImage", ctypes.wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.wintypes.LONG),
        ("biYPelsPerMeter", ctypes.wintypes.LONG),
        ("biClrUsed", ctypes.wintypes.DWORD),
        ("biClrImportant", ctypes.wintypes.DWORD),
    ]


class _RGBQuad(ctypes.Structure):
    _fields_ = [("rgbBlue", ctypes.c_ubyte), ("rgbGreen", ctypes.c_ubyte),
                ("rgbRed", ctypes.c_ubyte), ("rgbReserved", ctypes.c_ubyte)]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", _BitmapInfoHeader), ("bmiColors", _RGBQuad * 1)]


class WindowsDesktopAPI:
    """Small stdlib-only Windows desktop backend."""

    def _user32(self):
        if os.name != "nt":
            raise OSError("Desktop input is available only on Windows.")
        user32 = ctypes.windll.user32
        wintypes = ctypes.wintypes
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        return user32

    @staticmethod
    def _window_title(user32: Any, hwnd: int) -> str:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def get_windows(self) -> list[dict[str, Any]]:
        user32 = self._user32()
        windows: list[dict[str, Any]] = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows.argtypes = [callback_type, ctypes.c_void_p]
        user32.EnumWindows.restype = ctypes.wintypes.BOOL

        def visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            title = self._window_title(user32, hwnd)
            if not title.strip():
                return True
            rect = ctypes.wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            windows.append({"handle": int(hwnd), "title": title,
                            "x": rect.left, "y": rect.top,
                            "width": rect.right - rect.left, "height": rect.bottom - rect.top})
            return True

        user32.EnumWindows(callback_type(visit), 0)
        return windows

    def _find_window(self, title: str) -> int:
        needle = title.strip().casefold()
        if not needle:
            raise ValueError("A window title is required.")
        matches = [item for item in self.get_windows() if needle in item["title"].casefold()]
        if len(matches) != 1:
            raise ValueError("Window title did not match exactly one visible window.")
        return matches[0]["handle"]

    def move_mouse(self, x: int, y: int) -> dict[str, Any]:
        user32 = self._user32()
        width, height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"Coordinates must be inside the current screen ({width}x{height}).")
        if not user32.SetCursorPos(x, y):
            raise OSError("Windows could not move the mouse pointer.")
        return {"x": x, "y": y}

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> dict[str, Any]:
        user32 = self._user32()
        self.move_mouse(x, y)
        flags = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
        if button not in flags:
            raise ValueError("Mouse button must be left, right, or middle.")
        down, up = flags[button]
        for _ in range(clicks):
            user32.mouse_event(down, 0, 0, 0, 0)
            user32.mouse_event(up, 0, 0, 0, 0)
        return {"x": x, "y": y, "button": button, "clicks": clicks}

    def _virtual_key(self, key: str) -> int:
        user32 = self._user32()
        keys = {"ENTER": 0x0D, "RETURN": 0x0D, "ESC": 0x1B, "ESCAPE": 0x1B,
                "TAB": 0x09, "SPACE": 0x20, "BACKSPACE": 0x08, "DELETE": 0x2E,
                "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
                "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
                "CTRL": 0x11, "CONTROL": 0x11, "ALT": 0x12, "SHIFT": 0x10,
                "WIN": 0x5B, "WINDOWS": 0x5B}
        normalized = key.strip().upper()
        if normalized in keys:
            return keys[normalized]
        if len(normalized) == 1:
            mapped = user32.VkKeyScanW(ord(normalized))
            if mapped != -1:
                return mapped & 0xFF
        if normalized.startswith("F") and normalized[1:].isdigit() and 1 <= int(normalized[1:]) <= 24:
            return 0x70 + int(normalized[1:]) - 1
        raise ValueError(f"Unsupported key: {key}")

    def press_key(self, key: str) -> dict[str, Any]:
        user32 = self._user32()
        vk = self._virtual_key(key)
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 0x0002, 0)
        return {"key": key}

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        if not keys:
            raise ValueError("At least one key is required for a hotkey.")
        user32 = self._user32()
        virtual_keys = [self._virtual_key(key) for key in keys]
        for vk in virtual_keys:
            user32.keybd_event(vk, 0, 0, 0)
        for vk in reversed(virtual_keys):
            user32.keybd_event(vk, 0, 0x0002, 0)
        return {"keys": keys}

    def type_text(self, text: str) -> dict[str, Any]:
        user32 = self._user32()
        for character in text:
            codepoints = character.encode("utf-16-le", errors="surrogatepass")
            for offset in range(0, len(codepoints), 2):
                unit = int.from_bytes(codepoints[offset:offset + 2], "little")
                user32.keybd_event(0, unit, 0x0004, 0)
                user32.keybd_event(0, unit, 0x0004 | 0x0002, 0)
        return {"characters_typed": len(text)}

    def focus_window(self, title: str) -> dict[str, Any]:
        user32 = self._user32()
        hwnd = self._find_window(title)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        if not user32.SetForegroundWindow(hwnd):
            raise OSError("Windows refused to focus the requested window.")
        return {"handle": hwnd, "title": title}

    def set_window_bounds(self, title: str, x: int, y: int, width: int, height: int) -> dict[str, Any]:
        if width <= 0 or height <= 0:
            raise ValueError("Window width and height must be positive.")
        user32 = self._user32()
        hwnd = self._find_window(title)
        if not user32.SetWindowPos(hwnd, 0, x, y, width, height, 0x0004 | 0x0010):
            raise OSError("Windows could not change the window bounds.")
        return {"handle": hwnd, "x": x, "y": y, "width": width, "height": height}

    def close_window(self, title: str) -> dict[str, Any]:
        hwnd = self._find_window(title)
        if not self._user32().PostMessageW(hwnd, 0x0010, 0, 0):  # WM_CLOSE
            raise OSError("Windows could not close the requested window.")
        return {"handle": hwnd, "title": title}

    def take_screenshot(self, path: str) -> dict[str, Any]:
        user32 = self._user32()
        gdi32 = ctypes.windll.gdi32
        handle = ctypes.c_void_p
        user32.GetDC.argtypes = [ctypes.wintypes.HWND]
        user32.GetDC.restype = handle
        user32.ReleaseDC.argtypes = [ctypes.wintypes.HWND, handle]
        user32.ReleaseDC.restype = ctypes.c_int
        gdi32.CreateCompatibleDC.argtypes = [handle]
        gdi32.CreateCompatibleDC.restype = handle
        gdi32.CreateCompatibleBitmap.argtypes = [handle, ctypes.c_int, ctypes.c_int]
        gdi32.CreateCompatibleBitmap.restype = handle
        gdi32.SelectObject.argtypes = [handle, handle]
        gdi32.SelectObject.restype = handle
        gdi32.BitBlt.argtypes = [handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 handle, ctypes.c_int, ctypes.c_int, ctypes.wintypes.DWORD]
        gdi32.BitBlt.restype = ctypes.wintypes.BOOL
        gdi32.GetDIBits.argtypes = [handle, handle, ctypes.wintypes.UINT, ctypes.wintypes.UINT,
                                    ctypes.c_void_p, ctypes.POINTER(_BitmapInfo), ctypes.wintypes.UINT]
        gdi32.GetDIBits.restype = ctypes.c_int
        gdi32.DeleteObject.argtypes = [handle]
        gdi32.DeleteObject.restype = ctypes.wintypes.BOOL
        gdi32.DeleteDC.argtypes = [handle]
        gdi32.DeleteDC.restype = ctypes.wintypes.BOOL
        width, height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        if width <= 0 or height <= 0:
            raise OSError("No desktop screen is available.")
        target = Path(path).expanduser()
        if target.suffix.lower() != ".png":
            raise ValueError("Screenshot output path must end in .png.")
        target.parent.mkdir(parents=True, exist_ok=True)
        source_dc = user32.GetDC(None)
        if not source_dc:
            raise OSError("Could not access the desktop drawing surface.")
        memory_dc = gdi32.CreateCompatibleDC(source_dc)
        if not memory_dc:
            user32.ReleaseDC(None, source_dc)
            raise OSError("Could not create a compatible desktop drawing surface.")
        bitmap = gdi32.CreateCompatibleBitmap(source_dc, width, height)
        if not bitmap:
            gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(None, source_dc)
            raise OSError("Could not allocate a screenshot bitmap.")
        previous = gdi32.SelectObject(memory_dc, bitmap)
        try:
            if not previous:
                raise OSError("Could not select the screenshot bitmap.")
            if not gdi32.BitBlt(memory_dc, 0, 0, width, height, source_dc, 0, 0, 0x00CC0020):
                raise OSError("Windows could not capture the desktop pixels.")
            info = _BitmapInfo()
            info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
            info.bmiHeader.biWidth = width
            info.bmiHeader.biHeight = -height  # top-down rows
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            info.bmiHeader.biCompression = 0  # BI_RGB
            pixels = (ctypes.c_ubyte * (width * height * 4))()
            gdi32.SelectObject(memory_dc, previous)
            previous = None
            copied = gdi32.GetDIBits(memory_dc, bitmap, 0, height, ctypes.cast(pixels, ctypes.c_void_p), ctypes.byref(info), 0)
            if copied != height:
                raise OSError("Windows returned an incomplete screen capture.")
            from PySide6.QtGui import QImage
            image = QImage(bytes(pixels), width, height, width * 4, QImage.Format.Format_RGB32)
            if image.isNull() or not image.save(str(target), "PNG"):
                raise OSError(f"Could not save screenshot to {target}.")
        finally:
            if previous:
                gdi32.SelectObject(memory_dc, previous)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(None, source_dc)
        return {"path": str(target.resolve()), "format": "png"}


class WindowsDesktopController:
    """Desktop actions used by registered Jarvis tools."""

    def __init__(self, api: WindowsDesktopAPI | Any | None = None) -> None:
        self.api = api or WindowsDesktopAPI()

    def take_screenshot(self, path: str) -> dict[str, Any]:
        return {"success": True, **self.api.take_screenshot(path)}

    def move_mouse(self, x: int, y: int) -> dict[str, Any]:
        return {"success": True, **self.api.move_mouse(x, y)}

    def click(self, x: int, y: int, button: str = "left") -> dict[str, Any]:
        return {"success": True, **self.api.click(x, y, button)}

    def double_click(self, x: int, y: int) -> dict[str, Any]:
        return {"success": True, **self.api.click(x, y, "left", 2)}

    def right_click(self, x: int, y: int) -> dict[str, Any]:
        return {"success": True, **self.api.click(x, y, "right")}

    def type_text(self, text: str) -> dict[str, Any]:
        return {"success": True, **self.api.type_text(text)}

    def press_key(self, key: str) -> dict[str, Any]:
        return {"success": True, **self.api.press_key(key)}

    def hotkey(self, keys: str) -> dict[str, Any]:
        return {"success": True, **self.api.hotkey([key.strip() for key in keys.split("+") if key.strip()])}

    def get_windows(self) -> dict[str, Any]:
        return {"success": True, "windows": self.api.get_windows()}

    def focus_window(self, title: str) -> dict[str, Any]:
        return {"success": True, **self.api.focus_window(title)}

    def move_window(self, title: str, x: int, y: int) -> dict[str, Any]:
        windows = self.api.get_windows()
        matches = [window for window in windows if title.casefold() in window["title"].casefold()]
        if len(matches) != 1:
            raise ValueError("Window title did not match exactly one visible window.")
        window = matches[0]
        result = self.api.set_window_bounds(title, x, y, window["width"], window["height"])
        return {"success": True, **result}

    def resize_window(self, title: str, width: int, height: int) -> dict[str, Any]:
        windows = self.api.get_windows()
        matches = [window for window in windows if title.casefold() in window["title"].casefold()]
        if len(matches) != 1:
            raise ValueError("Window title did not match exactly one visible window.")
        window = matches[0]
        result = self.api.set_window_bounds(title, window["x"], window["y"], width, height)
        return {"success": True, **result}

    def close_application(self, title: str) -> dict[str, Any]:
        return {"success": True, **self.api.close_window(title)}
