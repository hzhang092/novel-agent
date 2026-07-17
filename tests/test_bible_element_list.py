from app.storage.bible_models import FactionElement, LocationElement, TerminologyElement
from app.ui.bible_element_list import BibleElementList


def _group_labels(widget):
    return [
        widget._tree.topLevelItem(index).text(0)
        for index in range(widget._tree.topLevelItemCount())
    ]


def test_element_list_searches_filters_and_groups_with_counts(qtbot):
    widget = BibleElementList()
    qtbot.addWidget(widget)
    widget.set_elements(
        [
            FactionElement(id="f1", name="青云宗", aliases=["剑宗"], tags=["正道"]),
            FactionElement(id="f2", name="魔渊殿", tags=["魔道"]),
            LocationElement(id="l1", name="青云山", tags=["正道"]),
            TerminologyElement(id="t1", name="灵石", definition="货币"),
        ]
    )

    assert _group_labels(widget) == [
        "World Overview", "Locations (1)", "Factions (2)", "Terminology (1)"
    ]

    widget.set_query("剑宗")
    assert _group_labels(widget) == ["World Overview", "Factions (1)"]
    widget.set_query("")
    widget.set_type_filter("faction")
    widget.set_tag_filters(["正道"])
    assert _group_labels(widget) == ["World Overview", "Factions (1)"]


def test_element_list_pins_overview_and_restores_collapsed_groups(qtbot):
    widget = BibleElementList()
    qtbot.addWidget(widget)
    widget.set_collapsed_type_groups(["faction"])
    widget.set_elements([FactionElement(id="f1", name="Jade Sect")])

    overview = widget._tree.topLevelItem(0)
    faction_group = widget._tree.topLevelItem(1)

    assert overview.data(0, 0x0100) == "overview"
    assert faction_group.isExpanded() is False
    widget.select_element("overview")
    assert widget.selected_element_id() == "overview"


def test_element_list_selects_by_id_and_marks_unsaved(qtbot):
    widget = BibleElementList()
    qtbot.addWidget(widget)
    widget.set_elements(
        [
            FactionElement(id="same-1", name="同名"),
            LocationElement(id="same-2", name="同名"),
        ]
    )
    selected = []
    widget.element_selected.connect(selected.append)

    widget.set_unsaved_ids({"same-2"})
    widget.select_element("same-2")

    assert widget.selected_element_id() == "same-2"
    assert selected[-1] == "same-2"
    item = widget._tree.currentItem()
    assert item.text(0).startswith("* ")
    assert "Location" in item.text(0)
