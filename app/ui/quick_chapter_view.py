"""Compact Quick Creation companion panel for the shared writing workspace."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

class QuickChapterView(QWidget):
    """A thin companion panel; prose and workflow state stay in Deep's workspace."""

    start_requested = Signal(str, str)  # chapter_id, scene_id
    adjust_requested = Signal(str)  # chapter_id
    adjustment_cancelled = Signal()
    save_requested = Signal()
    regenerate_requested = Signal()
    revision_selected = Signal(str)
    revision_instruction_requested = Signal(str)
    length_changed = Signal(str, int)  # mode, target Chinese characters
    ai_fix_requested = Signal()
    details_requested = Signal()
    override_requested = Signal()
    approve_requested = Signal()
    approve_next_requested = Signal()
    deep_control_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._chapter_id = ""
        self._scene_id = ""
        self._facts: list[Any] = []
        self._changes: list[Any] = []
        self._plan: dict[str, Any] = {}
        self._plan_before_adjustment: dict[str, Any] | None = None
        self._start_allowed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.chapter_identity_label = QLabel("选择章节")
        self.chapter_identity_label.setStyleSheet("font-weight: bold; font-size: 15px")
        layout.addWidget(self.chapter_identity_label)
        self.previous_chapter_label = QLabel()
        self.previous_chapter_label.setWordWrap(True)
        self.previous_chapter_label.hide()
        layout.addWidget(self.previous_chapter_label)
        layout.addWidget(QLabel("本章写作方案"))

        form = QFormLayout()
        self.goal_edit = QLineEdit()
        self.key_events_edit = QTextEdit()
        self.key_events_edit.setFixedHeight(54)
        self.emotional_turn_edit = QLineEdit()
        self.hook_edit = QLineEdit()
        for editor in (self.goal_edit, self.key_events_edit, self.emotional_turn_edit, self.hook_edit):
            editor.setReadOnly(True)
        form.addRow("目标", self.goal_edit)
        form.addRow("关键事件", self.key_events_edit)
        form.addRow("情绪转折", self.emotional_turn_edit)
        form.addRow("钩子", self.hook_edit)
        layout.addLayout(form)

        self.length_combo = QComboBox()
        for label, mode, words in (
            ("短 2000", "short", 2000),
            ("标准 3000", "standard", 3000),
            ("长 5000", "long", 5000),
            ("自定义", "custom", 3000),
        ):
            self.length_combo.addItem(label, mode)
            self.length_combo.setItemData(
                self.length_combo.count() - 1, words, Qt.ItemDataRole.UserRole + 1
            )
        self.length_combo.currentIndexChanged.connect(self._length_changed)
        self.custom_length_spin = QSpinBox()
        self.custom_length_spin.setRange(1, 100000)
        self.custom_length_spin.setValue(3000)
        self.custom_length_spin.valueChanged.connect(self._custom_length_changed)
        form = QFormLayout()
        form.addRow("章节长度", self.length_combo)
        form.addRow("自定义字数", self.custom_length_spin)
        layout.addLayout(form)
        self.length_warning_label = QLabel()
        self.length_warning_label.setWordWrap(True)
        layout.addWidget(self.length_warning_label)
        actions = QHBoxLayout()
        self.start_button = QPushButton("开始")
        self.adjust_button = QPushButton("调整方案")
        self.start_button.clicked.connect(self._start)
        self.adjust_button.clicked.connect(self._adjust)
        actions.addWidget(self.start_button)
        actions.addWidget(self.adjust_button)
        layout.addLayout(actions)

        self.revision_section = QWidget()
        layout.addWidget(self.revision_section)
        revision_row = QHBoxLayout(self.revision_section)
        self.revision_combo = QComboBox()
        self.revision_combo.currentTextChanged.connect(self._select_revision)
        self.published_label = QLabel()
        revision_row.addWidget(QLabel("修订"))
        revision_row.addWidget(self.revision_combo)
        revision_row.addWidget(self.published_label)

        self.prose_section = QWidget()
        layout.addWidget(self.prose_section)
        prose_layout = QVBoxLayout(self.prose_section)
        prose_actions = QHBoxLayout()
        self.save_button = QPushButton("保存修改")
        self.regenerate_button = QPushButton("重新生成")
        self.save_button.clicked.connect(self.save_requested.emit)
        self.regenerate_button.clicked.connect(self.regenerate_requested.emit)
        prose_actions.addWidget(self.regenerate_button)
        self.revision_instruction_edit = QLineEdit()
        self.revision_instruction_edit.setPlaceholderText("告诉 AI 如何修改")
        self.revision_instruction_button = QPushButton("告诉 AI 如何修改")
        self.revision_instruction_button.clicked.connect(
            lambda: self.revision_instruction_requested.emit(
                self.revision_instruction_edit.text().strip()
            )
        )
        prose_actions.addWidget(self.revision_instruction_edit)
        prose_actions.addWidget(self.revision_instruction_button)
        prose_actions.addWidget(self.save_button)
        self.approve_button = QPushButton("批准本章")
        self.approve_next_button = QPushButton("批准并进入下一章")
        self.approve_button.clicked.connect(self.approve_requested.emit)
        self.approve_next_button.clicked.connect(self.approve_next_requested.emit)
        prose_actions.addWidget(self.approve_button)
        prose_actions.addWidget(self.approve_next_button)
        prose_layout.addLayout(prose_actions)

        self.review_section = QWidget()
        layout.addWidget(self.review_section)
        review_layout = QVBoxLayout(self.review_section)
        review_layout.addWidget(QLabel("审查"))
        self.review_summary_label = QLabel()
        self.review_summary_label.setWordWrap(True)
        review_layout.addWidget(self.review_summary_label)
        review_actions = QHBoxLayout()
        self.ai_fix_button = QPushButton("AI 修复")
        self.details_button = QPushButton("详情")
        self.override_button = QPushButton("明确覆盖")
        self.ai_fix_button.clicked.connect(self.ai_fix_requested.emit)
        self.details_button.clicked.connect(self.details_requested.emit)
        self.override_button.clicked.connect(self.override_requested.emit)
        for button in (self.ai_fix_button, self.details_button, self.override_button):
            review_actions.addWidget(button)
        review_layout.addLayout(review_actions)
        for button in (self.ai_fix_button, self.details_button, self.override_button):
            button.hide()

        self.memory_section = QWidget()
        layout.addWidget(self.memory_section)
        memory_layout = QVBoxLayout(self.memory_section)
        memory_layout.addWidget(QLabel("记忆确认"))
        self.memory_label = QLabel()
        self.memory_label.setWordWrap(True)
        memory_layout.addWidget(self.memory_label)
        self.memory_layout = QVBoxLayout()
        memory_layout.addLayout(self.memory_layout)
        self.fact_checks: list[QCheckBox] = []
        self.change_checks: list[QCheckBox] = []

        self.approval_section = self.prose_section
        self.context_label = QLabel()
        self.review_label = QLabel()
        self.status_label = QLabel()
        for label in (self.context_label, self.review_label, self.status_label):
            label.hide()
        self.advanced_button = QPushButton("高级信息 ▸")
        advanced_menu = QMenu(self.advanced_button)
        self._advanced_actions = {}
        for name, text in (
            ("context", "上下文"),
            ("review", "审查"),
            ("memory", "记忆"),
            ("status", "状态"),
        ):
            action = advanced_menu.addAction(text)
            action.triggered.connect(
                lambda _checked=False, value=name: self.deep_control_requested.emit(
                    value
                )
            )
            self._advanced_actions[name] = action
        self.advanced_button.setMenu(advanced_menu)
        layout.addWidget(self.advanced_button)
        layout.addStretch()
        for section in (
            self.revision_section,
            self.prose_section,
            self.review_section,
            self.memory_section,
            self.approval_section,
        ):
            section.hide()

    @property
    def selected_revision(self) -> str:
        return self.revision_combo.currentData() or ""

    def select_revision(self, revision: str, *, emit: bool = False) -> bool:
        index = self.revision_combo.findData(revision)
        if index < 0:
            return False
        blocked = self.revision_combo.blockSignals(not emit)
        try:
            self.revision_combo.setCurrentIndex(index)
        finally:
            self.revision_combo.blockSignals(blocked)
        return True

    def set_chapter(self, chapter_id: str, scene_id: str) -> None:
        self._chapter_id = chapter_id
        self._scene_id = scene_id

    def set_chapter_metadata(
        self, chapter_number: int, title: str, previous_summary: str = ""
    ) -> None:
        prefix = f"第 {chapter_number} 章" if chapter_number else "当前章节"
        self.chapter_identity_label.setText(f"{prefix}：{title}" if title else prefix)
        self.previous_chapter_label.setText(
            f"上一章：{previous_summary}" if previous_summary else ""
        )
        self.previous_chapter_label.setVisible(bool(previous_summary))

    def reset_scene_state(self) -> None:
        self._chapter_id = ""
        self._scene_id = ""
        self.set_chapter_metadata(0, "")
        self._plan = {}
        self._plan_before_adjustment = None
        self._set_plan_editable(False)
        self.goal_edit.clear()
        self.key_events_edit.clear()
        self.emotional_turn_edit.clear()
        self.hook_edit.clear()
        self.show_review(True, "")
        self.show_memory([], [])
        self.set_revisions([], "", "")
        self.length_warning_label.clear()
        self.revision_instruction_edit.clear()
        self.set_context_summary("")
        self.set_status("")

    def set_workflow_state(
        self,
        *,
        has_scene: bool,
        generating: bool,
        waiting_for_plan: bool,
        has_revision: bool,
        publication_ready: bool,
    ) -> None:
        idle = has_scene and not generating
        self._start_allowed = has_scene and not generating and (
            waiting_for_plan or not has_revision
        )
        self.start_button.setEnabled(
            self._start_allowed or self._plan_before_adjustment is not None
        )
        self.adjust_button.setEnabled(idle or (has_scene and waiting_for_plan))
        self.save_button.setEnabled(idle and has_revision)
        self.regenerate_button.setEnabled(idle and has_revision)
        self.revision_instruction_edit.setEnabled(idle and has_revision)
        self.revision_instruction_button.setEnabled(idle and has_revision)
        self.revision_combo.setEnabled(
            idle and has_revision and self.revision_combo.count() > 1
        )
        self.length_combo.setEnabled(idle)
        self.custom_length_spin.setEnabled(idle)
        self.ai_fix_button.setEnabled(idle and has_revision)
        self.override_button.setEnabled(idle and has_revision)
        self.approve_button.setEnabled(idle and publication_ready)
        self.approve_next_button.setEnabled(idle and publication_ready)

    def show_plan(self, plan: dict[str, Any]) -> None:
        self._plan = deepcopy(plan)
        self._scene_id = str(plan.get("scene_id", self._scene_id))
        self.goal_edit.setText(str(plan.get("scene_goal", "")))
        self.key_events_edit.setPlainText("\n".join(plan.get("required_beats", [])))
        self.emotional_turn_edit.setText(str(plan.get("emotional_arc", "")))
        self.hook_edit.setText(str(plan.get("ending_hook", "")))

    def begin_plan_adjustment(self) -> None:
        if self._plan_before_adjustment is not None:
            return
        self._plan_before_adjustment = deepcopy(self._plan)
        self._set_plan_editable(True)

    def accept_plan_adjustment(self, plan: dict[str, Any] | None = None) -> None:
        if self._plan_before_adjustment is None:
            return
        plan = self.plan() if plan is None else plan
        self._plan_before_adjustment = None
        self.show_plan(plan)
        self._set_plan_editable(False)

    def cancel_plan_adjustment(self) -> bool:
        if self._plan_before_adjustment is None:
            return False
        plan = self._plan_before_adjustment
        self._plan_before_adjustment = None
        self.show_plan(plan)
        self._set_plan_editable(False)
        return True

    def show_review(self, passed: bool, summary: str) -> None:
        self.review_section.setVisible(bool(summary))
        self.review_summary_label.setText(
            (("审查通过：" if passed else "关键问题：") + summary) if summary else ""
        )
        self.review_label.setText(summary)
        for button in (self.ai_fix_button, self.details_button, self.override_button):
            button.setVisible(not passed and bool(summary))

    def show_memory(self, facts: list[Any], changes: list[Any]) -> None:
        self._set_memory(facts, changes)
        self.memory_label.setText(f"{len(facts)} 个事实，{len(changes)} 个状态变化待确认")
        self.memory_section.setVisible(bool(facts or changes))

    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def set_context_summary(self, context: str) -> None:
        self.context_label.setText(context)

    def set_revisions(
        self, revisions: list[Any], selected: str = "", published: str = ""
    ) -> None:
        self._set_revisions(revisions, selected)
        self.published_label.setText(f"已发布：{published}" if published else "未发布")
        visible = bool(revisions)
        self.revision_section.setVisible(visible)
        self.prose_section.setVisible(visible)
        self.approval_section.setVisible(visible)

    def set_length(self, mode: str, target_chinese_characters: int, warning: str = "") -> None:
        self._set_length(mode, target_chinese_characters)
        self.length_warning_label.setText(warning)

    def memory_selections(self) -> tuple[list[Any], list[Any]]:
        facts = [item for item, box in zip(self._facts, self.fact_checks) if box.isChecked()]
        changes = [
            item for item, box in zip(self._changes, self.change_checks) if box.isChecked()
        ]
        return facts, changes

    def plan(self) -> dict[str, Any]:
        plan = deepcopy(self._plan)
        plan.setdefault("scene_id", self._scene_id)
        plan.update(
            {
                "scene_goal": self.goal_edit.text(),
                "required_beats": [
                    line.strip()
                    for line in self.key_events_edit.toPlainText().splitlines()
                    if line.strip()
                ],
                "emotional_arc": self.emotional_turn_edit.text(),
                "ending_hook": self.hook_edit.text(),
            }
        )
        return plan

    def _start(self) -> None:
        self.accept_plan_adjustment()
        self.start_requested.emit(self._chapter_id, self._scene_id)

    def _adjust(self) -> None:
        if self.cancel_plan_adjustment():
            self.adjustment_cancelled.emit()
        else:
            self.adjust_requested.emit(self._chapter_id)

    def _set_plan_editable(self, editable: bool) -> None:
        for editor in (
            self.goal_edit,
            self.key_events_edit,
            self.emotional_turn_edit,
            self.hook_edit,
        ):
            editor.setReadOnly(not editable)
        self.start_button.setEnabled(editable or self._start_allowed)
        self.start_button.setText("应用" if editable else "开始")
        self.adjust_button.setText("取消" if editable else "调整方案")

    def _select_revision(self, revision_id: str) -> None:
        if revision_id:
            self.revision_selected.emit(self.revision_combo.currentData() or revision_id)

    def _set_revisions(self, revisions: list[Any], selected: str) -> None:
        self.revision_combo.blockSignals(True)
        self.revision_combo.clear()
        for revision in revisions:
            value = str(self._value(revision, "revision_id", "id", default=revision))
            self.revision_combo.addItem(value, value)
        if selected:
            index = self.revision_combo.findData(selected)
            self.revision_combo.setCurrentIndex(index)
        self.revision_combo.blockSignals(False)

    def _set_length(self, mode: str, words: int) -> None:
        self.length_combo.blockSignals(True)
        self.custom_length_spin.blockSignals(True)
        for index in range(self.length_combo.count()):
            if self.length_combo.itemData(index) == mode:
                self.length_combo.setCurrentIndex(index)
                break
        self.custom_length_spin.setValue(int(words))
        self.length_combo.blockSignals(False)
        self.custom_length_spin.blockSignals(False)

    def _length_changed(self, _index: int) -> None:
        mode = self.length_combo.currentData()
        words = self.length_combo.currentData(Qt.ItemDataRole.UserRole + 1)
        if mode == "custom":
            words = self.custom_length_spin.value()
        self.length_changed.emit(mode, words)

    def _custom_length_changed(self, words: int) -> None:
        if self.length_combo.currentData() == "custom":
            self.length_changed.emit("custom", words)

    def _set_memory(self, facts: list[Any], changes: list[Any]) -> None:
        for box in self.fact_checks + self.change_checks:
            box.deleteLater()
        self._facts = list(facts)
        self._changes = list(changes)
        self.fact_checks = [self._memory_box("事实", item) for item in self._facts]
        self.change_checks = [self._memory_box("状态变化", item) for item in self._changes]
        for box in self.fact_checks + self.change_checks:
            self.memory_layout.addWidget(box)

    @staticmethod
    def _memory_box(kind: str, item: Any) -> QCheckBox:
        text = item
        for name in ("description", "character_name", "text", "content"):
            if isinstance(item, dict) and name in item:
                text = item[name]
                break
            if hasattr(item, name):
                text = getattr(item, name)
                break
        return QCheckBox(f"{kind}：{text}")

    @staticmethod
    def _value(item: Any, *names: str, default: Any = "") -> Any:
        for name in names:
            if isinstance(item, dict) and name in item:
                return item[name]
            if hasattr(item, name):
                return getattr(item, name)
        return default
