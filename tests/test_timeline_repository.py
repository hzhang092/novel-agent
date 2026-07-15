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
    SceneSummary,
    SceneStateCheckpoint,
    SetFieldChange,
    StateChangeProposal,
    VolumeOutline,
)
from app.storage.character_events import append_events, load_events
from app.storage.character_state import (
    load_checkpoint,
    load_or_build_snapshot,
    load_snapshot,
    save_checkpoint,
    save_snapshot,
)
from app.storage.project_files import (
    create_project,
    get_active_scene_revision_id,
    load_canon_facts,
    load_scene_generation_record,
    load_scene_summaries,
    save_character,
    save_canon_facts,
    save_scene_generation_record,
    save_scene_summaries,
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


def test_first_scene_context_uses_authored_initial_state(tmp_path):
    from app.storage.timeline_repository import load_character_state_as_of_scene

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-hero", name="林轩", tier="major"),
            state=CharacterState(character_id="char-hero", current_goal="starting goal"),
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

    assert states["char-hero"].goal == "starting goal"
    assert read_points["char-hero"]["source"] == "story_start"
    assert read_points["char-hero"]["max_event_id"] == 1


def test_later_scene_replay_includes_authored_initial_state(tmp_path):
    from app.storage.timeline_repository import load_character_state_as_of_scene

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-hero", name="林轩", tier="major"),
            state=CharacterState(character_id="char-hero", current_goal="starting goal"),
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

    assert states["char-hero"].goal == "starting goal"
    assert read_points["char-hero"]["source"] == "replay"


def test_scene_change_preserves_unchanged_authored_state_through_replay(tmp_path):
    from app.storage.timeline_repository import (
        commit_scene_proposal,
        load_character_state_as_of_scene,
    )

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="hero", name="林轩", tier="major"),
            state=CharacterState(
                character_id="hero",
                current_goal="寻找妹妹",
                current_location="河村",
            ),
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

    event = commit_scene_proposal(
        proj_dir,
        StateChangeProposal(
            character_id="hero",
            changes=[
                SetFieldChange(type="set_field", field="emotion", value="害怕")
            ],
        ),
        "scene-1",
        "tx",
        "req",
    )

    assert event is not None
    assert event.event_id == 2
    assert [change.field for change in event.changes] == ["emotion"]
    checkpoint = load_checkpoint(proj_dir / "characters" / "hero", "scene-1")
    assert checkpoint is not None
    assert checkpoint.snapshot.goal == "寻找妹妹"
    assert checkpoint.snapshot.location == "河村"
    assert checkpoint.snapshot.emotion == "害怕"

    states, _ = load_character_state_as_of_scene(proj_dir, "scene-2", ["hero"])
    assert states["hero"].goal == "寻找妹妹"
    assert states["hero"].location == "河村"
    assert states["hero"].emotion == "害怕"

    char_dir = proj_dir / "characters" / "hero"
    (char_dir / "state.yaml").unlink()
    rebuilt = load_or_build_snapshot(char_dir, "hero")
    assert rebuilt.goal == "寻找妹妹"
    assert rebuilt.location == "河村"
    assert rebuilt.emotion == "害怕"


