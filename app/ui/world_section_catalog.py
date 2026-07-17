"""World Overview section definitions used by the progressive editor."""

from dataclasses import dataclass

from app.storage.bible_models import WorldOverview


@dataclass(frozen=True)
class WorldSectionDefinition:
    section_id: str
    label: str
    description: str
    keywords: tuple[str, ...]


WORLD_SECTION_DEFINITIONS = (
    WorldSectionDefinition("geography", "Geography", "", ("places", "map")),
    WorldSectionDefinition(
        "society", "Society and technology", "", ("culture", "social")
    ),
    WorldSectionDefinition("rules", "World rules", "", ("laws",)),
    WorldSectionDefinition("taboos", "Taboos", "", ("forbidden",)),
)


def populated_world_sections(world: WorldOverview) -> set[str]:
    populated = {"geography"} if world.geography.strip() else set()
    if world.technology_level.strip() or world.social_structure.strip():
        populated.add("society")
    for field in ("rules", "taboos"):
        if getattr(world, field):
            populated.add(field)
    return populated
