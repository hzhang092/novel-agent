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


def test_add_dialog_uses_type_then_minimum_details_steps(qtbot):
    dialog = BibleElementDialog()
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog._steps.currentIndex() == 0
    assert dialog._next_button.isVisible()
    assert not dialog._name.isVisible()

    dialog._type.setCurrentIndex(dialog._type.findData(BibleElementType.FACTION))
    dialog._next_button.click()

    assert dialog._steps.currentIndex() == 1
    assert dialog._name.isVisible()
    assert not dialog._definition.isVisible()


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


def test_add_dialog_rejects_missing_required_name(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    dialog = BibleElementDialog(default_type=BibleElementType.FACTION)
    qtbot.addWidget(dialog)
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *_args: warnings.append(True)
    )

    dialog.accept()

    assert dialog.result() == 0
    assert warnings == [True]


def test_add_dialog_rejects_missing_terminology_definition(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    dialog = BibleElementDialog(default_type=BibleElementType.TERMINOLOGY)
    qtbot.addWidget(dialog)
    dialog._name.setText("Qi")
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *_args: warnings.append(True)
    )

    dialog.accept()

    assert dialog.result() == 0
    assert warnings == [True]
