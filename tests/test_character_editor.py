"""Integration tests for character editor: load -> edit -> save -> reload round-trip."""

import pytest

from app.storage.models import (
    Character,
    CharacterCore,
    CharacterState,
    CharacterTier,
    Project,
)
from app.storage.project_files import create_project, load_character


def _project_with_character(tmp_path, *, character_id="char-1", name="林轩"):
    from app.storage.project_files import save_character

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id=character_id, name=name),
            state=CharacterState(character_id=character_id),
        ),
    )
    return proj_dir


def _add_saved_character(proj_dir, *, character_id, name):
    from app.storage.project_files import save_character

    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id=character_id, name=name),
            state=CharacterState(character_id=character_id),
        ),
    )


def test_character_layout_starts_with_tier_defaults_and_populated_fields(
    tmp_path, qtbot
):
    from app.storage.project_files import save_character
    from app.ui.character_editor import CharacterEditorView

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(
                id="char-1",
                name="林轩",
                tier=CharacterTier.MAJOR,
                speech_style="沉稳少言",
            ),
            state=CharacterState(character_id="char-1"),
        ),
    )
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)

    visible = {
        field_id
        for field_id, container in editor._detail_fields.items()
        if not container.isHidden()
    }
    assert visible == {"personality", "long_term_goal", "speech_style"}
    assert editor.is_dirty is False


def test_unknown_character_layout_ids_are_logged_and_pruned(tmp_path, qtbot, caplog):
    from app.storage.editor_layout import EditorLayoutStore
    from app.ui.character_editor import CharacterEditorView

    proj_dir = _project_with_character(tmp_path)
    _add_saved_character(proj_dir, character_id="char-2", name="韩立")
    store = EditorLayoutStore(proj_dir)
    layout = store.character_layout("char-1")
    layout.visible_fields = ["personality", "future-field"]
    layout.collapsed_sections = ["characterization", "future-section"]
    other_layout = store.character_layout("char-2")
    other_layout.visible_fields = ["future-other-field"]
    other_layout.collapsed_sections = ["future-other-section"]
    store.save()

    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)

    layout = editor._layout_store.character_layout("char-1")
    assert layout.visible_fields == ["personality"]
    assert layout.collapsed_sections == ["characterization"]
    assert editor._layout_store.character_layout("char-2").visible_fields == []
    assert editor._layout_store.character_layout("char-2").collapsed_sections == []
    assert "future-field" in caplog.text
    assert "future-section" in caplog.text
    assert "future-other-field" in caplog.text


def test_hiding_populated_detail_preserves_value_and_story_dirty_state(
    tmp_path, qtbot
):
    from PySide6.QtWidgets import QToolButton
    from app.storage.project_files import save_character
    from app.ui.character_editor import CharacterEditorView

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(
                id="char-1", name="林轩", speech_style="沉稳少言"
            ),
            state=CharacterState(character_id="char-1"),
        ),
    )
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)

    hide_button = editor._detail_fields["speech_style"].findChild(QToolButton)
    hide_button.click()
    qtbot.wait(200)

    assert editor._detail_fields["speech_style"].isHidden()
    assert editor._gather_core("char-1").speech_style == "沉稳少言"
    assert editor.is_dirty is False

    reopened = CharacterEditorView()
    qtbot.addWidget(reopened)
    reopened.load_project_dir(proj_dir)
    assert reopened._detail_fields["speech_style"].isHidden()
    assert reopened._gather_core("char-1").speech_style == "沉稳少言"


def test_hidden_edited_detail_survives_normal_save_and_reload(tmp_path, qtbot):
    from app.storage.project_files import save_character
    from app.ui.character_editor import CharacterEditorView

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(
                id="char-1", name="林轩", speech_style="沉稳少言"
            ),
            state=CharacterState(character_id="char-1"),
        ),
    )
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._core_speech.setText("言简意赅")
    editor._on_hide_detail("speech_style")

    assert editor.save_current_character() is True
    qtbot.wait(200)

    reopened = CharacterEditorView()
    qtbot.addWidget(reopened)
    reopened.load_project_dir(proj_dir)
    assert reopened._detail_fields["speech_style"].isHidden()
    assert load_character(proj_dir, "char-1").core.speech_style == "言简意赅"


