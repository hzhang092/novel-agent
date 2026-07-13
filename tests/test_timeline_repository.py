"""Tests for scene timeline helpers."""

import pytest
from pydantic import ValidationError

from app.storage.models import (
    Character,
    CanonFact,
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
from app.storage.character_events import append_events, load_events
from app.storage.character_state import (
    load_checkpoint,
    load_snapshot,
    save_checkpoint,
    save_snapshot,
)
from app.storage.project_files import (
    create_project,
    get_active_scene_revision_id,
    load_canon_facts,
    load_scene_generation_record,
    save_character,
    save_canon_facts,
    save_scene_generation_record,
    set_active_scene_prose_version,
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


def test_first_scene_context_does_not_use_latest_state_yaml(tmp_path):
    from app.storage.timeline_repository import load_character_state_as_of_scene

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-hero", name="林轩", tier="major"),
            state=CharacterState(character_id="char-hero", current_goal="future goal"),
        ),
    )
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )

    states, read_points = load_character_state_as_of_scene(
        proj_dir,
        "scene-1",
        ["char-hero"],
    )

    assert states["char-hero"].goal == ""
    assert read_points["char-hero"]["source"] == "story_start"


def test_first_character_event_before_later_scene_does_not_use_latest_state_yaml(tmp_path):
    from app.storage.timeline_repository import load_character_state_as_of_scene

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-hero", name="林轩", tier="major"),
            state=CharacterState(character_id="char-hero", current_goal="future goal"),
        ),
    )
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[
                        SceneOutline(id=f"scene-{i}", title=f"第{i}场")
                        for i in range(1, 6)
                    ],
                )
            ],
        ),
    )

    states, read_points = load_character_state_as_of_scene(
        proj_dir,
        "scene-5",
        ["char-hero"],
    )

    assert states["char-hero"].goal == ""
    assert read_points["char-hero"]["source"] == "replay"


def test_load_character_context_for_scene_uses_ids_with_duplicate_names(tmp_path):
    from app.storage.timeline_repository import load_character_context_for_scene

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-major-alex", name="Alex", tier="major"),
            state=CharacterState(character_id="char-major-alex", current_goal="selected"),
        ),
    )
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-support-alex", name="Alex", tier="supporting"),
            state=CharacterState(character_id="char-support-alex", current_goal="not selected"),
        ),
    )
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )

    characters, read_points = load_character_context_for_scene(
        proj_dir,
        "scene-1",
        ["char-major-alex"],
    )

    assert [char.core.id for char in characters] == ["char-major-alex"]
    assert set(read_points) == {"char-major-alex"}


def test_load_character_context_for_scene_raises_for_missing_ids(tmp_path):
    from app.storage.timeline_repository import load_character_context_for_scene

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )

    with pytest.raises(
        ValueError,
        match="Scene references missing character IDs: missing-char",
    ):
        load_character_context_for_scene(proj_dir, "scene-1", ["missing-char"])


def test_publish_scene_revision_switches_canon_and_marks_downstream_stale(tmp_path):
    from app.storage.timeline_repository import publish_scene_revision

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    scenes = [SceneOutline(id=f"scene-{i}", title=f"第{i}场") for i in range(1, 4)]
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[ChapterOutline(id="ch-1", title="第一章", scenes=scenes)],
        ),
    )
    old = SceneGenerationRecord(
        scene_id="scene-2",
        revision_id="old",
        revision_number=1,
        status="current",
        review={"overall_pass": True},
        approved_facts=[{"description": "old canon", "category": "plot"}],
        published_at="2026-01-01T00:00:00Z",
    )
    new = SceneGenerationRecord(
        scene_id="scene-2",
        revision_id="new",
        revision_number=2,
        status="draft",
        review={"overall_pass": True},
    )
    save_scene_generation_record(proj_dir, old)
    save_scene_generation_record(proj_dir, new)
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(scene_id="scene-3", revision_id="later", status="current"),
    )
    save_canon_facts(
        proj_dir,
        [
            CanonFact(
                description="old canon",
                category="plot",
                source_scene_id="scene-2",
                source_scene_revision_id="old",
            )
        ],
    )
    set_active_scene_prose_version(proj_dir, "ch-1", "scene-2", "v1", "old")

    publish_scene_revision(
        proj_dir,
        "scene-2",
        "new",
        [{"description": "new canon", "category": "plot"}],
        [],
    )

    assert get_active_scene_revision_id(proj_dir, "scene-2") == "new"
    assert [fact.description for fact in load_canon_facts(proj_dir)] == ["new canon"]
    assert load_scene_generation_record(proj_dir, "scene-2").revision_id == "new"
    assert load_scene_generation_record(proj_dir, "scene-3").status == "stale"

    publish_scene_revision(
        proj_dir,
        "scene-2",
        "old",
        [{"description": "old canon", "category": "plot"}],
        [],
    )
    publish_scene_revision(
        proj_dir,
        "scene-2",
        "old",
        [{"description": "old canon", "category": "plot"}],
        [],
    )

    assert [fact.description for fact in load_canon_facts(proj_dir)] == ["old canon"]
    assert len(load_canon_facts(proj_dir, active_only=False)) == 2


