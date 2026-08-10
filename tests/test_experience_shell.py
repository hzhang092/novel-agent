import pytest
from PySide6.QtWidgets import QMessageBox, QProgressBar

import app.ui.main_window as main_window_module
from app.storage.models import ChapterOutline, Project, SceneOutline, VolumeOutline
from app.storage.project_files import (
    create_project,
    load_all_volumes,
    load_project,
    save_volume_outline,
)
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


def test_quick_activity_surface_is_indeterminate_and_clears_cleanly(qtbot):
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)

    progress = window.findChild(QProgressBar, "quick_activity_progress")
    assert progress is not None
    assert progress.isHidden()

    window._set_quick_activity(True, "快速创作 · 第 3 章：正在写作…")

    assert not progress.isHidden()
    assert progress.minimum() == 0
    assert progress.maximum() == 0
    assert window.statusBar().currentMessage() == "快速创作 · 第 3 章：正在写作…"

    window._set_quick_activity(False, "第 3 章处理完成，可返回查看")

    assert progress.isHidden()
    assert window.statusBar().currentMessage() == "第 3 章处理完成，可返回查看"

    window._set_quick_activity(False)

    assert window.statusBar().currentMessage() == ""


def test_quick_story_activity_is_projected_into_the_shell(qtbot):
    class Signal:
        def connect(self, callback):
            self.callback = callback

        def emit(self, *args):
            self.callback(*args)

    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    signal = Signal()
    window._quick_story_view.activity_changed = signal
    window._connect_view_signals()

    signal.emit(True, "正在生成故事提案…")

    assert not window.findChild(QProgressBar, "quick_activity_progress").isHidden()
    assert window.statusBar().currentMessage() == "快速创作 · 正在生成故事提案…"

    signal.emit(False, "故事提案已生成")

    assert window.findChild(QProgressBar, "quick_activity_progress").isHidden()
    assert window.statusBar().currentMessage() == "快速创作 · 故事提案已生成"


def test_stale_story_or_scene_activity_cannot_clear_newer_owner(
    tmp_path, qtbot
):
    window = _window(tmp_path, qtbot)
    window._set_experience_mode("quick")
    window._workspace_view.set_scene("scene-1", "ch-1")
    observer = window._scene_workflow_observer("scene-1")
    progress = window.findChild(QProgressBar, "quick_activity_progress")

    observer.generating(True)
    window._on_quick_story_activity(True, "正在生成故事提案…")
    observer.generating(False)

    assert not progress.isHidden()
    assert window.statusBar().currentMessage() == "快速创作 · 正在生成故事提案…"

    window._on_quick_story_activity(True, "正在生成故事提案…")
    observer.generating(True)
    window._on_quick_story_activity(False, "故事提案已生成")

    assert not progress.isHidden()
    assert "当前章节" in window.statusBar().currentMessage()


def test_project_rebind_cancels_old_generation_and_clears_activity(
    tmp_path, qtbot, monkeypatch
):
    first_dir = create_project(tmp_path / "first", Project(title="First"))
    second_dir = create_project(tmp_path / "second", Project(title="Second"))
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(first_dir)
    old_application = window._application
    old_application.scene_workflow.state.active = True
    cancelled = []
    monkeypatch.setattr(
        window._quick_story_view,
        "cancel_generation",
        lambda: cancelled.append("story"),
    )
    monkeypatch.setattr(
        old_application.scene_workflow,
        "cancel",
        lambda: cancelled.append("scene"),
    )
    window._set_quick_activity(True, "快速创作 · 正在写作…")

    window._bind_project_application(second_dir)

    assert "story" in cancelled
    assert "scene" in cancelled
    assert window._application is not old_application
    assert window._quick_activity_progress.isHidden()


def test_close_cancels_generation_only_after_dirty_confirmation(
    tmp_path, qtbot, monkeypatch
):
    window = _window(tmp_path, qtbot)
    window._application.scene_workflow.state.active = True
    cancelled = []
    monkeypatch.setattr(
        window._quick_story_view,
        "cancel_generation",
        lambda: cancelled.append("story"),
    )
    monkeypatch.setattr(
        window._application.scene_workflow,
        "cancel",
        lambda: cancelled.append("scene"),
    )

    class Event:
        accepted = False

        def accept(self):
            self.accepted = True

        def ignore(self):
            self.accepted = False

    event = Event()
    monkeypatch.setattr(window, "_maybe_close_current_project", lambda: False)
    window.closeEvent(event)

    assert event.accepted is False
    assert cancelled == []

    monkeypatch.setattr(window, "_maybe_close_current_project", lambda: True)
    window.closeEvent(event)

    assert event.accepted is True
    assert cancelled == ["story", "scene"]


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


