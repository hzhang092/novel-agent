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
