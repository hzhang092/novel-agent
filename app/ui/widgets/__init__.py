"""Reusable editor widgets shared across UI modules."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets.collapsible_section import CollapsibleSection
from app.ui.widgets.detail_field import DetailFieldContainer
from app.ui.widgets.searchable_add_menu import AddMenuItem, SearchableAddMenu


class StringListEditor(QWidget):
    """Editable list of strings with add/remove buttons."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._editable_triggers = self._list.editTriggers()
        self._list.setMaximumHeight(100)
        self._list.itemChanged.connect(self._on_item_changed)
        self._populating = False
        layout.addWidget(self._list)
        btn_row = QHBoxLayout()
        self._add_button = QPushButton("+")
        self._add_button.setFixedWidth(30)
        self._add_button.clicked.connect(self._on_add)
        btn_row.addWidget(self._add_button)
        self._delete_button = QPushButton("-")
        self._delete_button.setFixedWidth(30)
        self._delete_button.clicked.connect(self._on_remove)
        btn_row.addWidget(self._delete_button)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_add(self) -> None:
        item = QListWidgetItem("")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._list.addItem(item)
        self._list.editItem(item)
        self.changed.emit()

    def _on_remove(self) -> None:
        selected = self._list.selectedItems()
        for item in selected:
            self._list.takeItem(self._list.row(item))
        if selected:
            self.changed.emit()

    def _on_item_changed(self) -> None:
        if not self._populating:
            self.changed.emit()

    def set_items(self, items: list[str]) -> None:
        self._populating = True
        try:
            self._list.clear()
            for text in items:
                item = QListWidgetItem(text)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self._list.addItem(item)
        finally:
            self._populating = False

    def get_items(self) -> list[str]:
        result = []
        for i in range(self._list.count()):
            text = self._list.item(i).text().strip()
            if text:
                result.append(text)
        return result

    def set_read_only(self, read_only: bool) -> None:
        self._list.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
            if read_only
            else self._editable_triggers
        )
        self._add_button.setEnabled(not read_only)
        self._delete_button.setEnabled(not read_only)


class KeyValueTable(QWidget):
    """Editable key-value table with add/remove row buttons."""

    changed = pyqtSignal()

    def __init__(self, headers: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._headers = headers
        self._table = QTableWidget(0, len(headers))
        self._editable_triggers = self._table.editTriggers()
        self._table.setHorizontalHeaderLabels(headers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setMaximumHeight(120)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._populating = False
        layout.addWidget(self._table)
        btn_row = QHBoxLayout()
        self._add_button = QPushButton("+ 行")
        self._add_button.clicked.connect(self._on_add_row)
        btn_row.addWidget(self._add_button)
        self._delete_button = QPushButton("- 行")
        self._delete_button.clicked.connect(self._on_remove_row)
        btn_row.addWidget(self._delete_button)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_add_row(self) -> None:
        row = self._table.rowCount()
        self._populating = True
        try:
            self._table.insertRow(row)
            for col in range(len(self._headers)):
                self._table.setItem(row, col, QTableWidgetItem(""))
        finally:
            self._populating = False
        self.changed.emit()

    def _on_remove_row(self) -> None:
        rows = set(idx.row() for idx in self._table.selectedIndexes())
        for row in sorted(rows, reverse=True):
            self._table.removeRow(row)
        if rows:
            self.changed.emit()

    def _on_cell_changed(self) -> None:
        if not self._populating:
            self.changed.emit()

    def set_rows(self, rows: list[list[str]]) -> None:
        self._populating = True
        try:
            self._table.setRowCount(0)
            for row_data in rows:
                row = self._table.rowCount()
                self._table.insertRow(row)
                for col, text in enumerate(row_data[: len(self._headers)]):
                    self._table.setItem(row, col, QTableWidgetItem(text))
        finally:
            self._populating = False

    def rowCount(self) -> int:
        return self._table.rowCount()

    def set_read_only(self, read_only: bool) -> None:
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
            if read_only
            else self._editable_triggers
        )
        self._add_button.setEnabled(not read_only)
        self._delete_button.setEnabled(not read_only)


def read_table_cell(table: QTableWidget, row: int, col: int) -> str:
    """Read a cell from a QTableWidget."""
    item = table.item(row, col)
    return item.text().strip() if item else ""


def set_combo(layout: QHBoxLayout, value: str) -> None:
    """Set a combo box inside a labeled row layout by its text value."""
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if isinstance(w, QComboBox):
            idx = w.findText(value)
            if idx >= 0:
                w.setCurrentIndex(idx)
            return


def combo_val(layout: QHBoxLayout) -> str:
    """Get the current text from a combo box inside a labeled row layout."""
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if isinstance(w, QComboBox):
            return w.currentText()
    return ""
