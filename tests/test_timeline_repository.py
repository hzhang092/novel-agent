"""Tests for scene timeline helpers."""

from app.storage.models import (
    Character,
    CharacterCore,
    CharacterState,
    CharacterStateEvent,
    CharacterStateSnapshot,
    CharacterStoredChange,
    ChapterOutline,
    Project,
    SceneGenerationRecord,
    SceneOutline,
    SceneStateCheckpoint,
    SetFieldChange,
    StateChangeProposal,
    VolumeOutline,
)
from app.storage.character_events import append_events
from app.storage.character_state import load_checkpoint, load_snapshot, save_checkpoint
from app.storage.project_files import (
    create_project,
    load_scene_generation_record,
    save_character,
    save_scene_generation_record,
    save_volume_outline,
)


def test_mark_downstream_scenes_stale_preserves_selected_scene(tmp_path):
    from app.storage.timeline_repository import mark_downstream_scenes_stale

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    scenes = [
        SceneOutline(id="scene-1", title="第一场"),
        SceneOutline(id="scene-2", title="第二场"),
        SceneOutline(id="scene-3", title="第三场"),
    ]
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[ChapterOutline(id="ch-1", title="第一章", scenes=scenes)],
        ),
    )
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(scene_id="scene-2", revision_id="rev-2", status="current"),
    )
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(scene_id="scene-3", revision_id="rev-3", status="current"),
    )

    stale = mark_downstream_scenes_stale(proj_dir, from_scene_order=2)

    assert stale == ["scene-3"]
    assert load_scene_generation_record(proj_dir, "scene-2").status == "current"
    assert load_scene_generation_record(proj_dir, "scene-3").status == "stale"


def test_commit_scene_proposal_uses_historical_state_and_rebuilds_head(tmp_path):
    from app.storage.timeline_repository import commit_scene_proposal

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-hero", name="林轩", tier="major"),
            state=CharacterState(character_id="char-hero"),
        ),
    )
    scenes = [
        SceneOutline(id="scene-1", title="第一场"),
        SceneOutline(id="scene-2", title="第二场"),
        SceneOutline(id="scene-3", title="第三场"),
    ]
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[ChapterOutline(id="ch-1", title="第一章", scenes=scenes)],
        ),
    )
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(
            scene_id="scene-2",
            revision_id="rev-2",
            revision_number=2,
            scene_order=2,
        ),
    )

    char_dir = proj_dir / "characters" / "char-hero"
    save_checkpoint(
        char_dir,
        SceneStateCheckpoint(
            scene_id="scene-1",
            checkpoint_id="cp-1",
            event_id=1,
            character_id="char-hero",
            snapshot=CharacterStateSnapshot(
                character_id="char-hero",
                goal="after scene 1",
                last_event_id=1,
            ),
        ),
    )
    append_events(
        char_dir,
        [
            CharacterStateEvent(
                event_id=1,
                scene_id="scene-3",
                scene_order=3,
                event_seq=1,
                character_id="char-hero",
                changes=[
                    CharacterStoredChange(
                        type="set_field",
                        field="goal",
                        value="after scene 3",
                    )
                ],
            )
        ],
    )

    event = commit_scene_proposal(
        proj_dir,
        StateChangeProposal(
            character_id="char-hero",
            character_name="林轩",
            changes=[
                SetFieldChange(type="set_field", field="goal", value="new scene 2"),
            ],
        ),
        scene_id="scene-2",
        transaction_id="tx",
        request_id="req",
    )

    assert event is not None
    assert event.scene_revision_id == "rev-2"
    assert event.scene_order == 2
    assert event.changes[0].old == "after scene 1"
    assert load_checkpoint(char_dir, "scene-2").snapshot.goal == "new scene 2"
    assert load_snapshot(char_dir).goal == "after scene 3"
