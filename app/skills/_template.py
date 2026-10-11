"""Template for a self-describing Jarvis skill.

Copy this file to ``app/skills/<your_skill>.py`` (drop the leading underscore so
discovery picks it up), then fill in ``TOOL`` and implement ``handler``.

A skill is a plain module. Jarvis imports every ``*.py`` in ``app/skills/`` that
does not start with ``_``, reads its module-level ``TOOL`` dict, and registers it
as a tool. Files that start with ``_`` (like this template) are ignored, so it is
safe to keep around.

Field reference
---------------
name             Lowercase identifier (``^[a-z][a-z0-9_]*$``). Must not collide
                 with a built-in tool name.
description      One line shown to the model so it knows when to call the skill.
permission_level ``"safe"`` (no confirmation), ``"moderate"`` or ``"dangerous"``
                 (Jarvis asks the user to approve before running).
parameters       Mapping of argument name -> human-readable description. These
                 become the tool's JSON-schema properties.
handler          Module-level callable implementing the skill. It receives the
                 declared parameters as keyword arguments and should return a
                 ``dict``. Conventionally include ``"ok": True`` (and/or
                 ``"success": True``) on success and ``"ok": False`` with an
                 ``"error"`` string on failure.

You can also put a ``"handler"`` key directly inside ``TOOL`` instead of using a
module-level ``handler`` function; either works.

Example
-------
::

    TOOL = {
        "name": "hello",
        "description": "Say hello to someone.",
        "permission_level": "safe",
        "parameters": {"name": "who to greet"},
    }

    def handler(name: str = "world") -> dict:
        return {"ok": True, "message": f"Hello, {name}!"}
"""

from __future__ import annotations

from typing import Any


TOOL = {
    "name": "hello",
    "description": "Example skill: say hello to someone.",
    "permission_level": "safe",
    "parameters": {"name": "who to greet (defaults to \"world\")"},
}


def handler(name: str = "world") -> dict[str, Any]:
    """Implement your skill here. Return a JSON-serializable dict."""
    return {"ok": True, "message": f"Hello, {name}!"}