def test_published_revision_memory_is_immutable_and_idempotent(tmp_path):
    from app.storage.timeline_repository import publish_scene_revision

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="hero", name="林轩", tier="major"),
            state=CharacterState(character_id="hero"),
        ),
    )
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="rev-1",
            revision_number=1,
            status="draft",
            review={"overall_pass": True},
        ),
    )
    approved = [
        StateChangeProposal(
            character_id="hero",
            changes=[SetFieldChange(type="set_field", field="goal", value="复仇")],
        ).model_dump(mode="json")
    ]

    publish_scene_revision(proj_dir, "scene-1", "rev-1", [], approved)
    char_dir = proj_dir / "characters" / "hero"
    with pytest.raises(ValueError, match="memory is immutable"):
        publish_scene_revision(proj_dir, "scene-1", "rev-1", [], [])

    publish_scene_revision(proj_dir, "scene-1", "rev-1", [], approved)

    events = load_events(char_dir)
    assert len(events) == 1
    assert events[0].changes[0].field == "goal"
    assert events[0].changes[0].value == "复仇"


def test_publish_validates_complete_batch_before_writing(tmp_path):
    from app.storage.timeline_repository import publish_scene_revision

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="hero", name="林轩", tier="major"),
            state=CharacterState(character_id="hero"),
        ),
    )
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        status="draft",
        review={"overall_pass": True},
    )
    save_scene_generation_record(proj_dir, record)
    save_canon_facts(
        proj_dir,
        [
            CanonFact(
                description="existing",
                category="plot",
                source_scene_id="scene-0",
            )
        ],
    )

    with pytest.raises(ValidationError):
        publish_scene_revision(
            proj_dir,
            "scene-1",
            "rev-1",
            [{"description": "new", "category": "plot"}],
            [
                {
                    "character_id": "hero",
                    "changes": [
                        {"type": "set_field", "field": "goal", "value": "复仇"}
                    ],
                },
                {
                    "character_id": "hero",
                    "changes": [{"type": "invalid_change"}],
                },
            ],
        )

    assert get_active_scene_revision_id(proj_dir, "scene-1") == ""
    assert [
        fact.description for fact in load_canon_facts(proj_dir, active_only=False)
    ] == ["existing"]
    assert load_events(proj_dir / "characters" / "hero") == []
    unchanged = load_scene_generation_record(
        proj_dir, "scene-1", revision_id="rev-1"
    )
    assert unchanged.approved_facts == []
    assert unchanged.approved_state_change_proposals == []


