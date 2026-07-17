from PyQt6.QtCore import Qt

from app.storage.bible_models import FactionElement, LocationElement
from app.ui.widgets.element_reference_picker import ElementReferencePicker


def _items(picker):
    return [
        group.child(index)
        for group_index in range(picker._tree.topLevelItemCount())
        for group in [picker._tree.topLevelItem(group_index)]
        for index in range(group.childCount())
    ]


def test_picker_groups_searches_and_stores_element_ids(qtbot):
    picker = ElementReferencePicker()
    qtbot.addWidget(picker)
    picker.set_elements(
        [
            FactionElement(id="faction-1", name="青云宗", aliases=["剑宗"], tags=["正道"]),
            LocationElement(id="location-1", name="青云山", tags=["山脉"]),
        ]
    )

    assert [
        picker._tree.topLevelItem(index).text(0)
        for index in range(picker._tree.topLevelItemCount())
    ] == ["Locations", "Factions"]

    picker._search.setText("正道")
    visible = [item.text(0) for item in _items(picker) if not item.isHidden()]
    assert visible == ["青云宗 · Faction"]

    faction = next(item for item in _items(picker) if item.data(0, Qt.ItemDataRole.UserRole) == "faction-1")
    faction.setCheckState(0, Qt.CheckState.Checked)
    assert picker.selected_ids() == ["faction-1"]


def test_picker_prevents_duplicates_and_keeps_missing_ids_visible(qtbot):
    picker = ElementReferencePicker()
    qtbot.addWidget(picker)
    picker.set_elements([FactionElement(id="faction-1", name="同名")])

    picker.set_selected_ids(["faction-1", "missing-1", "faction-1"])

    assert picker.selected_ids() == ["faction-1", "missing-1"]
    missing = next(item for item in _items(picker) if item.data(0, Qt.ItemDataRole.UserRole) == "missing-1")
    assert "Missing element" in missing.text(0)
    assert missing.checkState(0) == Qt.CheckState.Checked

