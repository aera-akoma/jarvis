"""Self-describing skills: any ``*.py`` module in ``app/skills/`` that exposes a
module-level ``TOOL`` description is discovered and registered as a Jarvis tool.

Design adapted from Mark-LV's ``core/action_loader.py`` + ``plugins/`` layout
(CC BY-NC 4.0; see README "Credits and licensing"): a skill is a plain module
that describes itself instead of being wired into the registry by hand.

A valid skill module looks like::

    TOOL = {
        "name": "disk_free",
        "description": "Report free space on the drive holding a directory.",
        "permission_level": "safe",
        "parameters": {"path": "directory path"},
    }

    def handler(path: str) -> dict:
        ...

The ``handler`` key is taken from the ``TOOL`` dict itself (Mark-LV renames it
at load time); if the dict omits it, a module-level callable named ``handler``
is used as a fallback.
"""

from __future__ import annotations

import importlib.util
import logging
import re
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.skills")

SKILLS_DIR = Path(__file__).resolve().parent / "skills"

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ALLOWED_LEVELS = {"safe", "moderate", "dangerous"}


def _tool_from_module(module: Any, source: str) -> ToolDefinition | None:
    from app.tooling import ToolDefinition

    spec = getattr(module, "TOOL", None)
    if not isinstance(spec, dict):
        logger.warning("skill %s has no TOOL dict and was skipped", source)
        return None
    name = str(spec.get("name") or "").strip()
    if not _NAME_RE.match(name):
        logger.warning("skill %s has an invalid tool name %r and was skipped", source, name)
        return None
    description = str(spec.get("description") or "").strip()
    if not description:
        logger.warning("skill %s has no description and was skipped", source)
        return None
    level = str(spec.get("permission_level") or "safe").strip()
    if level not in _ALLOWED_LEVELS:
        logger.warning("skill %s uses unknown permission level %r and was skipped", source, level)
        return None
    parameters = spec.get("parameters") or {}
    if not isinstance(parameters, dict):
        parameters = {}
    parameters = {str(k): str(v) for k, v in parameters.items()}
    handler = spec.get("handler")
    if not callable(handler):
        handler = getattr(module, "handler", None)
    if not callable(handler):
        logger.warning("skill %s declares no handler and was skipped", source)
        return None
    return ToolDefinition(name, description, level, parameters, handler)


def discover_skills(directory: Path | None = None) -> list[ToolDefinition]:
    """Import every ``*.py`` under *directory* (default ``app/skills``) and build
    the tools its ``TOOL`` dicts describe. Invalid or unloadable modules are
    logged and skipped rather than failing startup."""
    directory = directory or SKILLS_DIR
    if not directory.is_dir():
        return []
    from app.tooling import ToolDefinition

    tools: list[ToolDefinition] = []
    for module_path in sorted(directory.glob("*.py")):
        if module_path.name.startswith("_"):
            continue
        module_name = f"jarvis_skill_{module_path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                logger.warning("skill %s could not be loaded and was skipped", module_path.name)
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception:  # noqa: BLE001 - a broken skill must not break startup
            logger.warning("skill %s failed to load and was skipped", module_path.name, exc_info=True)
            continue
        tool = _tool_from_module(module, module_path.name)
        if tool is not None:
            tools.append(tool)
    return tools