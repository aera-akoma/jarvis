"""Example self-describing skill: report how long the machine has been up.

Uses ctypes + GetTickCount64 so no third-party dependency is needed.
"""

from __future__ import annotations

import ctypes
from typing import Any

TOOL = {
    "name": "uptime",
    "description": "Report how long this Windows machine has been running (days, hours, minutes).",
    "permission_level": "safe",
    "parameters": {},
}


def _ticks_ms() -> int:
    kernel32 = ctypes.windll.kernel32
    get_ticks = kernel32.GetTickCount64
    get_ticks.restype = ctypes.c_ulonglong
    return int(get_ticks())


def handler() -> dict[str, Any]:
    seconds = _ticks_ms() // 1000
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return {
        "ok": True,
        "success": True,
        "uptime_seconds": seconds,
        "uptime": f"{days} days, {hours} hours, {minutes} minutes",
    }