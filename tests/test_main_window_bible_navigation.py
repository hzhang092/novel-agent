import pytest

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from app.storage.bible_models import FactionElement
from app.storage.bible_repository import BibleElementRepository
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.models import CharacterCore, CharacterElementRelation, Project
from app.storage.project_files import create_project
from app.ui.bible_editor import BibleEditorView
from app.ui.main_window import MainWindow
from app.ui.outline_editor import OutlineEditorView


def _make_bible_dirty(bible, section):
    if section == "world":
        bible._world_tab._overview_geography.setPlainText("unsaved world")
    elif section == "style":
        bible._notes_edit.setPlainText("unsaved style")
    else:
        bible._character_tab._on_add_character()
        bible._character_tab._core_name.setText("unsaved character")
    assert bible.is_dirty is True


def test_main_window_binds_one_shared_project_context(tmp_path, qtbot):
    first_dir = create_project(
        tmp_path / "first", Project(title="First", genre="Fantasy")
    )
    second_dir = create_project(
        tmp_path / "second", Project(title="Second", genre="Fantasy")
    )
    window = MainWindow()
    qtbot.addWidget(window)

    window._bind_project_application(first_dir)

    first = window._application
    bible = window.views["bible"]
    outline = window.views["outline"]
    assert bible._application is first
    assert bible._character_tab._application is first.characters
    assert bible._world_tab._service is first.story_bible
    assert outline._application is first.outlines

    window._bind_project_application(second_dir)

    assert window._application is not first
    assert window._application.project_dir == second_dir
    assert bible._application is window._application
    assert outline._application is window._application.outlines


def test_failed_bible_save_blocks_navigation(tmp_path, qtbot, monkeypatch):
    project_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_nav_items_enabled(True)

    bible = window.views["bible"]
    assert isinstance(bible, BibleEditorView)
    bible.load_project_dir(project_dir)
    window.sidebar.setCurrentRow(1)
    bible._world_tab._overview_geography.setPlainText("未保存地理")
    monkeypatch.setattr(bible._world_tab, "save_all", lambda: False)
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
    bible = window.views["bible"]
    bible.load_project_dir(project_dir)
    window.sidebar.setCurrentRow(1)
    _make_bible_dirty(bible, section)
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
    bible = window.views["bible"]
    bible.load_project_dir(current_dir)
    _make_bible_dirty(bible, section)
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
    bible = window.views["bible"]
    bible.load_project_dir(project_dir)
    _make_bible_dirty(bible, section)
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
    bible = window.views["bible"]
    bible.load_project_dir(current_dir)
    _make_bible_dirty(bible, "world")

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


def test_scene_selection_updates_character_editor_scene_id(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = project_dir

    window._on_scene_selected("scene-42")

    bible = window.views["bible"]
    assert isinstance(bible, BibleEditorView)
    assert bible._character_tab._current_scene_id == "scene-42"
    assert bible._world_tab._current_scene_id == "scene-42"


def test_world_element_changes_refresh_outline_picker(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    bible = window.views["bible"]
    outline = window.views["outline"]
    assert isinstance(bible, BibleEditorView)
    assert isinstance(outline, OutlineEditorView)
    refreshed = []
    monkeypatch.setattr(
        outline, "_refresh_world_elements", lambda: refreshed.append(True)
    )

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
    bible._tabs.setCurrentWidget(bible._world_tab)

    bible._world_tab.character_requested.emit("hero")

    assert bible._tabs.currentWidget() is bible._character_tab
    assert bible._character_tab._current_id == "hero"


def test_connected_character_navigation_keeps_world_open_when_cancelled(
    tmp_path, qtbot, monkeypatch
):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    CharacterDefinitionService(project_dir).save(CharacterCore(id="hero", name="Lin"))
    bible = BibleEditorView()
    qtbot.addWidget(bible)
    bible.load_project_dir(project_dir)
    bible._tabs.setCurrentWidget(bible._world_tab)
    monkeypatch.setattr(bible._world_tab, "_resolve_dirty_before_switch", lambda: False)

    bible._world_tab.character_requested.emit("hero")

    assert bible._tabs.currentWidget() is bible._world_tab


def test_usage_scene_navigation_opens_requested_scene(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_nav_items_enabled(True)
    window.sidebar.setCurrentRow(1)
    bible = window.views["bible"]
    outline = window.views["outline"]
    selected = []
    opened = []
    monkeypatch.setattr(outline, "_select_by_id", selected.append)
    monkeypatch.setattr(window, "_on_scene_selected", opened.append)

    bible.scene_requested.emit("scene-42")

    assert selected == ["scene-42"]
    assert opened == ["scene-42"]
    assert window.sidebar.currentRow() == 3


def test_new_project_wires_scene_selection_once(tmp_path, qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    selected = []
    monkeypatch.setattr(window, "_on_scene_selected", selected.append)

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
    window._wire_project_signals()
    window.views["outline"].scene_selected.emit("scene-new")

    assert selected == ["scene-new"]


def test_open_project_wires_scene_selection_once(tmp_path, qtbot, monkeypatch):
    project_dir = create_project(tmp_path, Project(title="Open", genre="Fantasy"))
    window = MainWindow()
    qtbot.addWidget(window)
    selected = []
    monkeypatch.setattr(window, "_on_scene_selected", selected.append)
    monkeypatch.setattr(
        "app.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *_args: str(project_dir),
    )

    window._on_open_project()
    window._wire_project_signals()
    window.views["outline"].scene_selected.emit("scene-open")

    assert selected == ["scene-open"]
