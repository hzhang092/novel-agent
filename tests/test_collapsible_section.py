from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QToolButton

from app.ui.widgets.collapsible_section import CollapsibleSection


def test_clicking_header_collapses_section_and_emits(qtbot):
    section = CollapsibleSection("Motivation", section_id="motivation")
    section.set_content_widget(QLabel("content"))
    qtbot.addWidget(section)
    section.show()

    header = section.findChild(QPushButton, "collapsible-section-header")
    with qtbot.waitSignal(section.expanded_changed) as signal:
        qtbot.mouseClick(header, Qt.MouseButton.LeftButton)

    assert signal.args == [False]
    assert section.content_widget().isHidden()


def test_programmatic_loading_is_silent_and_preserves_content(qtbot):
    section = CollapsibleSection("Motivation", section_id="motivation")
    editor = QLineEdit("kept")
    section.set_content_widget(editor)
    qtbot.addWidget(section)

    with qtbot.assertNotEmitted(section.expanded_changed):
        section.set_expanded(False)
        section.set_expanded(True)

    assert editor.text() == "kept"
    assert not editor.isHidden()


def test_header_supports_space_and_enter(qtbot):
    section = CollapsibleSection("Motivation", section_id="motivation")
    section.set_content_widget(QLabel("content"))
    qtbot.addWidget(section)
    section.show()
    header = section.findChild(QPushButton, "collapsible-section-header")
    header.setFocus()

    qtbot.keyClick(header, Qt.Key.Key_Space)
    assert section.content_widget().isHidden()

    qtbot.keyClick(header, Qt.Key.Key_Return)
    assert not section.content_widget().isHidden()


def test_hide_action_is_only_available_when_requested(qtbot):
    fixed = CollapsibleSection("Core", section_id="core")
    optional = CollapsibleSection(
        "Factions", section_id="factions", hideable=True
    )
    qtbot.addWidget(fixed)
    qtbot.addWidget(optional)

    assert fixed.findChild(QToolButton) is None
    hide_button = optional.findChild(QToolButton)
    assert hide_button.toolTip() == "Hide section"
    with qtbot.waitSignal(optional.hide_requested):
        qtbot.mouseClick(hide_button, Qt.MouseButton.LeftButton)
