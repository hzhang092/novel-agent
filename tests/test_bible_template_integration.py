from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app.storage.bible_models import FactionElement, WorldOverview
from app.storage.bible_repository import WorldBibleService
from app.storage.models import Project
from app.storage.project_files import create_project
from app.ui.bible_editor import BibleEditorView
from app.ui.template_apply_dialog import TemplateApplyDialog
from app.ui.world_bible_editor import WorldBibleEditorView


def test_world_editor_stages_snapshot_without_writing_until_save(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    manifest_before = (project_dir / "bible" / "manifest.yaml").read_bytes()

    editor.stage_snapshot(
        WorldOverview(geography="Eastern continent"),
        [FactionElement(id="jade-sect", name="Jade Sect")],
    )

    assert editor.is_dirty is True
    assert (project_dir / "bible" / "manifest.yaml").read_bytes() == manifest_before
    assert not (project_dir / "bible" / "elements" / "jade-sect.yaml").exists()

    assert editor.save_all() is True
    saved = WorldBibleService(project_dir).load()
    assert saved.overview.geography == "Eastern continent"
    assert [element.name for element in saved.elements] == ["Jade Sect"]
    assert editor.is_dirty is False


def test_discard_reverts_staged_snapshot(tmp_path, qtbot, monkeypatch):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    editor.stage_snapshot(
        WorldOverview(geography="Eastern continent"),
        [FactionElement(id="jade-sect", name="Jade Sect")],
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard,
    )

    editor._element_list.select_element("jade-sect")

    assert editor.overview_in_memory() == WorldOverview()
    assert editor.elements_in_memory() == []
    assert editor.is_dirty is False


def test_bible_editor_applies_typed_template_in_memory_then_saves(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    manifest_before = (project_dir / "bible" / "manifest.yaml").read_bytes()

    def accept_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, TemplateApplyDialog)
        dialog.accept()

    QTimer.singleShot(0, accept_dialog)
    editor._overview_template_btn.click()

    assert editor.is_dirty is True
    assert len(editor._world_tab.elements_in_memory()) == 13
    assert (project_dir / "bible" / "manifest.yaml").read_bytes() == manifest_before

    assert editor.save_all() is True
    assert len(WorldBibleService(project_dir).load().elements) == 13


def test_replace_template_confirmation_shows_exact_counts(
    tmp_path, qtbot, monkeypatch
):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    messages = []

    def choose_replace():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, TemplateApplyDialog)
        dialog._replace.setChecked(True)
        dialog.accept()

    def confirm(_parent, _title, message, *_args, **_kwargs):
        messages.append(message)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", confirm)
    QTimer.singleShot(0, choose_replace)
    editor._overview_template_btn.click()

    assert len(messages) == 1
    assert "5 fields replaced" in messages[0]
    assert "5 factions replaced" in messages[0]
    assert "6 terminology entries replaced" in messages[0]
    assert "1 historical event replaced" in messages[0]
    assert "1 power system replaced" in messages[0]
    assert editor.is_dirty is False


def test_style_only_template_ignores_ambiguous_world_names(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    WorldBibleService(project_dir).apply_snapshot(
        WorldOverview(),
        [
            FactionElement(id="jade-1", name="青云宗"),
            FactionElement(id="jade-2", name=" 青云宗 "),
        ],
    )
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)

    def accept_style_only():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, TemplateApplyDialog)
        dialog._world.setChecked(False)
        dialog.accept()

    QTimer.singleShot(0, accept_style_only)
    editor._overview_template_btn.click()

    assert editor._gather_style().pacing == "很快"
    assert editor.is_dirty is True
