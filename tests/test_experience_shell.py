import pytest
from PySide6.QtWidgets import QMessageBox

from app.storage.models import ChapterOutline, Project, SceneOutline, VolumeOutline
from app.storage.project_files import create_project, load_all_volumes, save_volume_outline
from app.ui.main_window import MainWindow


def _window(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story"))
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    return window


def _labels(window):
    return [window.sidebar.item(index).text() for index in range(window.sidebar.count())]


def _switch(window, mode):
    window._experience_switch.setCurrentIndex(window._experience_switch.findData(mode))


def _outline_window(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    save_volume_outline(
        window._current_project_dir,
        VolumeOutline(
            id="volume-1",
            chapters=[
                ChapterOutline(
                    id="chapter-1",
                    scenes=[SceneOutline(id="scene-1", title="canonical")],
                )
            ],
        ),
    )
    window._outline_view.load_project_dir(window._current_project_dir)
    window._select_destination("outline")
    window._outline_view.activate_scene("scene-1")
    return window


def test_existing_project_defaults_to_deep_with_separate_presentations(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)

    assert _labels(window) == ["总览", "设定集", "大纲", "写作台"]
    assert window._deep_presentation is not window._quick_presentation
    assert window._deep_presentation.sidebar is not window._quick_presentation.sidebar


def test_quick_affordance_is_hidden_without_the_development_flag(qtbot):
    window = MainWindow(quick_creation_enabled=False)
    qtbot.addWidget(window)

    assert window._experience_switch.isHidden()


def test_experience_switch_requires_an_open_project(tmp_path, qtbot):
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)

    assert not window._experience_switch.isEnabled()

    project_dir = create_project(tmp_path, Project(title="Story"))
    window._bind_project_application(project_dir)

    assert window._experience_switch.isEnabled()


def test_disabled_flag_forces_a_quick_preference_back_to_deep(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story"))
    from app.storage.editor_layout import EditorLayoutStore

    layout = EditorLayoutStore(project_dir)
    layout.layout.experience_mode = "quick"
    layout.save()
    window = MainWindow(quick_creation_enabled=False)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    _switch(window, "quick")

    assert window._experience_mode == "deep"
    assert window._presentation_stack.currentWidget() is window._deep_presentation


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
    assert window._quick_presentation.stack.indexOf(window._quick_outline_view) >= 0
    assert window._quick_presentation.stack.indexOf(window._outline_view) == -1
    assert window._deep_presentation.stack.indexOf(window._outline_view) >= 0
    assert workspace.prose_text() == "in memory"
    assert workspace.current_scene_id == "scene-1"
    assert workspace.current_prose_version() == "v1"
    assert window._outline_view._selected_node_id == "chapter-1"


def test_switching_from_clean_deep_outline_does_not_save_before_quick_refresh(
    tmp_path, qtbot, monkeypatch
):
    window = _window(tmp_path, qtbot)
    window._outline_view.load_project_dir(window._current_project_dir)
    window._select_destination("outline")
    calls = []
    monkeypatch.setattr(
        window._outline_view,
        "save",
        lambda: pytest.fail("clean outline should not be saved during switching"),
    )
    monkeypatch.setattr(
        window._quick_outline_view,
        "refresh",
        lambda: calls.append("refresh"),
    )

    _switch(window, "quick")

    assert calls == ["refresh"]


@pytest.mark.parametrize(
    "answer, expected_call",
    [
        (QMessageBox.StandardButton.Save, "save"),
        (QMessageBox.StandardButton.Discard, "reload"),
        (QMessageBox.StandardButton.Cancel, None),
    ],
)
def test_switching_dirty_deep_outline_resolves_before_experience_change(
    tmp_path, qtbot, monkeypatch, answer, expected_call
):
    window = _outline_window(tmp_path, qtbot)
    window._outline_view._scene_title.setText("unsaved")
    window._workspace_view.set_scene("scene-1", "chapter-1")
    window._workspace_view.set_prose_text("in memory")
    calls = []
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: answer)
    real_save = window._outline_view.save
    monkeypatch.setattr(
        window._outline_view,
        "save",
        lambda: calls.append("save") or real_save(),
    )
    real_reload = window._outline_view.reload
    monkeypatch.setattr(
        window._outline_view,
        "reload",
        lambda: calls.append("reload") or real_reload(),
    )

    _switch(window, "quick")

    assert calls == ([] if expected_call is None else [expected_call])
    assert window._workspace_view.prose_text() == "in memory"
    if answer == QMessageBox.StandardButton.Cancel:
        assert window._experience_mode == "deep"
        assert window._previous_destination == "outline"
        assert window._outline_view._scene_title.text() == "unsaved"
        assert window._outline_view.is_dirty is True
    else:
        assert window._experience_mode == "quick"
        if answer == QMessageBox.StandardButton.Save:
            assert load_all_volumes(window._current_project_dir)[0].chapters[0].scenes[0].title == "unsaved"
        else:
            assert window._outline_view._scene_title.text() == "canonical"
            assert window._outline_view.is_dirty is False


@pytest.mark.parametrize(
    "answer, expected_call",
    [
        (QMessageBox.StandardButton.Save, "save"),
        (QMessageBox.StandardButton.Discard, "reload"),
        (QMessageBox.StandardButton.Cancel, None),
    ],
)
def test_switching_dirty_deep_outline_resolves_before_destination_change(
    tmp_path, qtbot, monkeypatch, answer, expected_call
):
    window = _outline_window(tmp_path, qtbot)
    window._outline_view._scene_title.setText("unsaved")
    window._workspace_view.set_scene("scene-1", "chapter-1")
    window._workspace_view.set_prose_text("in memory")
    calls = []
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: answer)
    real_save = window._outline_view.save
    monkeypatch.setattr(
        window._outline_view,
        "save",
        lambda: calls.append("save") or real_save(),
    )
    real_reload = window._outline_view.reload
    monkeypatch.setattr(
        window._outline_view,
        "reload",
        lambda: calls.append("reload") or real_reload(),
    )

    window._select_destination("workspace")

    assert calls == ([] if expected_call is None else [expected_call])
    assert window._workspace_view.prose_text() == "in memory"
    if answer == QMessageBox.StandardButton.Cancel:
        assert window._previous_destination == "outline"
        assert window._outline_view._scene_title.text() == "unsaved"
        assert window._outline_view.is_dirty is True
    else:
        assert window._previous_destination == "workspace"
        if answer == QMessageBox.StandardButton.Save:
            assert load_all_volumes(window._current_project_dir)[0].chapters[0].scenes[0].title == "unsaved"
        else:
            assert window._outline_view._scene_title.text() == "canonical"
            assert window._outline_view.is_dirty is False


def test_project_leave_guard_cannot_skip_dirty_deep_outline(
    tmp_path, qtbot, monkeypatch
):
    window = _outline_window(tmp_path, qtbot)
    window._outline_view._scene_title.setText("unsaved")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Cancel,
    )

    assert window._maybe_close_current_project() is False
    assert window._outline_view._scene_title.text() == "unsaved"
    assert window._outline_view.is_dirty is True


def test_quick_advanced_links_open_the_exact_deep_element(
    tmp_path, qtbot, monkeypatch
):
    window = _window(tmp_path, qtbot)
    calls = []
    monkeypatch.setattr(
        window._bible_view,
        "open_character",
        lambda item_id: calls.append(("character", item_id)) or True,
    )
    monkeypatch.setattr(
        window._bible_view,
        "open_world_element",
        lambda item_id: calls.append(("world", item_id)) or True,
    )
    _switch(window, "quick")

    window._quick_story_view.character_requested.emit("hero-1")
    _switch(window, "quick")
    window._quick_story_view.world_element_requested.emit("power-1")

    assert calls == [("character", "hero-1"), ("world", "power-1")]


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
