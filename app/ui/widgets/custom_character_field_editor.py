"""Small editor for author-defined character fields."""

from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.storage.models import CharacterCustomField, CharacterCustomFieldType


class CustomCharacterFieldEditor(QWidget):
    """Edit a compact list of custom fields; values remain model-owned."""

    changed = Signal()
    visibility_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fields: list[CharacterCustomField] = []
        self._hidden_ids: set[str] = set()
        self._populating = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._show_current)
        layout.addWidget(self._list)
        row = QHBoxLayout()
        self._label = QLineEdit()
        self._label.setPlaceholderText("字段名称")
        row.addWidget(self._label)
        self._type = QComboBox()
        for value_type, label in ((CharacterCustomFieldType.TEXT, "短文本"), (CharacterCustomFieldType.LONG_TEXT, "长文本"), (CharacterCustomFieldType.STRING_LIST, "列表")):
            self._type.addItem(label, value_type)
        self._type.currentIndexChanged.connect(self._on_type_changed)
        row.addWidget(self._type)
        self._include = QCheckBox("用于生成")
        self._include.setChecked(True)
        row.addWidget(self._include)
        layout.addLayout(row)
        self._value = QTextEdit()
        self._value.setPlaceholderText("列表每行一项")
        self._value.setMaximumHeight(72)
        layout.addWidget(self._value)
        buttons = QHBoxLayout()
        self._add = QPushButton("添加自定义字段")
        self._add.clicked.connect(self._add_field)
        buttons.addWidget(self._add)
        self._update = QPushButton("更新字段")
        self._update.clicked.connect(self._update_field)
        buttons.addWidget(self._update)
        self._clear = QPushButton("清空内容")
        self._clear.clicked.connect(self._clear_value)
        buttons.addWidget(self._clear)
        self._remove = QPushButton("删除字段")
        self._remove.clicked.connect(self._remove_field)
        buttons.addWidget(self._remove)
        self._hide = QPushButton("隐藏字段")
        self._hide.clicked.connect(self._toggle_hidden)
        buttons.addWidget(self._hide)
        self._show_hidden = QPushButton("显示隐藏字段")
        self._show_hidden.setCheckable(True)
        self._show_hidden.toggled.connect(lambda _: self._refresh())
        buttons.addWidget(self._show_hidden)
        buttons.addStretch()
        layout.addLayout(buttons)

    def set_fields(self, fields: list[CharacterCustomField]) -> None:
        self._fields = [field.model_copy(deep=True) for field in fields]
        self._refresh()

    def fields(self) -> list[CharacterCustomField]:
        return [field.model_copy(deep=True) for field in self._fields]

    def set_hidden_ids(self, field_ids: list[str]) -> None:
        self._hidden_ids = set(field_ids)
        self._refresh()

    def hidden_ids(self) -> list[str]:
        return [field.id for field in self._fields if field.id in self._hidden_ids]

    def add_empty_field(
        self, label: str, value_type: CharacterCustomFieldType, include: bool
    ) -> None:
        """Add through the existing validation path from the creation dialog."""
        self._label.setText(label)
        self._type.setCurrentIndex(self._type.findData(value_type))
        self._include.setChecked(include)
        self._value.clear()
        self._add_field()

    def _current_index(self) -> int:
        item = self._list.currentItem()
        return item.data(0x0100) if item else -1

    def _value_for_type(self, value_type: CharacterCustomFieldType):
        text = self._value.toPlainText().strip()
        return [line.strip() for line in text.splitlines() if line.strip()] if value_type == CharacterCustomFieldType.STRING_LIST else text

    def _editor_field(self, existing: CharacterCustomField | None = None) -> CharacterCustomField | None:
        value_type = CharacterCustomFieldType(self._type.currentData())
        try:
            return CharacterCustomField(
                id=existing.id if existing else str(uuid4()),
                label=self._label.text(), value_type=value_type,
                value=self._value_for_type(value_type), include_in_generation=self._include.isChecked(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "字段无效", str(error))
            return None

    def _add_field(self) -> None:
        if len(self._fields) >= 30:
            QMessageBox.warning(self, "字段过多", "最多可添加 30 个自定义字段。")
            return
        field = self._editor_field()
        if field is None:
            return
        if any(item.label.casefold() == field.label.casefold() for item in self._fields):
            QMessageBox.warning(self, "字段重复", "自定义字段名称不能重复。")
            return
        self._fields.append(field)
        self._refresh(len(self._fields) - 1)
        self.changed.emit()

    def _update_field(self) -> None:
        row = self._current_index()
        if row < 0:
            return
        field = self._editor_field(self._fields[row])
        if field is None:
            return
        if any(index != row and item.label.casefold() == field.label.casefold() for index, item in enumerate(self._fields)):
            QMessageBox.warning(self, "字段重复", "自定义字段名称不能重复。")
            return
        self._fields[row] = field
        self._refresh(row)
        self.changed.emit()

    def _remove_field(self) -> None:
        row = self._current_index()
        if row < 0:
            return
        if QMessageBox.question(self, "确认删除", "删除此自定义字段？") != QMessageBox.StandardButton.Yes:
            return
        self._fields.pop(row)
        self._refresh()
        self.changed.emit()

    def _refresh(self, selected: int = -1) -> None:
        self._populating = True
        self._list.clear()
        for index, field in enumerate(self._fields):
            if field.id in self._hidden_ids and not self._show_hidden.isChecked():
                continue
            suffix = "" if field.include_in_generation else "（不用于生成）"
            item = QListWidgetItem(f"{field.label}{suffix}")
            item.setData(0x0100, index)
            self._list.addItem(item)
            if index == selected:
                self._list.setCurrentItem(item)
        self._populating = False
        self._show_current(self._list.currentRow())

    def _show_current(self, row: int) -> None:
        row = self._current_index()
        if row < 0 or row >= len(self._fields):
            return
        field = self._fields[row]
        self._label.setText(field.label)
        self._type.setCurrentIndex(self._type.findData(field.value_type))
        self._include.setChecked(field.include_in_generation)
        self._value.setPlainText("\n".join(field.value) if isinstance(field.value, list) else field.value)

    def _toggle_hidden(self) -> None:
        row = self._current_index()
        if row < 0:
            return
        field_id = self._fields[row].id
        if field_id in self._hidden_ids:
            self._hidden_ids.remove(field_id)
        else:
            self._hidden_ids.add(field_id)
        self._refresh()
        self.visibility_changed.emit()

    def _clear_value(self) -> None:
        if self._current_index() < 0:
            return
        self._value.clear()
        self._update_field()

    def _on_type_changed(self) -> None:
        row = self._current_index()
        if row < 0 or row >= len(self._fields):
            return
        field = self._fields[row]
        value_type = CharacterCustomFieldType(self._type.currentData())
        if value_type == field.value_type:
            return
        populated = bool(field.value)
        if populated and QMessageBox.question(self, "转换字段类型", "转换类型会按行保留当前内容，是否继续？") != QMessageBox.StandardButton.Yes:
            with QSignalBlocker(self._type):
                self._type.setCurrentIndex(self._type.findData(field.value_type))
            return
        text = self._value.toPlainText()
        value = [line.strip() for line in text.splitlines() if line.strip()] if value_type == CharacterCustomFieldType.STRING_LIST else text
        self._fields[row] = field.model_copy(update={"value_type": value_type, "value": value})
        self.changed.emit()
