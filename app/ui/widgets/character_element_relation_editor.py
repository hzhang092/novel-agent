"""Editor for stable-ID character-to-Bible-element links."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from app.domain.character_element_relation_catalog import relation_definition
from app.storage.bible_models import BibleElement
from app.storage.models import CharacterElementRelation, CharacterElementRelationKind


class CharacterElementRelationEditor(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._relations: list[CharacterElementRelation] = []
        self._elements: list[BibleElement] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._show_relation)
        layout.addWidget(self._list)
        row = QHBoxLayout()
        self._kind = QComboBox()
        for kind in CharacterElementRelationKind:
            self._kind.addItem(relation_definition(kind).label, kind)
        self._kind.currentIndexChanged.connect(self._refresh_targets)
        row.addWidget(self._kind)
        self._target = QComboBox()
        self._target.setEditable(True)
        self._target.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        row.addWidget(self._target)
        self._note = QLineEdit()
        self._note.setPlaceholderText("备注（可选）")
        row.addWidget(self._note)
        self._add = QPushButton("添加连接")
        self._add.clicked.connect(self._add_relation)
        row.addWidget(self._add)
        self._update = QPushButton("更新连接")
        self._update.clicked.connect(self._update_relation)
        row.addWidget(self._update)
        self._remove = QPushButton("删除连接")
        self._remove.clicked.connect(self._remove_relation)
        row.addWidget(self._remove)
        layout.addLayout(row)

    def set_elements(self, elements: list[BibleElement]) -> None:
        self._elements = list(elements)
        self._refresh_targets()

    def set_relations(self, relations: list[CharacterElementRelation]) -> None:
        self._relations = [relation.model_copy(deep=True) for relation in relations]
        self._refresh_relations()

    def relations(self) -> list[CharacterElementRelation]:
        return [relation.model_copy(deep=True) for relation in self._relations]

    def _refresh_targets(self) -> None:
        kind = CharacterElementRelationKind(self._kind.currentData())
        allowed = relation_definition(kind).allowed_target_types
        self._target.clear()
        for element in self._elements:
            if element.element_type in allowed:
                self._target.addItem(element.name, element.id)

    def _add_relation(self) -> None:
        kind, target = CharacterElementRelationKind(self._kind.currentData()), self._target.currentData()
        if not isinstance(target, str):
            return
        relation = CharacterElementRelation(kind=kind, target_element_id=target, note=self._note.text())
        if any((item.kind, item.target_element_id) == (kind, target) for item in self._relations):
            return
        self._relations.append(relation)
        self._refresh_relations()
        self.changed.emit()

    def _update_relation(self) -> None:
        row = self._list.currentRow()
        kind, target = CharacterElementRelationKind(self._kind.currentData()), self._target.currentData()
        if row < 0 or not isinstance(target, str):
            return
        if any(index != row and (item.kind, item.target_element_id) == (kind, target) for index, item in enumerate(self._relations)):
            return
        self._relations[row] = CharacterElementRelation(kind=kind, target_element_id=target, note=self._note.text())
        self._refresh_relations(row)
        self.changed.emit()

    def _remove_relation(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        self._relations.pop(row)
        self._refresh_relations()
        self.changed.emit()

    def _refresh_relations(self, selected: int = -1) -> None:
        self._list.clear()
        names = {element.id: element.name for element in self._elements}
        for index, relation in enumerate(self._relations):
            suffix = f"（{relation.note}）" if relation.note else ""
            self._list.addItem(QListWidgetItem(f"{relation_definition(relation.kind).label}：{names.get(relation.target_element_id, relation.target_element_id)}{suffix}"))
            if index == selected:
                self._list.setCurrentRow(index)

    def _show_relation(self, row: int) -> None:
        if row < 0 or row >= len(self._relations):
            return
        relation = self._relations[row]
        self._kind.setCurrentIndex(self._kind.findData(relation.kind))
        self._target.setCurrentIndex(self._target.findData(relation.target_element_id))
        self._note.setText(relation.note)
