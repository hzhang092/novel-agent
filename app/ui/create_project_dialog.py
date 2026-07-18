"""Create Project dialog — collects title, genre, LLM provider, and storage location."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

GENRES = ["玄幻", "都市", "科幻", "历史", "无限流"]
PROVIDERS = ["ollama", "deepseek"]


class CreateProjectDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        default_storage_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("创建新项目")
        self.setMinimumWidth(400)
        self._default_storage_dir = default_storage_dir or (Path.home() / "NovelForge")

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

        storage_row = QWidget()
        storage_layout = QHBoxLayout(storage_row)
        storage_layout.setContentsMargins(0, 0, 0, 0)
        self.storage_dir_edit = QLineEdit(str(self._default_storage_dir))
        browse_button = QPushButton("浏览...")
        browse_button.clicked.connect(self._browse_storage_dir)
        storage_layout.addWidget(self.storage_dir_edit, 1)
        storage_layout.addWidget(browse_button)
        form.addRow("存储位置:", storage_row)

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
        storage_dir = self.storage_dir_edit.text().strip()
        if not storage_dir:
            self.storage_dir_edit.setFocus()
            self.storage_dir_edit.setStyleSheet("border: 1px solid red;")
            return
        self._result = {
            "title": title,
            "genre": self.genre_combo.currentText(),
            "llm_provider": self.provider_combo.currentText(),
            "storage_dir": storage_dir,
        }
        self.accept()

    def get_result(self) -> dict[str, str] | None:
        return self._result

    def _browse_storage_dir(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择项目存储位置", self.storage_dir_edit.text().strip()
        )
        if dir_path:
            self.storage_dir_edit.setText(dir_path)
