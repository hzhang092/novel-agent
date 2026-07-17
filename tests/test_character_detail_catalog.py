from app.storage.models import CharacterCore, CharacterTier
from app.ui.character_detail_catalog import (
    CHARACTER_DETAIL_DEFINITIONS,
    default_character_fields,
    initial_character_fields,
    populated_character_fields,
)


def test_character_detail_registry_and_tier_defaults() -> None:
    assert [definition.field_id for definition in CHARACTER_DETAIL_DEFINITIONS] == [
        "personality",
        "appearance",
        "speech_style",
        "long_term_goal",
        "hidden_motive",
        "background",
        "aliases",
        "age",
        "core_skills",
        "core_weaknesses",
    ]
    assert {
        definition.field_id: definition.widget_attribute
        for definition in CHARACTER_DETAIL_DEFINITIONS
    } == {
        "personality": "_core_personality",
        "appearance": "_core_appearance",
        "speech_style": "_core_speech",
        "long_term_goal": "_core_goal",
        "hidden_motive": "_core_motive",
        "background": "_core_background",
        "aliases": "_core_aliases",
        "age": "_core_age",
        "core_skills": "_core_skills",
        "core_weaknesses": "_core_weaknesses",
    }
    assert default_character_fields(CharacterTier.MAJOR) == {
        "personality",
        "long_term_goal",
    }
    assert default_character_fields(CharacterTier.SUPPORTING) == {"personality"}
    assert default_character_fields(CharacterTier.BACKGROUND) == set()


def test_initial_fields_include_populated_values_without_blank_values() -> None:
    core = CharacterCore(
        name="Lin",
        tier=CharacterTier.SUPPORTING,
        aliases=["", " Sword Saint "],
        age=" 19 ",
        appearance="   ",
        personality="patient",
        background="village blacksmith",
        long_term_goal=None,
        hidden_motive=" ",
        speech_style="formal",
        core_skills=["", "smithing"],
        core_weaknesses=["   "],
    )

    populated = {
        "aliases",
        "age",
        "personality",
        "background",
        "speech_style",
        "core_skills",
    }
    assert populated_character_fields(core) == populated
    assert initial_character_fields(core) == populated
