from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLineEdit, QPushButton, QTreeWidget

from app.ui.widgets.searchable_add_menu import AddMenuItem, SearchableAddMenu


ITEMS = [
    AddMenuItem(
        "personality",
        "Personality",
        "Suggested",
        "Temperament and habits",
        ("traits",),
    ),
    AddMenuItem("age", "Age", "Identity", "Years lived"),
]


def test_progressive_widgets_are_exported():
    from app.ui.widgets import (
        AddMenuItem as ExportedItem,
        CollapsibleSection,
        DetailFieldContainer,
        SearchableAddMenu as ExportedMenu,
    )

    assert (ExportedItem, ExportedMenu) == (AddMenuItem, SearchableAddMenu)
    assert CollapsibleSection.__name__ == "CollapsibleSection"
    assert DetailFieldContainer.__name__ == "DetailFieldContainer"


def _child_with_label(tree, label):
    for category_index in range(tree.topLevelItemCount()):
        category = tree.topLevelItem(category_index)
        for child_index in range(category.childCount()):
            child = category.child(child_index)
            if child.text(0) == label:
                return child
    raise AssertionError(f"missing menu item {label}")


def test_hidden_populated_item_has_data_badge(qtbot):
    menu = SearchableAddMenu()
    qtbot.addWidget(menu)

    menu.set_items(ITEMS, visible_ids=set(), populated_ids={"age"})

    tree = menu.findChild(QTreeWidget, "searchable-add-items")
    assert _child_with_label(tree, "Age").text(1) == "Has data"


def test_search_matches_keywords_and_hides_empty_categories(qtbot):
    menu = SearchableAddMenu()
    qtbot.addWidget(menu)
    menu.set_items(ITEMS, visible_ids=set(), populated_ids=set())

    search = menu.findChild(QLineEdit)
    search.setText("traits")

    tree = menu.findChild(QTreeWidget, "searchable-add-items")
    assert not _child_with_label(tree, "Personality").isHidden()
    assert _child_with_label(tree, "Age").isHidden()
    assert not tree.topLevelItem(0).isHidden()
    assert tree.topLevelItem(1).isHidden()


def test_added_item_remains_listed_but_is_disabled(qtbot):
    menu = SearchableAddMenu()
    qtbot.addWidget(menu)

    menu.set_items(
        ITEMS, visible_ids={"personality"}, populated_ids={"personality"}
    )

    tree = menu.findChild(QTreeWidget, "searchable-add-items")
    item = _child_with_label(tree, "Personality")
    assert item.text(1) == "Added"
    assert not item.flags() & Qt.ItemFlag.ItemIsEnabled


def test_selecting_item_emits_id_and_closes_popup(qtbot):
    menu = SearchableAddMenu()
    qtbot.addWidget(menu)
    menu.set_items(ITEMS, visible_ids=set(), populated_ids=set())
    menu.show()
    tree = menu.findChild(QTreeWidget, "searchable-add-items")
    item = _child_with_label(tree, "Personality")

    with qtbot.waitSignal(menu.item_selected) as signal:
        qtbot.mouseClick(
            tree.viewport(),
            Qt.MouseButton.LeftButton,
            pos=tree.visualItemRect(item).center(),
        )

    assert signal.args == ["personality"]
    assert menu.isHidden()


def test_open_below_clears_search_and_focuses_it(qtbot):
    anchor = QPushButton("Add Detail")
    menu = SearchableAddMenu()
    qtbot.addWidget(anchor)
    qtbot.addWidget(menu)
    menu.set_items(ITEMS, visible_ids=set(), populated_ids=set())
    anchor.show()
    search = menu.findChild(QLineEdit)
    search.setText("age")

    menu.open_below(anchor)

    assert menu.isVisible()
    assert search.text() == ""
    qtbot.waitUntil(search.hasFocus)


def test_down_and_enter_select_first_search_result(qtbot):
    menu = SearchableAddMenu()
    qtbot.addWidget(menu)
    menu.set_items(ITEMS, visible_ids=set(), populated_ids=set())
    menu.show()
    search = menu.findChild(QLineEdit)
    search.setText("age")
    search.setFocus()

    qtbot.keyClick(search, Qt.Key.Key_Down)

    tree = menu.findChild(QTreeWidget, "searchable-add-items")
    assert tree.hasFocus()
    assert tree.currentItem().text(0) == "Age"
    with qtbot.waitSignal(menu.item_selected) as signal:
        qtbot.keyClick(tree, Qt.Key.Key_Return)
    assert signal.args == ["age"]
