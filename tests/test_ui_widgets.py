from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QAbstractItemView, QListWidget, QPushButton, QTableWidget

from app.ui.widgets import KeyValueTable, StringListEditor


def test_string_list_reports_edits_but_not_population(qtbot):
    editor = StringListEditor()
    qtbot.addWidget(editor)
    changes = QSignalSpy(editor.changed)

    editor.set_items(["before"])
    assert len(changes) == 0

    editor.findChild(QListWidget).item(0).setText("after")
    assert len(changes) == 1


def test_string_list_reports_add_and_remove_once(qtbot):
    editor = StringListEditor()
    qtbot.addWidget(editor)
    changes = QSignalSpy(editor.changed)
    buttons = editor.findChildren(QPushButton)

    buttons[0].click()
    assert len(changes) == 1

    editor.findChild(QListWidget).item(0).setSelected(True)
    buttons[1].click()
    assert len(changes) == 2


def test_string_list_read_only_keeps_selection_but_blocks_changes(qtbot):
    editor = StringListEditor()
    qtbot.addWidget(editor)
    editor.set_items(["readable"])

    editor.set_read_only(True)

    list_widget = editor.findChild(QListWidget)
    assert list_widget.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert list_widget.selectionMode() != QAbstractItemView.SelectionMode.NoSelection
    assert all(not button.isEnabled() for button in editor.findChildren(QPushButton))


def test_key_value_table_reports_edits_but_not_population(qtbot):
    editor = KeyValueTable(["key", "value"])
    qtbot.addWidget(editor)
    changes = QSignalSpy(editor.changed)

    editor.set_rows([["before", "value"]])
    assert len(changes) == 0

    editor.findChild(QTableWidget).item(0, 0).setText("after")
    assert len(changes) == 1


def test_key_value_table_reports_add_and_remove_once(qtbot):
    editor = KeyValueTable(["key", "value"])
    qtbot.addWidget(editor)
    changes = QSignalSpy(editor.changed)
    buttons = editor.findChildren(QPushButton)

    buttons[0].click()
    assert len(changes) == 1

    editor.findChild(QTableWidget).selectRow(0)
    buttons[1].click()
    assert len(changes) == 2


def test_key_value_table_read_only_keeps_selection_but_blocks_changes(qtbot):
    editor = KeyValueTable(["key", "value"])
    qtbot.addWidget(editor)
    editor.set_rows([["readable", "selectable"]])

    editor.set_read_only(True)

    table = editor.findChild(QTableWidget)
    assert table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert table.selectionMode() != QAbstractItemView.SelectionMode.NoSelection
    assert all(not button.isEnabled() for button in editor.findChildren(QPushButton))
