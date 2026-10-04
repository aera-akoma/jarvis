from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTextEdit,
    QVBoxLayout, QWidget,
)

from app.memory.memory_manager import MEMORY_CATEGORIES, MemoryManager


class MemoryEditDialog(QDialog):
    def __init__(self, memory: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit memory" if memory else "Add memory")
        layout = QFormLayout(self)
        self.category = QComboBox()
        self.category.addItems(MEMORY_CATEGORIES)
        self.content = QTextEdit()
        self.content.setMaximumHeight(120)
        self.importance = QLineEdit(str(memory.get("importance", 0.5) if memory else 0.5))
        self.confidence = QLineEdit(str(memory.get("confidence", 0.8) if memory else 0.8))
        if memory:
            self.category.setCurrentText(memory["category"])
            self.content.setPlainText(memory["content"])
        layout.addRow("Category", self.category)
        layout.addRow("Content", self.content)
        layout.addRow("Importance (0–1)", self.importance)
        layout.addRow("Confidence (0–1)", self.confidence)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict:
        return {"category": self.category.currentText(), "content": self.content.toPlainText(),
                "importance": float(self.importance.text()), "confidence": float(self.confidence.text())}


class MemoryView(QDialog):
    def __init__(self, memory_manager: MemoryManager | None = None) -> None:
        super().__init__()
        self.memory_manager = memory_manager or MemoryManager()
        self.setWindowTitle("Jarvis Memory")
        self.resize(680, 500)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Jarvis stores only approved durable memories. Review, edit, or delete them here."))
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search memory…")
        self.search_input.textChanged.connect(self.refresh)
        search_row.addWidget(self.search_input, 1)
        add_button = QPushButton("Add memory")
        add_button.clicked.connect(self.add_memory)
        search_row.addWidget(add_button)
        layout.addLayout(search_row)
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.edit_memory())
        layout.addWidget(self.list_widget, 1)
        actions = QHBoxLayout()
        self.metadata_label = QLabel("")
        actions.addWidget(self.metadata_label, 1)
        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(self.edit_memory)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.delete_memory)
        actions.addWidget(edit_button)
        actions.addWidget(delete_button)
        layout.addLayout(actions)

    def refresh(self, *_args) -> None:
        self.list_widget.clear()
        term = self.search_input.text().strip()
        memories = self.memory_manager.search(term) if term else self.memory_manager.list_memories()
        for memory in memories:
            item = QListWidgetItem(f"[{memory['category']}] {memory['content']}")
            item.setData(256, memory)
            self.list_widget.addItem(item)
        self.metadata_label.setText(f"{len(memories)} memories")

    def add_memory(self) -> None:
        dialog = MemoryEditDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.memory_manager.add_memory(**dialog.values(), source="added in Memory settings")
                self.refresh()
            except (ValueError, TypeError) as exc:
                QMessageBox.warning(self, "Could not save memory", str(exc))

    def _selected(self) -> dict | None:
        item = self.list_widget.currentItem()
        return item.data(256) if item else None

    def edit_memory(self) -> None:
        memory = self._selected()
        if not memory:
            return
        dialog = MemoryEditDialog(memory, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.memory_manager.update_memory(memory["id"], **dialog.values(), source="edited in Memory settings")
                self.refresh()
            except (ValueError, TypeError) as exc:
                QMessageBox.warning(self, "Could not update memory", str(exc))

    def delete_memory(self) -> None:
        memory = self._selected()
        if not memory:
            return
        answer = QMessageBox.question(self, "Delete memory", f"Delete this memory?\n\n{memory['content']}",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.memory_manager.delete_memory(memory["id"])
            self.refresh()
