"""Quick Creation outline cards and reviewable planning actions."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.application.errors import (
    ConcurrentModificationError,
    OperationBlockedError,
    StoryDesignerProviderError,
)
from app.providers.config import ProviderConfigurationError


_PLANNING_ERRORS = (
    ConcurrentModificationError,
    OperationBlockedError,
    ProviderConfigurationError,
    StoryDesignerProviderError,
    ValueError,
)


class QuickOutlineView(QWidget):
    scene_selected = Signal(str)
    deep_outline_requested = Signal(str)
    chapter_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = None
        self._cards = {}
        self._selected_id = ""
        self._replan_preview = None
        self._task = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("快速大纲"))
        self.card_list = QComboBox()
        self.card_list.currentIndexChanged.connect(self._on_card_changed)
        layout.addWidget(self.card_list)

        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.summary_edit = QTextEdit()
        self.summary_edit.setFixedHeight(70)
        self.ending_hook_edit = QLineEdit()
        form.addRow("标题", self.title_edit)
        form.addRow("概要", self.summary_edit)
        form.addRow("结尾钩子", self.ending_hook_edit)
        layout.addLayout(form)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        actions = QHBoxLayout()
        self.save_button = QPushButton("保存卡片")
        self.write_button = QPushButton("开始写作")
        self.advanced_outline_button = QPushButton("高级大纲")
        self.save_button.clicked.connect(self._preview_card_edit)
        self.write_button.clicked.connect(self._write_selected)
        self.advanced_outline_button.clicked.connect(self._request_deep_outline)
        for button in (self.save_button, self.write_button, self.advanced_outline_button):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.drift_label = QLabel()
        self.drift_label.setWordWrap(True)
        layout.addWidget(self.drift_label)

        layout.addWidget(QLabel("安全重规划"))
        self.replan_instruction = QLineEdit()
        self.replan_instruction.setPlaceholderText("只影响未发布章节的调整说明")
        layout.addWidget(self.replan_instruction)
        replan_actions = QHBoxLayout()
        self.replan_button = QPushButton("生成重规划")
        self.confirm_published_button = QCheckBox("确认影响已发布章节")
        self.apply_replan_button = QPushButton("应用重规划")
        self.replan_button.clicked.connect(self._generate_replan)
        self.apply_replan_button.clicked.connect(self._apply_replan)
        replan_actions.addWidget(self.replan_button)
        replan_actions.addWidget(self.confirm_published_button)
        replan_actions.addWidget(self.apply_replan_button)
        layout.addLayout(replan_actions)
        self.replan_label = QLabel()
        self.replan_label.setWordWrap(True)
        layout.addWidget(self.replan_label)

        self.next_arc_button = QPushButton("规划下一故事弧")
        self.next_arc_button.clicked.connect(self._generate_later_arc)
        layout.addWidget(self.next_arc_button)
        self.next_arc_label = QLabel()
        self.next_arc_label.setWordWrap(True)
        layout.addWidget(self.next_arc_label)
        layout.addStretch()

    def bind_application(self, service) -> None:
        self.cancel_generation()
        self._service = service
        self.refresh()

    def refresh(self) -> None:
        if self._service is None:
            return
        projection = self._service.story_projection()
        selected = self._selected_id
        self._cards = {
            card.id: card
            for arc in projection.arcs
            for card in arc.chapter_cards
        }
        self.card_list.blockSignals(True)
        self.card_list.clear()
        for card in self._cards.values():
            self.card_list.addItem(f"{card.title} · {card.status.value}", card.id)
        self.card_list.blockSignals(False)
        if selected in self._cards:
            self.select_chapter(selected)
        elif self._cards:
            self.select_chapter(next(iter(self._cards)))
        drift = self._service.brief_drift()
        self.drift_label.setText(
            "Brief 漂移：" + ("、".join(drift.changed_fields) if drift.changed_fields else "无")
        )
        self.next_arc_button.setEnabled(bool(self._service.can_plan_next_arc()))

    def select_chapter(self, chapter_id: str) -> bool:
        index = self.card_list.findData(chapter_id)
        if index < 0:
            return False
        self.card_list.setCurrentIndex(index)
        self._show_card(chapter_id)
        self.chapter_selected.emit(chapter_id)
        return True

    @property
    def selected_chapter_id(self) -> str:
        return self._selected_id

    def cancel_generation(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    def _on_card_changed(self, index: int) -> None:
        chapter_id = self.card_list.itemData(index)
        if chapter_id:
            self._show_card(chapter_id)

    def _show_card(self, chapter_id: str) -> None:
        card = self._cards.get(chapter_id)
        if card is None:
            return
        self._selected_id = chapter_id
        self.title_edit.setText(card.title)
        self.summary_edit.setPlainText(card.summary)
        self.ending_hook_edit.setText(card.ending_hook)
        self.status_label.setText(f"状态：{card.status.value}")

    def _write_selected(self) -> None:
        if self._selected_id:
            scene_id = self._cards[self._selected_id].scene_id
            if scene_id:
                self.scene_selected.emit(scene_id)

    def _request_deep_outline(self) -> None:
        if self._selected_id:
            self.deep_outline_requested.emit(self._selected_id)

    def _preview_card_edit(self) -> None:
        if self._service is None or not self._selected_id:
            return
        try:
            preview = self._service.preview_card_edit(
                self._selected_id,
                title=self.title_edit.text(),
                summary=self.summary_edit.toPlainText(),
                ending_hook=self.ending_hook_edit.text(),
            )
            card = self._service.apply_card_edit(preview)
        except _PLANNING_ERRORS as error:
            self.status_label.setText(f"保存失败：{error}")
            return
        self._cards[card.id] = card
        self.refresh()

    def _generate_replan(self) -> None:
        if self._service is not None:
            self._start_task(self._run_replan())

    async def _run_replan(self) -> None:
        try:
            preview = await self._service.generate_replan(
                self.replan_instruction.text().strip()
            )
        except _PLANNING_ERRORS as error:
            self.replan_label.setText(f"重规划失败：{error}")
            return
        self._replan_preview = preview
        published = getattr(preview, "published_chapter_ids", [])
        impact = f"；已发布影响：{'、'.join(published)}，需额外确认" if published else ""
        downstream = getattr(preview, "downstream_review_chapter_ids", [])
        review = f"；需复核正文：{'、'.join(downstream)}" if downstream else ""
        self.replan_label.setText(
            "变更：" + "；".join(preview.changes) + "\n影响：" + "；".join(preview.consequences) + impact + review
        )

    def _apply_replan(self) -> None:
        if self._service is None or self._replan_preview is None:
            return
        published = bool(getattr(self._replan_preview, "published_chapter_ids", []))
        if published and not self.confirm_published_button.isChecked():
            self.replan_label.setText(self.replan_label.text() + "\n请先确认已发布章节影响。")
            return
        try:
            self._service.apply_replan(
                self._replan_preview,
                confirm_published=self.confirm_published_button.isChecked(),
            )
        except _PLANNING_ERRORS as error:
            self.replan_label.setText(f"应用失败：{error}")
            return
        self._replan_preview = None
        self.refresh()

    def _generate_later_arc(self) -> None:
        if self._service is not None:
            self._start_task(self._run_later_arc())

    async def _run_later_arc(self) -> None:
        try:
            draft = await self._service.generate_later_arc()
        except _PLANNING_ERRORS as error:
            self.next_arc_label.setText(f"规划失败：{error}")
            return
        conflicts = "；冲突：" + "；".join(draft.direction_conflicts) if draft.direction_conflicts else ""
        self.next_arc_label.setText(
            f"待审核草稿：{draft.title}\n{draft.summary}{conflicts}\n" + "；".join(draft.changes)
        )

    def _start_task(self, coroutine) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(coroutine)
        else:
            coroutine.close()
