from app.storage.models import PowerSystem, WorldSetting
from app.ui.world_section_catalog import (
    WORLD_SECTION_DEFINITIONS,
    populated_world_sections,
)


def test_world_section_registry_matches_phase_two_sections() -> None:
    assert [definition.section_id for definition in WORLD_SECTION_DEFINITIONS] == [
        "geography",
        "history",
        "society",
        "rules",
        "taboos",
        "factions",
        "terminology",
        "power_system",
    ]
    assert [definition.label for definition in WORLD_SECTION_DEFINITIONS] == [
        "Geography",
        "History",
        "Society and technology",
        "World rules",
        "Taboos",
        "Factions",
        "Terminology",
        "Power / cultivation system",
    ]


def test_populated_world_sections_detects_each_existing_model_section() -> None:
    assert populated_world_sections(
        WorldSetting(geography="   ", power_system=PowerSystem())
    ) == set()

    world = WorldSetting(
        geography="mountain continent",
        history="fallen dynasty",
        technology_level="bronze age",
        rules=["names bind spirits"],
        taboos=["never name the dead"],
        factions=[{"name": "Jade Sect"}],
        terminology={"qi": "life energy"},
        power_system=PowerSystem(limitations=["requires qi"]),
    )
    assert populated_world_sections(world) == {
        "geography",
        "history",
        "society",
        "rules",
        "taboos",
        "factions",
        "terminology",
        "power_system",
    }