def test_story_continuation_cta_opens_quick_outline(tmp_path, qtbot):
    window = _outline_window(tmp_path, qtbot)
    _switch(window, "quick")
    window._quick_story_view.refresh_quick_projection()
    window._select_destination("story")

    button = window._quick_story_view.continue_outline_button
    assert not button.isHidden()

    button.click()

    assert window._experience_mode == "quick"
    assert window._previous_destination == "outline"
    assert window.stack.currentWidget() is window._quick_outline_view


def test_bootstrap_reload_refreshes_story_continuation_cta(tmp_path, qtbot):
    window = _window(tmp_path, qtbot)
    save_volume_outline(
        window._current_project_dir,
        VolumeOutline(
            id="volume-1",
            chapters=[
                ChapterOutline(
                    id="chapter-1",
                    scenes=[SceneOutline(id="scene-1")],
                )
            ],
        ),
    )

    assert window._quick_story_view.continue_outline_button.isHidden()
    window._reload_after_bootstrap()

    assert not window._quick_story_view.continue_outline_button.isHidden()


def test_quick_project_creation_uses_status_bar_instead_of_modal(
    tmp_path, qtbot, monkeypatch
):
    class Dialog:
        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return True

        def get_result(self):
            return {
                "title": "快速新作",
                "storage_dir": str(tmp_path),
                "creation_mode": "quick",
            }

    information_calls = []
    monkeypatch.setattr(main_window_module, "CreateProjectDialog", Dialog)
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: information_calls.append(args),
    )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)

    window._on_new_project()

    assert information_calls == []
    assert window._current_project_dir is not None
    assert window._experience_mode == "quick"
    assert window._previous_destination == "story"
    assert window.stack.currentWidget() is window._quick_story_view
    assert window.statusBar().currentMessage() == "项目已创建，开始构思故事"
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


def test_quick_outline_save_refreshes_clean_deep_outline(tmp_path, qtbot):
    window = _outline_window(tmp_path, qtbot)
    window._quick_outline_view.refresh()
    window._quick_outline_view.select_chapter("chapter-1")
    window._quick_outline_view.title_edit.setText("快速标题")
    window._quick_outline_view.summary_edit.setPlainText("快速概要")
    window._quick_outline_view.ending_hook_edit.setText("快速钩子")

    window._quick_outline_view.save_button.click()

    chapter = window._outline_view._volumes[0].chapters[0]
    assert chapter.title == "快速标题"
    assert chapter.summary == "快速概要"
    assert chapter.scenes[0].ending_hook == "快速钩子"


def test_deep_outline_save_refreshes_quick_outline(tmp_path, qtbot, monkeypatch):
    window = _outline_window(tmp_path, qtbot)
    refreshed = []
    real_refresh = window._quick_outline_view.refresh
    monkeypatch.setattr(
        window._quick_outline_view,
        "refresh",
        lambda: refreshed.append(True) or real_refresh(),
    )
    window._outline_view._scene_title.setText("深度标题")

    assert window._outline_view.save() is True

    assert refreshed == [True]


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


@pytest.mark.parametrize(
    "answer",
    [
        QMessageBox.StandardButton.Save,
        QMessageBox.StandardButton.Discard,
        QMessageBox.StandardButton.Cancel,
    ],
)
def test_switching_dirty_quick_outline_resolves_before_experience_change(
    tmp_path, qtbot, monkeypatch, answer
):
    window = _outline_window(tmp_path, qtbot)
    _switch(window, "quick")
    quick = window._quick_outline_view
    quick.select_chapter("chapter-1")
    quick.title_edit.setText("快速未保存")
    prompts = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: prompts.append(True) or answer,
    )

    _switch(window, "deep")

    assert prompts == [True]
    if answer == QMessageBox.StandardButton.Cancel:
        assert window._experience_mode == "quick"
        assert window._previous_destination == "outline"
        assert quick.title_edit.text() == "快速未保存"
        assert quick.is_dirty is True
    else:
        assert window._experience_mode == "deep"
        assert quick.is_dirty is False
        assert window._outline_view._volumes[0].chapters[0].title == (
            "快速未保存" if answer == QMessageBox.StandardButton.Save else ""
        )


