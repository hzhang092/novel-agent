import asyncio

import pytest

from app.pipeline.bible_suggestions import BibleSuggestionResponse, CreateElementSuggestion
from app.providers.base import MockProvider
from app.storage.bible_models import (
    BibleElementRelation,
    BibleElementType,
    BibleRelationKind,
    FactionElement,
    PowerSystemElement,
    WorldOverview,
)
from app.storage.bible_repository import BibleElementRepository
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.models import (
    ChapterOutline,
    CharacterCore,
    CharacterElementRelation,
    Project,
    SceneGenerationRecord,
    SceneOutline,
    VolumeOutline,
    WorldSetting,
)
from app.storage.project_files import (
    create_project,
    save_scene_generation_record,
    save_volume_outline,
    save_world_setting,
    set_active_scene_prose_version,
)
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

    assert editor._element_list._tree.topLevelItem(0).text(0) == "世界概览"
    assert editor._element_list.selected_element_id() == "overview"
    assert editor._overview_geography.toPlainText() == "Mountain continent"
    assert editor._overview_technology.text() == "Bronze age"
    assert editor._overview_society.text() == "Clan rule"
    assert editor._overview_rules.get_items() == ["Names bind spirits"]
    assert editor._overview_taboos.get_items() == ["Never name the dead"]
    assert editor._element_list._find_item("faction-1") is not None
    assert editor.is_dirty is False


def test_add_element_is_an_unsaved_in_memory_draft_until_saved(tmp_path, qtbot):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
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
    from PySide6.QtWidgets import QMessageBox
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


def test_world_element_shows_and_opens_connected_character(tmp_path, qtbot):
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
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    requested = []
    editor.character_requested.connect(requested.append)

    editor.load_project_dir(project_dir)
    editor._element_list.select_element("faction")
    item = editor._element_editor._connected_characters.topLevelItem(0)
    editor._element_editor._connected_characters.itemActivated.emit(item, 0)

    assert requested == ["hero"]


def test_world_element_shows_usage_and_requests_scene(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="volume",
            chapters=[
                ChapterOutline(
                    id="chapter",
                    scenes=[
                        SceneOutline(
                            id="scene",
                            chapter_id="chapter",
                            title="At the gate",
                            world_element_ids=["faction"],
                        )
                    ],
                )
            ],
        ),
    )
    BibleElementRepository(project_dir).create(
        FactionElement(id="faction", name="Jade Sect")
    )
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    requested = []
    editor.scene_requested.connect(requested.append)

    editor.load_project_dir(project_dir)
    editor._element_list.select_element("faction")
    group = editor._usage_panel._tree.topLevelItem(0)
    scene = group.child(0)
    editor._usage_panel._tree.itemActivated.emit(scene, 0)

    assert group.text(0) == "场景大纲 (1)"
    assert "使用 1 次" in editor._element_list._find_item("faction").text(0)
    assert requested == ["scene"]


def test_delete_preview_counts_character_links_and_all_story_usage(
    tmp_path, qtbot, monkeypatch
):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="volume",
            chapters=[
                ChapterOutline(
                    id="chapter",
                    scenes=[SceneOutline(
                        id="scene",
                        title="Rumor",
                        world_element_ids=["faction"],
                    )],
                )
            ],
        ),
    )
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
    prose_dir = project_dir / "scenes" / "chapter"
    prose_dir.mkdir(parents=True)
    (prose_dir / "scene.v1.md").write_text(
        "The Jade Sect is whispered about.", encoding="utf-8"
    )
    set_active_scene_prose_version(project_dir, "chapter", "scene", "v1")
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene",
            generated_with={"bible_elements": {"faction": {"revision": 1}}},
        ),
    )
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    editor._element_list.select_element("faction")
    messages = []
    monkeypatch.setattr(
        editor, "_confirm_delete", lambda message: messages.append(message) or False
    )

    editor._on_delete_element()

    assert "Character connections: 1" in messages[0]
    assert "Scene outlines: 1" in messages[0]
    assert "Generated scene revisions: 1" in messages[0]
    assert "Detected prose mentions: 1" in messages[0]
    assert "remain in the prose" in messages[0]