def test_hidden_major_character_detail_remains_in_generation_context(
    tmp_path, qtbot
):
    from app.pipeline.context_builder import RetrievalEngine
    from app.storage.models import ChapterOutline, SceneOutline, VolumeOutline
    from app.storage.project_files import save_character, save_volume_outline
    from app.ui.character_editor import CharacterEditorView

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(
                id="char-1",
                name="林轩",
                tier=CharacterTier.MAJOR,
                speech_style="沉稳少言",
            ),
            state=CharacterState(character_id="char-1"),
        ),
    )
    scene = SceneOutline(title="测试场景", participating_character_ids=["char-1"])
    save_volume_outline(
        proj_dir,
        VolumeOutline(title="第一卷", chapters=[ChapterOutline(title="第一章", scenes=[scene])]),
    )
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._on_hide_detail("speech_style")

    context = RetrievalEngine().assemble(proj_dir, scene_id=scene.id)

    assert context["characters"]["major"][0]["core"]["speech_style"] == "沉稳少言"


def test_uncustomized_draft_recalculates_visible_fields_when_tier_changes(
    tmp_path, qtbot
):
    from app.ui.character_editor import CharacterEditorView

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._on_add_character()

    assert set(editor._current_layout.visible_fields) == {"personality"}
    editor._core_tier.setCurrentIndex(
        editor._core_tier.findData(CharacterTier.MAJOR)
    )

    assert set(editor._current_layout.visible_fields) == {
        "personality",
        "long_term_goal",
    }


def test_add_detail_reveals_and_focuses_existing_editor_without_story_change(
    tmp_path, qtbot
):
    from PySide6.QtCore import Qt
    from app.ui.character_editor import CharacterEditorView

    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(_project_with_character(tmp_path))
    editor.show()

    editor._add_detail_btn.click()
    tree = editor._add_detail_menu._tree
    age_item = next(
        category.child(index)
        for category_index in range(tree.topLevelItemCount())
        for category in [tree.topLevelItem(category_index)]
        for index in range(category.childCount())
        if category.child(index).data(0, Qt.ItemDataRole.UserRole).item_id == "age"
    )
    tree.itemClicked.emit(age_item, 0)

    assert not editor._detail_fields["age"].isHidden()
    assert editor.focusWidget() is editor._core_age
    assert editor.is_dirty is False


def test_character_section_collapse_persists_without_story_dirty_state(
    tmp_path, qtbot
):
    from app.ui.character_editor import CharacterEditorView

    proj_dir = _project_with_character(tmp_path)
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)

    editor._detail_sections["characterization"]._header.click()
    qtbot.wait(200)
    assert editor.is_dirty is False

    reopened = CharacterEditorView()
    qtbot.addWidget(reopened)
    reopened.load_project_dir(proj_dir)
    assert not reopened._detail_sections["characterization"].is_expanded()


def test_existing_tier_change_preserves_fields_and_can_add_recommendations(
    tmp_path, qtbot
):
    from app.ui.character_editor import CharacterEditorView

    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(_project_with_character(tmp_path))
    editor._on_add_detail("age")

    editor._core_tier.setCurrentIndex(
        editor._core_tier.findData(CharacterTier.MAJOR)
    )
    assert set(editor._current_layout.visible_fields) == {"personality", "age"}

    editor._recommended_btn.click()
    assert set(editor._current_layout.visible_fields) == {
        "personality",
        "age",
        "long_term_goal",
    }


def test_reset_visible_fields_keeps_defaults_and_populated_details(
    tmp_path, qtbot, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox
    from app.storage.project_files import save_character
    from app.ui.character_editor import CharacterEditorView

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(
                id="char-1",
                name="林轩",
                tier=CharacterTier.MAJOR,
                speech_style="沉稳少言",
            ),
            state=CharacterState(character_id="char-1"),
        ),
    )
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._on_add_detail("age")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    editor._reset_fields_btn.click()

    assert set(editor._current_layout.visible_fields) == {
        "personality",
        "long_term_goal",
        "speech_style",
    }


