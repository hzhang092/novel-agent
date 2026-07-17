from app.pipeline.agents._character_context import (
    character_prompt_lines,
    compact_character_core,
)
from app.storage.bible_models import FactionElement
from app.storage.models import (
    CharacterCore,
    CharacterCustomField,
    CharacterElementRelation,
)


def test_custom_fields_follow_generation_flag_and_character_tier_budget():
    fields = [
        CharacterCustomField(label=f"Field {index}", value_type="text", value=str(index))
        for index in range(7)
    ]
    fields.insert(
        1,
        CharacterCustomField(
            label="Private UI note",
            value_type="text",
            value="excluded",
            include_in_generation=False,
        ),
    )
    core = CharacterCore(name="Lin", tier="supporting", custom_fields=fields)

    compact = compact_character_core(core, tier=core.tier)

    assert [field["label"] for field in compact["custom_fields"]] == [
        "Field 0", "Field 1", "Field 2", "Field 3", "Field 4"
    ]
    assert compact_character_core(
        core.model_copy(update={"tier": "background"}), tier="background"
    )["custom_fields"] == []


def test_character_context_resolves_stable_story_connections_and_renders_them():
    faction = FactionElement(id="faction", name="Crimson Sect")
    core = CharacterCore(
        name="Lin",
        tier="major",
        custom_fields=[
            CharacterCustomField(
                label="Moral conflict", value_type="long_text", value="Protect or expose"
            )
        ],
        element_relations=[
            CharacterElementRelation(
                kind="member_of", target_element_id=faction.id, note="Outer disciple"
            )
        ],
    )

    compact = compact_character_core(core, tier=core.tier, elements=[faction])
    lines = character_prompt_lines(compact, {})

    assert compact["story_connections"] == [{
        "kind": "member_of",
        "target_id": "faction",
        "target_name": "Crimson Sect",
        "target_type": "faction",
        "note": "Outer disciple",
    }]
    assert any("Moral conflict：Protect or expose" in line for line in lines)
    assert any("Member of：Crimson Sect（Outer disciple）" in line for line in lines)
