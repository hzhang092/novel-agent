"""Quick Creation outline cards and reviewable planning actions."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
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
    outline_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = None
        self._cards = {}
        self._card_widgets = {}
        self._arc_groups = {}
        self._selected_id = ""
        self._baseline = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("快速大纲"))
        self.card_scroll = QScrollArea()
        self.card_scroll.setWidgetResizable(True)
        layout.addWidget(self.card_scroll, 1)

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
        self.save_button.clicked.connect(self.save_current_card)
        self.write_button.clicked.connect(self._write_selected)
        self.advanced_outline_button.clicked.connect(self._request_deep_outline)
        for button in (self.save_button, self.write_button, self.advanced_outline_button):
            actions.addWidget(button)
        layout.addLayout(actions)

    def bind_application(self, service) -> None:
        self._service = service
        self.refresh()

    def refresh(self, *, force: bool = False) -> None:
        if self._service is None or (self.is_dirty and not force):
            return
        projection = self._service.story_projection()
        selected = self._selected_id
        self._cards = {
            card.id: card
            for arc in projection.arcs
            for card in arc.chapter_cards
        }
        self._card_widgets = {}
        self._arc_groups = {}
        container = QWidget()
        groups = QVBoxLayout(container)
        for arc in projection.arcs:
            approved = sum(
                card.status.value == "已批准" for card in arc.chapter_cards
            )
            group = QGroupBox(
                f"{arc.title} · 已批准 {approved}/{len(arc.chapter_cards)}"
            )
            self._arc_groups[arc.id] = group
            cards_layout = QVBoxLayout(group)
            for card in arc.chapter_cards:
                frame = QFrame()
                card_layout = QVBoxLayout(frame)
                title = QLabel(card.title)
                title.setStyleSheet("font-weight: bold")
                summary = QLabel(card.summary)
                summary.setWordWrap(True)
                hook = QLabel(f"结尾：{card.ending_hook}")
                hook.setWordWrap(True)
                status = QLabel(f"状态：{card.status.value}")
                buttons = QHBoxLayout()
                edit = QPushButton("编辑")
                write = QPushButton("写这一章")
                edit.clicked.connect(
                    lambda _checked=False, chapter_id=card.id: self.select_chapter(
                        chapter_id
                    )
                )
                write.clicked.connect(
                    lambda _checked=False, chapter_id=card.id: self._write_chapter(
                        chapter_id
                    )
                )
                buttons.addWidget(edit)
                buttons.addWidget(write)
                buttons.addStretch()
                for widget in (title, summary, hook, status):
                    card_layout.addWidget(widget)
                card_layout.addLayout(buttons)
                cards_layout.addWidget(frame)
                self._card_widgets[card.id] = {
                    "frame": frame,
                    "title": title,
                    "summary": summary,
                    "hook": hook,
                    "status": status,
                    "edit": edit,
                    "write": write,
                }
            groups.addWidget(group)
        groups.addStretch()
        self.card_scroll.setWidget(container)
        if selected in self._cards:
            self._show_card(selected)
        elif self._cards:
            self.select_chapter(next(iter(self._cards)))

    def select_chapter(self, chapter_id: str) -> bool:
        if chapter_id not in self._cards:
            return False
        if chapter_id == self._selected_id:
            return True
        if self.is_dirty:
            return False
        self._show_card(chapter_id)
        self.chapter_selected.emit(chapter_id)
        return True

    @property
    def selected_chapter_id(self) -> str:
        return self._selected_id

    def _show_card(self, chapter_id: str) -> None:
        card = self._cards.get(chapter_id)
        if card is None:
            return
        self._selected_id = chapter_id
        self.title_edit.setText(card.title)
        self.summary_edit.setPlainText(card.summary)
        self.ending_hook_edit.setText(card.ending_hook)
        self._baseline = (card.title, card.summary, card.ending_hook)
        self.status_label.setText(f"状态：{card.status.value}")

    @property
    def is_dirty(self) -> bool:
        return bool(
            self._selected_id
            and self._baseline != (
                self.title_edit.text(),
                self.summary_edit.toPlainText(),
                self.ending_hook_edit.text(),
            )
        )

    def _write_selected(self) -> None:
        if self._selected_id:
            self._write_chapter(self._selected_id)

    def _write_chapter(self, chapter_id: str) -> None:
        scene_id = self._cards[chapter_id].scene_id
        if scene_id:
            self.scene_selected.emit(scene_id)

    def _request_deep_outline(self) -> None:
        if self._selected_id:
            self.deep_outline_requested.emit(self._selected_id)

    def save_current_card(self) -> bool:
        if self._service is None or not self._selected_id:
            return False
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
            return False
        self._cards[card.id] = card
        self._baseline = (card.title, card.summary, card.ending_hook)
        self.refresh()
        self.outline_changed.emit(card.id)
        return True

    def discard_edits(self) -> bool:
        if self._service is None or not self._selected_id:
            return False
        self.refresh(force=True)
        return True