def test_character_definition_dirty_state_is_semantic(tmp_path, qtbot):
    from app.ui.character_editor import CharacterEditorView

    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(_project_with_character(tmp_path))

    assert editor.is_dirty is False

    editor._core_name.setText("林轩改")
    assert editor.is_dirty is True

    editor._core_name.setText("林轩")
    assert editor.is_dirty is False


def test_character_list_detail_participates_in_semantic_dirty_state(tmp_path, qtbot):
    from PySide6.QtWidgets import QListWidget
    from app.ui.character_editor import CharacterEditorView

    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(_project_with_character(tmp_path))

    editor._core_aliases._add_button.click()
    assert editor.is_dirty is False

    editor._core_aliases.findChild(QListWidget).item(0).setText("小轩")
    assert editor.is_dirty is True


def test_definition_save_clears_dirty_without_state_event(tmp_path, qtbot):
    from app.storage.character_events import load_events
    from app.ui.character_editor import CharacterEditorView

    proj_dir = _project_with_character(tmp_path)
    char_dir = proj_dir / "characters" / "char-1"
    initial_event_count = len(load_events(char_dir))
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._core_name.setText("林轩改")

    assert editor.save_current_character() is True
    assert editor.is_dirty is False
    assert load_character(proj_dir, "char-1").core.name == "林轩改"
    assert len(load_events(char_dir)) == initial_event_count


