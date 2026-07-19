"""Writing Workspace — three-pane layout with context, editor, and trace."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.ui.context_preview import ContextPreviewView
from app.ui.widgets.agent_trace import AgentTracePanel
from app.ui.widgets.planner_checkpoint import PlannerCheckpointWidget
from app.ui.widgets.prose_editor import ProseEditorWidget
from app.ui.widgets.fact_approval import FactApprovalPanel


class SceneWorkspaceView(QWidget):
    """Three-pane writing workspace for scene generation.

    Left: Context Preview panel
    Center: Prose editor with preview toggle
    Right: Agent Trace panel

    Emits ``generate_requested`` when the user clicks Generate or presses Enter.
    """

    generate_requested = Signal(str)  # emits scene_id
    retry_requested = Signal(str)  # emits agent_name
    next_scene_requested = Signal()  # emits when user clicks Next Scene
    continue_review_requested = Signal()
    prose_version_selected = Signal(str)
    publish_version_requested = Signal(str)
    plan_approved = Signal(dict)
    plan_rejected = Signal()
    approval_batch_approved = Signal(str, str, list, list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._current_scene_id: str | None = None
        self._current_chapter_id: str | None = None
        self._generating = False
        self._next_scene_available = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Toolbar ──
        toolbar = QHBoxLayout()

        self._generate_btn = QPushButton("生成")
        self._generate_btn.setEnabled(False)
        self._generate_btn.setStyleSheet(
            "QPushButton { padding: 6px 20px; font-weight: bold; }"
        )
        self._generate_btn.clicked.connect(self._on_generate_clicked)
        toolbar.addWidget(self._generate_btn)

        self._regenerate_btn = QPushButton("重新生成")
        self._regenerate_btn.setEnabled(False)
        self._regenerate_btn.setStyleSheet(
            "QPushButton { padding: 6px 16px; }"
        )
        self._regenerate_btn.clicked.connect(self._on_regenerate_clicked)
        toolbar.addWidget(self._regenerate_btn)

        toolbar.addSpacing(16)
        self._next_scene_btn = QPushButton("下一场景 ▸")
        self._next_scene_btn.setEnabled(False)
        self._next_scene_btn.setStyleSheet(
            "QPushButton { padding: 6px 14px; }"
        )
        self._next_scene_btn.clicked.connect(
            lambda: self.next_scene_requested.emit()
        )
        toolbar.addWidget(self._next_scene_btn)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; font-size: 12px;")
        toolbar.addWidget(self._status_label)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Planner Checkpoint (shown during plan approval)
        self._planner_checkpoint = PlannerCheckpointWidget()
        self._planner_checkpoint.approved.connect(self.plan_approved.emit)
        self._planner_checkpoint.rejected.connect(self.plan_rejected.emit)
        self._planner_checkpoint.hide()
        layout.addWidget(self._planner_checkpoint)

        # ── Three-pane splitter ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Context Preview
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.addWidget(QLabel("<b>上下文预览</b>"))
        self._context_preview = ContextPreviewView()
        left_layout.addWidget(self._context_preview)
        left_layout.addStretch()
        splitter.addWidget(left_pane)

        # Center: Prose Editor
        center_pane = QWidget()
        center_layout = QVBoxLayout(center_pane)
        center_layout.setContentsMargins(4, 0, 4, 0)
        center_layout.addWidget(QLabel("<b>正文编辑器</b>"))
        self._editor = ProseEditorWidget()
        self._editor.version_selected.connect(self.prose_version_selected.emit)
        self._editor.set_active_requested.connect(self.publish_version_requested.emit)
        center_layout.addWidget(self._editor)
        splitter.addWidget(center_pane)

        # Right: Agent Trace
        right_pane = QWidget()
        right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(4, 0, 0, 0)
        self._trace_panel = AgentTracePanel()
        self._trace_panel.retry_requested.connect(self.retry_requested.emit)
        right_layout.addWidget(self._trace_panel)
        splitter.addWidget(right_pane)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([280, 500, 200])
        layout.addWidget(splitter)

        # ── Review result bar (shown after review completes) ──
        self._review_bar = QWidget()
        review_layout = QHBoxLayout(self._review_bar)
        review_layout.setContentsMargins(8, 4, 8, 4)
        self._review_label = QLabel("")
        self._review_label.setStyleSheet("font-size: 12px;")
        review_layout.addWidget(self._review_label)
        review_layout.addStretch()
        self._continue_review_btn = QPushButton("仍然继续")
        self._continue_review_btn.clicked.connect(self.continue_review_requested.emit)
        self._continue_review_btn.hide()
        review_layout.addWidget(self._continue_review_btn)
        self._review_bar.hide()
        layout.addWidget(self._review_bar)

        # ── Fact Approval panel ──
        self._fact_approval = FactApprovalPanel()
        self._fact_approval.approval_batch_approved.connect(
            self.approval_batch_approved.emit
        )
        self._fact_approval.hide()
        layout.addWidget(self._fact_approval)

    # ── Public API ────────────────────────────────────────────────────────

    def load_project_dir(self, project_dir: Path) -> None:
        """Store project directory reference."""
        self._project_dir = project_dir

    @property
    def current_scene_id(self) -> str | None:
        """Return the active scene ID."""
        return self._current_scene_id

    @property
    def current_chapter_id(self) -> str | None:
        """Return the active chapter ID."""
        return self._current_chapter_id

    def is_showing_scene(self, scene_id: str, chapter_id: str) -> bool:
        """Return whether the workspace shows the requested scene."""
        return (
            self._current_scene_id == scene_id
            and self._current_chapter_id == chapter_id
        )

    def set_prose_text(self, text: str) -> None:
        """Replace the prose editor text."""
        self._editor.setPlainText(text)

    def prose_text(self) -> str:
        """Return the current prose text."""
        return self._editor.toPlainText()

    def append_prose(self, text: str) -> None:
        """Append streaming prose text."""
        self._editor.append(text)

    def prose_is_modified(self) -> bool:
        """Return whether prose has unsaved user edits."""
        return self._editor.is_modified()

    def set_prose_versions(
        self,
        versions: list[str],
        current: str | None = None,
    ) -> None:
        """Set available prose versions."""
        self._editor.set_versions(versions, current)

    def current_prose_version(self) -> str:
        """Return the selected prose version."""
        return self._editor.current_version()

    def clear_trace(self) -> None:
        """Clear the generation trace."""
        self._trace_panel.clear()

    def show_trace_waiting(self, message: str) -> None:
        """Show a waiting message in the trace panel."""
        self._trace_panel.set_waiting(message)

    def update_trace(self, trace: list) -> None:
        """Display the current generation trace."""
        self._trace_panel.update_trace(trace)

    def show_plan_checkpoint(self, plan: dict) -> None:
        """Show a plan for user approval."""
        self._planner_checkpoint.show_plan(plan)

    def hide_plan_checkpoint(self) -> None:
        """Hide the plan approval checkpoint."""
        self._planner_checkpoint.hide_plan()

    def set_plan_checkpoint_waiting(self) -> None:
        """Disable plan decisions while generation continues."""
        self._planner_checkpoint.set_waiting()

    def set_status(self, text: str) -> None:
        """Set the workspace status message."""
        self._status_label.setText(text)

    def set_next_scene_available(self, available: bool) -> None:
        """Set whether next-scene navigation is available."""
        self._next_scene_available = available
        self._next_scene_btn.setEnabled(
            available and not self._generating and self._current_scene_id is not None
        )

    def mark_last_scene(self) -> None:
        """Disable next-scene navigation at the end of the outline."""
        self.set_next_scene_available(False)
        self.set_status("已是最后一场景")

    def hide_continue_review(self) -> None:
        """Hide the continue-after-review action."""
        self._continue_review_btn.hide()

    def begin_generation(self, waiting_message: str = "正在组装上下文...") -> None:
        """Reset the workspace and enter generation state."""
        self.set_generating(True)
        self.set_prose_text("")
        self.clear_trace()
        self.show_trace_waiting(waiting_message)
        self.hide_review_result()
        self.hide_fact_approval()

    def set_scene(self, scene_id: str, chapter_id: str) -> None:
        """Called when a scene is selected in the outline."""
        self._current_scene_id = scene_id
        self._current_chapter_id = chapter_id
        self._generate_btn.setEnabled(True)
        self._regenerate_btn.setEnabled(True)
        self._status_label.setText("就绪")
        self.set_next_scene_available(True)

    def clear_scene(self) -> None:
        """Called when no scene is selected."""
        self._current_scene_id = None
        self._current_chapter_id = None
        self._generate_btn.setEnabled(False)
        self._regenerate_btn.setEnabled(False)
        self.hide_fact_approval()
        self.set_next_scene_available(False)

    def show_context(self, context: dict) -> None:
        """Display assembled context in the preview panel."""
        self._context_preview.set_context(context)

    def clear_context(self) -> None:
        """Clear the context preview."""
        self._context_preview.clear()

    def set_generating(self, generating: bool) -> None:
        """Set the UI into generating/idle state."""
        self._generating = generating
        self._generate_btn.setEnabled(not generating and self._current_scene_id is not None)
        self._regenerate_btn.setEnabled(not generating and self._current_scene_id is not None)
        self._next_scene_btn.setEnabled(
            not generating
            and self._current_scene_id is not None
            and self._next_scene_available
        )
        if generating:
            self._status_label.setText("生成中...")
        else:
            self._status_label.setText("就绪")

    def show_review_result(self, passed: bool, summary: str) -> None:
        """Show the review result bar."""
        if passed:
            self._review_label.setText(f"✅ 审查通过 — {summary}")
            self._review_label.setStyleSheet("color: #27ae60; font-size: 12px;")
            self._continue_review_btn.hide()
        else:
            self._review_label.setText(f"⚠️ 审查发现问题 — {summary}")
            self._review_label.setStyleSheet("color: #f39c12; font-size: 12px;")
            self._continue_review_btn.show()
        self._review_bar.show()

    def hide_review_result(self) -> None:
        """Hide the review result bar."""
        self._review_bar.hide()

    def show_fact_approval(
        self,
        source_scene_id: str,
        source_revision_id: str,
        facts: list[dict],
        state_changes: list[dict],
    ) -> None:
        """Show the fact approval panel with extracted facts and state changes."""
        self._fact_approval.show_items(
            source_scene_id, source_revision_id, facts, state_changes
        )

    def hide_fact_approval(self) -> None:
        """Hide the fact approval panel."""
        self._fact_approval.clear_and_hide()

    # ── Actions ────────────────────────────────────────────────────────────

    def _on_generate_clicked(self) -> None:
        if self._current_scene_id and not self._generating:
            self.generate_requested.emit(self._current_scene_id)

    def _on_regenerate_clicked(self) -> None:
        """Trigger regeneration — same as generate but re-runs full pipeline."""
        if self._current_scene_id and not self._generating:
            self.generate_requested.emit(self._current_scene_id)

    def keyPressEvent(self, event) -> None:
        """Capture Enter key to trigger generation."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._current_scene_id and not self._generating:
                self.generate_requested.emit(self._current_scene_id)
            return
        super().keyPressEvent(event)
