from app.storage.bible_models import FactionElement
from app.storage.bible_repository import BibleElementRepository
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.models import CharacterCore, CharacterElementRelation, Project
from app.storage.project_files import create_project
from app.ui.bible_editor import BibleEditorView
from app.ui.main_window import MainWindow
from app.ui.outline_editor import OutlineEditorView


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

    window.sidebar.setCurrentRow(2)

    assert window.sidebar.currentRow() == 1
    assert window.stack.currentWidget() is bible
    assert bible.is_dirty is True


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
    monkeypatch.setattr(outline, "_select_by_id", selected.append)

    bible.scene_requested.emit("scene-42")

    assert selected == ["scene-42"]
    assert window.sidebar.currentRow() == 3
