"""PlannerCheckpointWidget — inline panel showing the Planner's scene plan with Approve/Regenerate."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
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

    approved = Signal(dict)
    rejected = Signal()

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

        # Editable plan content (scrollable)
        content = QWidget()
        form = QFormLayout(content)
        self._scene_goal_edit = QLineEdit()
        self._conflict_edit = QLineEdit()
        self._emotional_arc_edit = QLineEdit()
        self._ending_hook_edit = QLineEdit()
        self._required_beats_edit = QPlainTextEdit()
        self._continuity_constraints_edit = QPlainTextEdit()
        self._required_beats_edit.setMaximumHeight(100)
        self._continuity_constraints_edit.setMaximumHeight(80)
        form.addRow("场景目标", self._scene_goal_edit)
        form.addRow("核心冲突", self._conflict_edit)
        form.addRow("剧情节拍（每行一项）", self._required_beats_edit)
        form.addRow("情绪曲线", self._emotional_arc_edit)
        form.addRow("断章钩子", self._ending_hook_edit)
        form.addRow("连续性约束（每行一项）", self._continuity_constraints_edit)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
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
        self._plan = dict(plan_dict)
        self._scene_goal_edit.setText(plan_dict.get("scene_goal", ""))
        self._conflict_edit.setText(plan_dict.get("conflict", ""))
        self._emotional_arc_edit.setText(plan_dict.get("emotional_arc", ""))
        self._ending_hook_edit.setText(plan_dict.get("ending_hook", ""))
        self._required_beats_edit.setPlainText("\n".join(plan_dict.get("required_beats", [])))
        self._continuity_constraints_edit.setPlainText(
            "\n".join(plan_dict.get("continuity_constraints", []))
        )
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
        plan = dict(self._plan or {})
        plan.update({
            "scene_goal": self._scene_goal_edit.text(),
            "conflict": self._conflict_edit.text(),
            "emotional_arc": self._emotional_arc_edit.text(),
            "ending_hook": self._ending_hook_edit.text(),
            "required_beats": _nonempty_lines(self._required_beats_edit.toPlainText()),
            "continuity_constraints": _nonempty_lines(
                self._continuity_constraints_edit.toPlainText()
            ),
        })
        self.approved.emit(plan)

    def _on_reject(self) -> None:
        self._approve_btn.setEnabled(False)
        self._reject_btn.setEnabled(False)
        self.rejected.emit()

def _nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]
