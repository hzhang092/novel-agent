from app.storage.bible_models import WorldOverview
from app.ui.world_section_catalog import (
    WORLD_SECTION_DEFINITIONS,
    populated_world_sections,
)


def test_world_section_registry_contains_only_world_overview_sections() -> None:
    assert [definition.section_id for definition in WORLD_SECTION_DEFINITIONS] == [
        "geography",
        "society",
        "rules",
        "taboos",
    ]
    assert [definition.label for definition in WORLD_SECTION_DEFINITIONS] == [
        "Geography",
        "Society and technology",
        "World rules",
        "Taboos",
    ]


def test_populated_world_sections_detects_overview_content() -> None:
    assert populated_world_sections(WorldOverview(geography="   ")) == set()

    world = WorldOverview(
        geography="mountain continent",
        technology_level="bronze age",
        rules=["names bind spirits"],
        taboos=["never name the dead"],
    )
    assert populated_world_sections(world) == {
        "geography",
        "society",
        "rules",
        "taboos",
    }
