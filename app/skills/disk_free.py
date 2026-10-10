"""Example self-describing skill: report free disk space.

This file participates in Jarvis's auto-discovery: the module-level ``TOOL``
dict tells the registry everything it needs to expose ``disk_free``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

TOOL = {
    "name": "disk_free",
    "description": "Report the free and total space on the drive holding a directory.",
    "permission_level": "safe",
    "parameters": {"path": "directory path (defaults to the current working directory)"},
}


def handler(path: str = "") -> dict:
    directory = Path(path) if path else Path.cwd()
    usage = shutil.disk_usage(directory)
    return {
        "ok": True,
        "success": True,
        "path": str(directory),
        "free_bytes": usage.free,
        "total_bytes": usage.total,
        "free_gib": round(usage.free / (1024 ** 3), 2),
    }