"""AgentTracePanel — shows pipeline agent status, duration, and token counts."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class AgentTracePanel(QWidget):
    """Collapsible panel showing live agent execution trace.

    Each agent step is displayed as a row with status icon, name,
    duration, and token count. In v1 (Issue #7) only the Writer
    agent is shown.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[dict] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        header = QLabel("<b>Agent Trace</b>")
        layout.addWidget(header)

        self._token_label = QLabel("Tokens: —")
        self._token_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._token_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Entries container
        self._entries_layout = QVBoxLayout()
        layout.addLayout(self._entries_layout)
        layout.addStretch()

        self._empty_label = QLabel("等待生成...")
        self._empty_label.setStyleSheet("color: #666; font-size: 12px;")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._entries_layout.addWidget(self._empty_label)

    def clear(self) -> None:
        """Remove all trace entries."""
        while self._entries_layout.count():
            item = self._entries_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._entries_layout.addWidget(self._empty_label)
        self._token_label.setText("Tokens: —")
        self._entries.clear()

    def set_running(self, agent_name: str = "Writer") -> None:
        """Show an agent as running."""
        self.clear()
        self._add_entry(agent_name, "running")
        self._token_label.setText("Tokens: —")

    def set_completed(self, agent_name: str, duration_ms: int, token_count: int) -> None:
        """Show the agent as completed with stats."""
        self.clear()
        self._add_entry(agent_name, "completed", duration_ms, token_count)
        self._token_label.setText(f"Tokens: {token_count}")

    def set_failed(self, agent_name: str, error: str = "Generation failed") -> None:
        """Show the agent as failed with error message."""
        self.clear()
        self._add_entry(agent_name, "failed")
        err_label = QLabel(f"错误: {error}")
        err_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        err_label.setWordWrap(True)
        self._entries_layout.addWidget(err_label)
        self._token_label.setText("Tokens: —")

    def _add_entry(
        self,
        agent_name: str,
        status: str,
        duration_ms: int = 0,
        token_count: int = 0,
    ) -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 2, 4, 2)

        # Status icon
        icon_map = {
            "running": ("⏳", "#f39c12"),
            "completed": ("✓", "#27ae60"),
            "failed": ("✗", "#e74c3c"),
        }
        icon, color = icon_map.get(status, ("?", "#888"))
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"color: {color}; font-size: 14px;")
        row_layout.addWidget(icon_label)

        # Agent name
        name_label = QLabel(agent_name)
        name_label.setStyleSheet("font-weight: bold; color: #ddd;")
        row_layout.addWidget(name_label)

        row_layout.addStretch()

        # Duration
        if duration_ms > 0:
            dur_text = f"{duration_ms}ms" if duration_ms < 1000 else f"{duration_ms/1000:.1f}s"
            dur_label = QLabel(dur_text)
            dur_label.setStyleSheet("color: #888; font-size: 11px;")
            row_layout.addWidget(dur_label)

        # Token count
        if token_count > 0:
            tok_label = QLabel(f"{token_count} tokens")
            tok_label.setStyleSheet("color: #888; font-size: 11px;")
            row_layout.addWidget(tok_label)

        self._entries_layout.insertWidget(self._entries_layout.count() - 1, row)