@pytest.mark.parametrize(
    "answer",
    [
        QMessageBox.StandardButton.Save,
        QMessageBox.StandardButton.Discard,
        QMessageBox.StandardButton.Cancel,
    ],
)
def test_switching_dirty_quick_outline_resolves_before_destination_change(
    tmp_path, qtbot, monkeypatch, answer
):
    window = _outline_window(tmp_path, qtbot)
    _switch(window, "quick")
    quick = window._quick_outline_view
    quick.select_chapter("chapter-1")
    quick.title_edit.setText("快速未保存")
    prompts = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: prompts.append(True) or answer,
    )

    window._select_destination("workspace")

    assert prompts == [True]
    if answer == QMessageBox.StandardButton.Cancel:
        assert window._previous_destination == "outline"
        assert quick.title_edit.text() == "快速未保存"
        assert quick.is_dirty is True
    else:
        assert window._previous_destination == "workspace"
        assert quick.is_dirty is False
        assert window._outline_view._volumes[0].chapters[0].title == (
            "快速未保存" if answer == QMessageBox.StandardButton.Save else ""
        )


def test_dirty_quick_outline_blocks_project_close(tmp_path, qtbot, monkeypatch):
    window = _outline_window(tmp_path, qtbot)
    _switch(window, "quick")
    quick = window._quick_outline_view
    quick.select_chapter("chapter-1")
    quick.title_edit.setText("快速未保存")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Cancel,
    )

    assert window._maybe_close_current_project() is False
    assert quick.title_edit.text() == "快速未保存"


def test_dirty_quick_outline_blocks_advanced_outline_shortcut(
    tmp_path, qtbot, monkeypatch
):
    window = _outline_window(tmp_path, qtbot)
    _switch(window, "quick")
    quick = window._quick_outline_view
    quick.select_chapter("chapter-1")
    quick.title_edit.setText("快速未保存")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Cancel,
    )

    window._open_deep_outline("chapter-1")

    assert window._experience_mode == "quick"
    assert window._previous_destination == "outline"
    assert quick.title_edit.text() == "快速未保存"


@pytest.mark.parametrize(
    "answer",
    [
        QMessageBox.StandardButton.Save,
        QMessageBox.StandardButton.Discard,
        QMessageBox.StandardButton.Cancel,
    ],
)
def test_quick_outline_write_chapter_resolves_dirty_card_before_scene_navigation(
    tmp_path, qtbot, monkeypatch, answer
):
    window = _window(tmp_path, qtbot)
    save_volume_outline(
        window._current_project_dir,
        VolumeOutline(
            id="volume-1",
            chapters=[
                ChapterOutline(
                    id="chapter-a",
                    scenes=[SceneOutline(id="scene-a", title="A")],
                ),
                ChapterOutline(
                    id="chapter-b",
                    scenes=[SceneOutline(id="scene-b", title="B")],
                ),
            ],
        ),
    )
    window._outline_view.load_project_dir(window._current_project_dir)
    window._quick_outline_view.refresh()
    _switch(window, "quick")
    window._select_destination("outline")
    quick = window._quick_outline_view
    quick.select_chapter("chapter-a")
    quick.title_edit.setText("快速未保存")
    window._on_scene_selected("scene-a")
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: answer)

    quick._card_widgets["chapter-b"]["write"].click()

    if answer == QMessageBox.StandardButton.Cancel:
        assert window._previous_destination == "outline"
        assert window._workspace_view.current_scene_id == "scene-a"
        assert window._workspace_view.current_chapter_id == "chapter-a"
        assert load_project(window._current_project_dir).last_active_chapter_id == "chapter-a"
        assert quick.title_edit.text() == "快速未保存"
        assert quick.is_dirty is True
    else:
        assert window._previous_destination == "workspace"
        assert window._workspace_view.current_scene_id == "scene-b"
        assert window._workspace_view.current_chapter_id == "chapter-b"
        assert quick.is_dirty is False
        assert load_project(window._current_project_dir).last_active_chapter_id == "chapter-b"
        if answer == QMessageBox.StandardButton.Save:
            assert load_all_volumes(window._current_project_dir)[0].chapters[0].title == (
                "快速未保存"
            )
        else:
            assert load_all_volumes(window._current_project_dir)[0].chapters[0].title == ""


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
