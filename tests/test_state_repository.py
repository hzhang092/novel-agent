"""Tests for StateRepository — the commit pipeline for event sourcing."""
import tempfile
import uuid
from pathlib import Path

import pytest

from app.storage.state_repository import (
    StateRepository,
    commit_character_state_edit,
    ensure_initial_state_event,
)
from app.storage.models import (
    StateChangeProposal,
    SetFieldChange,
    RelationshipChange,
    KnowledgeAddChange,
    KnowledgeRemoveChange,
    SecretAddChange,
    CharacterStateEvent,
    CharacterStoredChange,
    CharacterStateSnapshot,
)
from app.storage.character_state import load_snapshot
from app.storage.character_events import append_events, load_events, get_latest_event_id
from app.events.bus import EventBus


def test_existing_event_log_is_never_backfilled(tmp_path):
    append_events(
        tmp_path,
        [CharacterStateEvent(event_id=1, scene_id="scene-1", character_id="hero")],
    )

    assert ensure_initial_state_event(tmp_path, "hero") is None
    assert len(load_events(tmp_path)) == 1


class TestCommitProposal:
    def test_commit_proposal_writes_event_and_updates_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            # Seed an initial snapshot
            from app.storage.character_state import save_snapshot
            initial = CharacterStateSnapshot(
                character_id="char-1",
                goal="become_elder",
                emotion="nervous",
                location="dojo",
                relationships={"master": "respect"},
            )
            save_snapshot(char_dir, initial)

            bus = EventBus()
            events_fired: list = []
            bus.subscribe("character_state_updated", lambda **kw: events_fired.append(kw))

            repo = StateRepository(bus=bus)
            proposal = StateChangeProposal(
                character_id="char-1",
                character_name="林轩",
                changes=[
                    SetFieldChange(type="set_field", field="goal", value="revenge"),
                    SetFieldChange(type="set_field", field="emotion", value="angry"),
                ],
            )

            event = repo.commit_proposal(
                char_dir=char_dir,
                proposal=proposal,
                scene_id="scene_001",
                transaction_id=str(uuid.uuid4()),
                request_id=str(uuid.uuid4()),
            )

            # Event has the right structure
            assert event is not None
            assert event.event_id == 2
            assert len(event.changes) == 2
            assert event.changes[0].old == "become_elder"
            assert event.changes[0].value == "revenge"
            assert event.changes[1].old == "nervous"
            assert event.changes[1].value == "angry"

            # events.jsonl has the event
            all_events = load_events(char_dir)
            assert len(all_events) == 2
            assert all_events[0].source == "system"

            # snapshot is updated
            snap = load_snapshot(char_dir)
            assert snap.goal == "revenge"
            assert snap.emotion == "angry"
            assert snap.last_event_id == 2

            # Domain event was published
            assert len(events_fired) == 1
            assert events_fired[0]["character_id"] == "char-1"

    def test_commit_proposal_relationship_and_knowledge(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            from app.storage.character_state import save_snapshot
            save_snapshot(char_dir, CharacterStateSnapshot(
                character_id="char-2",
                relationships={"ally": "friend"},
                knowledge=["old_info"],
            ))

            repo = StateRepository()
            proposal = StateChangeProposal(
                character_id="char-2",
                character_name="配角",
                changes=[
                    RelationshipChange(type="relationship_change", target_character_id="ally", relationship="enemy"),
                    KnowledgeAddChange(type="knowledge_add", fact="new_fact"),
                    KnowledgeRemoveChange(type="knowledge_remove", fact="old_info"),
                    SecretAddChange(type="secret_add", fact="hidden"),
                ],
            )

            event = repo.commit_proposal(char_dir, proposal, "scene_002", "tx", "req")
            assert event is not None
            assert len(event.changes) == 4

            snap = load_snapshot(char_dir)
            assert snap.relationships == {"ally": "enemy"}
            assert snap.knowledge == ["new_fact"]
            assert snap.secrets == ["hidden"]

    def test_commit_proposal_empty_changes_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            from app.storage.character_state import save_snapshot
            save_snapshot(char_dir, CharacterStateSnapshot(character_id="char-3", goal="idle"))

            repo = StateRepository()
            proposal = StateChangeProposal(character_id="char-3", character_name="x", changes=[])

            event = repo.commit_proposal(char_dir, proposal, "scene", "tx", "req")
            assert event is None  # Nothing to commit

    def test_commit_proposal_recovers_stale_snapshot_before_applying_next_event(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            from app.storage.character_state import save_snapshot
            save_snapshot(char_dir, CharacterStateSnapshot(character_id="char-1", goal="old", last_event_id=1))
            append_events(char_dir, [
                CharacterStateEvent(
                    event_id=2, scene_id="s2", character_id="char-1",
                    changes=[CharacterStoredChange(type="set_field", field="goal", value="from_log", old="old")],
                ),
            ])

            repo = StateRepository()
            proposal = StateChangeProposal(
                character_id="char-1",
                character_name="x",
                changes=[SetFieldChange(type="set_field", field="emotion", value="calm")],
            )

            event = repo.commit_proposal(char_dir, proposal, "s3", "tx", "req")

            assert event is not None
            assert event.event_id == 3
            assert event.changes[0].old == ""
            snap = load_snapshot(char_dir)
            assert snap.goal == "from_log"
            assert snap.emotion == "calm"
            assert snap.last_event_id == 3


class TestInvalidateEvent:
    def test_invalidate_then_rebuild(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            from app.storage.character_state import save_snapshot, load_or_build_snapshot
            save_snapshot(char_dir, CharacterStateSnapshot(character_id="char-1", goal="old"))

            repo = StateRepository()
            # Commit first event
            p1 = StateChangeProposal(character_id="char-1", character_name="x", changes=[
                SetFieldChange(type="set_field", field="goal", value="first")
            ])
            repo.commit_proposal(char_dir, p1, "s1", "tx", "req")

            # Commit second event
            p2 = StateChangeProposal(character_id="char-1", character_name="x", changes=[
                SetFieldChange(type="set_field", field="goal", value="second")
            ])
            repo.commit_proposal(char_dir, p2, "s2", "tx", "req")

            snap = load_snapshot(char_dir)
            assert snap.goal == "second"

            # Invalidate the second proposal event (the seed is event 1).
            deleted = repo.invalidate_event(char_dir, event_id=3)
            assert deleted is True

            # State should revert to "first"
            snap2 = load_snapshot(char_dir)
            assert snap2.goal == "first"

    def test_invalidate_nonexistent_returns_false(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            from app.storage.character_state import save_snapshot
            save_snapshot(char_dir, CharacterStateSnapshot(character_id="char-1"))

            repo = StateRepository()
            result = repo.invalidate_event(char_dir, event_id=999)
            assert result is False


class TestCommitUserEdit:
    def test_commit_user_edit_accepts_manual_event_source(self, tmp_path):
        repo = StateRepository()

        event = repo.commit_user_edit(
            tmp_path,
            "char-1",
            [{"type": "set_field", "field": "goal", "value": "new", "old": ""}],
            source="manual_event",
        )

        assert event is not None
        assert event.source == "manual_event"

    def test_commit_user_edit(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            from app.storage.character_state import save_snapshot
            save_snapshot(char_dir, CharacterStateSnapshot(character_id="char-1", goal="old", emotion="sad"))

            bus = EventBus()
            events_fired = []
            bus.subscribe("character_state_updated", lambda **kw: events_fired.append(kw))

            repo = StateRepository(bus=bus)
            changes = [
                {"type": "set_field", "field": "goal", "value": "new_goal", "old": "old"},
                {"type": "set_field", "field": "emotion", "value": "happy", "old": "sad"},
            ]
            event = repo.commit_user_edit(char_dir, "char-1", changes, scene_id="scene_003")
            assert event is not None
            assert event.source == "user"
            assert event.event_id == 2

            snap = load_snapshot(char_dir)
            assert snap.goal == "new_goal"
            assert snap.emotion == "happy"

            assert len(events_fired) == 1

    def test_manual_state_edit_survives_reload_replay(self):
        with tempfile.TemporaryDirectory() as td:
            from app.storage.character_state import save_snapshot
            from app.storage.models import Character, CharacterCore, CharacterState, Project
            from app.storage.project_files import create_project, load_character, save_character

            proj_dir = create_project(Path(td), Project(title="测试", genre="玄幻"))
            save_character(
                proj_dir,
                Character(
                    core=CharacterCore(id="char-hero", name="林轩"),
                    state=CharacterState(character_id="char-hero"),
                ),
            )

            char_dir = proj_dir / "characters" / "char-hero"
            repo = StateRepository()
            repo.commit_proposal(
                char_dir,
                StateChangeProposal(
                    character_id="char-hero",
                    character_name="林轩",
                    changes=[
                        SetFieldChange(type="set_field", field="goal", value="旧目标"),
                        RelationshipChange(
                            type="relationship_change",
                            target_character_id="ally",
                            relationship="盟友",
                        ),
                        KnowledgeAddChange(type="knowledge_add", fact="旧线索"),
                    ],
                ),
                "scene_001",
                "tx",
                "req",
            )

            old_state = load_character(proj_dir, "char-hero").state
            new_state = CharacterState(
                character_id="char-hero",
                current_goal="新目标",
                current_relationships={},
                current_knowledge=["新线索"],
            )

            event = commit_character_state_edit(char_dir, old_state, new_state, scene_id="scene_002")

            assert event is not None
            assert event.source == "user"
            assert event.scene_id == "scene_002"

            save_snapshot(
                char_dir,
                CharacterStateSnapshot(character_id="char-hero", goal="stale", last_event_id=1),
            )

            reloaded = load_character(proj_dir, "char-hero")
            assert reloaded.state.current_goal == "新目标"
            assert reloaded.state.current_relationships == {}
            assert reloaded.state.current_knowledge == ["新线索"]
