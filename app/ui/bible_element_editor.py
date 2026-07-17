"""Typed editor for one Story Bible element."""

from collections import Counter

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.domain.bible_relation_catalog import RELATION_DEFINITIONS, relation_definition
from app.storage.bible_models import (
    BibleElement,
    BibleElementBase,
    BibleElementRelation,
    BibleElementType,
    FactionElement,
    HistoricalEventElement,
    LocationElement,
    PowerRealm,
    PowerSystemElement,
    TerminologyElement,
    normalize_text,
)
from app.ui.bible_element_list import ELEMENT_TYPE_DETAILS
from app.ui.widgets import KeyValueTable, StringListEditor, read_table_cell


def _semantic_data(element: BibleElementBase) -> dict:
    return element.model_dump(exclude={"revision", "updated_at"})


class BibleElementEditor(QWidget):
    dirty_changed = pyqtSignal(bool)
    changed = pyqtSignal()
    element_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._baseline: BibleElement | None = None
        self._elements: list[BibleElement] = []
        self._dirty = False
        self._populating = False
        self._pages: dict[BibleElementType, QWidget] = {}
        self._setup_ui()
        self._connect_changes()

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def load_element(
        self,
        element: BibleElement,
        *,
        elements: list[BibleElement] | None = None,
        inbound_relations: list[tuple[BibleElement, BibleElementRelation]] | None = None,
    ) -> None:
        self._baseline = element.model_copy(deep=True)
        self._elements = list(elements or [element])
        self._populating = True
        try:
            self._name.setText(element.name)
            self._aliases.set_items(element.aliases)
            self._summary.setPlainText(element.summary)
            self._tags.set_items(element.tags)
            self._importance.setValue(element.importance)
            self._always_include.setChecked(element.always_include)
            self._typed_stack.setCurrentWidget(self._pages[element.element_type])
            self._populate_typed_fields(element)
            self._populate_relations(element.relationships)
            self._populate_inbound(inbound_relations or [])
        finally:
            self._populating = False
        self._set_dirty(False)

    def gather_element(self) -> BibleElement:
        if self._baseline is None:
            raise RuntimeError("No Bible Element is loaded")
        values = {
            "name": self._name.text(),
            "aliases": self._aliases.get_items(),
            "summary": self._summary.toPlainText(),
            "tags": self._tags.get_items(),
            "importance": self._importance.value(),
            "always_include": self._always_include.isChecked(),
            "relationships": self._gather_relations(),
        }
        values.update(self._gather_typed_fields(self._baseline))
        data = self._baseline.model_dump()
        data.update(values)
        return type(self._baseline).model_validate(data)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._name = QLineEdit()
        self._aliases = StringListEditor()
        self._summary = QTextEdit()
        self._summary.setMaximumHeight(80)
        self._tags = StringListEditor()
        self._importance = QSpinBox()
        self._importance.setRange(1, 5)
        self._always_include = QCheckBox("Always include in generation context")
        for label, widget in (
            ("Name", self._name),
            ("Aliases", self._aliases),
            ("Summary", self._summary),
            ("Tags", self._tags),
            ("Importance", self._importance),
        ):
            layout.addWidget(QLabel(label))
            layout.addWidget(widget)
        layout.addWidget(self._always_include)

        self._typed_stack = QStackedWidget()
        self._build_typed_pages()
        layout.addWidget(self._typed_stack)

        layout.addWidget(QLabel("Relationships"))
        self._relations = QTableWidget(0, 3)
        self._relations.setHorizontalHeaderLabels(["Kind", "Target", "Note"])
        self._relations.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._relations)
        relation_buttons = QHBoxLayout()
        self._add_relation = QPushButton("+ Add relationship")
        self._add_relation.clicked.connect(self._add_empty_relation)
        relation_buttons.addWidget(self._add_relation)
        self._remove_relation = QPushButton("Remove")
        self._remove_relation.clicked.connect(self._remove_selected_relations)
        relation_buttons.addWidget(self._remove_relation)
        relation_buttons.addStretch()
        layout.addLayout(relation_buttons)

        layout.addWidget(QLabel("Referenced by"))
        self._inbound = QTreeWidget()
        self._inbound.setHeaderHidden(True)
        self._inbound.setMaximumHeight(100)
        self._inbound.itemActivated.connect(self._request_inbound_source)
        layout.addWidget(self._inbound)

    def _build_typed_pages(self) -> None:
        self._faction_description = QTextEdit()
        self._faction_goals = StringListEditor()
        self._faction_ideology = QTextEdit()
        self._add_page(
            BibleElementType.FACTION,
            (
                ("Description", self._faction_description),
                ("Goals", self._faction_goals),
                ("Ideology", self._faction_ideology),
            ),
        )

        self._term_definition = QTextEdit()
        self._term_category = QLineEdit()
        self._term_examples = StringListEditor()
        self._add_page(
            BibleElementType.TERMINOLOGY,
            (
                ("Definition", self._term_definition),
                ("Category", self._term_category),
                ("Examples", self._term_examples),
            ),
        )

        self._history_time = QLineEdit()
        self._history_description = QTextEdit()
        self._history_consequences = StringListEditor()
        self._add_page(
            BibleElementType.HISTORICAL_EVENT,
            (
                ("Time", self._history_time),
                ("Description", self._history_description),
                ("Consequences", self._history_consequences),
            ),
        )

        self._power_realms = KeyValueTable(["Realm", "Abilities (one per line)"])
        self._power_limitations = StringListEditor()
        self._power_costs = StringListEditor()
        self._power_resources = StringListEditor()
        self._power_forbidden = StringListEditor()
        self._add_page(
            BibleElementType.POWER_SYSTEM,
            (
                ("Realms", self._power_realms),
                ("Limitations", self._power_limitations),
                ("Costs", self._power_costs),
                ("Rare resources", self._power_resources),
                ("Forbidden methods", self._power_forbidden),
            ),
        )

        self._location_description = QTextEdit()
        self._location_atmosphere = QTextEdit()
        self._location_features = StringListEditor()
        self._add_page(
            BibleElementType.LOCATION,
            (
                ("Description", self._location_description),
                ("Atmosphere", self._location_atmosphere),
                ("Notable features", self._location_features),
            ),
        )

    def _add_page(self, element_type: BibleElementType, fields) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        for label, widget in fields:
            layout.addWidget(QLabel(label))
            layout.addWidget(widget)
        self._pages[element_type] = page
        self._typed_stack.addWidget(page)

    def _connect_changes(self) -> None:
        for widget in (
            self._name,
            self._term_category,
            self._history_time,
        ):
            widget.textChanged.connect(self._recompute_dirty)
        for widget in (
            self._summary,
            self._faction_description,
            self._faction_ideology,
            self._term_definition,
            self._history_description,
            self._location_description,
            self._location_atmosphere,
        ):
            widget.textChanged.connect(self._recompute_dirty)
        for widget in (
            self._aliases,
            self._tags,
            self._faction_goals,
            self._term_examples,
            self._history_consequences,
            self._power_limitations,
            self._power_costs,
            self._power_resources,
            self._power_forbidden,
            self._location_features,
            self._power_realms,
        ):
            widget.changed.connect(self._recompute_dirty)
        self._importance.valueChanged.connect(self._recompute_dirty)
        self._always_include.toggled.connect(self._recompute_dirty)
        self._relations.cellChanged.connect(self._recompute_dirty)

    def _populate_typed_fields(self, element: BibleElement) -> None:
        if isinstance(element, FactionElement):
            self._faction_description.setPlainText(element.description)
            self._faction_goals.set_items(element.goals)
            self._faction_ideology.setPlainText(element.ideology)
        elif isinstance(element, TerminologyElement):
            self._term_definition.setPlainText(element.definition)
            self._term_category.setText(element.category)
            self._term_examples.set_items(element.examples)
        elif isinstance(element, HistoricalEventElement):
            self._history_time.setText(element.time_label)
            self._history_description.setPlainText(element.description)
            self._history_consequences.set_items(element.consequences)
        elif isinstance(element, PowerSystemElement):
            self._power_realms.set_rows(
                [[realm.name, "\n".join(realm.abilities)] for realm in element.realms]
            )
            self._power_limitations.set_items(element.limitations)
            self._power_costs.set_items(element.costs)
            self._power_resources.set_items(element.rare_resources)
            self._power_forbidden.set_items(element.forbidden_methods)
        elif isinstance(element, LocationElement):
            self._location_description.setPlainText(element.description)
            self._location_atmosphere.setPlainText(element.atmosphere)
            self._location_features.set_items(element.notable_features)

    def _gather_typed_fields(self, element: BibleElement) -> dict:
        if isinstance(element, FactionElement):
            return {
                "description": self._faction_description.toPlainText(),
                "goals": self._faction_goals.get_items(),
                "ideology": self._faction_ideology.toPlainText(),
            }
        if isinstance(element, TerminologyElement):
            return {
                "definition": self._term_definition.toPlainText(),
                "category": self._term_category.text(),
                "examples": self._term_examples.get_items(),
            }
        if isinstance(element, HistoricalEventElement):
            return {
                "time_label": self._history_time.text(),
                "description": self._history_description.toPlainText(),
                "consequences": self._history_consequences.get_items(),
            }
        if isinstance(element, PowerSystemElement):
            realms = []
            for row in range(self._power_realms.rowCount()):
                name = read_table_cell(self._power_realms._table, row, 0)
                if name:
                    abilities = [
                        value.strip()
                        for value in read_table_cell(
                            self._power_realms._table, row, 1
                        ).splitlines()
                        if value.strip()
                    ]
                    realms.append(PowerRealm(name=name, abilities=abilities))
            return {
                "realms": realms,
                "limitations": self._power_limitations.get_items(),
                "costs": self._power_costs.get_items(),
                "rare_resources": self._power_resources.get_items(),
                "forbidden_methods": self._power_forbidden.get_items(),
            }
        return {
            "description": self._location_description.toPlainText(),
            "atmosphere": self._location_atmosphere.toPlainText(),
            "notable_features": self._location_features.get_items(),
        }

    def _populate_relations(self, relations: list[BibleElementRelation]) -> None:
        self._relations.setRowCount(0)
        for relation in relations:
            self._add_relation_row(relation)

    def _add_empty_relation(self) -> None:
        self._add_relation_row(None)
        self._recompute_dirty()

    def _add_relation_row(self, relation: BibleElementRelation | None) -> None:
        row = self._relations.rowCount()
        self._relations.insertRow(row)
        kind = QComboBox()
        for definition in RELATION_DEFINITIONS.values():
            kind.addItem(definition.label, definition.kind)
        if relation is not None:
            kind.setCurrentIndex(kind.findData(relation.kind))
        kind.currentIndexChanged.connect(self._recompute_dirty)
        self._relations.setCellWidget(row, 0, kind)

        target = QComboBox()
        target.setEditable(True)
        target.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        target.lineEdit().setPlaceholderText("Search by name, alias, or tag")
        current_id = self._baseline.id if self._baseline else ""
        candidates = [element for element in self._elements if element.id != current_id]
        duplicates = Counter(
            (normalize_text(element.name), element.element_type) for element in candidates
        )
        for element in candidates:
            type_label = ELEMENT_TYPE_DETAILS[element.element_type][1]
            label = f"{element.name} · {type_label}"
            if duplicates[(normalize_text(element.name), element.element_type)] > 1:
                label += f" · {element.id[:8]}"
            target.addItem(label, element.id)
            target.setItemData(
                target.count() - 1,
                normalize_text(" ".join((element.name, *element.aliases, *element.tags))),
                Qt.ItemDataRole.UserRole + 1,
            )
        target_id = relation.target_element_id if relation is not None else ""
        index = target.findData(target_id)
        if target_id and index < 0:
            target.addItem(f"⚠ Missing element · {target_id}", target_id)
            target.setItemData(
                target.count() - 1,
                normalize_text(target_id),
                Qt.ItemDataRole.UserRole + 1,
            )
            index = target.count() - 1
        if index >= 0:
            target.setCurrentIndex(index)
        target.lineEdit().textEdited.connect(
            lambda text, combo=target: self._filter_relation_targets(combo, text)
        )
        target.activated.connect(
            lambda _index, combo=target: self._filter_relation_targets(combo, "")
        )
        target.currentIndexChanged.connect(self._recompute_dirty)
        self._relations.setCellWidget(row, 1, target)
        self._relations.setItem(row, 2, QTableWidgetItem(relation.note if relation else ""))

    @staticmethod
    def _filter_relation_targets(combo: QComboBox, text: str) -> None:
        terms = normalize_text(text).split()
        for index in range(combo.count()):
            document = combo.itemData(index, Qt.ItemDataRole.UserRole + 1) or ""
            combo.view().setRowHidden(
                index, not all(term in document for term in terms)
            )

    def _remove_selected_relations(self) -> None:
        rows = {index.row() for index in self._relations.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            self._relations.removeRow(row)
        if rows:
            self._recompute_dirty()

    def _gather_relations(self) -> list[BibleElementRelation]:
        relations = []
        for row in range(self._relations.rowCount()):
            kind = self._relations.cellWidget(row, 0).currentData()
            target = self._relations.cellWidget(row, 1).currentData()
            note_item = self._relations.item(row, 2)
            if target:
                relations.append(
                    BibleElementRelation(
                        kind=kind,
                        target_element_id=target,
                        note=note_item.text() if note_item else "",
                    )
                )
        return relations

    def _populate_inbound(
        self, inbound_relations: list[tuple[BibleElement, BibleElementRelation]]
    ) -> None:
        self._inbound.clear()
        for source, relation in inbound_relations:
            item = QTreeWidgetItem(
                self._inbound,
                [f"{source.name} — {relation_definition(relation.kind).inverse_label}"],
            )
            item.setData(0, Qt.ItemDataRole.UserRole, source.id)

    def _request_inbound_source(self, item: QTreeWidgetItem, _column: int) -> None:
        self.element_requested.emit(item.data(0, Qt.ItemDataRole.UserRole))

    def _recompute_dirty(self, *_args) -> None:
        if self._populating or self._baseline is None:
            return
        self._set_dirty(_semantic_data(self.gather_element()) != _semantic_data(self._baseline))
        self.changed.emit()

    def _set_dirty(self, dirty: bool) -> None:
        if dirty != self._dirty:
            self._dirty = dirty
            self.dirty_changed.emit(dirty)