def test_failed_definition_save_keeps_dirty_state(tmp_path, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from app.ui.character_editor import CharacterEditorView

    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(_project_with_character(tmp_path))
    editor._core_name.setText("林轩改")
    monkeypatch.setattr(
        editor._application,
        "save_definition",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: None)

    assert editor.save_current_character() is False
    assert editor.is_dirty is True


def test_saving_new_character_creates_initial_state(tmp_path, qtbot):
    from PySide6.QtCore import Qt
    from app.ui.character_editor import CharacterEditorView

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._on_add_character()
    char_id = editor._list.currentItem().data(Qt.ItemDataRole.UserRole)

    assert editor.save_current_character() is True
    assert load_character(proj_dir, char_id).state == CharacterState(
        character_id=char_id
    )


def test_failed_save_prevents_character_switch(tmp_path, qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from app.ui.character_editor import CharacterEditorView

    proj_dir = _project_with_character(tmp_path)
    _add_saved_character(proj_dir, character_id="char-2", name="梅兰")
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._core_name.setText("未保存名字")
    monkeypatch.setattr(
        editor._application,
        "save_definition",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Save,
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: None)

    editor._list.setCurrentRow(1)

    assert editor._list.currentItem().data(Qt.ItemDataRole.UserRole) == "char-1"
    assert editor._core_name.text() == "未保存名字"
    assert editor.is_dirty is True


def test_cancel_character_switch_keeps_unsaved_edit(tmp_path, qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from app.ui.character_editor import CharacterEditorView

    proj_dir = _project_with_character(tmp_path)
    _add_saved_character(proj_dir, character_id="char-2", name="梅兰")
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._core_name.setText("未保存名字")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    editor._list.setCurrentRow(1)

    assert editor._list.currentItem().data(Qt.ItemDataRole.UserRole) == "char-1"
    assert editor._core_name.text() == "未保存名字"
    assert editor.is_dirty is True


def test_discard_character_switch_restores_saved_definition(tmp_path, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from app.ui.character_editor import CharacterEditorView

    proj_dir = _project_with_character(tmp_path)
    _add_saved_character(proj_dir, character_id="char-2", name="梅兰")
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._core_name.setText("不要保存")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )

    editor._list.setCurrentRow(1)

    assert editor._core_name.text() == "梅兰"
    assert editor.is_dirty is False
    assert load_character(proj_dir, "char-1").core.name == "林轩"


def test_save_character_switch_persists_definition(tmp_path, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from app.ui.character_editor import CharacterEditorView

    proj_dir = _project_with_character(tmp_path)
    _add_saved_character(proj_dir, character_id="char-2", name="梅兰")
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._core_name.setText("已保存名字")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Save,
    )

    editor._list.setCurrentRow(1)

    assert editor._core_name.text() == "梅兰"
    assert editor.is_dirty is False
    assert load_character(proj_dir, "char-1").core.name == "已保存名字"


def test_discard_new_character_removes_draft_without_files(tmp_path, qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from app.ui.character_editor import CharacterEditorView

    proj_dir = _project_with_character(tmp_path)
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._on_add_character()
    draft_id = editor._list.currentItem().data(Qt.ItemDataRole.UserRole)
    assert editor.is_dirty is True
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )

    editor._list.setCurrentRow(0)

    assert editor._list.count() == 1
    assert draft_id not in editor._characters
    assert draft_id not in editor._layout_store.layout.characters
    assert not (proj_dir / "characters" / draft_id).exists()


def test_cancel_add_while_current_character_is_dirty_keeps_current_form(
    tmp_path, qtbot, monkeypatch
):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from app.ui.character_editor import CharacterEditorView

    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(_project_with_character(tmp_path))
    editor._core_name.setText("未保存名字")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
    )

    editor._on_add_character()

    assert editor._list.count() == 1
    assert editor._list.currentItem().data(Qt.ItemDataRole.UserRole) == "char-1"
    assert editor._core_name.text() == "未保存名字"


def test_dirty_character_delete_confirmation_mentions_unsaved_changes(
    tmp_path, qtbot, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox
    from app.ui.character_editor import CharacterEditorView

    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(_project_with_character(tmp_path))
    editor._core_name.setText("未保存名字")
    prompts = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda _parent, title, message, *_args, **_kwargs: (
            prompts.append((title, message)) or QMessageBox.StandardButton.No
        ),
    )

    editor._on_delete_character()

    assert "未保存的修改" in prompts[-1][1]


def test_successful_character_delete_removes_layout_entry(
    tmp_path, qtbot, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox
    from app.ui.character_editor import CharacterEditorView

    proj_dir = _project_with_character(tmp_path)
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    assert "char-1" in editor._layout_store.layout.characters
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    editor._on_delete_character()

    assert "char-1" not in editor._layout_store.layout.characters
    assert not (proj_dir / "characters" / "char-1").exists()


def test_character_delete_confirmation_lists_impacted_scenes(
    tmp_path, qtbot, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox
    from app.storage.models import ChapterOutline, SceneOutline, VolumeOutline
    from app.storage.project_files import save_volume_outline
    from app.ui.character_editor import CharacterEditorView

    proj_dir = _project_with_character(tmp_path)
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="volume",
            chapters=[
                ChapterOutline(
                    id="chapter",
                    scenes=[
                        SceneOutline(
                            id="scene",
                            title="Bridge Meeting",
                            participating_character_ids=["char-1"],
                        )
                    ],
                )
            ],
        ),
    )
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    prompts = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda _parent, _title, message, *_args: (
            prompts.append(message) or QMessageBox.StandardButton.No
        ),
    )

    editor._on_delete_character()

    assert "1" in prompts[-1]
    assert "Bridge Meeting" in prompts[-1]


def test_current_state_view_is_read_only(tmp_path, qtbot):
    from app.ui.character_editor import CharacterEditorView

    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(_project_with_character(tmp_path))

    assert all(
        field.isReadOnly()
        for field in (
            editor._state_goal,
            editor._state_emotion,
            editor._state_location,
            editor._state_power,
            editor._state_status,
            editor._state_last_scene,
        )
    )
    for compound in (
        editor._state_relationships,
        editor._state_knowledge,
        editor._state_secrets,
    ):
        assert compound._button_row.isHidden()
    assert editor._presence_panel.isHidden()


def test_manual_state_override_appends_event_for_active_scene(
    tmp_path, qtbot, monkeypatch
):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox
    from app.storage.character_events import load_events
    from app.ui.character_editor import CharacterEditorView
    from app.ui.character_state_edit_dialog import CharacterStateEditDialog

    proj_dir = _project_with_character(tmp_path)
    char_dir = proj_dir / "characters" / "char-1"
    initial_count = len(load_events(char_dir))
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor.set_current_scene_id("scene-9")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    def edit_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, CharacterStateEditDialog)
        dialog.findChild(QLineEdit, "current_goal").setText("寻找剑谱")
        dialog.accept()

    QTimer.singleShot(0, edit_dialog)
    editor._edit_state_btn.click()

    events = load_events(char_dir)
    assert len(events) == initial_count + 1
    assert events[-1].source == "manual_event"
    assert events[-1].scene_id == "scene-9"
    assert load_character(proj_dir, "char-1").state.current_goal == "寻找剑谱"


