"""ID-backed multi-select picker for Story Bible elements."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.storage.bible_models import BibleElement, BibleElementType, normalize_text


_TYPE_DETAILS = {
    BibleElementType.LOCATION: ("Locations", "Location"),
    BibleElementType.FACTION: ("Factions", "Faction"),
    BibleElementType.HISTORICAL_EVENT: ("Historical Events", "Historical event"),
    BibleElementType.POWER_SYSTEM: ("Power Systems", "Power system"),
    BibleElementType.TERMINOLOGY: ("Terminology", "Terminology"),
}


class ElementReferencePicker(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._elements: list[BibleElement] = []
        self._selected_ids: list[str] = []
        self._populating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search and select elements...")
        self._search.setAccessibleName("Search Story Bible elements")
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setMaximumHeight(180)
        self._tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._tree)

    def set_elements(self, elements: list[BibleElement]) -> None:
        self._elements = list(elements)
        self._rebuild()

    def set_selected_ids(self, element_ids: list[str]) -> None:
        self._selected_ids = list(dict.fromkeys(element_ids))
        self._rebuild()

    def selected_ids(self) -> list[str]:
        return list(self._selected_ids)

    def _rebuild(self) -> None:
        self._populating = True
        try:
            self._tree.clear()
            stored_ids = {element.id for element in self._elements}
            for element_type, (group_label, type_label) in _TYPE_DETAILS.items():
                elements = [
                    element for element in self._elements if element.element_type == element_type
                ]
                if not elements:
                    continue
                group = QTreeWidgetItem(self._tree, [group_label])
                group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                for element in elements:
                    item = QTreeWidgetItem(group, [f"{element.name} · {type_label}"])
                    item.setData(0, Qt.ItemDataRole.UserRole, element.id)
                    item.setData(
                        0,
                        Qt.ItemDataRole.UserRole + 1,
                        normalize_text(" ".join((element.name, *element.aliases, *element.tags))),
                    )
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(
                        0,
                        Qt.CheckState.Checked
                        if element.id in self._selected_ids
                        else Qt.CheckState.Unchecked,
                    )

            missing_ids = [
                element_id for element_id in self._selected_ids if element_id not in stored_ids
            ]
            if missing_ids:
                group = QTreeWidgetItem(self._tree, ["Missing References"])
                group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                for element_id in missing_ids:
                    item = QTreeWidgetItem(group, [f"⚠ Missing element · {element_id}"])
                    item.setData(0, Qt.ItemDataRole.UserRole, element_id)
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, normalize_text(element_id))
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.CheckState.Checked)
            self._tree.expandAll()
            self._apply_filter(self._search.text())
        finally:
            self._populating = False

    def _apply_filter(self, text: str) -> None:
        terms = normalize_text(text).split()
        for group_index in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(group_index)
            any_visible = False
            for item_index in range(group.childCount()):
                item = group.child(item_index)
                document = item.data(0, Qt.ItemDataRole.UserRole + 1) or ""
                visible = all(term in document for term in terms)
                item.setHidden(not visible)
                any_visible |= visible
            group.setHidden(not any_visible)

    def _on_item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._populating:
            return
        element_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not element_id:
            return
        if item.checkState(0) == Qt.CheckState.Checked:
            if element_id not in self._selected_ids:
                self._selected_ids.append(element_id)
        elif element_id in self._selected_ids:
            self._selected_ids.remove(element_id)
        self.changed.emit()
