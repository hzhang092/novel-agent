import os
from pathlib import Path

import yaml
import pytest

from app.storage.bible_migration import ensure_bible_store
from app.storage.bible_repository import BibleElementRepository
from app.storage.bible_models import (
    FactionElement,
    HistoricalEventElement,
    PowerSystemElement,
    TerminologyElement,
)
from app.storage.models import PowerSystem, Project, WorldSetting
from app.storage.project_files import create_project, load_project


def write_legacy_project(project_dir: Path, project: Project) -> None:
    project_dir.mkdir()
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(
            project.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (project_dir / "world.md").write_text("legacy world", encoding="utf-8")


def test_empty_project_initializes_empty_bible_store_without_placeholders(tmp_path):
    project_dir = tmp_path / "empty"
    write_legacy_project(
        project_dir,
        Project(
            id="project-1",
            title="空项目",
            genre="玄幻",
            world_setting=WorldSetting(geography="东荒"),
        ),
    )

    bible = ensure_bible_store(project_dir)

    assert bible.overview.geography == "东荒"
    assert bible.elements == []
    assert bible.manifest.element_order == []
    assert bible.manifest.migrated_from_world_setting is False
    assert (project_dir / "bible" / "manifest.yaml").exists()
    assert list((project_dir / "bible" / "elements").glob("*.yaml")) == []
    assert not (project_dir / ".novel-agent" / "backups").exists()


def test_full_legacy_world_migrates_exactly_and_synchronizes_compatibility_files(tmp_path):
    project_dir = tmp_path / "legacy"
    world = WorldSetting(
        geography="东荒大陆",
        factions=[
            {"name": "青云宗", "description": "剑修宗门", "goals": "维护秩序，对抗魔道"},
            {"name": "魔渊殿", "description": "魔道宗门", "goals": "夺取天下"},
        ],
        terminology={"灵石": "修仙货币", "灵气": "天地能量"},
        history="五百年前，正魔大战。\n此后天下三分。",
        power_system=PowerSystem(
            realms=["炼气", "筑基"],
            abilities={"炼气": "引气入体", "金丹": "凝结金丹"},
            limitations=["不可越级"],
            costs=["消耗灵力"],
            rare_resources=["灵石"],
            forbidden_methods=["夺舍"],
        ),
        rules=["不得干涉凡人"],
        taboos=["禁术"],
        technology_level="古代",
        social_structure="宗门治理",
    )
    project = Project(id="project-1", title="旧项目", genre="玄幻", world_setting=world)
    write_legacy_project(project_dir, project)
    original_yaml = (project_dir / "project.yaml").read_text(encoding="utf-8")

    bible = ensure_bible_store(project_dir)

    assert [type(element) for element in bible.elements] == [
        FactionElement,
        FactionElement,
        TerminologyElement,
        TerminologyElement,
        HistoricalEventElement,
        PowerSystemElement,
    ]
    first_faction = bible.elements[0]
    assert first_faction.name == "青云宗"
    assert first_faction.description == "剑修宗门"
    assert first_faction.goals == ["维护秩序，对抗魔道"]
    assert bible.elements[2].name == "灵石"
    assert bible.elements[2].definition == "修仙货币"
    assert bible.elements[4].name == "World History"
    assert bible.elements[4].description == world.history
    power = bible.elements[5]
    assert [(realm.name, realm.abilities) for realm in power.realms] == [
        ("炼气", ["引气入体"]),
        ("筑基", []),
        ("金丹", ["凝结金丹"]),
    ]
    assert power.limitations == ["不可越级"]
    assert power.costs == ["消耗灵力"]
    assert power.rare_resources == ["灵石"]
    assert power.forbidden_methods == ["夺舍"]
    assert power.always_include is True
    assert bible.manifest.primary_power_system_id == power.id
    assert bible.manifest.migrated_from_world_setting is True
    assert bible.manifest.migration_fingerprint
    projected = load_project(project_dir).world_setting
    assert projected.model_copy(update={"power_system": None}) == world.model_copy(
        update={"power_system": None}
    )
    assert projected.power_system is not None
    assert projected.power_system.realms == ["炼气", "筑基", "金丹"]
    assert projected.power_system.abilities == world.power_system.abilities
    assert projected.power_system.limitations == world.power_system.limitations
    assert projected.power_system.costs == world.power_system.costs
    assert projected.power_system.rare_resources == world.power_system.rare_resources
    assert projected.power_system.forbidden_methods == world.power_system.forbidden_methods
    markdown = (project_dir / "world.md").read_text(encoding="utf-8")
    assert "### 青云宗" in markdown
    assert "### World History" in markdown
    assert "### Power System" in markdown
    backup_dirs = list((project_dir / ".novel-agent" / "backups").iterdir())
    assert len(backup_dirs) == 1
    assert (backup_dirs[0] / "project.yaml").read_text(encoding="utf-8") == original_yaml
    assert (backup_dirs[0] / "world.md").read_text(encoding="utf-8") == "legacy world"


def test_migration_ids_are_deterministic_and_existing_manifest_is_idempotent(tmp_path):
    project = Project(
        id="stable-project",
        title="旧项目",
        genre="玄幻",
        world_setting=WorldSetting(
            factions=[{"name": "青云宗", "description": "原描述", "goals": "原目标"}],
            terminology={"灵石": "货币"},
        ),
    )
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    write_legacy_project(first_dir, project)
    write_legacy_project(second_dir, project)

    first = ensure_bible_store(first_dir)
    second = ensure_bible_store(second_dir)
    first_ids = [element.id for element in first.elements]

    assert first_ids == [element.id for element in second.elements]

    legacy_projection = load_project(first_dir)
    legacy_projection.world_setting.factions[0]["description"] = "不应重新导入"
    (first_dir / "project.yaml").write_text(
        yaml.safe_dump(
            legacy_projection.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    rerun = ensure_bible_store(first_dir)

    assert [element.id for element in rerun.elements] == first_ids
    assert rerun.elements[0].description == "原描述"
    assert len(list((first_dir / ".novel-agent" / "backups").iterdir())) == 1


def test_manifest_failure_cleans_staging_and_keeps_legacy_fallback(
    tmp_path, monkeypatch, caplog
):
    project_dir = tmp_path / "legacy"
    project = Project(
        id="project-1",
        title="旧项目",
        genre="玄幻",
        world_setting=WorldSetting(
            factions=[{"name": "青云宗", "description": "原描述", "goals": "原目标"}]
        ),
    )
    write_legacy_project(project_dir, project)
    original_yaml = (project_dir / "project.yaml").read_bytes()
    real_write = BibleElementRepository._write_yaml_atomic

    def fail_manifest(path, data):
        if Path(path).name == "manifest.yaml":
            raise OSError("manifest write failed")
        return real_write(path, data)

    monkeypatch.setattr(BibleElementRepository, "_write_yaml_atomic", staticmethod(fail_manifest))

    with pytest.raises(OSError, match="manifest write failed"):
        ensure_bible_store(project_dir)

    assert not (project_dir / "bible" / "manifest.yaml").exists()
    assert list((project_dir / "bible" / "elements").glob("*.yaml")) == []
    assert list((project_dir / "bible").glob(".migration-*")) == []
    assert (project_dir / "project.yaml").read_bytes() == original_yaml
    assert load_project(project_dir).world_setting == project.world_setting
    assert "World Bible migration failed" in caplog.text


def test_compatibility_failure_does_not_commit_migration(tmp_path, monkeypatch):
    project_dir = tmp_path / "legacy"
    project = Project(
        id="project-1",
        title="旧项目",
        genre="玄幻",
        world_setting=WorldSetting(
            factions=[{"name": "青云宗", "description": "原描述", "goals": "原目标"}]
        ),
    )
    write_legacy_project(project_dir, project)
    original_project = (project_dir / "project.yaml").read_bytes()
    original_world = (project_dir / "world.md").read_bytes()
    real_replace = os.replace

    def fail_world_markdown(source, destination):
        if Path(destination).name == "world.md":
            raise OSError("world markdown replace failed")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_world_markdown)

    with pytest.raises(OSError, match="world markdown replace failed"):
        ensure_bible_store(project_dir)

    assert not (project_dir / "bible" / "manifest.yaml").exists()
    assert list((project_dir / "bible" / "elements").glob("*.yaml")) == []
    assert (project_dir / "project.yaml").read_bytes() == original_project
    assert (project_dir / "world.md").read_bytes() == original_world


def test_new_project_creation_initializes_bible_store(tmp_path):
    project_dir = create_project(
        tmp_path,
        Project(id="new-project", title="新项目", genre="玄幻"),
    )

    assert (project_dir / "bible" / "elements").is_dir()
    manifest = BibleElementRepository(project_dir).load_manifest()
    assert manifest.element_order == []
    assert manifest.migrated_from_world_setting is False


def test_duplicate_normalized_legacy_terms_do_not_commit_manifest(tmp_path):
    project_dir = tmp_path / "legacy"
    write_legacy_project(
        project_dir,
        Project(
            id="project-1",
            title="旧项目",
            genre="玄幻",
            world_setting=WorldSetting(
                terminology={
                    "Spirit Stone": "first",
                    "ＳＰＩＲＩＴ ＳＴＯＮＥ": "second",
                }
            ),
        ),
    )

    with pytest.raises(ValueError, match="unique"):
        ensure_bible_store(project_dir)

    assert not (project_dir / "bible" / "manifest.yaml").exists()
    assert list((project_dir / "bible" / "elements").glob("*.yaml")) == []