def test_noop_manual_state_override_appends_no_event(tmp_path, qtbot, monkeypatch):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.storage.character_events import load_events
    from app.ui.character_editor import CharacterEditorView
    from app.ui.character_state_edit_dialog import CharacterStateEditDialog

    proj_dir = _project_with_character(tmp_path)
    char_dir = proj_dir / "characters" / "char-1"
    initial_count = len(load_events(char_dir))
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)

    def accept_unchanged_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, CharacterStateEditDialog)
        dialog.accept()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: pytest.fail("no-op override asked for confirmation"),
    )
    QTimer.singleShot(0, accept_unchanged_dialog)
    editor._edit_state_btn.click()

    assert len(load_events(char_dir)) == initial_count


def test_stale_manual_state_override_is_rejected(tmp_path, qtbot, monkeypatch):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox
    from app.storage.character_events import load_events
    from app.storage.state_repository import commit_character_state_edit
    from app.ui.character_editor import CharacterEditorView
    from app.ui.character_state_edit_dialog import CharacterStateEditDialog

    proj_dir = _project_with_character(tmp_path)
    char_dir = proj_dir / "characters" / "char-1"
    initial_count = len(load_events(char_dir))
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    def edit_stale_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, CharacterStateEditDialog)
        current = load_character(proj_dir, "char-1").state
        concurrent = current.model_copy(update={"current_goal": "并发更新"})
        commit_character_state_edit(char_dir, current, concurrent, source="user")
        dialog.findChild(QLineEdit, "current_goal").setText("过期修改")
        dialog.accept()

    QTimer.singleShot(0, edit_stale_dialog)
    editor._edit_state_btn.click()

    events = load_events(char_dir)
    assert len(events) == initial_count + 1
    assert events[-1].source == "user"
    assert load_character(proj_dir, "char-1").state.current_goal == "并发更新"
    assert warnings and warnings[-1][0] == "状态已变化"


def test_character_save_load_round_trip(tmp_path):
    """Create a character via the editor's gather pattern, save, reload, verify."""
    from app.storage.project_files import (
        list_character_ids,
        save_character,
    )

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    core = CharacterCore(
        name="林轩",
        tier=CharacterTier.MAJOR,
        identity="落云宗外门弟子",
        personality="坚韧不拔",
        core_skills=["基础剑法", "炼药"],
        core_weaknesses=["修为低微"],
    )
    state = CharacterState(
        character_id=core.id,
        current_goal="通过考核",
        current_emotion="紧张",
        current_relationships={"苏清鸾": "暗恋对象"},
    )
    character = Character(core=core, state=state)

    save_character(proj_dir, character)
    loaded = load_character(proj_dir, core.id)

    assert loaded.core.name == "林轩"
    assert loaded.core.tier == CharacterTier.MAJOR
    assert loaded.core.core_skills == ["基础剑法", "炼药"]
    assert loaded.state.current_goal == "通过考核"
    assert loaded.state.current_relationships == {"苏清鸾": "暗恋对象"}

    ids = list_character_ids(proj_dir)
    assert core.id in ids


