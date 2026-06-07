"""Tests for Repository character CRUD methods."""

import pytest

from app.storage.models import (
    Character,
    CharacterCore,
    CharacterState,
    Project,
)
from app.storage.repository import Repository


def test_repo_save_and_load_character(tmp_path):
    repo = Repository(tmp_path)
    project = Project(title="测试", genre="玄幻")
    proj_dir = repo.create(project)

    core = CharacterCore(name="林轩")
    state = CharacterState(character_id=core.id)
    character = Character(core=core, state=state)

    repo.save_character(proj_dir, character)
    loaded = repo.load_character(proj_dir, core.id)
    assert loaded.core.name == "林轩"


def test_repo_delete_character(tmp_path):
    repo = Repository(tmp_path)
    project = Project(title="测试", genre="玄幻")
    proj_dir = repo.create(project)

    core = CharacterCore(name="路人")
    state = CharacterState(character_id=core.id)
    repo.save_character(proj_dir, Character(core=core, state=state))

    repo.delete_character(proj_dir, core.id)
    with pytest.raises(FileNotFoundError):
        repo.load_character(proj_dir, core.id)


def test_repo_list_character_ids(tmp_path):
    repo = Repository(tmp_path)
    project = Project(title="测试", genre="玄幻")
    proj_dir = repo.create(project)

    ids = []
    for name in ["A", "B", "C"]:
        core = CharacterCore(name=name)
        state = CharacterState(character_id=core.id)
        repo.save_character(proj_dir, Character(core=core, state=state))
        ids.append(core.id)

    assert set(repo.list_character_ids(proj_dir)) == set(ids)


def test_repo_load_all_characters(tmp_path):
    repo = Repository(tmp_path)
    project = Project(title="测试", genre="玄幻")
    proj_dir = repo.create(project)

    for name in ["A", "B"]:
        core = CharacterCore(name=name)
        state = CharacterState(character_id=core.id)
        repo.save_character(proj_dir, Character(core=core, state=state))

    chars = repo.load_all_characters(proj_dir)
    assert len(chars) == 2
