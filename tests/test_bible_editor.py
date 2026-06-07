"""Integration tests for Bible editor: load → edit → save → reload round-trip."""

import pytest
import yaml

from app.storage.models import Project
from app.storage.project_files import (
    create_project,
    load_project,
    save_style_guide,
    save_world_setting,
)


def test_world_setting_save_load_round_trip(tmp_path):
    """Save a full WorldSetting, reload, verify all fields preserved."""
    project = Project(title="测试项目", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import PowerSystem, WorldSetting

    world = WorldSetting(
        geography="测试地理",
        power_system=PowerSystem(
            realms=["炼气", "筑基", "金丹"],
            abilities={"炼气": "灵气感知", "筑基": "御剑飞行", "金丹": "金丹领域"},
            limitations=["需要灵石"],
            costs=["消耗寿元"],
            rare_resources=["天火"],
            forbidden_methods=["血祭"],
        ),
        factions=[
            {"name": "青云宗", "description": "正道宗门", "goals": "维护和平"},
            {"name": "魔渊殿", "description": "魔道势力", "goals": "统治世界"},
        ],
        history="上古大战",
        rules=["规则一", "规则二"],
        taboos=["禁忌一"],
        technology_level="修仙文明",
        social_structure="宗门制",
        terminology={"灵石": "修炼货币", "秘境": "上古遗迹"},
    )

    save_world_setting(proj_dir, world)
    loaded = load_project(proj_dir)

    ws = loaded.world_setting
    assert ws.geography == "测试地理"
    assert ws.power_system is not None
    assert ws.power_system.realms == ["炼气", "筑基", "金丹"]
    assert ws.power_system.abilities == {"炼气": "灵气感知", "筑基": "御剑飞行", "金丹": "金丹领域"}
    assert ws.power_system.limitations == ["需要灵石"]
    assert ws.power_system.costs == ["消耗寿元"]
    assert ws.power_system.rare_resources == ["天火"]
    assert ws.power_system.forbidden_methods == ["血祭"]
    assert len(ws.factions) == 2
    assert ws.factions[0]["name"] == "青云宗"
    assert ws.factions[1]["description"] == "魔道势力"
    assert ws.history == "上古大战"
    assert ws.rules == ["规则一", "规则二"]
    assert ws.taboos == ["禁忌一"]
    assert ws.technology_level == "修仙文明"
    assert ws.social_structure == "宗门制"
    assert ws.terminology == {"灵石": "修炼货币", "秘境": "上古遗迹"}

    # Verify world.md contains key data
    md = (proj_dir / "world.md").read_text(encoding="utf-8")
    assert "测试地理" in md
    assert "青云宗" in md
    assert "炼气" in md
    assert "灵石" in md


def test_style_guide_save_load_round_trip(tmp_path):
    """Save a full StyleGuide, reload, verify all fields preserved."""
    project = Project(title="测试项目", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import StyleGuide

    style = StyleGuide(
        pacing="快节奏",
        dialogue_density="对白适中",
        description_style="简练",
        tone="热血",
        sentence_length="短句多",
        pov="第三人称",
        taboo_patterns=["禁忌一", "禁忌二"],
        preferred_patterns=["偏好一", "偏好二"],
        reference_passages=["段落一", "段落二"],
        freeform_notes="测试笔记内容",
    )

    save_style_guide(proj_dir, style)
    loaded = load_project(proj_dir)

    sg = loaded.style_guide
    assert sg.pacing == "快节奏"
    assert sg.dialogue_density == "对白适中"
    assert sg.description_style == "简练"
    assert sg.tone == "热血"
    assert sg.sentence_length == "短句多"
    assert sg.pov == "第三人称"
    assert sg.taboo_patterns == ["禁忌一", "禁忌二"]
    assert sg.preferred_patterns == ["偏好一", "偏好二"]
    assert sg.reference_passages == ["段落一", "段落二"]
    assert sg.freeform_notes == "测试笔记内容"

    # Verify style.yaml contains key data
    with open(proj_dir / "style.yaml", "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    assert raw["pacing"] == "快节奏"
    assert raw["tone"] == "热血"
    assert len(raw["reference_passages"]) == 2


def test_world_setting_empty_save_load(tmp_path):
    """Save an empty WorldSetting, verify it reloads with defaults."""
    project = Project(title="空项目", genre="科幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import WorldSetting

    world = WorldSetting()
    save_world_setting(proj_dir, world)
    loaded = load_project(proj_dir)

    assert loaded.world_setting.geography == ""
    assert loaded.world_setting.power_system is None
    assert loaded.world_setting.factions == []
    assert loaded.world_setting.rules == []


def test_style_guide_empty_save_load(tmp_path):
    """Save an empty StyleGuide, verify it reloads with defaults."""
    project = Project(title="空项目", genre="科幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import StyleGuide

    style = StyleGuide()
    save_style_guide(proj_dir, style)
    loaded = load_project(proj_dir)

    assert loaded.style_guide.pacing == ""
    assert loaded.style_guide.pov == ""
    assert loaded.style_guide.taboo_patterns == []


def test_world_md_without_power_system(tmp_path):
    """World markdown should not include power system section when None."""
    project = Project(title="无修炼", genre="都市")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import WorldSetting

    world = WorldSetting(geography="现代都市")
    save_world_setting(proj_dir, world)

    md = (proj_dir / "world.md").read_text(encoding="utf-8")
    assert "现代都市" in md
    assert "修炼体系" not in md  # No power system section