def test_character_delete_removes_file(tmp_path):
    """Delete removes the character file from disk."""
    from app.storage.project_files import (
        delete_character,
        list_character_ids,
        save_character,
    )

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    core = CharacterCore(name="路人")
    state = CharacterState(character_id=core.id)
    save_character(proj_dir, Character(core=core, state=state))

    assert core.id in list_character_ids(proj_dir)

    delete_character(proj_dir, core.id)
    assert core.id not in list_character_ids(proj_dir)


def test_custom_field_user_flow_saves_and_reloads(tmp_path, qtbot):
    from app.storage.models import CharacterCustomFieldType
    from app.ui.character_editor import CharacterEditorView

    project_dir = _project_with_character(tmp_path)
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    fields = editor._custom_fields
    fields._label.setText("法宝")
    fields._type.setCurrentIndex(fields._type.findData(CharacterCustomFieldType.STRING_LIST))
    fields._value.setPlainText("青锋剑\n玄铁盾")
    fields._include.setChecked(False)
    fields._add.click()

    assert editor._gather_core("char-1").custom_fields[0].value == ["青锋剑", "玄铁盾"]
    assert editor.is_dirty
    assert editor.save_current_character()

    reopened = CharacterEditorView()
    qtbot.addWidget(reopened)
    reopened.load_project_dir(project_dir)
    saved = reopened._gather_core("char-1").custom_fields[0]
    assert (saved.label, saved.value, saved.include_in_generation) == ("法宝", ["青锋剑", "玄铁盾"], False)


def test_story_connection_filters_targets_and_persists_stable_id(tmp_path, qtbot):
    from app.storage.bible_models import FactionElement, LocationElement
    from app.storage.bible_repository import BibleElementRepository
    from app.storage.models import CharacterElementRelationKind
    from app.ui.character_editor import CharacterEditorView

    project_dir = _project_with_character(tmp_path)
    repository = BibleElementRepository(project_dir)
    repository.create(FactionElement(id="faction-1", name="青云门"))
    repository.create(LocationElement(id="location-1", name="云州"))
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    links = editor._element_relations
    links._kind.setCurrentIndex(links._kind.findData(CharacterElementRelationKind.MEMBER_OF))
    assert [links._target.itemData(index) for index in range(links._target.count())] == ["faction-1"]
    links._add.click()

    assert editor.save_current_character()
    assert load_character(project_dir, "char-1").core.element_relations[0].target_element_id == "faction-1"


def test_custom_field_type_conversion_requires_confirmation_and_is_predictable(
    tmp_path, qtbot, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox
    from app.storage.models import CharacterCustomField, CharacterCustomFieldType
    from app.ui.character_editor import CharacterEditorView

    project_dir = _project_with_character(tmp_path)
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    editor._custom_fields.set_fields([
        CharacterCustomField(label="备注", value_type=CharacterCustomFieldType.LONG_TEXT, value="甲\n乙")
    ])
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    fields = editor._custom_fields
    fields._list.setCurrentRow(0)
    fields._type.setCurrentIndex(fields._type.findData(CharacterCustomFieldType.STRING_LIST))

    assert editor._gather_core("char-1").custom_fields[0].value == ["甲", "乙"]
    assert editor.is_dirty


def test_hiding_custom_field_preserves_value_without_story_dirty_state(tmp_path, qtbot):
    from app.storage.models import CharacterCustomField, CharacterCustomFieldType
    from app.storage.project_files import save_character
    from app.ui.character_editor import CharacterEditorView

    project_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    field = CharacterCustomField(label="暗号", value_type=CharacterCustomFieldType.TEXT, value="春风")
    save_character(project_dir, Character(core=CharacterCore(id="char-1", name="林轩", custom_fields=[field]), state=CharacterState(character_id="char-1")))
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    editor._custom_fields._list.setCurrentRow(0)
    editor._custom_fields._hide.click()

    assert editor._custom_fields.hidden_ids() == [field.id]
    assert editor._gather_core("char-1").custom_fields[0].value == "春风"
    assert editor.is_dirty is False


def test_public_select_character_supports_cross_editor_navigation(tmp_path, qtbot):
    from app.ui.character_editor import CharacterEditorView

    project_dir = _project_with_character(tmp_path)
    _add_saved_character(project_dir, character_id="char-2", name="苏清鸾")
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)

    assert editor.select_character("char-2") is True
    assert editor._current_id == "char-2"
    assert editor.select_character("missing") is False


