from pathlib import Path

import pytest

import app.application.outlines as outline_module
from app.application.outlines import OutlineApplicationService
from app.storage.bible_models import FactionElement
from app.storage.bible_repository import BibleElementRepository
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.models import (
    ChapterOutline,
    CharacterCore,
    Project,
    SceneOutline,
    VolumeOutline,
)
from app.storage.project_files import create_project, load_all_volumes, save_volume_outline


def _project(tmp_path: Path) -> Path:
    return create_project(tmp_path, Project(title="Story", genre="Fantasy"))


def _volume(volume_id: str, scene_id: str = "scene") -> VolumeOutline:
    return VolumeOutline(
        id=volume_id,
        title=volume_id,
        chapters=[
            ChapterOutline(
                id=f"chapter-{volume_id}",
                scenes=[
                    SceneOutline(
                        id=scene_id,
                        world_element_ids=["sect"],
                    )
                ],
            )
        ],
    )


def test_load_snapshot_contains_complete_editor_reference_data(tmp_path):
    project_dir = _project(tmp_path)
    save_volume_outline(project_dir, _volume("one"))
    CharacterDefinitionService(project_dir).save(CharacterCore(id="hero", name="Lin"))
    BibleElementRepository(project_dir).create(
        FactionElement(id="sect", name="Jade Sect")
    )

    snapshot = OutlineApplicationService(project_dir).load_editor_snapshot()

    assert [volume.id for volume in snapshot.volumes] == ["one"]
    assert [character.core.id for character in snapshot.characters] == ["hero"]
    assert [element.id for element in snapshot.bible_elements] == ["sect"]


def test_save_reloads_complete_outline_and_removes_stale_volume(tmp_path):
    project_dir = _project(tmp_path)
    service = OutlineApplicationService(project_dir)
    save_volume_outline(project_dir, _volume("stale", "old-scene"))
    target = [_volume("two", "last"), _volume("one", "first")]

    saved = service.save_outline(target)
    reloaded = service.load_editor_snapshot().volumes

    assert [volume.id for volume in saved] == ["two", "one"]
    assert {volume.id for volume in reloaded} == {"one", "two"}
    assert not (project_dir / "outline" / "stale.yaml").exists()


def test_failed_aggregate_save_restores_every_volume_file(tmp_path, monkeypatch):
    project_dir = _project(tmp_path)
    service = OutlineApplicationService(project_dir)
    save_volume_outline(project_dir, _volume("one", "old-one"))
    save_volume_outline(project_dir, _volume("stale", "old-stale"))
    before = {
        path.name: path.read_bytes()
        for path in (project_dir / "outline").glob("*.yaml")
    }
    real_save = outline_module.save_volume_outline
    calls = 0

    def fail_second_save(path, volume):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("second volume failed")
        return real_save(path, volume)

    monkeypatch.setattr(outline_module, "save_volume_outline", fail_second_save)

    with pytest.raises(OSError, match="second volume failed"):
        service.save_outline([_volume("one", "new-one"), _volume("two", "new-two")])

    after = {
        path.name: path.read_bytes()
        for path in (project_dir / "outline").glob("*.yaml")
    }
    assert after == before


def test_rejects_duplicate_volume_ids_before_writing(tmp_path):
    project_dir = _project(tmp_path)
    service = OutlineApplicationService(project_dir)

    with pytest.raises(ValueError, match="duplicate"):
        service.save_outline([_volume("same"), _volume("same")])

    assert load_all_volumes(project_dir) == []


def test_scene_queries(tmp_path):
    project_dir = _project(tmp_path)
    service = OutlineApplicationService(project_dir)
    service.save_outline([_volume("one", "wanted")])

    assert service.chapter_for_scene("wanted") == "chapter-one"
    assert service.chapter_for_scene("missing") is None
    assert service.scene_element_ids("wanted") == frozenset({"sect"})
    assert service.scene_element_ids("missing") == frozenset()
