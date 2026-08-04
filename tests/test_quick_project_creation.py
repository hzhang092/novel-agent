from pathlib import Path

from app.storage.models import Project
from app.storage.project_files import create_quick_project, load_project


def test_quick_project_uses_a_sanitized_unique_folder_and_keeps_its_title(tmp_path):
    first = create_quick_project(tmp_path, "  A / story?  ")
    second = create_quick_project(tmp_path, "  A / story?  ")
    untitled = create_quick_project(tmp_path, "")

    assert first.name == "A story"
    assert second.name == "A story-2"
    assert load_project(first).title == "A / story?"
    assert untitled.name == "未命名故事"
    assert load_project(untitled).title == "未命名故事"
