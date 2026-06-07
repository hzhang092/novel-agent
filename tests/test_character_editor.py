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
