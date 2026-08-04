"""Tests for project file I/O operations."""

import pytest

from app.storage.models import PowerSystem, Project, StyleGuide, WorldSetting
from app.storage.project_files import (
    create_project,
    delete_project,
    load_planning,
    load_project,
    project_exists,
)


def test_load_project_missing_yaml(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path / "nonexistent")


def test_load_project_rejects_invalid_files(tmp_path):
    cases = [
        ("bad_project", ": bad yaml : :", "Invalid YAML"),
        ("empty_project", "", "Empty"),
        ("partial_project", "id: abc\n", "Invalid project data"),
    ]
    for name, content, message in cases:
        project_dir = tmp_path / name
        project_dir.mkdir()
        (project_dir / "project.yaml").write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            load_project(project_dir)


def test_project_exists(tmp_path):
    assert not project_exists(tmp_path)

    project = Project(title="测试小说", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    assert project_exists(proj_dir)
    with pytest.raises(FileExistsError):
        create_project(tmp_path, project)
    delete_project(proj_dir)
    assert not project_exists(proj_dir)


def test_load_planning_discards_deferred_legacy_drafts(tmp_path):
    path = tmp_path / "planning.yaml"
    for kind in ("story_patch", "replan", "later_arc"):
        path.write_text(
            f"schema_version: 1\nprovisional_destination: preserved\n"
            f"active_draft:\n  kind: {kind}\n",
            encoding="utf-8",
        )

        planning = load_planning(tmp_path)

        assert planning.provisional_destination == "preserved"
        assert planning.active_draft is None


def test_full_round_trip_with_world_and_style(tmp_path):
    """End-to-end: create a full project, load it back, verify all fields."""
    project = Project(
        title="修仙之路",
        genre="玄幻",
        llm_provider="deepseek",
        world_setting=WorldSetting(
            geography="东荒大陆",
            power_system=PowerSystem(realms=["炼气", "筑基", "金丹"]),
            rules=["修士不可对凡人出手"],
        ),
        style_guide=StyleGuide(
            pacing="快节奏",
            tone="热血",
        ),
    )
    proj_dir = create_project(tmp_path, project)

    # Verify all subdirectories exist
    for sub in ["characters", "outline", "scenes", "canon", "exports"]:
        assert (proj_dir / sub).is_dir()

    # Load and verify
    loaded = load_project(proj_dir)
    assert loaded.id == project.id
    assert loaded.title == project.title
    assert loaded.genre == "玄幻"
    assert loaded.language == "zh-CN"
    assert loaded.llm_provider == "deepseek"
    assert loaded.world_setting.geography == "东荒大陆"
    assert loaded.world_setting.power_system is not None
    assert len(loaded.world_setting.power_system.realms) == 3
    assert loaded.style_guide.tone == "热血"

    # Verify .gitignore excludes exports/
    gitignore = (proj_dir / ".gitignore").read_text(encoding="utf-8")
    assert gitignore == "exports/\n.novel-agent/\n"


def test_save_world_and_style_preserve_other_fields(tmp_path):
    from app.storage.project_files import save_style_guide, save_world_setting

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    new_world = WorldSetting(
        geography="新地理描述",
        power_system=PowerSystem(realms=["炼气", "筑基"]),
        rules=["新规则"],
    )
    save_world_setting(proj_dir, new_world)

    loaded = load_project(proj_dir)
    assert loaded.title == "测试"
    assert loaded.world_setting.geography == "新地理描述"
    assert len(loaded.world_setting.power_system.realms) == 2
    assert loaded.world_setting.rules == ["新规则"]

    md_content = (proj_dir / "world.md").read_text(encoding="utf-8")
    assert "新地理描述" in md_content
    assert "炼气" in md_content

    new_style = StyleGuide(
        pacing="快节奏",
        tone="热血",
        taboo_patterns=["禁止灌水"],
        reference_passages=["参考段落一"],
    )
    save_style_guide(proj_dir, new_style)

    loaded = load_project(proj_dir)
    assert loaded.title == "测试"
    assert loaded.style_guide.pacing == "快节奏"
    assert loaded.style_guide.tone == "热血"
    assert loaded.style_guide.taboo_patterns == ["禁止灌水"]
    assert loaded.style_guide.reference_passages == ["参考段落一"]
