"""ErrorDetailDialog — shows failed agent prompt, output, and error in collapsible sections."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class CollapsibleSection(QWidget):
    """Toggle-able section with a header button and content widget."""

    def __init__(self, title: str, content: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expanded = False
        self._title = title
        self._content = content
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._toggle_btn = QPushButton(f"\u25b8 {self._title}")
        self._toggle_btn.setStyleSheet(
            "QPushButton { text-align: left; border: none; padding: 4px 8px; "
            "background: #333; color: #ccc; font-size: 12px; }"
            "QPushButton:hover { background: #444; }"
        )
        self._toggle_btn.clicked.connect(self._toggle)
        layout.addWidget(self._toggle_btn)

        self._content_widget = QTextEdit()
        self._content_widget.setReadOnly(True)
        self._content_widget.setPlainText(self._content)
        self._content_widget.setStyleSheet(
            "QTextEdit { background: #1e1e1e; color: #ddd; border: 1px solid #444; "
            "font-family: 'Consolas', monospace; font-size: 11px; }"
        )
        self._content_widget.setMinimumHeight(80)
        self._content_widget.setMaximumHeight(300)
        self._content_widget.hide()
        layout.addWidget(self._content_widget)

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        if self._expanded:
            self._content_widget.show()
            self._toggle_btn.setText(f"\u25be {self._title}")
        else:
            self._content_widget.hide()
            self._toggle_btn.setText(f"\u25b8 {self._title}")


class ErrorDetailDialog(QDialog):
    """Modal dialog showing the full error context for a failed agent call."""

    def __init__(
        self,
        agent_name: str,
        error_message: str,
        prompt: str,
        output: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Agent Error \u2014 {agent_name}")
        self.resize(700, 500)
        self._setup_ui(agent_name, error_message, prompt, output)

    def _setup_ui(
        self, agent_name: str, error_message: str, prompt: str, output: str
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QLabel(f"<b>{agent_name}</b> <span style='color:#e74c3c;'>failed</span>")
        layout.addWidget(header)

        err_label = QLabel(f"<span style='color:#e74c3c;'>{error_message}</span>")
        err_label.setWordWrap(True)
        err_label.setStyleSheet("font-size: 12px; padding: 4px 0;")
        layout.addWidget(err_label)

        sep = QLabel("")
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #444;")
        layout.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(6)

        if prompt:
            scroll_layout.addWidget(CollapsibleSection("Sent Prompt", prompt))
        if output:
            scroll_layout.addWidget(CollapsibleSection("Received Output", output))

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "QPushButton { padding: 6px 20px; background: #555; color: #eee; "
            "border: 1px solid #777; border-radius: 3px; }"
            "QPushButton:hover { background: #666; }"
        )
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
