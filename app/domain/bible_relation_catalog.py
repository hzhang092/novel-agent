"""Display and context behavior for Bible Element relationships."""

from dataclasses import dataclass

from app.storage.bible_models import BibleRelationKind


@dataclass(frozen=True)
class BibleRelationDefinition:
    kind: BibleRelationKind
    label: str
    inverse_label: str
    symmetric: bool
    expand_in_context: bool = True


RELATION_DEFINITIONS = {
    definition.kind: definition
    for definition in (
        BibleRelationDefinition(BibleRelationKind.RELATED_TO, "Related to", "Related to", True),
        BibleRelationDefinition(BibleRelationKind.PART_OF, "Part of", "Contains", False),
        BibleRelationDefinition(BibleRelationKind.LOCATED_IN, "Located in", "Contains", False),
        BibleRelationDefinition(BibleRelationKind.CONTROLS, "Controls", "Controlled by", False),
        BibleRelationDefinition(BibleRelationKind.USES, "Uses", "Used by", False),
        BibleRelationDefinition(BibleRelationKind.ALLIED_WITH, "Allied with", "Allied with", True),
        BibleRelationDefinition(BibleRelationKind.OPPOSED_TO, "Opposed to", "Opposed to", True),
        BibleRelationDefinition(BibleRelationKind.CAUSED, "Caused", "Caused by", False),
        BibleRelationDefinition(BibleRelationKind.PRECEDED_BY, "Preceded by", "Followed by", False),
        BibleRelationDefinition(BibleRelationKind.DEPENDS_ON, "Depends on", "Required by", False),
    )
}


def relation_definition(kind: BibleRelationKind) -> BibleRelationDefinition:
    return RELATION_DEFINITIONS[kind]
