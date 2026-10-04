from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.db import DatabaseManager
from app.ui.main_window import MainWindow


def main() -> int:
    if os.name == "nt":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QApplication(sys.argv)
    app.setApplicationName("Jarvis")

    config = AppConfig()
    DatabaseManager(config)
    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