def test_character_presence_is_read_only_and_navigates_to_scene(tmp_path, qtbot):
    from app.storage.models import ChapterOutline, SceneOutline, VolumeOutline
    from app.storage.project_files import save_volume_outline
    from app.ui.character_editor import CharacterEditorView

    project_dir = _project_with_character(tmp_path)
    save_volume_outline(project_dir, VolumeOutline(id="volume-1", chapters=[
        ChapterOutline(id="chapter-1", scenes=[SceneOutline(
            id="scene-1", title="初入宗门", pov_character_id="char-1"
        )])
    ]))
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)

    group = editor._presence_panel._tree.topLevelItem(0)
    assert not editor._presence_panel.isHidden()
    assert group.text(0) == "角色出场 (1)"
    assert "当前位置" in editor._saved_state_summary.text()
    with qtbot.waitSignal(editor.scene_requested) as signal:
        editor._presence_panel._request_scene(group.child(0), 0)
    assert signal.args == ["scene-1"]
    assert editor.is_dirty is False


def test_story_connection_can_search_edit_note_and_remove(tmp_path, qtbot):
    from app.storage.bible_models import FactionElement
    from app.storage.models import CharacterElementRelationKind
    from app.ui.widgets.character_element_relation_editor import CharacterElementRelationEditor

    links = CharacterElementRelationEditor()
    qtbot.addWidget(links)
    links.set_elements([FactionElement(id="faction-1", name="青云门")])
    links._kind.setCurrentIndex(links._kind.findData(CharacterElementRelationKind.MEMBER_OF))
    assert links._target.isEditable()
    links._note.setText("外门弟子")
    links._add.click()
    links._list.setCurrentRow(0)
    links._note.setText("掌门")
    links._update.click()
    assert links.relations()[0].note == "掌门"
    links._remove.click()
    assert links.relations() == []


def test_add_detail_menu_creates_custom_detail_in_dedicated_section(
    tmp_path, qtbot, monkeypatch
):
    from app.storage.models import CharacterCustomFieldType
    from app.ui.character_editor import CharacterEditorView

    project_dir = _project_with_character(tmp_path)
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    editor._open_add_detail_menu()
    custom_group = next(
        editor._add_detail_menu._tree.topLevelItem(index)
        for index in range(editor._add_detail_menu._tree.topLevelItemCount())
        if editor._add_detail_menu._tree.topLevelItem(index).text(0) == "Custom"
    )
    assert custom_group.child(0).text(0) == "+ Create custom detail"
    monkeypatch.setattr(
        editor,
        "_show_custom_detail_dialog",
        lambda: ("法宝", CharacterCustomFieldType.TEXT, False),
    )

    editor._on_add_detail("__create_custom__")

    assert editor._custom_section.is_expanded()
    assert [(field.label, field.include_in_generation) for field in editor._custom_fields.fields()] == [("法宝", False)]


def test_custom_field_clear_value_updates_field(tmp_path, qtbot):
    from app.storage.models import CharacterCustomField, CharacterCustomFieldType
    from app.ui.widgets.custom_character_field_editor import CustomCharacterFieldEditor

    fields = CustomCharacterFieldEditor()
    qtbot.addWidget(fields)
    fields.set_fields([CharacterCustomField(label="法宝", value_type=CharacterCustomFieldType.TEXT, value="青锋剑")])
    fields._list.setCurrentRow(0)
    fields._clear.click()

    assert fields.fields()[0].value == ""
