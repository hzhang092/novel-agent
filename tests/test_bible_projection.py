from app.storage.bible_models import (
    BibleManifest,
    FactionElement,
    HistoricalEventElement,
    PowerRealm,
    PowerSystemElement,
    TerminologyElement,
    WorldOverview,
)
from app.storage.bible_projection import project_elements_to_legacy_world
from app.storage.bible_renderer import render_world_markdown, write_world_markdown


def test_projects_world_overview_and_factions_to_legacy_world():
    overview = WorldOverview(
        geography="东荒大陆",
        rules=["不得干涉凡人"],
        taboos=["禁术"],
        technology_level="古代",
        social_structure="宗门治理",
    )
    faction = FactionElement(
        id="f1",
        name="青云宗",
        description="剑修宗门",
        goals=["维护秩序", "对抗魔道"],
    )

    world = project_elements_to_legacy_world(
        overview,
        [faction],
        BibleManifest(element_order=["f1"]),
    )

    assert world.geography == "东荒大陆"
    assert world.rules == ["不得干涉凡人"]
    assert world.taboos == ["禁术"]
    assert world.technology_level == "古代"
    assert world.social_structure == "宗门治理"
    assert world.factions == [
        {"name": "青云宗", "description": "剑修宗门", "goals": "维护秩序；对抗魔道"}
    ]


def test_projects_terminology_in_manifest_order():
    elements = [
        TerminologyElement(id="t2", name="灵石", definition="修仙货币"),
        TerminologyElement(id="t1", name="灵气", definition="天地能量"),
    ]

    world = project_elements_to_legacy_world(
        WorldOverview(),
        elements,
        BibleManifest(element_order=["t1", "t2"]),
    )

    assert list(world.terminology.items()) == [
        ("灵气", "天地能量"),
        ("灵石", "修仙货币"),
    ]


def test_projection_rejects_duplicate_normalized_terminology_names():
    elements = [
        TerminologyElement(id="t1", name="Spirit Stone"),
        TerminologyElement(id="t2", name="ＳＰＩＲＩＴ ＳＴＯＮＥ"),
    ]

    with pytest.raises(ValueError, match="unique"):
        project_elements_to_legacy_world(
            WorldOverview(),
            elements,
            BibleManifest(element_order=["t1", "t2"]),
        )


def test_single_migrated_history_projects_to_exact_original_text():
    history = HistoricalEventElement(
        id="h1",
        name="World History",
        description="五百年前，正魔大战。\n此后天下三分。",
    )

    world = project_elements_to_legacy_world(
        WorldOverview(),
        [history],
        BibleManifest(
            element_order=["h1"],
            migrated_from_world_setting=True,
        ),
    )

    assert world.history == "五百年前，正魔大战。\n此后天下三分。"


def test_multiple_histories_project_in_manifest_order():
    first = HistoricalEventElement(
        id="h1",
        name="正魔大战",
        time_label="五百年前",
        description="正道获胜。",
        consequences=["魔道退守"],
    )
    second = HistoricalEventElement(id="h2", name="宗门联盟", description="联盟成立。")

    world = project_elements_to_legacy_world(
        WorldOverview(),
        [second, first],
        BibleManifest(element_order=["h1", "h2"]),
    )

    assert world.history == (
        "五百年前 正魔大战\n正道获胜。\nConsequences: 魔道退守\n\n"
        "宗门联盟\n联盟成立。"
    )


def test_projection_uses_manifest_primary_power_system():
    first = PowerSystemElement(id="p1", name="旧体系")
    primary = PowerSystemElement(
        id="p2",
        name="九重天境",
        realms=[PowerRealm(name="炼气", abilities=["感知灵气", "引气入体"])],
        limitations=["不可越级"],
        costs=["消耗灵力"],
        rare_resources=["灵石"],
        forbidden_methods=["夺舍"],
    )

    world = project_elements_to_legacy_world(
        WorldOverview(),
        [first, primary],
        BibleManifest(element_order=["p1", "p2"], primary_power_system_id="p2"),
    )

    assert world.power_system is not None
    assert world.power_system.realms == ["炼气"]
    assert world.power_system.abilities == {"炼气": "感知灵气；引气入体"}
    assert world.power_system.limitations == ["不可越级"]
    assert world.power_system.costs == ["消耗灵力"]
    assert world.power_system.rare_resources == ["灵石"]
    assert world.power_system.forbidden_methods == ["夺舍"]


def test_projection_repairs_missing_primary_power_system(caplog):
    power = PowerSystemElement(id="p1", name="九重天境")
    manifest = BibleManifest(element_order=["p1"])

    project_elements_to_legacy_world(WorldOverview(), [power], manifest)

    assert manifest.primary_power_system_id == "p1"
    assert "primary power system" in caplog.text.lower()


def test_world_markdown_renders_overview_and_all_power_systems_in_order(tmp_path):
    overview = WorldOverview(geography="东荒", rules=["不可干涉凡人"])
    first = PowerSystemElement(
        id="p1",
        name="九重天境",
        realms=[PowerRealm(name="炼气", abilities=["引气入体"])],
    )
    second = PowerSystemElement(id="p2", name="灵术", limitations=["消耗精神"])
    manifest = BibleManifest(element_order=["p1", "p2"], primary_power_system_id="p1")

    markdown = render_world_markdown(overview, [second, first], manifest)
    path = write_world_markdown(tmp_path, overview, [second, first], manifest)

    assert "# 世界观" in markdown
    assert "## 地理\n\n东荒" in markdown
    assert "- 不可干涉凡人" in markdown
    assert markdown.index("### 九重天境") < markdown.index("### 灵术")
    assert "- **炼气**: 引气入体" in markdown
    assert "- 消耗精神" in markdown
    assert path == tmp_path / "world.md"
    assert path.read_text(encoding="utf-8") == markdown


def test_world_markdown_renders_factions():
    faction = FactionElement(
        id="f1",
        name="青云宗",
        description="剑修宗门",
        goals=["维护秩序"],
        tags=["正道"],
    )

    markdown = render_world_markdown(
        WorldOverview(),
        [faction],
        BibleManifest(element_order=["f1"]),
    )

    assert "## 势力" in markdown
    assert "### 青云宗" in markdown
    assert "剑修宗门" in markdown
    assert "- 维护秩序" in markdown
    assert "- 正道" in markdown


def test_world_markdown_renders_historical_events():
    event = HistoricalEventElement(
        id="h1",
        name="正魔大战",
        time_label="五百年前",
        description="正道获胜。",
        consequences=["魔道退守"],
    )

    markdown = render_world_markdown(
        WorldOverview(),
        [event],
        BibleManifest(element_order=["h1"]),
    )

    assert "## 历史事件" in markdown
    assert "### 正魔大战" in markdown
    assert "五百年前" in markdown
    assert "- 魔道退守" in markdown


def test_world_markdown_renders_terminology():
    term = TerminologyElement(id="t1", name="灵石", definition="修仙货币")

    markdown = render_world_markdown(
        WorldOverview(),
        [term],
        BibleManifest(element_order=["t1"]),
    )

    assert "## 术语" in markdown
    assert "### 灵石" in markdown
    assert "修仙货币" in markdown
import pytest
