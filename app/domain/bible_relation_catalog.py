"""Display and context behavior for Bible Element relationships."""

from dataclasses import dataclass

from app.storage.bible_models import BibleElementType, BibleRelationKind


@dataclass(frozen=True)
class BibleRelationDefinition:
    kind: BibleRelationKind
    label: str
    inverse_label: str
    symmetric: bool
    expand_in_context: bool = True
    allowed_source_types: frozenset[BibleElementType] | None = None
    allowed_target_types: frozenset[BibleElementType] | None = None


RELATION_DEFINITIONS = {
    definition.kind: definition
    for definition in (
        BibleRelationDefinition(BibleRelationKind.RELATED_TO, "Related to", "Related to", True),
        BibleRelationDefinition(BibleRelationKind.PART_OF, "Part of", "Contains", False),
        BibleRelationDefinition(
            BibleRelationKind.LOCATED_IN,
            "Located in",
            "Contains",
            False,
            allowed_target_types=frozenset({BibleElementType.LOCATION}),
        ),
        BibleRelationDefinition(BibleRelationKind.CONTROLS, "Controls", "Controlled by", False),
        BibleRelationDefinition(BibleRelationKind.USES, "Uses", "Used by", False),
        BibleRelationDefinition(
            BibleRelationKind.ALLIED_WITH,
            "Allied with",
            "Allied with",
            True,
            allowed_source_types=frozenset({BibleElementType.FACTION}),
            allowed_target_types=frozenset({BibleElementType.FACTION}),
        ),
        BibleRelationDefinition(
            BibleRelationKind.OPPOSED_TO,
            "Opposed to",
            "Opposed to",
            True,
            allowed_source_types=frozenset({BibleElementType.FACTION}),
            allowed_target_types=frozenset({BibleElementType.FACTION}),
        ),
        BibleRelationDefinition(
            BibleRelationKind.CAUSED,
            "Caused",
            "Caused by",
            False,
            allowed_source_types=frozenset({BibleElementType.HISTORICAL_EVENT}),
            allowed_target_types=frozenset({BibleElementType.HISTORICAL_EVENT}),
        ),
        BibleRelationDefinition(
            BibleRelationKind.PRECEDED_BY,
            "Preceded by",
            "Followed by",
            False,
            allowed_source_types=frozenset({BibleElementType.HISTORICAL_EVENT}),
            allowed_target_types=frozenset({BibleElementType.HISTORICAL_EVENT}),
        ),
        BibleRelationDefinition(BibleRelationKind.DEPENDS_ON, "Depends on", "Required by", False),
    )
}


def relation_definition(kind: BibleRelationKind) -> BibleRelationDefinition:
    return RELATION_DEFINITIONS[kind]
