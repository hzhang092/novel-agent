"""Searchable, grouped list of typed Story Bible elements."""

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.domain.bible_search import search_elements
from app.storage.bible_models import BibleElement, BibleElementType


ELEMENT_TYPE_DETAILS = {
    BibleElementType.LOCATION: ("Locations", "Location"),
    BibleElementType.FACTION: ("Factions", "Faction"),
    BibleElementType.HISTORICAL_EVENT: ("Historical Events", "Historical event"),
    BibleElementType.POWER_SYSTEM: ("Power Systems", "Power system"),
    BibleElementType.TERMINOLOGY: ("Terminology", "Terminology"),
}


class BibleElementList(QWidget):
    element_selected = pyqtSignal(str)
    filters_changed = pyqtSignal(str, object)
    group_collapsed_changed = pyqtSignal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._elements: list[BibleElement] = []
        self._unsaved_ids: set[str] = set()
        self._selected_id: str | None = None
        self._collapsed_type_groups: set[str] = set()
        self._current_scene_element_ids: set[str] | None = None
        self._rebuilding = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search elements...")
        self._search.textChanged.connect(self._rebuild)
        layout.addWidget(self._search)

        self._type_filter = QComboBox()
        self._type_filter.addItem("All types", "")
        for element_type, (_group, label) in ELEMENT_TYPE_DETAILS.items():
            self._type_filter.addItem(label, element_type.value)
        self._type_filter.currentIndexChanged.connect(self._on_filters_changed)
        layout.addWidget(self._type_filter)

        self._tag_filter = QLineEdit()
        self._tag_filter.setPlaceholderText("Filter tags (comma separated)")
        self._tag_filter.textChanged.connect(self._on_filters_changed)
        layout.addWidget(self._tag_filter)

        self._scope_filter = QComboBox()
        self._scope_filter.addItem("All elements", "")
        self._scope_filter.addItem("Always included", "always")
        self._scope_filter.addItem("Referenced by current scene", "referenced")
        self._scope_filter.currentIndexChanged.connect(self._rebuild)
        layout.addWidget(self._scope_filter)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.currentItemChanged.connect(self._on_selection_changed)
        self._tree.itemCollapsed.connect(
            lambda item: self._on_group_expanded(item, False)
        )
        self._tree.itemExpanded.connect(
            lambda item: self._on_group_expanded(item, True)
        )
        layout.addWidget(self._tree)

    def set_elements(self, elements: list[BibleElement]) -> None:
        self._elements = list(elements)
        self._rebuild()

    def set_query(self, query: str) -> None:
        self._search.setText(query)

    def set_type_filter(self, element_type: str) -> None:
        index = self._type_filter.findData(element_type)
        blocker = QSignalBlocker(self._type_filter)
        self._type_filter.setCurrentIndex(max(index, 0))
        del blocker
        self._rebuild()

    def set_tag_filters(self, tags: list[str]) -> None:
        blocker = QSignalBlocker(self._tag_filter)
        self._tag_filter.setText(", ".join(tags))
        del blocker
        self._rebuild()

    def type_filter(self) -> str:
        return self._type_filter.currentData() or ""

    def tag_filters(self) -> list[str]:
        return self._tag_filters()

    def set_collapsed_type_groups(self, groups: list[str]) -> None:
        self._collapsed_type_groups = set(groups)
        self._rebuild()

    def collapsed_type_groups(self) -> list[str]:
        return sorted(self._collapsed_type_groups)

    def set_current_scene_element_ids(self, element_ids: set[str] | None) -> None:
        self._current_scene_element_ids = (
            None if element_ids is None else set(element_ids)
        )
        self._rebuild()

    def set_unsaved_ids(self, element_ids: set[str]) -> None:
        self._unsaved_ids = set(element_ids)
        self._rebuild()

    def select_element(self, element_id: str) -> None:
        item = self._find_item(element_id)
        if item is not None:
            self._tree.setCurrentItem(item)

    def selected_element_id(self) -> str | None:
        item = self._tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None

    def _tag_filters(self) -> list[str]:
        return [tag.strip() for tag in self._tag_filter.text().split(",") if tag.strip()]

    def _rebuild(self, *_args) -> None:
        selected_id = self.selected_element_id() or self._selected_id
        scope = self._scope_filter.currentData()
        filtered = search_elements(
            self._elements,
            query=self._search.text(),
            type_filter=self._type_filter.currentData() or "",
            tag_filters=self._tag_filters(),
            always_included=scope == "always",
            referenced_ids=(
                self._current_scene_element_ids or set()
                if scope == "referenced"
                else None
            ),
        )
        blocker = QSignalBlocker(self._tree)
        self._rebuilding = True
        try:
            self._tree.clear()
            overview = QTreeWidgetItem(self._tree, ["World Overview"])
            overview.setData(0, Qt.ItemDataRole.UserRole, "overview")
            for element_type, (group_label, type_label) in ELEMENT_TYPE_DETAILS.items():
                elements = [item for item in filtered if item.element_type == element_type]
                if not elements:
                    continue
                group = QTreeWidgetItem(self._tree, [f"{group_label} ({len(elements)})"])
                group.setData(0, Qt.ItemDataRole.UserRole + 1, element_type.value)
                group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                for element in elements:
                    marker = "* " if element.id in self._unsaved_ids else ""
                    tags = f" · {', '.join(element.tags)}" if element.tags else ""
                    item = QTreeWidgetItem(group, [f"{marker}{element.name} · {type_label}{tags}"])
                    item.setData(0, Qt.ItemDataRole.UserRole, element.id)
                group.setExpanded(element_type.value not in self._collapsed_type_groups)
            item = self._find_item(selected_id) if selected_id else None
            if item is not None:
                self._tree.setCurrentItem(item)
        finally:
            self._rebuilding = False
            del blocker

    def _find_item(self, element_id: str) -> QTreeWidgetItem | None:
        overview = self._tree.topLevelItem(0)
        if overview is not None and overview.data(0, Qt.ItemDataRole.UserRole) == element_id:
            return overview
        for group_index in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(group_index)
            for item_index in range(group.childCount()):
                item = group.child(item_index)
                if item.data(0, Qt.ItemDataRole.UserRole) == element_id:
                    return item
        return None

    def _on_selection_changed(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        if current is None:
            return
        element_id = current.data(0, Qt.ItemDataRole.UserRole)
        if element_id:
            self._selected_id = element_id
            self.element_selected.emit(element_id)

    def _on_filters_changed(self, *_args) -> None:
        self._rebuild()
        self.filters_changed.emit(self.type_filter(), self.tag_filters())

    def _on_group_expanded(self, item: QTreeWidgetItem, expanded: bool) -> None:
        if self._rebuilding:
            return
        group_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if not group_id:
            return
        if expanded:
            self._collapsed_type_groups.discard(group_id)
        else:
            self._collapsed_type_groups.add(group_id)
        self.group_collapsed_changed.emit(group_id, not expanded)
