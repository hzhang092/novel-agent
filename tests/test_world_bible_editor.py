from app.storage.bible_models import (
    BibleElementRelation,
    BibleElementType,
    BibleRelationKind,
    FactionElement,
    PowerSystemElement,
    WorldOverview,
)
from app.storage.bible_repository import BibleElementRepository
from app.storage.models import Project, WorldSetting
from app.storage.project_files import create_project, save_world_setting
from app.ui.world_bible_editor import WorldBibleEditorView


def test_world_editor_loads_pinned_overview_and_typed_elements(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    save_world_setting(
        project_dir,
        WorldSetting(
            geography="Mountain continent",
            technology_level="Bronze age",
            social_structure="Clan rule",
            rules=["Names bind spirits"],
            taboos=["Never name the dead"],
        ),
    )
    BibleElementRepository(project_dir).create(
        FactionElement(id="faction-1", name="Jade Sect")
    )

    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)

    assert editor._element_list._tree.topLevelItem(0).text(0) == "World Overview"
    assert editor._element_list.selected_element_id() == "overview"
    assert editor._overview_geography.toPlainText() == "Mountain continent"
    assert editor._overview_technology.text() == "Bronze age"
    assert editor._overview_society.text() == "Clan rule"
    assert editor._overview_rules.get_items() == ["Names bind spirits"]
    assert editor._overview_taboos.get_items() == ["Never name the dead"]
    assert editor._element_list._find_item("faction-1") is not None
    assert editor.is_dirty is False


def test_add_element_is_an_unsaved_in_memory_draft_until_saved(tmp_path, qtbot):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    from app.ui.bible_element_dialog import BibleElementDialog

    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    dirty = []
    changed = []
    saved = []
    editor.dirty_changed.connect(dirty.append)
    editor.elements_changed.connect(lambda: changed.append(True))
    editor.element_saved.connect(saved.append)

    def accept_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, BibleElementDialog)
        dialog._name.setText("Jade Sect")
        dialog.accept()

    QTimer.singleShot(0, accept_dialog)
    editor.open_add_element_dialog(BibleElementType.FACTION)
    draft_id = editor._current_id

    assert draft_id not in editor._persisted_ids
    assert not (project_dir / "bible" / "elements" / f"{draft_id}.yaml").exists()
    assert editor.is_dirty is True
    assert dirty[-1] is True
    assert changed == [True]

    assert editor.save_current_element() is True
    assert (project_dir / "bible" / "elements" / f"{draft_id}.yaml").exists()
    assert editor.is_dirty is False
    assert dirty[-1] is False
    assert saved == [draft_id]


def test_failed_migration_clears_previous_project_state_and_cannot_save_it(
    tmp_path, qtbot, monkeypatch
):
    from PyQt6.QtWidgets import QMessageBox
    from app.storage.bible_repository import WorldBibleService

    first_dir = create_project(
        tmp_path / "first", Project(title="First", genre="Fantasy")
    )
    failed_dir = create_project(
        tmp_path / "failed", Project(title="Failed", genre="Fantasy")
    )
    BibleElementRepository(first_dir).create(
        FactionElement(id="from-first", name="First faction")
    )
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(first_dir)
    editor._element_list.select_element("from-first")
    editor._element_editor._name.setText("Unsaved first faction")
    assert editor.is_dirty is True

    real_load = WorldBibleService.load

    def fail_second_project(service):
        if service.project_dir == failed_dir:
            raise OSError("migration failed")
        return real_load(service)

    monkeypatch.setattr(WorldBibleService, "load", fail_second_project)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: None)

    editor.load_project_dir(failed_dir)

    assert editor._project_dir is None
    assert editor._service is None
    assert editor._elements == []
    assert editor._persisted_ids == set()
    assert editor._current_id is None
    assert editor.is_dirty is False
    assert editor.save_all() is True
    assert BibleElementRepository(failed_dir).load_all() == []


def test_migration_notice_is_shown_once_even_when_project_creation_migrated(
    tmp_path, qtbot
):
    project_dir = create_project(
        tmp_path,
        Project(
            title="Legacy",
            genre="Fantasy",
            world_setting=WorldSetting(history="An old war"),
        ),
    )
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)

    assert not editor._migration_notice.isHidden()

    reopened = WorldBibleEditorView()
    qtbot.addWidget(reopened)
    reopened.load_project_dir(project_dir)
    assert reopened._migration_notice.isHidden()


def test_delete_confirmation_reports_outgoing_and_primary_status(
    tmp_path, qtbot, monkeypatch
):
    from app.storage.bible_repository import WorldBibleService

    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    service = WorldBibleService(project_dir)
    faction = FactionElement(id="faction", name="Jade Sect")
    power = PowerSystemElement(
        id="power",
        name="Cultivation",
        relationships=[
            BibleElementRelation(
                kind=BibleRelationKind.USES, target_element_id=faction.id
            )
        ],
    )
    service.apply_snapshot(WorldOverview(), [faction, power])
    service.set_primary_power_system(power.id)
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    editor._element_list.select_element(power.id)
    messages = []
    monkeypatch.setattr(
        editor, "_confirm_delete", lambda message: messages.append(message) or False
    )

    editor._on_delete_element()

    assert "Outgoing relationships: 1" in messages[0]
    assert "Primary power system: yes" in messages[0]
    assert BibleElementRepository(project_dir).load(power.id).name == "Cultivation"
