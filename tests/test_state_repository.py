"""Tests for StateRepository — the commit pipeline for event sourcing."""
import tempfile
import uuid
from pathlib import Path

import pytest

from app.storage.state_repository import StateRepository
from app.storage.models import (
    StateChangeProposal,
    SetFieldChange,
    RelationshipChange,
    KnowledgeAddChange,
    KnowledgeRemoveChange,
    SecretAddChange,
    CharacterStateSnapshot,
)
from app.storage.character_state import load_snapshot
from app.storage.character_events import load_events, get_latest_event_id
from app.events.bus import EventBus


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
            assert event.event_id == 1
            assert len(event.changes) == 2
            assert event.changes[0].old == "become_elder"
            assert event.changes[0].value == "revenge"
            assert event.changes[1].old == "nervous"
            assert event.changes[1].value == "angry"

            # events.jsonl has the event
            all_events = load_events(char_dir)
            assert len(all_events) == 1

            # snapshot is updated
            snap = load_snapshot(char_dir)
            assert snap.goal == "revenge"
            assert snap.emotion == "angry"
            assert snap.last_event_id == 1

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

            # Invalidate event 2
            deleted = repo.invalidate_event(char_dir, event_id=2)
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
            assert event.event_id == 1

            snap = load_snapshot(char_dir)
            assert snap.goal == "new_goal"
            assert snap.emotion == "happy"

            assert len(events_fired) == 1
