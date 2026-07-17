from datetime import datetime

import pytest
import yaml
from pydantic import ValidationError

from app.storage.models import (
    CharacterCore,
    CharacterCustomField,
    CharacterCustomFieldType,
)


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        (CharacterCustomFieldType.TEXT, "青云弟子"),
        (CharacterCustomFieldType.LONG_TEXT, "守护宗门，哪怕与师父为敌。"),
        (CharacterCustomFieldType.STRING_LIST, ["剑术", "炼丹"]),
    ],
)
def test_custom_field_types_round_trip_through_yaml(value_type, value):
    core = CharacterCore(
        name="林风",
        custom_fields=[
            CharacterCustomField(
                id="field-1",
                label="自定义详情",
                value_type=value_type,
                value=value,
                include_in_generation=False,
            )
        ],
    )

    loaded = CharacterCore.model_validate(
        yaml.safe_load(yaml.safe_dump(core.model_dump(mode="json"), allow_unicode=True))
    )

    assert loaded.custom_fields[0].value == value
    assert loaded.custom_fields[0].include_in_generation is False


def test_legacy_definition_gets_extensibility_defaults_without_rewrite_metadata():
    before = datetime.now()
    core = CharacterCore.model_validate({"id": "legacy", "name": "旧角色"})

    assert core.custom_fields == []
    assert core.element_relations == []
    assert core.definition_revision == 1
    assert core.definition_updated_at >= before


def test_custom_field_labels_and_ids_are_unique_and_labels_are_trimmed():
    field = CharacterCustomField(label="  秘密  ", value_type="text", value="value")
    assert field.label == "秘密"

    with pytest.raises(ValidationError):
        CharacterCustomField(label="   ", value_type="text")
    with pytest.raises(ValidationError):
        CharacterCustomField(label="x" * 61, value_type="text")
    with pytest.raises(ValidationError, match="labels"):
        CharacterCore(
            name="林风",
            custom_fields=[
                CharacterCustomField(id="one", label="秘密", value_type="text"),
                CharacterCustomField(id="two", label=" 秘密 ", value_type="text"),
            ],
        )
    with pytest.raises(ValidationError, match="IDs"):
        CharacterCore(
            name="林风",
            custom_fields=[
                CharacterCustomField(id="same", label="秘密", value_type="text"),
                CharacterCustomField(id="same", label="目标", value_type="text"),
            ],
        )


def test_custom_field_values_match_type_and_string_lists_are_normalized():
    field = CharacterCustomField(
        label="招式",
        value_type="string_list",
        value=["  青云剑法 ", "御剑术"],
    )
    assert field.value == ["青云剑法", "御剑术"]

    with pytest.raises(ValidationError):
        CharacterCustomField(label="招式", value_type="string_list", value="青云剑法")
    with pytest.raises(ValidationError):
        CharacterCustomField(label="招式", value_type="string_list", value=[" "])
    with pytest.raises(ValidationError):
        CharacterCustomField(label="秘密", value_type="text", value=["不是文本"])


def test_character_accepts_at_most_thirty_custom_fields():
    with pytest.raises(ValidationError):
        CharacterCore(
            name="林风",
            custom_fields=[
                CharacterCustomField(id=str(index), label=f"字段 {index}", value_type="text")
                for index in range(31)
            ],
        )
