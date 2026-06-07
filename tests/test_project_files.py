"""Tests for project file I/O operations."""

from pathlib import Path

import pytest

from app.storage.models import Project, WorldSetting
from app.storage.project_files import (
    create_project,
    delete_project,
    load_project,
    project_exists,
)


def test_create_project_creates_directory_structure(tmp_path):
    project = Project(title="测试小说", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    assert proj_dir.exists()
    assert (proj_dir / "project.yaml").exists()
    assert (proj_dir / "world.md").exists()
    assert (proj_dir / "style.yaml").exists()
    assert (proj_dir / ".gitignore").exists()
    assert (proj_dir / "characters").is_dir()
    assert (proj_dir / "outline").is_dir()
    assert (proj_dir / "scenes").is_dir()
    assert (proj_dir / "canon").is_dir()
    assert (proj_dir / "exports").is_dir()


def test_create_project_writes_project_yaml(tmp_path):
    project = Project(title="修仙之路", genre="玄幻", llm_provider="deepseek")
    proj_dir = create_project(tmp_path, project)

    loaded = load_project(proj_dir)
    assert loaded.title == "修仙之路"
    assert loaded.genre == "玄幻"
    assert loaded.llm_provider == "deepseek"
    assert loaded.id == project.id  # UUID preserved


def test_load_project_round_trip(tmp_path):
    project = Project(
        title="测试小说",
        genre="都市",
        world_setting=WorldSetting(geography="现代都市，隐藏修仙世界"),
    )
    proj_dir = create_project(tmp_path, project)

    loaded = load_project(proj_dir)
    assert loaded.world_setting.geography == "现代都市，隐藏修仙世界"
    assert loaded.language == "zh-CN"


def test_load_project_missing_yaml(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path / "nonexistent")


def test_load_project_invalid_yaml(tmp_path):
    proj_dir = tmp_path / "bad_project"
    proj_dir.mkdir()
    (proj_dir / "project.yaml").write_text(": bad yaml : :", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid YAML"):
        load_project(proj_dir)


def test_load_project_empty_yaml(tmp_path):
    proj_dir = tmp_path / "empty_project"
    proj_dir.mkdir()
    (proj_dir / "project.yaml").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="Empty"):
        load_project(proj_dir)


def test_load_project_missing_required_fields(tmp_path):
    proj_dir = tmp_path / "partial_project"
    proj_dir.mkdir()
    (proj_dir / "project.yaml").write_text("id: abc\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid project data"):
        load_project(proj_dir)


def test_project_exists(tmp_path):
    assert not project_exists(tmp_path)

    project = Project(title="测试小说", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    assert project_exists(proj_dir)


def test_delete_project(tmp_path):
    project = Project(title="测试小说", genre="玄幻")
    proj_dir = create_project(tmp_path, project)
    assert proj_dir.exists()

    delete_project(proj_dir)
    assert not proj_dir.exists()


def test_create_project_duplicate_raises(tmp_path):
    project = Project(title="测试小说", genre="玄幻")
    create_project(tmp_path, project)
    with pytest.raises(FileExistsError):
        create_project(tmp_path, project)


def test_full_round_trip_with_world_and_style(tmp_path):
    """End-to-end: create a full project, load it back, verify all fields."""
    from app.storage.models import PowerSystem, StyleGuide, WorldSetting

    project = Project(
        title="修仙之路",
        genre="玄幻",
        llm_provider="ollama",
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
    assert loaded.title == project.title
    assert loaded.world_setting.geography == "东荒大陆"
    assert loaded.world_setting.power_system is not None
    assert len(loaded.world_setting.power_system.realms) == 3
    assert loaded.style_guide.tone == "热血"

    # Verify .gitignore excludes exports/
    gitignore = (proj_dir / ".gitignore").read_text(encoding="utf-8")
    assert "exports/" in gitignore
