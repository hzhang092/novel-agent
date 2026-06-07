"""Create Project dialog — collects title, genre, and LLM provider."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

GENRES = ["玄幻", "都市", "科幻", "历史", "无限流"]
PROVIDERS = ["ollama", "deepseek"]


class CreateProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("创建新项目")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        header = QLabel("创建新项目")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(12)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("输入小说标题")
        form.addRow("标题:", self.title_edit)

        self.genre_combo = QComboBox()
        self.genre_combo.addItems(GENRES)
        form.addRow("类型:", self.genre_combo)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(PROVIDERS)
        form.addRow("LLM 服务:", self.provider_combo)

        layout.addLayout(form)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self._result: dict[str, str] | None = None

    def _validate_and_accept(self) -> None:
        title = self.title_edit.text().strip()
        if not title:
            self.title_edit.setFocus()
            self.title_edit.setStyleSheet("border: 1px solid red;")
            return
        self._result = {
            "title": title,
            "genre": self.genre_combo.currentText(),
            "llm_provider": self.provider_combo.currentText(),
        }
        self.accept()

    def get_result(self) -> dict[str, str] | None:
        return self._result
