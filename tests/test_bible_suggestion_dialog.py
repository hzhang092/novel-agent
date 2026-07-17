import pytest

from app.pipeline.bible_suggestions import (
    AddElementRelationSuggestion,
    CreateElementSuggestion,
    UpdateElementSuggestion,
)
from app.storage.bible_models import FactionElement, LocationElement
from app.ui.bible_suggestion_dialog import BibleSuggestionDialog


def test_dialog_returns_only_checked_edited_proposals(qtbot):
    create = CreateElementSuggestion(
        proposal_id="sect",
        confidence=0.92,
        element_type="faction",
        name="赤云宗",
    )
    relation = AddElementRelationSuggestion(
        proposal_id="link",
        confidence=0.8,
        source_ref="sect",
        kind="controls",
        target_ref="existing-place",
    )
    dialog = BibleSuggestionDialog(
        [create, relation], [FactionElement(id="existing-sect", name="已有宗门")]
    )
    qtbot.addWidget(dialog)

    dialog._editors["sect"]["name"].setText("赤云仙宗")
    dialog._checks["link"].setChecked(False)

    assert dialog.selected_proposals() == [
        create.model_copy(update={"name": "赤云仙宗"})
    ]


def test_dialog_rejects_relation_target_not_in_existing_or_checked_new(qtbot):
    relation = AddElementRelationSuggestion(
        proposal_id="link",
        confidence=0.8,
        source_ref="missing-source",
        kind="controls",
        target_ref="missing-target",
    )
    dialog = BibleSuggestionDialog([relation])
    qtbot.addWidget(dialog)

    with pytest.raises(ValueError, match="accepted new element or existing"):
        dialog.selected_proposals()


def test_dialog_can_merge_duplicate_and_rewrite_relation_reference(qtbot):
    create = CreateElementSuggestion(
        proposal_id="sect", confidence=0.9, element_type="faction", name="赤云宗"
    )
    relation = AddElementRelationSuggestion(
        proposal_id="link", confidence=0.8, source_ref="sect", kind="controls", target_ref="mine"
    )
    dialog = BibleSuggestionDialog(
        [create, relation],
        [FactionElement(id="existing-sect", name="赤云宗"), LocationElement(id="mine", name="灵矿")],
    )
    qtbot.addWidget(dialog)
    dialog._duplicate_choices["sect"].setCurrentIndex(1)

    selected = dialog.selected_proposals()

    assert isinstance(selected[0], UpdateElementSuggestion)
    assert selected[0].target_element_id == "existing-sect"
    assert selected[1].source_ref == "existing-sect"


def test_dialog_parses_typed_fields_json_and_validates_schema(qtbot):
    create = CreateElementSuggestion(
        proposal_id="sect", confidence=0.9, element_type="faction", name="赤云宗"
    )
    dialog = BibleSuggestionDialog([create])
    qtbot.addWidget(dialog)

    dialog._editors["sect"]["typed_fields"].setPlainText('{"goals": ["夺矿"]}')

    assert dialog.selected_proposals()[0].typed_fields == {"goals": ["夺矿"]}

    dialog._editors["sect"]["typed_fields"].setPlainText('{"realms": []}')
    with pytest.raises(ValueError, match="invalid typed fields"):
        dialog.selected_proposals()
    assert "invalid typed fields" in dialog._errors["sect"].text()


def test_apply_keeps_dialog_open_and_shows_row_error_for_invalid_json(qtbot):
    create = CreateElementSuggestion(
        proposal_id="sect", confidence=0.9, element_type="faction", name="赤云宗"
    )
    dialog = BibleSuggestionDialog([create])
    qtbot.addWidget(dialog)
    dialog.show()
    dialog._editors["sect"]["typed_fields"].setPlainText("not json")

    dialog._accept_selected()

    assert dialog.result() == 0
    assert "valid JSON" in dialog._errors["sect"].text()


def test_dialog_validates_update_typed_fields_against_existing_element(qtbot):
    update = UpdateElementSuggestion(
        proposal_id="sect", confidence=0.9, target_element_id="sect-id"
    )
    dialog = BibleSuggestionDialog(
        [update], [FactionElement(id="sect-id", name="赤云宗")]
    )
    qtbot.addWidget(dialog)
    dialog._editors["sect"]["typed_fields"].setPlainText('{"goals": "not a list"}')

    with pytest.raises(ValueError, match="invalid typed fields"):
        dialog.selected_proposals()
    assert "invalid typed fields" in dialog._errors["sect"].text()


def test_dialog_revalidates_edited_element_type_and_relation_kind(qtbot):
    create = CreateElementSuggestion(
        proposal_id="place", confidence=0.9, element_type="faction", name="北谷"
    )
    relation = AddElementRelationSuggestion(
        proposal_id="link", confidence=0.8, source_ref="place", kind="controls", target_ref="mine"
    )
    dialog = BibleSuggestionDialog(
        [create, relation], [LocationElement(id="mine", name="灵矿")]
    )
    qtbot.addWidget(dialog)
    dialog._editors["place"]["element_type"].setCurrentIndex(
        dialog._editors["place"]["element_type"].findData("location")
    )
    dialog._editors["link"]["kind"].setCurrentIndex(
        dialog._editors["link"]["kind"].findData("located_in")
    )

    selected = dialog.selected_proposals()

    assert selected[0].element_type == "location"
    assert selected[1].kind == "located_in"
