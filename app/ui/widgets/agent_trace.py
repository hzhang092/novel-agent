"""AgentTracePanel — tree view showing live pipeline agent execution trace.

Displays Planner → Character Intents (expandable children) → Writer → Reviewer
as a collapsible tree. Each node shows status icon, name, duration, token count.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


# Status icons
ICONS = {
    "pending": ("○", "#888"),
    "running": ("⏳", "#f39c12"),
    "completed": ("✓", "#27ae60"),
    "failed": ("✗", "#e74c3c"),
}


class AgentTracePanel(QWidget):
    """Collapsible tree panel showing live agent execution trace.

    Emits ``retry_requested`` when a user clicks the retry button on a failed agent.
    """

    retry_requested = Signal(str)  # emits agent_name

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header with token breakdown
        header_layout = QHBoxLayout()
        header = QLabel("<b>Agent Trace</b>")
        header_layout.addWidget(header)
        header_layout.addStretch()
        self._token_label = QLabel("Tokens: —")
        self._token_label.setStyleSheet("color: #888; font-size: 11px;")
        header_layout.addWidget(self._token_label)
        layout.addLayout(header_layout)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(20)
        self._tree.setAnimated(True)
        self._tree.setStyleSheet(
            "QTreeWidget { border: none; background: transparent; }"
            "QTreeWidget::item { padding: 2px 0; }"
        )
        layout.addWidget(self._tree)

        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.setVisible(False)
        self._empty_label = QLabel("等待生成...")
        self._empty_label.setStyleSheet("color: #666; font-size: 12px;")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

    def clear(self) -> None:
        """Remove all trace entries."""
        self._tree.clear()
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.setVisible(False)
        self._empty_label.setVisible(True)
        self._token_label.setText("Tokens: —")

    def update_trace(self, trace: list) -> None:
        """Rebuild the tree from the current trace list.

        Args:
            trace: List of AgentTraceEntry dataclass instances.
        """
        self._tree.clear()
        self._tree.setVisible(True)
        self._empty_label.setVisible(False)

        total_tokens = 0
        for entry in trace:
            total_tokens += self._add_tree_node(None, entry)

        self._token_label.setText(f"Tokens: {total_tokens if total_tokens else '—'}")
        self._tree.expandAll()

    def set_waiting(self, message: str) -> None:
        """Show a waiting state with a message."""
        self._tree.clear()
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.setVisible(False)
        self._empty_label.setVisible(True)
        self._token_label.setText(message)

    def _add_tree_node(
        self, parent: QTreeWidgetItem | None, entry
    ) -> int:
        """Add a trace entry as a tree node. Returns token count."""
        icon, _color = ICONS.get(entry.status, ("?", "#888"))
        display_name = entry.agent_name

        # Duration
        dur_str = ""
        if entry.duration_ms > 0:
            dur_str = (
                f"{entry.duration_ms}ms"
                if entry.duration_ms < 1000
                else f"{entry.duration_ms / 1000:.1f}s"
            )

        # Token count
        tok_str = f"{entry.token_count} tk" if entry.token_count > 0 else ""

        # Build display text
        parts = [f"{icon} {display_name}"]
        if dur_str:
            parts.append(dur_str)
        if tok_str:
            parts.append(tok_str)
        label = "  ".join(parts)

        actual_parent = self._tree if parent is None else parent
        item = QTreeWidgetItem(actual_parent)
        item.setText(0, label)
        item.setData(0, Qt.ItemDataRole.UserRole, entry.agent_name)
        item.setExpanded(True)

        # Tooltip for failed agents
        if entry.status == "failed":
            item.setToolTip(0, entry.error_message or "Unknown error")
            item.setData(0, Qt.ItemDataRole.UserRole + 1, {
                "agent_name": entry.agent_name,
                "error_message": entry.error_message,
                "failed_prompt": getattr(entry, "failed_prompt", ""),
                "failed_output": getattr(entry, "failed_output", ""),
            })

        tokens = entry.token_count
        for child in entry.children:
            tokens += self._add_tree_node(item, child)

        return tokens

    def _on_item_clicked(self, item, column: int) -> None:
        """Open error detail dialog when a failed agent node is clicked."""
        error_data = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if error_data is None:
            return
        from app.ui.widgets.error_detail import ErrorDetailDialog
        dialog = ErrorDetailDialog(
            agent_name=error_data.get("agent_name", ""),
            error_message=error_data.get("error_message", ""),
            prompt=error_data.get("failed_prompt", ""),
            output=error_data.get("failed_output", ""),
            parent=self,
        )
        dialog.exec()

    def _on_context_menu(self, pos) -> None:
        """Show retry context menu for failed agent nodes."""
        item = self._tree.itemAt(pos)
        if item is None:
            return
        error_data = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if error_data is None:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        retry_action = menu.addAction("Retry this step")
        action = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if action == retry_action:
            self.retry_requested.emit(error_data.get("agent_name", ""))
