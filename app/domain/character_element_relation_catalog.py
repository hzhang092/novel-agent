"""Display and target rules for Character-to-Bible-Element relationships."""

from dataclasses import dataclass

from app.storage.bible_models import BibleElementType
from app.storage.models import CharacterElementRelationKind


@dataclass(frozen=True)
class CharacterElementRelationDefinition:
    kind: CharacterElementRelationKind
    label: str
    inverse_label: str
    allowed_target_types: frozenset[BibleElementType]
    expand_in_context: bool = True


_FACTION = frozenset({BibleElementType.FACTION})
_LOCATION = frozenset({BibleElementType.LOCATION})

RELATION_DEFINITIONS = {
    definition.kind: definition
    for definition in (
        CharacterElementRelationDefinition(CharacterElementRelationKind.MEMBER_OF, "Member of", "Has member", _FACTION),
        CharacterElementRelationDefinition(CharacterElementRelationKind.LEADS, "Leads", "Led by", _FACTION),
        CharacterElementRelationDefinition(CharacterElementRelationKind.SERVES, "Serves", "Served by", _FACTION),
        CharacterElementRelationDefinition(CharacterElementRelationKind.OPPOSED_TO, "Opposed to", "Opposed by", _FACTION),
        CharacterElementRelationDefinition(CharacterElementRelationKind.ORIGINATES_FROM, "Originates from", "Origin of", _LOCATION),
        CharacterElementRelationDefinition(CharacterElementRelationKind.BASED_IN, "Based in", "Base of", _LOCATION),
        CharacterElementRelationDefinition(
            CharacterElementRelationKind.USES,
            "Uses",
            "Used by",
            frozenset({BibleElementType.POWER_SYSTEM, BibleElementType.TERMINOLOGY}),
        ),
        CharacterElementRelationDefinition(
            CharacterElementRelationKind.ASSOCIATED_WITH,
            "Associated with",
            "Associated character",
            frozenset(BibleElementType),
        ),
    )
}


def relation_definition(
    kind: CharacterElementRelationKind,
) -> CharacterElementRelationDefinition:
    return RELATION_DEFINITIONS[kind]
