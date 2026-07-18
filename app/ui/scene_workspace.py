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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._current_scene_id: str | None = None
        self._current_chapter_id: str | None = None
        self._generating = False
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
        self.planner_checkpoint = PlannerCheckpointWidget()
        self.planner_checkpoint.hide()
        layout.addWidget(self.planner_checkpoint)

        # ── Three-pane splitter ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Context Preview
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.addWidget(QLabel("<b>上下文预览</b>"))
        self.context_preview = ContextPreviewView()
        left_layout.addWidget(self.context_preview)
        left_layout.addStretch()
        splitter.addWidget(left_pane)

        # Center: Prose Editor
        center_pane = QWidget()
        center_layout = QVBoxLayout(center_pane)
        center_layout.setContentsMargins(4, 0, 4, 0)
        center_layout.addWidget(QLabel("<b>正文编辑器</b>"))
        self.editor = ProseEditorWidget()
        center_layout.addWidget(self.editor)
        splitter.addWidget(center_pane)

        # Right: Agent Trace
        right_pane = QWidget()
        right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(4, 0, 0, 0)
        self.trace_panel = AgentTracePanel()
        self.trace_panel.retry_requested.connect(self.retry_requested.emit)
        right_layout.addWidget(self.trace_panel)
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
        self.fact_approval = FactApprovalPanel()
        self.fact_approval.hide()
        layout.addWidget(self.fact_approval)

    # ── Public API ────────────────────────────────────────────────────────

    def load_project_dir(self, project_dir: Path) -> None:
        """Store project directory reference."""
        self._project_dir = project_dir

    def set_scene(self, scene_id: str, chapter_id: str) -> None:
        """Called when a scene is selected in the outline."""
        self._current_scene_id = scene_id
        self._current_chapter_id = chapter_id
        self._generate_btn.setEnabled(True)
        self._regenerate_btn.setEnabled(True)
        self._status_label.setText("就绪")
        self._next_scene_btn.setEnabled(True)

    def clear_scene(self) -> None:
        """Called when no scene is selected."""
        self._current_scene_id = None
        self._current_chapter_id = None
        self._generate_btn.setEnabled(False)
        self._regenerate_btn.setEnabled(False)
        self.hide_fact_approval()
        self._next_scene_btn.setEnabled(False)

    def show_context(self, context: dict) -> None:
        """Display assembled context in the preview panel."""
        self.context_preview.set_context(context)

    def clear_context(self) -> None:
        """Clear the context preview."""
        self.context_preview.clear()

    def set_generating(self, generating: bool) -> None:
        """Set the UI into generating/idle state."""
        self._generating = generating
        self._generate_btn.setEnabled(not generating and self._current_scene_id is not None)
        self._regenerate_btn.setEnabled(not generating and self._current_scene_id is not None)
        self._next_scene_btn.setEnabled(not generating and self._current_scene_id is not None)
        if generating:
            self._status_label.setText("生成中...")
        else:
            self._status_label.setText("就绪")
        self._next_scene_btn.setEnabled(True)

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
        self.fact_approval.show_items(
            source_scene_id, source_revision_id, facts, state_changes
        )

    def hide_fact_approval(self) -> None:
        """Hide the fact approval panel."""
        self.fact_approval.clear_and_hide()

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
