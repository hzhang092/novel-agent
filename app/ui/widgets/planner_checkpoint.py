"""PlannerCheckpointWidget — inline panel showing the Planner's scene plan with Approve/Regenerate."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PlannerCheckpointWidget(QWidget):
    """Inline panel embedded in the Writing Workspace during planner checkpoint.

    Shows the structured plan (beats, conflict, emotional arc, hook) and
    provides Approve / Regenerate buttons.
    """

    approved = pyqtSignal()
    rejected = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plan: dict | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QLabel("<b>场景规划审查</b>")
        header.setStyleSheet("font-size: 14px; color: #f39c12;")
        layout.addWidget(header)

        desc = QLabel("检查 Planner 生成的场景规划。确认无误后批准继续，或拒绝以重新生成。")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(desc)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Plan content (scrollable)
        self._content_label = QLabel()
        self._content_label.setWordWrap(True)
        self._content_label.setTextFormat(Qt.TextFormat.RichText)
        self._content_label.setStyleSheet("color: #ccc; font-size: 12px;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._content_label)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMaximumHeight(300)
        layout.addWidget(scroll)

        # Button bar
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._reject_btn = QPushButton("拒绝 · 重新规划")
        self._reject_btn.setStyleSheet(
            "QPushButton { padding: 8px 16px; background: #555; color: #eee; "
            "border: 1px solid #777; border-radius: 4px; }"
            "QPushButton:hover { background: #666; }"
        )
        self._reject_btn.clicked.connect(self._on_reject)
        button_layout.addWidget(self._reject_btn)

        self._approve_btn = QPushButton("批准 · 继续生成")
        self._approve_btn.setStyleSheet(
            "QPushButton { padding: 8px 24px; background: #27ae60; color: white; "
            "border: none; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #2ecc71; }"
        )
        self._approve_btn.clicked.connect(self._on_approve)
        button_layout.addWidget(self._approve_btn)

        layout.addLayout(button_layout)
        self.hide()

    def show_plan(self, plan_dict: dict) -> None:
        """Display the plan and show the widget."""
        self._plan = plan_dict
        self._content_label.setText(_format_plan_html(plan_dict))
        self._approve_btn.setEnabled(True)
        self._reject_btn.setEnabled(True)
        self.show()

    def hide_plan(self) -> None:
        """Hide the checkpoint widget."""
        self._plan = None
        self.hide()

    def set_waiting(self) -> None:
        """Disable buttons while waiting."""
        self._approve_btn.setEnabled(False)
        self._reject_btn.setEnabled(False)

    def _on_approve(self) -> None:
        self._approve_btn.setEnabled(False)
        self._reject_btn.setEnabled(False)
        self.approved.emit()

    def _on_reject(self) -> None:
        self._approve_btn.setEnabled(False)
        self._reject_btn.setEnabled(False)
        self.rejected.emit()


def _format_plan_html(plan: dict) -> str:
    """Format a plan dict as simple HTML for display."""
    parts = []

    if plan.get("scene_goal"):
        parts.append(f"<p><b>🎯 场景目标</b><br>{plan['scene_goal']}</p>")

    if plan.get("conflict"):
        parts.append(f"<p><b>⚔️ 核心冲突</b><br>{plan['conflict']}</p>")

    beats = plan.get("required_beats", [])
    if beats:
        beats_html = "<br>".join(f"{i+1}. {b}" for i, b in enumerate(beats))
        parts.append(f"<p><b>📋 剧情节拍</b><br>{beats_html}</p>")

    if plan.get("emotional_arc"):
        parts.append(f"<p><b>📈 情绪曲线</b><br>{plan['emotional_arc']}</p>")

    if plan.get("ending_hook"):
        parts.append(f"<p><b>🪝 断章钩子</b><br>{plan['ending_hook']}</p>")

    constraints = plan.get("continuity_constraints", [])
    if constraints:
        cons_html = "<br>".join(f"• {c}" for c in constraints)
        parts.append(f"<p><b>🔒 连续性约束</b><br>{cons_html}</p>")

    return "".join(parts) if parts else "<p><i>规划为空</i></p>"
