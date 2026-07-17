"""Shared compact rendering for character generation context."""

from app.domain.character_element_relation_catalog import relation_definition
from app.storage.bible_models import BibleElement
from app.storage.models import CharacterCore, CharacterTier


def custom_fields_for_generation(
    core: CharacterCore,
    *,
    max_fields: int,
    max_characters: int,
) -> list[dict]:
    result: list[dict] = []
    used = 0
    for field in core.custom_fields:
        if not field.include_in_generation or len(result) >= max_fields:
            continue
        value = field.value
        text = "\n".join(value) if isinstance(value, list) else value
        remaining = max_characters - used
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining]
        result.append({"label": field.label, "value": text})
        used += len(text)
    return result


def compact_character_core(
    core: CharacterCore,
    *,
    tier: CharacterTier | str,
    elements: list[BibleElement] | None = None,
) -> dict:
    tier = CharacterTier(tier)
    if tier == CharacterTier.BACKGROUND:
        return {"name": core.name, "tier": tier.value, "custom_fields": []}

    if tier == CharacterTier.MAJOR:
        result = core.model_dump(
            mode="json",
            exclude={
                "custom_fields",
                "element_relations",
                "definition_revision",
                "definition_updated_at",
            },
        )
        max_fields = 20
    else:
        result = {
            "name": core.name,
            "tier": tier.value,
            "personality": core.personality[:120],
        }
        max_fields = 5
    result["custom_fields"] = custom_fields_for_generation(
        core, max_fields=max_fields, max_characters=4_000
    )

    by_id = {element.id: element for element in elements or []}
    result["story_connections"] = [
        {
            "kind": relation.kind.value,
            "target_id": relation.target_element_id,
            "target_name": target.name,
            "target_type": target.element_type.value,
            "note": relation.note,
        }
        for relation in core.element_relations
        if (target := by_id.get(relation.target_element_id)) is not None
    ]
    return result


def character_prompt_lines(core: dict, state: dict) -> list[str]:
    lines: list[str] = []
    for field in core.get("custom_fields", []):
        if field.get("value"):
            lines.append(f"  {field['label']}：{field['value']}")
    for connection in core.get("story_connections", []):
        label = relation_definition(connection["kind"]).label
        note = f"（{connection['note']}）" if connection.get("note") else ""
        lines.append(f"  {label}：{connection['target_name']}{note}")
    return lines
