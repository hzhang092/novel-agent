"""Tests for Repository outline delegation methods."""
from pathlib import Path

import pytest

from app.storage.models import (
    Project,
    VolumeOutline,
)
from app.storage.project_files import create_project
from app.storage.repository import Repository


@pytest.fixture
def repo():
    return Repository(Path("/tmp/test-workspace"))


def test_repo_save_and_load_volume(repo, tmp_path):
    """Repository.save_volume writes; Repository.load_volume reads back."""
    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    volume = VolumeOutline(title="第一卷")
    repo.save_volume(proj_dir, volume)

    loaded = repo.load_volume(proj_dir, volume.id)
    assert loaded.title == "第一卷"


def test_repo_delete_volume(repo, tmp_path):
    """Repository.delete_volume removes the file."""
    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    volume = VolumeOutline(title="第一卷")
    repo.save_volume(proj_dir, volume)

    repo.delete_volume(proj_dir, volume.id)

    with pytest.raises(FileNotFoundError):
        repo.load_volume(proj_dir, volume.id)


def test_repo_list_volume_ids(repo, tmp_path):
    """Repository.list_volume_ids returns all IDs."""
    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    v1 = VolumeOutline(title="第一卷")
    v2 = VolumeOutline(title="第二卷")
    repo.save_volume(proj_dir, v1)
    repo.save_volume(proj_dir, v2)

    ids = repo.list_volume_ids(proj_dir)
    assert set(ids) == {v1.id, v2.id}


def test_repo_load_all_volumes(repo, tmp_path):
    """Repository.load_all_volumes loads all volumes."""
    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    repo.save_volume(proj_dir, VolumeOutline(title="第一卷"))
    repo.save_volume(proj_dir, VolumeOutline(title="第二卷"))

    volumes = repo.load_all_volumes(proj_dir)
    assert len(volumes) == 2
