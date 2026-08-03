"""Quick Creation outline cards and reviewable planning actions."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
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

        layout.addStretch()

    def bind_application(self, service) -> None:
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