def test_save_refreshes_usage_revision_mismatch(tmp_path, qtbot):
    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    save_volume_outline(
        project_dir,
        VolumeOutline(id="volume", chapters=[ChapterOutline(
            id="chapter",
            scenes=[SceneOutline(id="scene", world_element_ids=["faction"])],
        )]),
    )
    BibleElementRepository(project_dir).create(
        FactionElement(id="faction", name="Jade Sect")
    )
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene",
            generated_with={"bible_elements": {"faction": {"revision": 1}}},
        ),
    )
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    editor._element_list.select_element("faction")

    editor._element_editor._summary.setPlainText("Changed after generation")
    assert editor.save_current_element()

    generated = editor._usage_panel._tree.topLevelItem(1).child(0)
    assert "修订已变化 (1 → 2)" in generated.text(0)


def test_suggest_menu_offers_all_phase4_text_sources(qtbot):
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)

    assert [action.text() for action in editor._suggest_menu.actions()] == [
        "世界概览",
        "当前故事元素",
        "当前场景大纲",
        "当前场景正文",
        "粘贴文本",
        "选中文本",
    ]


def test_suggest_menu_disables_unavailable_context_sources(qtbot):
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)

    editor._update_suggestion_actions()

    assert not editor._suggest_actions["overview"].isEnabled()
    assert editor._suggest_actions["overview"].toolTip() == "请先打开项目"
    assert not editor._suggest_actions["element"].isEnabled()
    assert not editor._suggest_actions["scene_outline"].isEnabled()
    assert not editor._suggest_actions["scene_prose"].isEnabled()
    assert editor._suggest_actions["paste"].isEnabled()
    assert not editor._suggest_actions["selected"].isEnabled()


@pytest.mark.asyncio
async def test_rejected_ai_review_writes_nothing_and_closes_provider(
    tmp_path, qtbot, monkeypatch
):
    from PySide6.QtWidgets import QDialog
    from app.ui.bible_suggestion_dialog import BibleSuggestionDialog

    class ClosingProvider(MockProvider):
        closed = False

        async def close(self):
            self.closed = True

    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    provider = ClosingProvider(
        structured_response=BibleSuggestionResponse(
            proposals=[
                CreateElementSuggestion(
                    proposal_id="new-sect",
                    confidence=0.9,
                    element_type="faction",
                    name="Jade Sect",
                )
            ]
        )
    )
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    monkeypatch.setattr(BibleSuggestionDialog, "exec", lambda _self: QDialog.DialogCode.Rejected)

    await editor._run_suggestions("The Jade Sect rules the valley.", provider=provider)

    assert BibleElementRepository(project_dir).load_all() == []
    assert provider.closed is True
    assert editor._suggest_button.isEnabled()


@pytest.mark.asyncio
async def test_accepted_ai_review_applies_selected_suggestions(
    tmp_path, qtbot, monkeypatch
):
    from PySide6.QtWidgets import QDialog
    from app.ui.bible_suggestion_dialog import BibleSuggestionDialog

    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    provider = MockProvider(
        structured_response=BibleSuggestionResponse(
            proposals=[
                CreateElementSuggestion(
                    proposal_id="new-sect",
                    confidence=0.9,
                    element_type="faction",
                    name="Jade Sect",
                )
            ]
        )
    )
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    monkeypatch.setattr(BibleSuggestionDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)

    await editor._run_suggestions("The Jade Sect rules the valley.", provider=provider)

    assert [item.name for item in BibleElementRepository(project_dir).load_all()] == [
        "Jade Sect"
    ]
    assert editor._suggest_status.text() == "已应用 1 条建议"


@pytest.mark.asyncio
async def test_cancel_ai_extraction_closes_provider_and_restores_controls(
    tmp_path, qtbot, monkeypatch
):
    from app.pipeline.agents.bible_assistant import BibleAssistantAgent

    class ClosingProvider(MockProvider):
        closed = False

        async def close(self):
            self.closed = True

    async def wait_forever(*_args, **_kwargs):
        await asyncio.Event().wait()

    project_dir = create_project(tmp_path, Project(title="Story", genre="Fantasy"))
    provider = ClosingProvider()
    editor = WorldBibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    monkeypatch.setattr(BibleAssistantAgent, "generate", wait_forever)
    editor._suggest_task = asyncio.create_task(
        editor._run_suggestions("Jade Sect", provider=provider)
    )
    await asyncio.sleep(0)

    editor._cancel_suggestions()
    await editor._suggest_task

    assert provider.closed is True
    assert editor._suggest_button.isEnabled()
    assert not editor._cancel_suggest_button.isVisible()
    assert editor._suggest_status.text() == "已取消建议"
