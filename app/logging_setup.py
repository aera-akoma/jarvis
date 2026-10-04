from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable


def configure_logging(log_dir: Path) -> Path:
    """Configure bounded local logs without recording prompts or credentials."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "jarvis.log"
    handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=4, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)
    return log_path


def install_exception_logging(log_path: Path, notify: Callable[[str], None] | None = None) -> None:
    """Record uncaught Python exceptions and optionally show a safe user message."""
    logger = logging.getLogger("jarvis.crash")

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        frames = "".join(traceback.format_tb(exc_traceback))
        logger.critical("Uncaught application exception (%s)\n%s", exc_type.__name__, frames)
        if notify:
            notify(f"Jarvis encountered an unexpected error. Details were saved to:\n{log_path}")

    sys.excepthook = handle_exception
