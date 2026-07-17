from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLineEdit, QToolButton

from app.ui.widgets.detail_field import DetailFieldContainer


def test_focus_editor_transfers_focus(qtbot):
    editor = QLineEdit()
    field = DetailFieldContainer("age", "Age", editor)
    qtbot.addWidget(field)
    field.show()

    field.focus_editor()

    qtbot.waitUntil(editor.hasFocus)


def test_hide_action_describes_non_destructive_behavior_and_emits(qtbot):
    field = DetailFieldContainer("age", "Age", QLineEdit("28"))
    fixed = DetailFieldContainer(
        "name", "Name", QLineEdit("Lin"), hideable=False
    )
    qtbot.addWidget(field)
    qtbot.addWidget(fixed)

    assert fixed.findChild(QToolButton) is None
    hide_button = field.findChild(QToolButton)
    assert hide_button.text() == "从编辑器隐藏"
    assert (
        hide_button.toolTip()
        == "隐藏不会删除内容，也不会影响生成上下文。"
    )
    with qtbot.waitSignal(field.hide_requested) as signal:
        qtbot.mouseClick(hide_button, Qt.MouseButton.LeftButton)

    assert signal.args == ["age"]
