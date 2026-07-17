"""Character Detail Field definitions used by the progressive editor."""

from dataclasses import dataclass

from app.storage.models import CharacterCore, CharacterTier


@dataclass(frozen=True)
class CharacterDetailDefinition:
    field_id: str
    label: str
    section_id: str
    description: str
    keywords: tuple[str, ...]
    default_tiers: frozenset[CharacterTier]
    widget_attribute: str


_MAJOR = frozenset({CharacterTier.MAJOR})
_MAJOR_SUPPORTING = frozenset(
    {CharacterTier.MAJOR, CharacterTier.SUPPORTING}
)
_OPTIONAL: frozenset[CharacterTier] = frozenset()

CHARACTER_DETAIL_DEFINITIONS = (
    CharacterDetailDefinition(
        "personality", "Personality", "characterization", "", (),
        _MAJOR_SUPPORTING, "_core_personality",
    ),
    CharacterDetailDefinition(
        "appearance", "Appearance", "characterization", "", (),
        _OPTIONAL, "_core_appearance",
    ),
    CharacterDetailDefinition(
        "speech_style", "Speech style", "characterization", "", (),
        _OPTIONAL, "_core_speech",
    ),
    CharacterDetailDefinition(
        "long_term_goal", "Long-term goal", "motivation_history", "", (),
        _MAJOR, "_core_goal",
    ),
    CharacterDetailDefinition(
        "hidden_motive", "Hidden motive", "motivation_history", "", (),
        _OPTIONAL, "_core_motive",
    ),
    CharacterDetailDefinition(
        "background", "Background", "motivation_history", "", (),
        _OPTIONAL, "_core_background",
    ),
    CharacterDetailDefinition(
        "aliases", "Aliases", "identity_details", "", (),
        _OPTIONAL, "_core_aliases",
    ),
    CharacterDetailDefinition(
        "age", "Age", "identity_details", "", (),
        _OPTIONAL, "_core_age",
    ),
    CharacterDetailDefinition(
        "core_skills", "Core skills", "capabilities", "", (),
        _OPTIONAL, "_core_skills",
    ),
    CharacterDetailDefinition(
        "core_weaknesses", "Core weaknesses", "capabilities", "", (),
        _OPTIONAL, "_core_weaknesses",
    ),
)


def default_character_fields(tier: CharacterTier) -> set[str]:
    return {
        definition.field_id
        for definition in CHARACTER_DETAIL_DEFINITIONS
        if tier in definition.default_tiers
    }


def populated_character_fields(core: CharacterCore) -> set[str]:
    populated = set()
    for definition in CHARACTER_DETAIL_DEFINITIONS:
        value = getattr(core, definition.field_id)
        if (
            isinstance(value, str) and bool(value.strip())
            or isinstance(value, list)
            and any(isinstance(item, str) and item.strip() for item in value)
        ):
            populated.add(definition.field_id)
    return populated


def initial_character_fields(core: CharacterCore) -> set[str]:
    return default_character_fields(core.tier) | populated_character_fields(core)
