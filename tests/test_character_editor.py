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
    from PyQt6.QtWidgets import QListWidget
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
    from PyQt6.QtWidgets import QMessageBox
    from app.ui.character_editor import CharacterEditorView

    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(_project_with_character(tmp_path))
    editor._core_name.setText("林轩改")
    monkeypatch.setattr(
        "app.ui.character_editor.save_character_definition",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: None)

    assert editor.save_current_character() is False
    assert editor.is_dirty is True


def test_saving_new_character_creates_initial_state(tmp_path, qtbot):
    from PyQt6.QtCore import Qt
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
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox
    from app.ui.character_editor import CharacterEditorView

    proj_dir = _project_with_character(tmp_path)
    _add_saved_character(proj_dir, character_id="char-2", name="梅兰")
    editor = CharacterEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._core_name.setText("未保存名字")
    monkeypatch.setattr(
        "app.ui.character_editor.save_character_definition",
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
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox
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
    from PyQt6.QtWidgets import QMessageBox
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
    from PyQt6.QtWidgets import QMessageBox
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
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox
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
    assert not (proj_dir / "characters" / draft_id).exists()


def test_cancel_add_while_current_character_is_dirty_keeps_current_form(
    tmp_path, qtbot, monkeypatch
):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox
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
    from PyQt6.QtWidgets import QMessageBox
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


def test_current_state_view_is_read_only(tmp_path, qtbot):
    from PyQt6.QtWidgets import QPushButton
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
        assert all(not button.isEnabled() for button in compound.findChildren(QPushButton))


def test_manual_state_override_appends_event_for_active_scene(
    tmp_path, qtbot, monkeypatch
):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QLineEdit, QMessageBox
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
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QMessageBox
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
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QLineEdit, QMessageBox
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
