"""Writing Workspace — hosts Context Preview panel and scene generation area."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.ui.context_preview import ContextPreviewView


class SceneWorkspaceView(QWidget):
    """Writing workspace with Context Preview panel.

    Emits ``enter_pressed`` when Enter key is pressed, for downstream
    pipeline triggering (wired in later issues).
    """

    enter_pressed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Placeholder header (shown when no scene is selected)
        self._header = QLabel("选择大纲中的场景以查看上下文预览")
        self._header.setStyleSheet("color: #888; font-size: 13px;")
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._header)

        # Context Preview panel (hidden until context is set)
        self.context_preview = ContextPreviewView()
        layout.addWidget(self.context_preview)

        layout.addStretch()

    def load_project_dir(self, project_dir: Path) -> None:
        """Store project directory reference for context assembly."""
        self._project_dir = project_dir

    def show_context(self, context: dict) -> None:
        """Display assembled context in the preview panel."""
        self.context_preview.set_context(context)
        self._header.hide()

    def clear_context(self) -> None:
        """Clear the preview and show the placeholder header."""
        self.context_preview.clear()
        self._header.show()

    def keyPressEvent(self, event) -> None:
        """Capture Enter key for pipeline trigger."""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.enter_pressed.emit()
            return
        super().keyPressEvent(event)
