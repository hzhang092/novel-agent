import asyncio

import pytest

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from app.storage.bible_models import FactionElement
from app.storage.bible_repository import BibleElementRepository
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.models import CharacterCore, CharacterElementRelation, Project
from app.storage.project_files import create_project
from app.ui.bible_editor import BibleEditorView
from app.ui.character_editor import CharacterEditorView
from app.ui.main_window import MainWindow
from app.ui.outline_editor import OutlineEditorView
from app.ui.world_bible_editor import WorldBibleEditorView


def _make_bible_dirty(bible, _section, monkeypatch):
    monkeypatch.setattr(type(bible), "is_dirty", property(lambda _self: True))
    assert bible.is_dirty is True


def test_main_window_binds_one_shared_project_context(tmp_path, qtbot, monkeypatch):
    first_dir = create_project(
        tmp_path / "first", Project(title="First", genre="Fantasy")
    )
    second_dir = create_project(
        tmp_path / "second", Project(title="Second", genre="Fantasy")
    )
    window = MainWindow()
    qtbot.addWidget(window)

    bible_bindings = []
    outline_bindings = []
    monkeypatch.setattr(window._bible_view, "bind_application", bible_bindings.append)
    monkeypatch.setattr(window._outline_view, "bind_application", outline_bindings.append)

    window._bind_project_application(first_dir)
    first = window._application
    assert bible_bindings == [first]
    assert outline_bindings == [first.outlines]

    window._bind_project_application(second_dir)

    assert window._application is not first
    assert window._application.project_dir == second_dir
    assert bible_bindings[-1] is window._application
    assert outline_bindings[-1] is window._application.outlines


def test_failed_bible_save_blocks_navigation(tmp_path, qtbot, monkeypatch):
    project_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_nav_items_enabled(True)

    bible = window._bible_view
    assert isinstance(bible, BibleEditorView)
    bible.load_project_dir(project_dir)
    window.sidebar.setCurrentRow(1)
    _make_bible_dirty(bible, "world", monkeypatch)
    monkeypatch.setattr(bible, "save_all", lambda: False)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Save,
    )

    window.sidebar.setCurrentRow(2)

    assert window.sidebar.currentRow() == 1
    assert window.stack.currentWidget() is bible
    assert bible.is_dirty is True


@pytest.mark.parametrize("section", ["world", "style", "character"])
def test_cancel_keeps_dirty_bible_open_during_navigation(
    tmp_path, qtbot, monkeypatch, section
):
    project_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_nav_items_enabled(True)
    bible = window._bible_view
    bible.load_project_dir(project_dir)
    window.sidebar.setCurrentRow(1)
    _make_bible_dirty(bible, section, monkeypatch)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    window.sidebar.setCurrentRow(2)

    assert window.sidebar.currentRow() == 1
    assert bible.is_dirty is True


