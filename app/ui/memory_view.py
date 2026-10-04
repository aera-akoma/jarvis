from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.memory.memory_manager import MemoryManager


class MemoryView(QDialog):
    def __init__(self, memory_manager: MemoryManager | None = None) -> None:
        super().__init__()
        self.memory_manager = memory_manager or MemoryManager()
        self.setWindowTitle("Jarvis Memory")
        self.resize(600, 400)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        info = QLabel("Personal memory is stored locally and can be searched and reviewed here.")
        layout.addWidget(info)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        buttons = QHBoxLayout()
        self.search_label = QLabel("Search")
        buttons.addWidget(self.search_label)
        self.search_input = QWidget()
        layout.addLayout(buttons)

    def refresh(self) -> None:
        self.list_widget.clear()
        for memory in self.memory_manager.list_memories():
            item = QListWidgetItem(f"[{memory['category']}] {memory['content']}")
            self.list_widget.addItem(item)
