"""One shared undo stack for every Jarvis action that changes state.

Design adapted from Mark-LV's ``core/undo.py`` (CC BY-NC 4.0; see README
"Credits and licensing"): acting immediately is better than asking "are you
sure?" before everything, and the remedy for a misunderstood action is a
reliable *reverse*. Confirmation stays reserved for actions that genuinely
cannot be reversed.

Each tool captures its "before" state and hands back a zero-argument callable:
only the tool itself knows that the reverse of "move A to B" is "move B to A".
What is central here is the stack, its ordering, thread safety, and the
``undo`` tool the model calls when the user asks.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("jarvis.undo")


@dataclass
class UndoEntry:
    label: str
    undo: Callable[[], Any]


class UndoManager:
    """A thread-safe LIFO stack of reversible actions for a Jarvis session."""

    def __init__(self, max_entries: int = 100) -> None:
        self._stack: list[UndoEntry] = []
        self._lock = threading.Lock()
        self._max_entries = max(1, max_entries)

    def push(self, label: str, undo: Callable[[], Any]) -> None:
        if not label or not callable(undo):
            logger.warning("undo push rejected: label=%r callable=%s", label, callable(undo))
            return
        with self._lock:
            self._stack.append(UndoEntry(label, undo))
            while len(self._stack) > self._max_entries:
                self._stack.pop(0)

    def pop(self) -> UndoEntry | None:
        with self._lock:
            if not self._stack:
                return None
            return self._stack.pop()

    def peek_label(self) -> str | None:
        with self._lock:
            return self._stack[-1].label if self._stack else None

    def count(self) -> int:
        with self._lock:
            return len(self._stack)

    def clear(self) -> None:
        with self._lock:
            self._stack.clear()