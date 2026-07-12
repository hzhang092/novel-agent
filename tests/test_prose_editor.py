"""Tests for the prose editor widget."""

from app.ui.widgets.prose_editor import ProseEditorWidget


def test_version_selector_emits_selected_version(qtbot):
    widget = ProseEditorWidget()
    qtbot.addWidget(widget)
    selected: list[str] = []
    widget.version_selected.connect(selected.append)

    widget.set_versions(["v2", "v1", "legacy"], current="v2")

    assert widget.current_version() == "v2"
    assert widget._version_combo.itemText(0) == "已选 (v2)"
    widget._version_combo.setCurrentIndex(1)
    assert selected == ["v1"]


def test_version_selector_disabled_for_single_version(qtbot):
    widget = ProseEditorWidget()
    qtbot.addWidget(widget)

    widget.set_versions(["v1"], current="v1")

    assert not widget._version_combo.isEnabled()


def test_set_active_button_emits_current_version(qtbot):
    widget = ProseEditorWidget()
    qtbot.addWidget(widget)
    activated: list[str] = []
    widget.set_active_requested.connect(activated.append)

    widget.set_versions(["v2", "v1"], current="v1")
    widget._set_active_btn.click()

    assert activated == ["v1"]
