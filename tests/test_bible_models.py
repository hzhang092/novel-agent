from datetime import datetime, timedelta

import pytest
from pydantic import TypeAdapter, ValidationError

from app.storage.bible_models import (
    BibleElement,
    BibleElementRelation,
    BibleElementType,
    BibleRelationKind,
    FactionElement,
    PowerSystemElement,
    TerminologyElement,
    power_realms_from_legacy,
    semantically_equal,
)


def test_bible_element_union_uses_element_type_discriminator():
    element = TypeAdapter(BibleElement).validate_python(
        {"element_type": "terminology", "name": "灵石", "definition": "货币"}
    )

    assert isinstance(element, TerminologyElement)
    with pytest.raises(ValidationError):
        TypeAdapter(BibleElement).validate_python(
            {"element_type": "unknown", "name": "anything"}
        )


def test_aliases_and_tags_are_trimmed_normalized_and_stably_deduplicated():
    element = FactionElement(
        name="青云宗",
        aliases=[" QingYun ", "ＱｉｎｇＹｕｎ", "", "青云"],
        tags=[" 正道 ", "正道", "宗门", " "],
    )

    assert element.aliases == ["QingYun", "青云"]
    assert element.tags == ["正道", "宗门"]


def test_alias_and_tag_values_have_a_reasonable_length_limit():
    with pytest.raises(ValidationError):
        FactionElement(name="青云宗", aliases=["a" * 81])


def test_importance_and_relationship_shape_are_validated():
    relation = BibleElementRelation(
        kind=BibleRelationKind.OPPOSED_TO,
        target_element_id="faction-2",
        note="  长期敌对  ",
    )
    assert relation.note == "长期敌对"

    with pytest.raises(ValidationError):
        FactionElement(name="青云宗", importance=6)
    with pytest.raises(ValidationError):
        BibleElementRelation(kind="unknown", target_element_id="faction-2")


def test_power_realms_preserve_order_and_append_unlisted_abilities():
    realms = power_realms_from_legacy(
        ["炼气", "筑基"],
        {"炼气": "灵气感知", "金丹": "凝结金丹"},
    )

    assert [(realm.name, realm.abilities) for realm in realms] == [
        ("炼气", ["灵气感知"]),
        ("筑基", []),
        ("金丹", ["凝结金丹"]),
    ]


def test_semantic_comparison_ignores_revision_and_timestamps_only():
    original = PowerSystemElement(name="九重天境")
    bookkeeping_change = original.model_copy(
        update={
            "revision": 9,
            "created_at": original.created_at - timedelta(days=1),
            "updated_at": datetime.now(),
        }
    )
    content_change = original.model_copy(update={"always_include": True})

    assert semantically_equal(original, bookkeeping_change)
    assert not semantically_equal(original, content_change)
    assert original.element_type == BibleElementType.POWER_SYSTEM
