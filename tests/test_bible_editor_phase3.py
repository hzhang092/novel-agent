from app.storage.models import Project
from app.storage.project_files import create_project, load_project


def test_bible_editor_saves_world_overview_before_style(tmp_path, qtbot, monkeypatch):
    from app.storage.bible_repository import WorldBibleService
    from app.ui.bible_editor import BibleEditorView
    from app.ui.world_bible_editor import WorldBibleEditorView

    project_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)

    assert isinstance(editor._world_tab, WorldBibleEditorView)
    editor._world_tab._overview_geography.setPlainText("东荒大陆")
    editor._notes_edit.setPlainText("短句")
    assert editor.is_dirty is True

    order = []
    original_world_save = editor._world_tab.save_all

    def save_world():
        order.append("world")
        return original_world_save()

    monkeypatch.setattr(editor._world_tab, "save_all", save_world)
    assert editor.save_all() is True

    assert order == ["world"]
    assert WorldBibleService(project_dir).load().overview.geography == "东荒大陆"
    assert load_project(project_dir).style_guide.freeform_notes == "短句"
    assert editor.is_dirty is False


def test_bible_editor_stops_save_when_world_save_fails(tmp_path, qtbot, monkeypatch):
    from app.ui.bible_editor import BibleEditorView

    project_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    editor._notes_edit.setPlainText("不要保存")

    monkeypatch.setattr(editor._world_tab, "save_all", lambda: False)

    assert editor.save_all() is False
    assert load_project(project_dir).style_guide.freeform_notes == ""
    assert editor.is_dirty is True
