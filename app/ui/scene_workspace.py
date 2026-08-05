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
from app.ui.quick_chapter_view import QuickChapterView


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
    quick_start_requested = Signal(str, str)
    quick_adjust_requested = Signal(str)
    quick_adjust_cancelled = Signal()
    quick_save_requested = Signal()
    quick_regenerate_requested = Signal()
    quick_revision_instruction_requested = Signal(str)
    quick_length_changed = Signal(str, int)
    quick_ai_fix_requested = Signal()
    quick_details_requested = Signal()
    quick_override_requested = Signal()
    quick_approve_requested = Signal()
    quick_approve_next_requested = Signal()
    deep_control_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_dir: Path | None = None
        self._current_scene_id: str | None = None
        self._current_chapter_id: str | None = None
        self._generating = False
        self._next_scene_available = False
        self._experience_mode = "deep"
        self._has_review = False
        self._has_memory = False
        self._quick_memory_source = ("", "")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Toolbar ──
        self._deep_toolbar = QWidget()
        toolbar = QHBoxLayout(self._deep_toolbar)
        toolbar.setContentsMargins(0, 0, 0, 0)

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
        layout.addWidget(self._deep_toolbar)

        self._quick_chapter = QuickChapterView()
        for source, target in (
            (self._quick_chapter.start_requested, self.quick_start_requested),
            (self._quick_chapter.adjust_requested, self.quick_adjust_requested),
            (
                self._quick_chapter.adjustment_cancelled,
                self.quick_adjust_cancelled,
            ),
            (self._quick_chapter.save_requested, self.quick_save_requested),
            (self._quick_chapter.regenerate_requested, self.quick_regenerate_requested),
            (
                self._quick_chapter.revision_instruction_requested,
                self.quick_revision_instruction_requested,
            ),
            (self._quick_chapter.length_changed, self.quick_length_changed),
            (self._quick_chapter.ai_fix_requested, self.quick_ai_fix_requested),
            (self._quick_chapter.details_requested, self.quick_details_requested),
            (self._quick_chapter.override_requested, self.quick_override_requested),
            (self._quick_chapter.approve_requested, self.quick_approve_requested),
            (
                self._quick_chapter.approve_next_requested,
                self.quick_approve_next_requested,
            ),
            (
                self._quick_chapter.deep_control_requested,
                self.deep_control_requested,
            ),
            (
                self._quick_chapter.revision_selected,
                self.prose_version_selected,
            ),
        ):
            source.connect(target.emit)
        self._quick_chapter.hide()
        layout.addWidget(self._quick_chapter)

        # Planner Checkpoint (shown during plan approval)
        self._planner_checkpoint = PlannerCheckpointWidget()
        self._planner_checkpoint.approved.connect(self.plan_approved.emit)
        self._planner_checkpoint.rejected.connect(self.plan_rejected.emit)
        self._planner_checkpoint.hide()
        layout.addWidget(self._planner_checkpoint)

        # ── Three-pane splitter ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter = splitter

        # Left: Context Preview
        left_pane = QWidget()
        self._left_pane = left_pane
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
        self._right_pane = right_pane
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

    def set_experience_mode(self, mode: str) -> None:
        """Switch presentation while preserving the shared editor and run state."""
        self._experience_mode = "quick" if mode == "quick" else "deep"
        quick = self._experience_mode == "quick"
        self._deep_toolbar.setVisible(not quick)
        self._quick_chapter.setVisible(quick)
        self._editor.set_compact_mode(quick)
        self._left_pane.setVisible(not quick)
        self._right_pane.setVisible(not quick)
        self._planner_checkpoint.setVisible(
            not quick and self._planner_checkpoint.has_plan
        )
        self._review_bar.setVisible(not quick and self._has_review)
        self._fact_approval.setVisible(not quick and self._has_memory)

    @property
    def current_scene_id(self) -> str | None:
        """Return the active scene ID."""
        return self._current_scene_id

    @property
    def current_chapter_id(self) -> str | None:
        """Return the active chapter ID."""
        return self._current_chapter_id

    @property
    def status_text(self) -> str:
        """Return the user-facing workflow status."""
        return self._status_label.text()

    @property
    def continue_review_is_visible(self) -> bool:
        """Return whether the saved-draft retry action is available."""
        return not self._continue_review_btn.isHidden()

    @property
    def review_summary(self) -> str:
        """Return the current review message."""
        return self._review_label.text()

    @property
    def fact_approval_is_visible(self) -> bool:
        """Return whether a fact approval batch is being shown."""
        return not self._fact_approval.isHidden()

    @property
    def pending_approval_counts(self) -> tuple[int, int]:
        """Return pending fact and state-change counts."""
        return self._fact_approval.pending_counts

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
        published: str | None = None,
    ) -> None:
        """Set available prose versions."""
        self._editor.set_versions(versions, current)
        self._quick_chapter.set_revisions(versions, current or "", published or "")

    def select_prose_version(self, version: str) -> bool:
        selected = self._editor.select_version(version)
        self._quick_chapter.select_revision(version)
        return selected

    def set_quick_length(self, mode: str, target: int, warning: str = "") -> None:
        """Project the active chapter length into Quick Creation."""
        self._quick_chapter.set_length(mode, target, warning)

    def begin_quick_plan_adjustment(self) -> None:
        self._quick_chapter.begin_plan_adjustment()

    def accept_quick_plan_adjustment(self, plan: dict) -> None:
        self._quick_chapter.accept_plan_adjustment(plan)

    def cancel_quick_plan_adjustment(self) -> None:
        self._quick_chapter.cancel_plan_adjustment()

    def focus_deep_control(self, control: str) -> None:
        """Move focus to the Deep control linked from Quick."""
        target = {
            "context": self._context_preview,
            "review": self._review_bar,
            "memory": self._fact_approval,
            "status": self._status_label,
        }.get(control)
        if target is not None:
            target.setFocus(Qt.FocusReason.OtherFocusReason)

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
        self._quick_chapter.show_plan(plan)
        if self._experience_mode == "quick":
            self._planner_checkpoint.hide()

    def show_quick_plan(self, plan: dict) -> None:
        """Show stored plan data without reopening the Deep approval checkpoint."""
        self._quick_chapter.show_plan(plan)

    def hide_plan_checkpoint(self) -> None:
        """Hide the plan approval checkpoint."""
        self._planner_checkpoint.hide_plan()

    def set_plan_checkpoint_waiting(self) -> None:
        """Disable plan decisions while generation continues."""
        self._planner_checkpoint.set_waiting()

    def set_status(self, text: str) -> None:
        """Set the workspace status message."""
        self._status_label.setText(text)
        self._quick_chapter.set_status(text)

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
        self._quick_chapter.show_review(True, "")

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
        changed = (
            self._current_scene_id != scene_id
            or self._current_chapter_id != chapter_id
        )
        if changed:
            self._quick_chapter.reset_scene_state()
            self.hide_plan_checkpoint()
            self.hide_review_result()
            self.hide_fact_approval()
            self.clear_context()
            self.set_prose_versions([])
            self.set_prose_text("")
        self._current_scene_id = scene_id
        self._current_chapter_id = chapter_id
        self._quick_chapter.set_chapter(chapter_id, scene_id)
        self._generate_btn.setEnabled(True)
        self._regenerate_btn.setEnabled(True)
        self.set_status("就绪")
        self.set_next_scene_available(True)

    def clear_scene(self) -> None:
        """Called when no scene is selected."""
        self._current_scene_id = None
        self._current_chapter_id = None
        self._quick_chapter.set_chapter("", "")
        self._generate_btn.setEnabled(False)
        self._regenerate_btn.setEnabled(False)
        self.hide_fact_approval()
        self.set_next_scene_available(False)

    def show_context(self, context: dict) -> None:
        """Display assembled context in the preview panel."""
        self._context_preview.set_context(context)
        self._quick_chapter.set_context_summary(f"{len(context)} 个上下文分区")

    def clear_context(self) -> None:
        """Clear the context preview."""
        self._context_preview.clear()
        self._quick_chapter.set_context_summary("")

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
        self._has_review = True
        self._quick_chapter.show_review(passed, summary)
        self._review_bar.setVisible(self._experience_mode == "deep")

    def show_stale_warning(self) -> None:
        self._review_label.setText("⚠️ 基于旧设定 — 请复核后继续，或重新生成")
        self._review_label.setStyleSheet("color: #f39c12; font-size: 12px;")
        self._continue_review_btn.show()
        self._quick_chapter.show_review(False, "基于旧设定，请复核后继续或重新生成")
        self._review_bar.setVisible(self._experience_mode == "deep")

    def hide_review_result(self) -> None:
        """Hide the review result bar."""
        self._review_bar.hide()
        self._has_review = False
        self._quick_chapter.show_review(True, "")

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
        self._quick_memory_source = (source_scene_id, source_revision_id)
        self._has_memory = True
        self._quick_chapter.show_memory(facts, state_changes)
        self._fact_approval.setVisible(self._experience_mode == "deep")

    def hide_fact_approval(self) -> None:
        """Hide the fact approval panel."""
        self._fact_approval.clear_and_hide()
        self._has_memory = False
        self._quick_memory_source = ("", "")
        self._quick_chapter.show_memory([], [])

    def quick_plan(self) -> dict:
        return self._quick_chapter.plan()

    def quick_memory_selections(self) -> tuple[list, list]:
        return self._quick_chapter.memory_selections()

    def quick_approval_batch(self) -> tuple[str, str, list, list]:
        facts, changes = self.quick_memory_selections()
        scene_id, revision_id = self._quick_memory_source
        return scene_id, revision_id, facts, changes

    def set_quick_revision_metadata(
        self,
        scene_id: str,
        revision_id: str,
        review_passed: bool,
        review_summary: str,
        facts: list,
        changes: list,
    ) -> None:
        """Project one stored revision into Quick's review and memory controls."""
        self._quick_memory_source = (scene_id, revision_id)
        self._quick_chapter.show_review(review_passed, review_summary)
        self._quick_chapter.show_memory(facts, changes)

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
