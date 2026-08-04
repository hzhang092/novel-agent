"""Tests for the Repository CRUD wrapper."""

from pathlib import Path

import pytest

from app.storage.models import (
    CanonFact,
    Character,
    CharacterCore,
    CharacterState,
    Project,
    SceneSummary,
    VolumeOutline,
)
from app.storage.repository import Repository


def test_repository_create_and_open(tmp_path):
    repo = Repository(tmp_path)
    project = Project(title="测试小说", genre="玄幻")
    proj_dir = repo.create(project)

    loaded = repo.open(proj_dir)
    assert loaded.title == "测试小说"


def test_repository_exists(tmp_path):
    repo = Repository(tmp_path)
    project = Project(title="测试小说", genre="玄幻")
    proj_dir = repo.create(project)

    assert repo.exists(proj_dir)
    assert not repo.exists(tmp_path / "nope")


def test_repository_open_invalid_raises(tmp_path):
    repo = Repository(tmp_path)
    with pytest.raises(FileNotFoundError):
        repo.open(tmp_path / "nope")


def test_repository_bible_element_wrappers_use_synchronized_service(tmp_path):
    from app.storage.bible_models import FactionElement

    repo = Repository(tmp_path)
    project_dir = repo.create(Project(title="测试小说", genre="玄幻"))

    saved = repo.save_element(project_dir, FactionElement(id="f1", name="青云宗"))

    assert repo.load_element(project_dir, "f1") == saved
    assert repo.list_elements(project_dir) == [saved]
    assert repo.open(project_dir).world_setting.factions[0]["name"] == "青云宗"

    repo.delete_element(project_dir, "f1")

    assert repo.list_elements(project_dir) == []
    assert repo.open(project_dir).world_setting.factions == []


def test_repository_storage_wrappers_delegate_to_project_files(tmp_path):
    repo = Repository(tmp_path)
    project_dir = repo.create(Project(title="测试小说", genre="玄幻"))

    core = CharacterCore(name="林轩")
    character = Character(core=core, state=CharacterState(character_id=core.id))
    repo.save_character(project_dir, character)
    assert repo.load_character(project_dir, core.id) == character
    assert repo.list_character_ids(project_dir) == [core.id]
    assert repo.load_all_characters(project_dir) == [character]
    repo.delete_character(project_dir, core.id)
    with pytest.raises(FileNotFoundError):
        repo.load_character(project_dir, core.id)

    volume = VolumeOutline(title="第一卷")
    repo.save_volume(project_dir, volume)
    assert repo.load_volume(project_dir, volume.id) == volume
    assert repo.list_volume_ids(project_dir) == [volume.id]
    assert repo.load_all_volumes(project_dir) == [volume]
    repo.delete_volume(project_dir, volume.id)
    with pytest.raises(FileNotFoundError):
        repo.load_volume(project_dir, volume.id)

    facts = [CanonFact(description="事实", category="world", source_scene_id="s1")]
    repo.save_canon_facts(project_dir, facts)
    assert repo.load_canon_facts(project_dir) == facts

    summaries = [
        SceneSummary(
            scene_id="s1",
            chapter_id="ch1",
            summary="摘要",
            new_facts=[],
            character_state_changes={},
            relationship_changes=[],
            open_threads=[],
        )
    ]
    repo.save_scene_summaries(project_dir, summaries)
    assert repo.load_scene_summaries(project_dir) == summaries
