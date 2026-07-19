from __future__ import annotations

import yaml
import pytest

from app.application.characters import CharacterApplicationService
from app.application.errors import (
    ApplicationValidationError,
    ConcurrentModificationError,
    OperationBlockedError,
)
from app.storage.character_events import load_events
from app.storage.models import (
    ChapterOutline,
    Character,
    CharacterCore,
    CharacterElementRelation,
    CharacterState,
    Project,
    SceneOutline,
    VolumeOutline,
)
from app.storage.project_files import (
    create_project,
    load_character,
    load_volume_outline,
    save_character,
    save_volume_outline,
)
from app.storage.state_repository import commit_character_state_edit


def _project(tmp_path):
    return create_project(tmp_path, Project(title="Story", genre="Fantasy"))


def _save_character(project_dir, character_id, name, *, relationships=None):
    save_character(
        project_dir,
        Character(
            core=CharacterCore(id=character_id, name=name),
            state=CharacterState(
                character_id=character_id,
                current_relationships=relationships or {},
            ),
        ),
    )


def test_list_load_and_save_definition_revision_semantics(tmp_path):
    project_dir = _project(tmp_path)
    _save_character(project_dir, "hero", "Hero")
    service = CharacterApplicationService(project_dir)

    assert [item.core.id for item in service.list_characters()] == ["hero"]
    loaded = service.load_character("hero")
    assert loaded.core.name == "Hero"

    unchanged = service.save_definition(loaded.core.model_copy(deep=True))
    assert unchanged.core.definition_revision == loaded.core.definition_revision
    changed = service.save_definition(loaded.core.model_copy(update={"name": "Heroine"}))
    assert changed.core.name == "Heroine"
    assert changed.core.definition_revision == loaded.core.definition_revision + 1
    assert load_events(project_dir / "characters" / "hero")[-1].event_id == 1


def test_save_new_character_creates_initial_state_and_rejects_empty_name(tmp_path):
    project_dir = _project(tmp_path)
    service = CharacterApplicationService(project_dir)

    saved = service.save_definition(CharacterCore(id="new", name="New"))
    assert saved.state == CharacterState(character_id="new")
    assert len(load_events(project_dir / "characters" / "new")) == 1

    with pytest.raises(ApplicationValidationError):
        service.save_definition(CharacterCore(id="blank", name="   "))


def test_save_rejects_invalid_bible_relationship(tmp_path):
    project_dir = _project(tmp_path)
    service = CharacterApplicationService(project_dir)

    with pytest.raises(ApplicationValidationError, match="missing"):
        service.save_definition(
            CharacterCore(
                id="hero",
                name="Hero",
                element_relations=[
                    CharacterElementRelation(
                        kind="member_of", target_element_id="missing"
                    )
                ],
            )
        )


def test_deletion_impact_blocks_pov_then_requires_and_performs_unlink(tmp_path):
    project_dir = _project(tmp_path)
    _save_character(project_dir, "hero", "Hero")
    _save_character(
        project_dir,
        "friend",
        "Friend",
        relationships={"hero": "ally"},
    )
    volume = VolumeOutline(
        id="volume",
        chapters=[
            ChapterOutline(
                id="chapter",
                scenes=[
                    SceneOutline(id="pov", title="POV", pov_character_id="hero"),
                    SceneOutline(
                        id="party",
                        title="Party",
                        participating_character_ids=["hero"],
                    ),
                ],
            )
        ],
    )
    save_volume_outline(project_dir, volume)
    service = CharacterApplicationService(project_dir)

    impact = service.inspect_deletion("hero")
    assert [(item.scene_id, item.chapter_id) for item in impact.pov_scenes] == [
        ("pov", "chapter")
    ]
    assert [item.scene_id for item in impact.participant_scenes] == ["party"]
    assert [item.character_id for item in impact.relationship_characters] == [
        "friend"
    ]
    assert impact.is_blocked and impact.requires_unlink
    with pytest.raises(OperationBlockedError):
        service.delete_character("hero", unlink_references=True)

    volume.chapters[0].scenes[0].pov_character_id = ""
    save_volume_outline(project_dir, volume)
    with pytest.raises(OperationBlockedError):
        service.delete_character("hero", unlink_references=False)
    service.delete_character("hero", unlink_references=True)

    assert not (project_dir / "characters" / "hero").exists()
    assert (
        load_volume_outline(project_dir, "volume")
        .chapters[0]
        .scenes[1]
        .participating_character_ids
        == []
    )
    assert load_character(project_dir, "friend").state.current_relationships == {}


def test_state_edit_commit_noop_and_concurrency(tmp_path):
    project_dir = _project(tmp_path)
    _save_character(project_dir, "hero", "Hero")
    service = CharacterApplicationService(project_dir)
    char_dir = project_dir / "characters" / "hero"

    session = service.begin_state_edit("hero")
    assert service.commit_state_edit(
        session, session.original_state.model_copy(deep=True), scene_id="scene-1"
    ) is None
    assert len(load_events(char_dir)) == 1

    session = service.begin_state_edit("hero")
    updated = session.original_state.model_copy(update={"current_goal": "Win"})
    result = service.commit_state_edit(session, updated, scene_id="scene-1")
    assert result.current_goal == "Win"
    assert load_events(char_dir)[-1].source == "manual_event"

    stale = service.begin_state_edit("hero")
    current = service.load_character("hero").state
    commit_character_state_edit(
        char_dir,
        current,
        current.model_copy(update={"current_goal": "Concurrent"}),
    )
    with pytest.raises(ConcurrentModificationError):
        service.commit_state_edit(
            stale,
            stale.original_state.model_copy(update={"current_goal": "Stale"}),
            scene_id="scene-2",
        )


def test_legacy_definition_save_preserves_state_and_creates_current_layout(tmp_path):
    project_dir = _project(tmp_path)
    legacy = Character(
        core=CharacterCore(id="legacy", name="Old"),
        state=CharacterState(character_id="legacy", current_goal="Keep me"),
    )
    path = project_dir / "characters" / "legacy.yaml"
    path.write_text(
        yaml.safe_dump(legacy.model_dump(mode="json"), allow_unicode=True),
        encoding="utf-8",
    )

    saved = CharacterApplicationService(project_dir).save_definition(
        legacy.core.model_copy(update={"name": "New"})
    )

    assert saved.core.name == "New"
    assert saved.state.current_goal == "Keep me"
    assert (project_dir / "characters" / "legacy" / "definition.yaml").exists()


def test_new_character_storage_failure_rolls_back_partial_files(
    tmp_path, monkeypatch
):
    project_dir = _project(tmp_path)

    def fail_after_definition(_project_dir, character):
        path = _project_dir / "characters" / character.core.id / "definition.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("partial", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr("app.application.characters.save_character", fail_after_definition)
    with pytest.raises(OSError, match="disk full"):
        CharacterApplicationService(project_dir).save_definition(
            CharacterCore(id="broken", name="Broken")
        )

    char_dir = project_dir / "characters" / "broken"
    assert not any(char_dir.glob("*"))
