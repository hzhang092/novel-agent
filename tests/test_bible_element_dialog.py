import pytest

from app.storage.bible_models import (
    BibleElementType,
    FactionElement,
    HistoricalEventElement,
    LocationElement,
    PowerSystemElement,
    TerminologyElement,
)
from app.ui.bible_element_dialog import BibleElementDialog


@pytest.mark.parametrize(
    ("element_type", "expected_class"),
    [
        (BibleElementType.LOCATION, LocationElement),
        (BibleElementType.FACTION, FactionElement),
        (BibleElementType.HISTORICAL_EVENT, HistoricalEventElement),
        (BibleElementType.POWER_SYSTEM, PowerSystemElement),
    ],
)
def test_add_dialog_creates_name_only_typed_draft(
    element_type, expected_class, qtbot
):
    dialog = BibleElementDialog(default_type=element_type)
    qtbot.addWidget(dialog)
    dialog._name.setText("新元素")

    draft = dialog.create_draft()

    assert isinstance(draft, expected_class)
    assert draft.name == "新元素"
    assert dialog._definition.isHidden()


def test_add_dialog_asks_for_terminology_definition(qtbot):
    dialog = BibleElementDialog(default_type=BibleElementType.TERMINOLOGY)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._name.setText("灵石")
    dialog._definition.setPlainText("修行货币")

    draft = dialog.create_draft()

    assert isinstance(draft, TerminologyElement)
    assert draft.name == "灵石"
    assert draft.definition == "修行货币"
    assert not dialog._definition.isHidden()

