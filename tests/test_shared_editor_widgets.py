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
