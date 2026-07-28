"""New-project entry, including the development-only Quick Creation route."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

GENRES = ["玄幻", "都市", "科幻", "历史", "无限流"]
PROVIDERS = ["ollama", "deepseek"]


class CreateProjectDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        default_storage_dir: Path | None = None,
        quick_creation_enabled: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("创建新项目")
        self.setMinimumWidth(400)
        self._default_storage_dir = default_storage_dir or (Path.home() / "NovelForge")
        self._result: dict[str, str] | None = None
        self._layout = QVBoxLayout(self)
        if quick_creation_enabled:
            self._build_choice()
        else:
            self._build_setup("blank")

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _build_choice(self) -> None:
        self._clear()
        self._layout.addWidget(QLabel("你想怎样开始？"))
        self.quick_button = QPushButton("快速构思故事\n选择几个方向，让 AI 帮你构思和规划")
        self.quick_button.setStyleSheet("font-size: 16px; font-weight: bold; padding: 22px;")
        self.quick_button.clicked.connect(lambda: self._build_setup("quick"))
        self._layout.addWidget(self.quick_button)
        self.blank_button = QPushButton("创建空白项目\n直接进入深度创作")
        self.blank_button.clicked.connect(lambda: self._build_setup("blank"))
        self._layout.addWidget(self.blank_button)

    def _build_setup(self, mode: str) -> None:
        self._clear()
        self._mode = mode
        self._layout.addWidget(QLabel("快速构思故事" if mode == "quick" else "创建新项目"))
        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("工作标题（可选）" if mode == "quick" else "输入小说标题")
        form.addRow("标题:", self.title_edit)
        if mode == "blank":
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
        self._layout.addLayout(form)
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        self._layout.addWidget(self.button_box)

    def _validate_and_accept(self) -> None:
        title = self.title_edit.text().strip()
        if self._mode == "blank" and not title:
            self.title_edit.setFocus()
            self.title_edit.setStyleSheet("border: 1px solid red;")
            return
        storage_dir = self.storage_dir_edit.text().strip()
        if not storage_dir:
            self.storage_dir_edit.setFocus()
            self.storage_dir_edit.setStyleSheet("border: 1px solid red;")
            return
        self._result = {"title": title, "storage_dir": storage_dir, "creation_mode": self._mode}
        if self._mode == "blank":
            self._result.update(
                genre=self.genre_combo.currentText(), llm_provider=self.provider_combo.currentText()
            )
        self.accept()

    def get_result(self) -> dict[str, str] | None:
        return self._result

    def _browse_storage_dir(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择项目存储位置", self.storage_dir_edit.text().strip()
        )
        if dir_path:
            self.storage_dir_edit.setText(dir_path)
