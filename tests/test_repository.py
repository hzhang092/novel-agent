"""Tests for the Repository CRUD wrapper."""

from pathlib import Path

import pytest

from app.storage.models import Project
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
