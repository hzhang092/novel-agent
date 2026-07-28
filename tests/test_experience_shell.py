from PySide6.QtWidgets import QMessageBox

from app.storage.models import Project
from app.storage.project_files import create_project
from app.ui.main_window import MainWindow


def labels(window):
    return [window.sidebar.item(index).text() for index in range(window.sidebar.count())]


def test_experience_switch_uses_exact_navigation_and_shared_writing_buffer(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)

    assert labels(window) == ["总览", "设定集", "大纲", "写作台"]
    window._workspace_view.set_scene("scene-1", "chapter-1")
    window._workspace_view.set_prose_text("in memory")
    window._workspace_view.set_prose_versions(["v1"], "v1")
    window._experience_switch.setCurrentIndex(window._experience_switch.findData("quick"))

    assert labels(window) == ["故事", "大纲", "写章节"]
    assert window._workspace_view.prose_text() == "in memory"
    assert window._workspace_view.current_scene_id == "scene-1"
    assert window._workspace_view.current_prose_version() == "v1"


def test_experience_switch_prompts_before_leaving_dirty_bible(tmp_path, qtbot, monkeypatch):
    project_dir = create_project(tmp_path, Project(title="Story"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._bible_view.load_project_dir(project_dir)
    window.sidebar.setCurrentRow(1)
    monkeypatch.setattr(type(window._bible_view), "is_dirty", property(lambda _: True))
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Cancel
    )

    window._experience_switch.setCurrentIndex(window._experience_switch.findData("quick"))

    assert window._experience_mode == "deep"
    assert labels(window) == ["总览", "设定集", "大纲", "写作台"]


def test_story_maps_to_bible_when_returning_to_deep(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)

    window._experience_switch.setCurrentIndex(window._experience_switch.findData("quick"))
    window._experience_switch.setCurrentIndex(window._experience_switch.findData("deep"))

    assert window.sidebar.currentItem().data(256) == "bible"
