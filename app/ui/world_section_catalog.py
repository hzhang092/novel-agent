"""World section definitions used by the progressive editor."""

from dataclasses import dataclass

from app.storage.models import WorldSetting


@dataclass(frozen=True)
class WorldSectionDefinition:
    section_id: str
    label: str
    description: str
    keywords: tuple[str, ...]


WORLD_SECTION_DEFINITIONS = (
    WorldSectionDefinition("geography", "Geography", "", ("places", "map")),
    WorldSectionDefinition("history", "History", "", ("past", "timeline")),
    WorldSectionDefinition(
        "society", "Society and technology", "", ("culture", "social")
    ),
    WorldSectionDefinition("rules", "World rules", "", ("laws",)),
    WorldSectionDefinition("taboos", "Taboos", "", ("forbidden",)),
    WorldSectionDefinition("factions", "Factions", "", ("groups",)),
    WorldSectionDefinition("terminology", "Terminology", "", ("glossary",)),
    WorldSectionDefinition(
        "power_system",
        "Power / cultivation system",
        "",
        ("magic", "realms", "abilities"),
    ),
)


def populated_world_sections(world: WorldSetting) -> set[str]:
    populated = {
        field
        for field in ("geography", "history")
        if getattr(world, field).strip()
    }
    if world.technology_level.strip() or world.social_structure.strip():
        populated.add("society")
    for field in ("rules", "taboos", "factions", "terminology"):
        if getattr(world, field):
            populated.add(field)
    if world.power_system and any(world.power_system.model_dump().values()):
        populated.add("power_system")
    return populated