@pytest.mark.parametrize("section", ["world", "style", "character"])
def test_cancel_keeps_current_project_when_opening_another(
    tmp_path, qtbot, monkeypatch, section
):
    current_dir = create_project(
        tmp_path / "current", Project(title="Current", genre="Fantasy")
    )
    other_dir = create_project(
        tmp_path / "other", Project(title="Other", genre="Fantasy")
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project = window._repo.open(current_dir)
    window._current_project_dir = current_dir
    bible = window._bible_view
    bible.load_project_dir(current_dir)
    _make_bible_dirty(bible, section, monkeypatch)
    monkeypatch.setattr(
        "app.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *args: str(other_dir),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    window._on_open_project()

    assert window._current_project_dir == current_dir
    assert bible.is_dirty is True


@pytest.mark.parametrize("section", ["world", "style", "character"])
def test_cancel_rejects_window_close_with_dirty_bible(
    tmp_path, qtbot, monkeypatch, section
):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = project_dir
    bible = window._bible_view
    bible.load_project_dir(project_dir)
    _make_bible_dirty(bible, section, monkeypatch)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )
    event = QCloseEvent()

    window.closeEvent(event)

    assert event.isAccepted() is False


def test_cancel_keeps_current_project_when_creating_another(
    tmp_path, qtbot, monkeypatch
):
    current_dir = create_project(tmp_path, Project(title="Current", genre="Fantasy"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project = window._repo.open(current_dir)
    window._current_project_dir = current_dir
    bible = window._bible_view
    bible.load_project_dir(current_dir)
    _make_bible_dirty(bible, "world", monkeypatch)

    class AcceptedDialog:
        def __init__(self, *_args):
            pass

        def exec(self):
            return True

        def get_result(self):
            return {
                "title": "New",
                "genre": "Fantasy",
                "llm_provider": "",
                "storage_dir": str(tmp_path / "new-parent"),
            }

    monkeypatch.setattr("app.ui.main_window.CreateProjectDialog", AcceptedDialog)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    window._on_new_project()

    assert window._current_project_dir == current_dir
    assert not (tmp_path / "new-parent" / "New").exists()


def test_scene_selection_updates_bible_scene_context(tmp_path, qtbot, monkeypatch):
    project_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = project_dir

    contexts = []
    monkeypatch.setattr(
        window._bible_view,
        "set_current_scene_context",
        lambda scene_id, element_ids: contexts.append((scene_id, element_ids)),
    )

    window._on_scene_selected("scene-42")

    assert contexts == [("scene-42", set())]


def test_world_element_changes_refresh_outline_picker(qtbot, monkeypatch):
    refreshed = []
    monkeypatch.setattr(
        OutlineEditorView,
        "refresh_world_elements",
        lambda _self: refreshed.append(True),
    )
    window = MainWindow()
    qtbot.addWidget(window)
    bible = window._bible_view
    outline = window._outline_view
    assert isinstance(bible, BibleEditorView)
    assert isinstance(outline, OutlineEditorView)
    bible.elements_changed.emit()

    assert refreshed == [True]


def test_connected_character_navigation_switches_bible_tab(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    BibleElementRepository(project_dir).create(
        FactionElement(id="faction", name="Jade Sect")
    )
    CharacterDefinitionService(project_dir).save(
        CharacterCore(
            id="hero",
            name="Lin",
            element_relations=[
                CharacterElementRelation(
                    kind="member_of", target_element_id="faction"
                )
            ],
        )
    )
    bible = BibleEditorView()
    qtbot.addWidget(bible)
    bible.load_project_dir(project_dir)
    world = bible.findChild(WorldBibleEditorView)
    character = bible.findChild(CharacterEditorView)

    world.character_requested.emit("hero")

    assert character.selected_character_id == "hero"


def test_connected_character_navigation_keeps_world_open_when_cancelled(
    tmp_path, qtbot, monkeypatch
):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    CharacterDefinitionService(project_dir).save(CharacterCore(id="other", name="Mei"))
    CharacterDefinitionService(project_dir).save(CharacterCore(id="hero", name="Lin"))
    bible = BibleEditorView()
    qtbot.addWidget(bible)
    bible.load_project_dir(project_dir)
    world = bible.findChild(WorldBibleEditorView)
    character = bible.findChild(CharacterEditorView)
    assert character.select_character("other") is True
    monkeypatch.setattr(world, "prepare_for_navigation", lambda: False)

    world.character_requested.emit("hero")

    assert character.selected_character_id == "other"


def test_usage_scene_navigation_opens_requested_scene(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_nav_items_enabled(True)
    window.sidebar.setCurrentRow(1)
    bible = window._bible_view
    outline = window._outline_view
    selected = []
    monkeypatch.setattr(
        outline, "activate_scene", lambda scene_id: selected.append(scene_id) or True
    )

    bible.scene_requested.emit("scene-42")

    assert selected == ["scene-42"]
    assert window.sidebar.currentRow() == 3


def test_new_project_wires_scene_selection_once(tmp_path, qtbot, monkeypatch):
    selected = []
    monkeypatch.setattr(MainWindow, "_on_scene_selected", lambda _self, scene_id: selected.append(scene_id))
    window = MainWindow()
    qtbot.addWidget(window)

    class AcceptedDialog:
        def __init__(self, *_args):
            pass

        def exec(self):
            return True

        def get_result(self):
            return {
                "title": "New",
                "genre": "Fantasy",
                "llm_provider": "",
                "storage_dir": str(tmp_path),
            }

    monkeypatch.setattr("app.ui.main_window.CreateProjectDialog", AcceptedDialog)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)

    window._on_new_project()
    window._outline_view.scene_selected.emit("scene-new")

    assert selected == ["scene-new"]


def test_open_project_wires_scene_selection_once(tmp_path, qtbot, monkeypatch):
    project_dir = create_project(tmp_path, Project(title="Open", genre="Fantasy"))
    selected = []
    monkeypatch.setattr(MainWindow, "_on_scene_selected", lambda _self, scene_id: selected.append(scene_id))
    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(
        "app.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *_args: str(project_dir),
    )

    window._on_open_project()
    window._outline_view.scene_selected.emit("scene-open")

    assert selected == ["scene-open"]


def test_leaving_outline_uses_public_save_contract(tmp_path, qtbot, monkeypatch):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._outline_view.load_project_dir(project_dir)
    saved = []
    monkeypatch.setattr(window._outline_view, "save", lambda: saved.append(True) or True)
    window._previous_tab_index = 2

    window._on_nav_changed(1)

    assert saved == [True]


def test_bible_navigation_uses_event_bus_facade(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    buses = []
    monkeypatch.setattr(window._bible_view, "set_event_bus", buses.append)
    monkeypatch.setattr(window._bible_view, "refresh_usage", lambda: None)

    window._on_nav_changed(1)

    assert buses == [window._domain_bus]


def test_discarding_dirty_bible_uses_reload_facade(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(BibleEditorView, "is_loaded", property(lambda _self: True))
    monkeypatch.setattr(BibleEditorView, "is_dirty", property(lambda _self: True))
    reloaded = []
    monkeypatch.setattr(window._bible_view, "reload", lambda: reloaded.append(True))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard,
    )

    assert window._maybe_close_current_project() is True
    assert reloaded == [True]


@pytest.mark.asyncio
async def test_plan_decision_signals_resolve_once(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    loop = asyncio.get_running_loop()

    approved = loop.create_future()
    window._plan_decision = approved
    window._workspace_view.plan_approved.emit({"goal": "cross the pass"})
    window._workspace_view.plan_approved.emit({"goal": "duplicate"})
    assert approved.result() == (True, {"goal": "cross the pass"})

    rejected = loop.create_future()
    window._plan_decision = rejected
    window._workspace_view.plan_rejected.emit()
    window._workspace_view.plan_rejected.emit()
    assert rejected.result() == (False, None)


def test_repeated_navigation_does_not_duplicate_generation_signal(qtbot, monkeypatch):
    requested = []
    monkeypatch.setattr(
        MainWindow,
        "_on_generate_requested",
        lambda _self, scene_id: requested.append(scene_id),
    )
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_nav_changed(3)
    window._on_nav_changed(1)
    window._on_nav_changed(3)
    window._workspace_view.generate_requested.emit("scene-1")

    assert requested == ["scene-1"]


def test_next_scene_exhaustion_uses_workspace_facade(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window._workspace_view.set_scene("last-scene", "chapter-1")
    monkeypatch.setattr(
        window._outline_view,
        "select_next_scene",
        lambda _scene_id: None,
    )
    exhausted = []
    monkeypatch.setattr(
        window._workspace_view,
        "mark_last_scene",
        lambda: exhausted.append(True),
    )

    window._on_next_scene()

    assert exhausted == [True]
