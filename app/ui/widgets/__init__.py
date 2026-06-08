"""Reusable editor widgets shared across UI modules."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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


class StringListEditor(QWidget):
    """Editable list of strings with add/remove buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.setMaximumHeight(100)
        layout.addWidget(self._list)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(30)
        add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(add_btn)
        del_btn = QPushButton("-")
        del_btn.setFixedWidth(30)
        del_btn.clicked.connect(self._on_remove)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_add(self) -> None:
        item = QListWidgetItem("")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._list.addItem(item)
        self._list.editItem(item)

    def _on_remove(self) -> None:
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))

    def set_items(self, items: list[str]) -> None:
        self._list.clear()
        for text in items:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._list.addItem(item)

    def get_items(self) -> list[str]:
        result = []
        for i in range(self._list.count()):
            text = self._list.item(i).text().strip()
            if text:
                result.append(text)
        return result


class KeyValueTable(QWidget):
    """Editable key-value table with add/remove row buttons."""

    def __init__(self, headers: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._headers = headers
        self._table = QTableWidget(0, len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setMaximumHeight(120)
        layout.addWidget(self._table)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 行")
        add_btn.clicked.connect(self._on_add_row)
        btn_row.addWidget(add_btn)
        del_btn = QPushButton("- 行")
        del_btn.clicked.connect(self._on_remove_row)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_add_row(self) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        for col in range(len(self._headers)):
            self._table.setItem(row, col, QTableWidgetItem(""))

    def _on_remove_row(self) -> None:
        rows = set(idx.row() for idx in self._table.selectedIndexes())
        for row in sorted(rows, reverse=True):
            self._table.removeRow(row)

    def set_rows(self, rows: list[list[str]]) -> None:
        self._table.setRowCount(0)
        for row_data in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, text in enumerate(row_data[: len(self._headers)]):
                self._table.setItem(row, col, QTableWidgetItem(text))

    def rowCount(self) -> int:
        return self._table.rowCount()


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
