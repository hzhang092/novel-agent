"""Searchable popup for revealing existing editor fields or sections."""

from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class AddMenuItem:
    item_id: str
    label: str
    category: str
    description: str = ""
    keywords: tuple[str, ...] = ()


class SearchableAddMenu(QFrame):
    item_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        layout = QVBoxLayout(self)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search...")
        self._search.setAccessibleName("Search items")
        self._search.textChanged.connect(self._filter_items)
        self._search.installEventFilter(self)
        layout.addWidget(self._search)

        self._tree = QTreeWidget()
        self._tree.setObjectName("searchable-add-items")
        self._tree.setColumnCount(2)
        self._tree.setHeaderHidden(True)
        self._tree.itemClicked.connect(self._select_item)
        self._tree.itemActivated.connect(self._select_item)
        layout.addWidget(self._tree)

    def set_items(
        self,
        items: list[AddMenuItem],
        *,
        visible_ids: set[str],
        populated_ids: set[str],
    ) -> None:
        self._tree.clear()
        categories: dict[str, QTreeWidgetItem] = {}
        for item in items:
            category = categories.get(item.category)
            if category is None:
                category = QTreeWidgetItem(self._tree, [item.category])
                category.setFlags(category.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                categories[item.category] = category
            status = (
                "Added"
                if item.item_id in visible_ids
                else "Has data" if item.item_id in populated_ids else ""
            )
            child = QTreeWidgetItem(category, [item.label, status])
            child.setData(0, Qt.ItemDataRole.UserRole, item)
            if item.item_id in visible_ids:
                child.setFlags(
                    child.flags()
                    & ~Qt.ItemFlag.ItemIsEnabled
                    & ~Qt.ItemFlag.ItemIsSelectable
                )
        self._tree.expandAll()

    def open_below(self, anchor: QWidget) -> None:
        self._search.clear()
        self.move(anchor.mapToGlobal(QPoint(0, anchor.height())))
        self.show()
        self.raise_()
        self.activateWindow()
        self._search.setFocus(Qt.FocusReason.PopupFocusReason)

    def _filter_items(self, text: str) -> None:
        query = text.strip().casefold()
        for category_index in range(self._tree.topLevelItemCount()):
            category = self._tree.topLevelItem(category_index)
            any_visible = False
            for child_index in range(category.childCount()):
                child = category.child(child_index)
                item = child.data(0, Qt.ItemDataRole.UserRole)
                haystack = " ".join(
                    (item.label, item.description, *item.keywords)
                ).casefold()
                matches = query in haystack
                child.setHidden(not matches)
                any_visible |= matches
            category.setHidden(not any_visible)

    def _select_item(self, tree_item: QTreeWidgetItem, _column: int) -> None:
        item = tree_item.data(0, Qt.ItemDataRole.UserRole)
        if item is None:
            return
        self.item_selected.emit(item.item_id)
        self.hide()

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self._search
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Down
        ):
            for category_index in range(self._tree.topLevelItemCount()):
                category = self._tree.topLevelItem(category_index)
                if category.isHidden():
                    continue
                for child_index in range(category.childCount()):
                    child = category.child(child_index)
                    if (
                        not child.isHidden()
                        and child.flags() & Qt.ItemFlag.ItemIsEnabled
                    ):
                        self._tree.setCurrentItem(child)
                        self._tree.setFocus()
                        return True
        return super().eventFilter(watched, event)
