from PySide6.QtWidgets import QTableWidget

from app.ui.widgets import KeyValueTable


def test_key_value_rows_preserve_order_empty_cells_and_return_copies(qtbot):
    editor = KeyValueTable(["key", "value"])
    qtbot.addWidget(editor)
    editor.set_rows([[" first ", " one "], ["second"], ["", "three"]])

    rows = editor.rows()

    assert rows == [["first", "one"], ["second", ""], ["", "three"]]
    assert editor.row_count() == 3
    rows[0][0] = "changed"
    assert editor.rows()[0][0] == "first"


def test_key_value_rows_are_unchanged_by_read_only_mode(qtbot):
    editor = KeyValueTable(["key", "value"])
    qtbot.addWidget(editor)
    editor.set_rows([["readable", "selectable"]])

    before = editor.rows()
    editor.set_read_only(True)

    assert editor.rows() == before
    assert editor.findChild(QTableWidget).item(0, 0).text() == "readable"
