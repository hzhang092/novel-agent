"""Tests for character file I/O: save, load, delete, list."""

import pytest

from app.storage.models import (
    Character,
    CharacterCore,
    CharacterState,
    CharacterTier,
    Project,
)
from app.storage.project_files import create_project


def test_save_and_load_character_round_trip(tmp_path):
    """Save a full character, reload, verify all Core + State fields preserved."""
    from app.storage.project_files import save_character, load_character

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    core = CharacterCore(
        name="林轩",
        aliases=["轩哥", "废物"],
        tier=CharacterTier.MAJOR,
        identity="落云宗外门弟子",
        age="17",
        appearance="清秀少年，略显瘦弱",
        personality="坚韧不拔，外冷内热",
        background="从小父母失踪，被宗门收养",
        long_term_goal="成为最强修士",
        hidden_motive="寻找父母失踪的真相",
        speech_style="沉稳，少言",
        core_skills=["基础剑法", "炼药"],
        core_weaknesses=["修为低微", "冲动"],
    )
    state = CharacterState(
        character_id=core.id,
        current_goal="通过宗门考核",
        current_emotion="紧张但坚定",
        current_location="落云宗广场",
        current_power_level="炼气三层",
        current_relationships={"苏清鸾": "暗恋对象，不敢接近"},
        current_knowledge=["考核有三关"],
        current_secrets=["体内有神秘力量"],
        current_status="备战考核",
        last_updated_scene="scene-001",
    )
    character = Character(core=core, state=state)

    save_character(proj_dir, character)
    loaded = load_character(proj_dir, character.core.id)

    # Core fields
    assert loaded.core.id == core.id
    assert loaded.core.name == "林轩"
    assert loaded.core.tier == CharacterTier.MAJOR
    assert loaded.core.aliases == ["轩哥", "废物"]
    assert loaded.core.identity == "落云宗外门弟子"
    assert loaded.core.age == "17"
    assert loaded.core.appearance == "清秀少年，略显瘦弱"
    assert loaded.core.personality == "坚韧不拔，外冷内热"
    assert loaded.core.background == "从小父母失踪，被宗门收养"
    assert loaded.core.long_term_goal == "成为最强修士"
    assert loaded.core.hidden_motive == "寻找父母失踪的真相"
    assert loaded.core.speech_style == "沉稳，少言"
    assert loaded.core.core_skills == ["基础剑法", "炼药"]
    assert loaded.core.core_weaknesses == ["修为低微", "冲动"]

    # State fields
    assert loaded.state.character_id == core.id
    assert loaded.state.current_goal == "通过宗门考核"
    assert loaded.state.current_emotion == "紧张但坚定"
    assert loaded.state.current_location == "落云宗广场"
    assert loaded.state.current_power_level == "炼气三层"
    assert loaded.state.current_relationships == {"苏清鸾": "暗恋对象，不敢接近"}
    assert loaded.state.current_knowledge == ["考核有三关"]
    assert loaded.state.current_secrets == ["体内有神秘力量"]
    assert loaded.state.current_status == "备战考核"
    assert loaded.state.last_updated_scene == "scene-001"


def test_save_character_minimal(tmp_path):
    """Save a character with only required fields, verify round-trip."""
    from app.storage.project_files import save_character, load_character

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    core = CharacterCore(name="无名")
    state = CharacterState(character_id=core.id)
    character = Character(core=core, state=state)

    save_character(proj_dir, character)
    loaded = load_character(proj_dir, character.core.id)

    assert loaded.core.name == "无名"
    assert loaded.core.tier == CharacterTier.SUPPORTING  # default
    assert loaded.core.aliases == []
    assert loaded.state.current_goal == ""


def test_load_character_missing_file(tmp_path):
    """Loading a nonexistent character raises FileNotFoundError."""
    from app.storage.project_files import load_character

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    with pytest.raises(FileNotFoundError):
        load_character(proj_dir, "nonexistent-id")


def test_load_character_invalid_yaml(tmp_path):
    """Loading corrupt YAML raises ValueError."""
    from app.storage.project_files import load_character

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    bad_file = proj_dir / "characters" / "bad.yaml"
    bad_file.write_text(": invalid : yaml :", encoding="utf-8")

    with pytest.raises(ValueError):
        load_character(proj_dir, "bad")


def test_delete_character(tmp_path):
    """Delete removes the character YAML file."""
    from app.storage.project_files import (
        delete_character,
        load_character,
        save_character,
    )

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    core = CharacterCore(name="路人甲")
    state = CharacterState(character_id=core.id)
    character = Character(core=core, state=state)

    save_character(proj_dir, character)
    assert (proj_dir / "characters" / f"{core.id}.yaml").exists()

    delete_character(proj_dir, core.id)
    assert not (proj_dir / "characters" / f"{core.id}.yaml").exists()

    with pytest.raises(FileNotFoundError):
        load_character(proj_dir, core.id)


def test_delete_nonexistent_character_no_error(tmp_path):
    """Deleting a nonexistent character does not raise."""
    from app.storage.project_files import delete_character

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    # Should not raise
    delete_character(proj_dir, "nonexistent-id")


def test_list_character_ids(tmp_path):
    """List returns all character IDs in the characters directory."""
    from app.storage.project_files import (
        list_character_ids,
        save_character,
    )

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    ids = []
    for name in ["林轩", "苏清鸾", "路人甲"]:
        core = CharacterCore(name=name)
        state = CharacterState(character_id=core.id)
        save_character(proj_dir, Character(core=core, state=state))
        ids.append(core.id)

    result = list_character_ids(proj_dir)
    assert set(result) == set(ids)


def test_list_character_ids_empty_directory(tmp_path):
    """Empty characters directory returns empty list."""
    from app.storage.project_files import list_character_ids

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    assert list_character_ids(proj_dir) == []


def test_load_all_characters(tmp_path):
    """Load all characters from disk."""
    from app.storage.project_files import (
        load_all_characters,
        save_character,
    )

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    chars = []
    for name in ["林轩", "苏清鸾"]:
        core = CharacterCore(name=name)
        state = CharacterState(character_id=core.id)
        char = Character(core=core, state=state)
        save_character(proj_dir, char)
        chars.append(char)

    loaded = load_all_characters(proj_dir)
    assert len(loaded) == 2
    loaded_names = {c.core.name for c in loaded}
    assert loaded_names == {"林轩", "苏清鸾"}


def test_load_all_characters_empty(tmp_path):
    """Empty directory returns empty list."""
    from app.storage.project_files import load_all_characters

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    assert load_all_characters(proj_dir) == []