def test_draft_memory_is_invisible_until_revision_is_active(tmp_path):
    from app.storage.timeline_repository import load_character_state_as_of_scene

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="hero", name="林轩", tier="major"),
            state=CharacterState(character_id="hero"),
        ),
    )
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[
                        SceneOutline(id="scene-1", title="第一场"),
                        SceneOutline(id="scene-2", title="第二场"),
                    ],
                )
            ],
        ),
    )
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(
            scene_id="scene-1", revision_id="draft-rev", status="draft"
        ),
    )
    save_canon_facts(
        proj_dir,
        [
            CanonFact(
                description="draft fact",
                category="plot",
                source_scene_id="scene-1",
                source_scene_revision_id="draft-rev",
            )
        ],
    )
    append_events(
        proj_dir / "characters" / "hero",
        [
            CharacterStateEvent(
                event_id=1,
                scene_id="scene-1",
                scene_revision_id="draft-rev",
                scene_order=1,
                character_id="hero",
                changes=[
                    CharacterStoredChange(
                        type="set_field", field="goal", value="draft goal"
                    )
                ],
            )
        ],
    )

    states, _ = load_character_state_as_of_scene(proj_dir, "scene-2", ["hero"])

    assert get_active_scene_revision_id(proj_dir, "scene-1") == ""
    assert load_canon_facts(proj_dir) == []
    assert states["hero"].goal == ""


def test_publication_failure_before_pointer_preserves_old_canon(
    tmp_path, monkeypatch
):
    import app.storage.timeline_repository as timeline

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="hero", name="林轩", tier="major"),
            state=CharacterState(character_id="hero"),
        ),
    )
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    for revision_id, number, status in (("old", 1, "current"), ("new", 2, "draft")):
        save_scene_generation_record(
            proj_dir,
            SceneGenerationRecord(
                scene_id="scene-1",
                revision_id=revision_id,
                revision_number=number,
                status=status,
                review={"overall_pass": True},
            ),
        )
    set_active_scene_prose_version(proj_dir, "ch-1", "scene-1", "v1", "old")
    char_dir = proj_dir / "characters" / "hero"
    old_snapshot = CharacterStateSnapshot(character_id="hero", goal="old goal")
    save_snapshot(char_dir, old_snapshot)
    save_checkpoint(
        char_dir,
        SceneStateCheckpoint(
            scene_id="scene-1",
            scene_revision_id="old",
            character_id="hero",
            snapshot=old_snapshot,
        ),
    )
    monkeypatch.setattr(
        timeline,
        "set_active_scene_prose_version",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        timeline.publish_scene_revision(
            proj_dir,
            "scene-1",
            "new",
            [{"description": "new fact", "category": "plot"}],
            [
                StateChangeProposal(
                    character_id="hero",
                    changes=[
                        SetFieldChange(
                            type="set_field", field="goal", value="new goal"
                        )
                    ],
                ).model_dump(mode="json")
            ],
        )

    assert get_active_scene_revision_id(proj_dir, "scene-1") == "old"
    assert load_canon_facts(proj_dir) == []
    assert load_checkpoint(char_dir, "scene-1").scene_revision_id == "old"
    assert load_checkpoint(char_dir, "scene-1").snapshot.goal == "old goal"
    assert load_snapshot(char_dir).goal == "old goal"
    timeline.recover_pending_publication(proj_dir)
    assert not (proj_dir / ".publish.pending.json").exists()


def test_recovery_finishes_publication_after_pointer_swap(tmp_path, monkeypatch):
    import app.storage.timeline_repository as timeline

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    old = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="old",
        revision_number=1,
        status="current",
        review={"overall_pass": True},
    )
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="new",
        revision_number=2,
        status="draft",
        review={"overall_pass": True},
    )
    save_scene_generation_record(proj_dir, old)
    save_scene_generation_record(proj_dir, record)
    set_active_scene_prose_version(proj_dir, "ch-1", "scene-1", "v1", "old")
    finish = timeline._finish_publication
    monkeypatch.setattr(
        timeline,
        "_finish_publication",
        lambda *args: (_ for _ in ()).throw(OSError("interrupted")),
    )

    with pytest.raises(OSError, match="interrupted"):
        timeline.publish_scene_revision(proj_dir, "scene-1", "new", [], [])

    assert get_active_scene_revision_id(proj_dir, "scene-1") == "new"
    assert (proj_dir / ".publish.pending.json").exists()
    monkeypatch.setattr(timeline, "_finish_publication", finish)
    timeline.recover_pending_publication(proj_dir)

    assert load_scene_generation_record(proj_dir, "scene-1").status == "current"
    assert load_scene_generation_record(
        proj_dir, "scene-1", revision_id="old"
    ).status == "superseded"
    assert not (proj_dir / ".publish.pending.json").exists()
