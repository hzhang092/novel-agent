import pytest
from PySide6.QtWidgets import QMessageBox

from app.storage.models import Project
from app.storage.project_files import create_project
from app.ui.main_window import MainWindow


def _window(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    return window


def _labels(window):
    return [window.sidebar.item(index).text() for index in range(window.sidebar.count())]


def _switch(window, mode):
    window._experience_switch.setCurrentIndex(window._experience_switch.findData(mode))


def test_existing_project_defaults_to_deep_with_separate_presentations(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)

    assert _labels(window) == ["总览", "设定集", "大纲", "写作台"]
    assert window._deep_presentation is not window._quick_presentation
    assert window._deep_presentation.sidebar is not window._quick_presentation.sidebar


def test_quick_affordance_is_hidden_without_the_development_flag(qtbot):
    window = MainWindow(quick_creation_enabled=False)
    qtbot.addWidget(window)

    assert window._experience_switch.isHidden()


def test_switching_preserves_shared_writing_and_outline_state(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    workspace = window._workspace_view
    workspace.set_scene("scene-1", "chapter-1")
    workspace.set_prose_text("in memory")
    workspace.set_prose_versions(["v1"], "v1")
    window._outline_view._selected_node_id = "chapter-1"

    _switch(window, "quick")

    assert _labels(window) == ["故事", "大纲", "写章节"]
    assert window._quick_presentation.stack.indexOf(workspace) >= 0
    assert workspace.prose_text() == "in memory"
    assert workspace.current_scene_id == "scene-1"
    assert workspace.current_prose_version() == "v1"
    assert window._outline_view._selected_node_id == "chapter-1"


def test_story_mapping_restores_remembered_deep_location(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)

    _switch(window, "quick")
    _switch(window, "deep")

    assert window.sidebar.currentItem().data(256) == "dashboard"
    window._select_destination("bible")
    _switch(window, "quick")
    _switch(window, "deep")
    assert window.sidebar.currentItem().data(256) == "bible"


@pytest.mark.parametrize("answer", [QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Discard])
def test_bible_to_story_resolves_dirty_editor(tmp_path, qtbot, monkeypatch, answer):
    window = _window(tmp_path, qtbot)
    window._bible_view.load_project_dir(window._current_project_dir)
    window._select_destination("bible")
    calls = []
    monkeypatch.setattr(type(window._bible_view), "is_dirty", property(lambda _: True))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: answer)
    monkeypatch.setattr(window._bible_view, "save_all", lambda: calls.append("save") or True)
    monkeypatch.setattr(window._bible_view, "reload", lambda: calls.append("discard"))

    _switch(window, "quick")

    assert window._experience_mode == "quick"
    assert calls == (["save"] if answer == QMessageBox.StandardButton.Save else ["discard"])


def test_bible_to_story_can_cancel(tmp_path, qtbot, monkeypatch):
    window = _window(tmp_path, qtbot)
    window._bible_view.load_project_dir(window._current_project_dir)
    window._select_destination("bible")
    monkeypatch.setattr(type(window._bible_view), "is_dirty", property(lambda _: True))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Cancel)

    _switch(window, "quick")

    assert window._experience_mode == "deep"
    assert _labels(window) == ["总览", "设定集", "大纲", "写作台"]


@pytest.mark.parametrize("destination", ["outline", "workspace"])
def test_same_editor_switch_skips_unrelated_dirty_bible_and_workflow(tmp_path, qtbot, monkeypatch, destination):
    window = _window(tmp_path, qtbot)
    window._bible_view.load_project_dir(window._current_project_dir)
    window._select_destination(destination)
    monkeypatch.setattr(type(window._bible_view), "is_dirty", property(lambda _: True))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: pytest.fail("unexpected dirty prompt"))
    monkeypatch.setattr(
        window._application.scene_workflow,
        "start",
        lambda *_args: pytest.fail("experience switch started generation"),
    )

    _switch(window, "quick")

    assert window._previous_destination == destination
    assert window.stack.currentWidget() is window._views[destination]
