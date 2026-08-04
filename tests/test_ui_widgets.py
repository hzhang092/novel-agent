from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QPushButton, QTableWidget

from app.ui.widgets import KeyValueTable, StringListEditor


def test_string_list_reports_user_edits_once(qtbot):
    editor = StringListEditor()
    qtbot.addWidget(editor)
    changes = QSignalSpy(editor.changed)

    editor.set_items(["before"])
    assert changes.count() == 0

    editor.findChild(QListWidget).item(0).setText("after")
    assert changes.count() == 1
    buttons = editor.findChildren(QPushButton)

    buttons[0].click()
    assert changes.count() == 2

    editor.findChild(QListWidget).item(0).setSelected(True)
    buttons[1].click()
    assert changes.count() == 3


def test_string_list_read_only_keeps_selection_but_blocks_changes(qtbot):
    editor = StringListEditor()
    qtbot.addWidget(editor)
    editor.set_items(["readable"])

    editor.set_read_only(True)

    list_widget = editor.findChild(QListWidget)
    assert list_widget.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert list_widget.selectionMode() != QAbstractItemView.SelectionMode.NoSelection
    assert editor._button_row.isHidden()

    editor.set_read_only(False)

    assert not editor._button_row.isHidden()
    assert list_widget.editTriggers() != QAbstractItemView.EditTrigger.NoEditTriggers


def test_key_value_table_reports_user_edits_once(qtbot):
    editor = KeyValueTable(["key", "value"])
    qtbot.addWidget(editor)
    changes = QSignalSpy(editor.changed)

    editor.set_rows([["before", "value"]])
    assert changes.count() == 0

    editor.findChild(QTableWidget).item(0, 0).setText("after")
    assert changes.count() == 1
    buttons = editor.findChildren(QPushButton)

    buttons[0].click()
    assert changes.count() == 2

    editor.findChild(QTableWidget).selectRow(0)
    buttons[1].click()
    assert changes.count() == 3


def test_key_value_table_read_only_keeps_selection_but_blocks_changes(qtbot):
    editor = KeyValueTable(["key", "value"])
    qtbot.addWidget(editor)
    editor.set_rows([["readable", "selectable"]])
    before = editor.rows()

    editor.set_read_only(True)

    table = editor.findChild(QTableWidget)
    assert table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert table.selectionMode() != QAbstractItemView.SelectionMode.NoSelection
    assert editor._button_row.isHidden()
    assert editor.rows() == before

    editor.set_read_only(False)

    assert not editor._button_row.isHidden()
    assert table.editTriggers() != QAbstractItemView.EditTrigger.NoEditTriggers