def test_eventless_snapshot_is_backfilled_once_before_story_start_replay(tmp_path):
    from app.storage.project_files import save_character_definition
    from app.storage.timeline_repository import load_character_state_as_of_scene

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character_definition(
        proj_dir,
        CharacterCore(id="hero", name="林轩", tier="major"),
    )
    char_dir = proj_dir / "characters" / "hero"
    save_snapshot(
        char_dir,
        CharacterStateSnapshot(character_id="hero", goal="寻找妹妹"),
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

    first, _ = load_character_state_as_of_scene(proj_dir, "scene-1", ["hero"])
    second, _ = load_character_state_as_of_scene(proj_dir, "scene-1", ["hero"])

    assert first["hero"].goal == "寻找妹妹"
    assert second["hero"].goal == "寻找妹妹"
    events = load_events(char_dir)
    assert len(events) == 1
    assert events[0].source == "system"
    assert events[0].scene_id == ""


def test_eventless_snapshot_with_scene_anchor_does_not_leak_backwards(tmp_path):
    from app.storage.project_files import save_character_definition
    from app.storage.timeline_repository import load_character_state_as_of_scene

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_character_definition(
        proj_dir,
        CharacterCore(id="hero", name="林轩", tier="major"),
    )
    char_dir = proj_dir / "characters" / "hero"
    save_snapshot(
        char_dir,
        CharacterStateSnapshot(
            character_id="hero",
            goal="scene-one goal",
            last_scene_id="scene-1",
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

    before, _ = load_character_state_as_of_scene(proj_dir, "scene-1", ["hero"])
    after, _ = load_character_state_as_of_scene(proj_dir, "scene-2", ["hero"])

    assert before["hero"].goal == ""
    assert after["hero"].goal == "scene-one goal"
    assert load_events(char_dir)[0].scene_id == "scene-1"


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
    assert len(events) == 2
    assert events[1].changes[0].field == "goal"
    assert events[1].changes[0].value == "复仇"


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
    events = load_events(proj_dir / "characters" / "hero")
    assert len(events) == 1
    assert events[0].scene_id == ""
    assert events[0].changes == []
    unchanged = load_scene_generation_record(
        proj_dir, "scene-1", revision_id="rev-1"
    )
    assert unchanged.approved_facts == []
    assert unchanged.approved_state_change_proposals == []


def test_partial_event_staging_is_invisible_and_retryable(tmp_path, monkeypatch):
    import app.storage.timeline_repository as timeline

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    for character_id in ("hero", "ally"):
        save_character(
            proj_dir,
            Character(
                core=CharacterCore(id=character_id, name=character_id, tier="major"),
                state=CharacterState(character_id=character_id),
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
            scene_id="scene-1",
            revision_id="old",
            revision_number=1,
            status="current",
            published_at="2026-01-01T00:00:00Z",
        ),
    )
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="new",
            revision_number=2,
            status="draft",
            review={"overall_pass": True},
            scene_summary_raw={
                "scene_id": "scene-1",
                "chapter_id": "ch-1",
                "summary": "new summary",
                "new_facts": ["rejected fact"],
                "character_state_changes": {"rejected": "rejected change"},
                "relationship_changes": ["rejected relationship"],
            },
        ),
    )
    set_active_scene_prose_version(proj_dir, "ch-1", "scene-1", "v1", "old")
    save_canon_facts(
        proj_dir,
        [
            CanonFact(
                description="old fact",
                category="plot",
                source_scene_id="scene-1",
                source_scene_revision_id="old",
            )
        ],
    )
    save_scene_summaries(
        proj_dir,
        [SceneSummary(scene_id="scene-1", chapter_id="ch-1", summary="old summary")],
    )
    for character_id in ("hero", "ally"):
        append_events(
            proj_dir / "characters" / character_id,
            [
                CharacterStateEvent(
                    event_id=2,
                    scene_id="scene-1",
                    scene_revision_id="old",
                    scene_order=1,
                    character_id=character_id,
                    changes=[
                        CharacterStoredChange(
                            type="set_field", field="goal", value="old"
                        )
                    ],
                )
            ],
        )
    approved = [
        StateChangeProposal(
            character_id=character_id,
            changes=[SetFieldChange(type="set_field", field="goal", value="changed")],
        ).model_dump(mode="json")
        for character_id in ("hero", "ally")
    ]
    append = timeline.append_events
    calls = 0

    def fail_second_append(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        return append(*args, **kwargs)

    monkeypatch.setattr(timeline, "append_events", fail_second_append)
    with pytest.raises(OSError, match="disk full"):
        timeline.publish_scene_revision(
            proj_dir,
            "scene-1",
            "new",
            [{"description": "new fact", "category": "plot"}],
            approved,
        )

    assert get_active_scene_revision_id(proj_dir, "scene-1") == "old"
    assert [fact.description for fact in load_canon_facts(proj_dir)] == ["old fact"]
    assert [summary.summary for summary in load_scene_summaries(proj_dir)] == [
        "old summary"
    ]
    states, _ = timeline.load_character_state_as_of_scene(
        proj_dir, "scene-2", ["hero", "ally"]
    )
    assert {character_id: state.goal for character_id, state in states.items()} == {
        "hero": "old",
        "ally": "old",
    }

    monkeypatch.setattr(timeline, "append_events", append)
    timeline.publish_scene_revision(
        proj_dir,
        "scene-1",
        "new",
        [{"description": "new fact", "category": "plot"}],
        approved,
    )

    assert get_active_scene_revision_id(proj_dir, "scene-1") == "new"
    assert [fact.description for fact in load_canon_facts(proj_dir)] == ["new fact"]
    active_summaries = load_scene_summaries(proj_dir)
    assert [summary.summary for summary in active_summaries] == ["new summary"]
    assert active_summaries[0].new_facts == ["new fact"]
    assert active_summaries[0].character_state_changes == {
        "hero": "goal→changed",
        "ally": "goal→changed",
    }
    assert active_summaries[0].relationship_changes == []
    all_summaries = load_scene_summaries(proj_dir, active_only=False)
    assert {
        summary.summary: summary.source_scene_revision_id
        for summary in all_summaries
    } == {"old summary": "old", "new summary": "new"}
    states, _ = timeline.load_character_state_as_of_scene(
        proj_dir, "scene-2", ["hero", "ally"]
    )
    assert {character_id: state.goal for character_id, state in states.items()} == {
        "hero": "changed",
        "ally": "changed",
    }
    for character_id in ("hero", "ally"):
        events = [
            event
            for event in load_events(proj_dir / "characters" / character_id)
            if event.scene_revision_id == "new"
        ]
        assert len(events) == 1
        assert events[0].changes[0].value == "changed"


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


def test_retry_finishes_publication_after_pointer_swap(tmp_path, monkeypatch):
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
    approved_facts = [{"description": "new fact", "category": "plot"}]
    approved_changes = [
        StateChangeProposal(
            character_id="hero",
            changes=[SetFieldChange(type="set_field", field="goal", value="changed")],
        ).model_dump(mode="json")
    ]
    finish = timeline._finish_publication
    monkeypatch.setattr(
        timeline,
        "_finish_publication",
        lambda *args: (_ for _ in ()).throw(OSError("interrupted")),
    )

    with pytest.raises(OSError, match="interrupted"):
        timeline.publish_scene_revision(
            proj_dir, "scene-1", "new", approved_facts, approved_changes
        )

    assert get_active_scene_revision_id(proj_dir, "scene-1") == "new"
    assert (proj_dir / ".publish.pending.json").exists()
    monkeypatch.setattr(timeline, "_finish_publication", finish)
    timeline.publish_scene_revision(
        proj_dir, "scene-1", "new", approved_facts, approved_changes
    )

    assert load_scene_generation_record(proj_dir, "scene-1").status == "current"
    assert load_scene_generation_record(
        proj_dir, "scene-1", revision_id="old"
    ).status == "superseded"
    assert not (proj_dir / ".publish.pending.json").exists()
    assert [fact.description for fact in load_canon_facts(proj_dir)] == ["new fact"]
    events = [
        event
        for event in load_events(proj_dir / "characters" / "hero")
        if event.scene_revision_id == "new"
    ]
    assert len(events) == 1
    assert events[0].changes[0].value == "changed"


def test_publish_replaces_legacy_unscoped_memory(tmp_path):
    from app.storage.timeline_repository import (
        load_character_state_as_of_scene,
        publish_scene_revision,
    )

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
            scene_id="scene-1",
            revision_id="old",
            revision_number=1,
            status="current",
        ),
    )
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="new",
            revision_number=2,
            status="draft",
            review={"overall_pass": True},
        ),
    )
    save_canon_facts(
        proj_dir,
        [CanonFact(description="old fact", category="plot", source_scene_id="scene-1")],
    )
    append_events(
        proj_dir / "characters" / "hero",
        [
            CharacterStateEvent(
                event_id=2,
                scene_id="scene-1",
                scene_order=1,
                character_id="hero",
                changes=[
                    CharacterStoredChange(
                        type="set_field", field="goal", value="old goal"
                    )
                ],
            )
        ],
    )

    publish_scene_revision(
        proj_dir,
        "scene-1",
        "new",
        [{"description": "new fact", "category": "plot"}],
        [],
    )

    assert get_active_scene_revision_id(proj_dir, "scene-1") == "new"
    assert [fact.description for fact in load_canon_facts(proj_dir)] == ["new fact"]
    all_facts = load_canon_facts(proj_dir, active_only=False)
    assert {
        fact.description: fact.source_scene_revision_id for fact in all_facts
    } == {"old fact": "old", "new fact": "new"}
    states, _ = load_character_state_as_of_scene(proj_dir, "scene-2", ["hero"])
    assert states["hero"].goal == ""
    assert next(
        event
        for event in load_events(proj_dir / "characters" / "hero")
        if event.scene_id == "scene-1"
    ).scene_revision_id == "old"
