from app.storage.models import Project
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
