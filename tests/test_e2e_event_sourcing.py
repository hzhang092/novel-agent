"""End-to-end test: pipeline → proposal → approval → event → snapshot → UI refresh."""
import tempfile
import uuid
from pathlib import Path

import pytest

from app.storage.models import Project as ProjectModel, Character, CharacterCore, CharacterState
from app.storage.project_files import create_project, save_character
from app.storage.state_repository import StateRepository
from app.storage.character_state import load_snapshot
from app.storage.character_events import load_events_for_scene
from app.storage.models import StateChangeProposal, SetFieldChange
from app.events.bus import EventBus


def test_full_event_sourcing_flow():
    """Create project, character, approve state changes, verify events and snapshots."""
    with tempfile.TemporaryDirectory() as td:
        proj = ProjectModel(title="E2E测试", genre="玄幻", llm_provider="ollama")
        proj_dir = create_project(Path(td) / "projects", proj)

        char = Character(
            core=CharacterCore(id="char-hero", name="林轩", tier="major"),
            state=CharacterState(character_id="char-hero", current_goal="通过考核", current_emotion="紧张"),
        )
        save_character(proj_dir, char)

        # Set up state repo with event bus
        bus = EventBus()
        events_fired = []
        bus.subscribe("character_state_updated", lambda **kw: events_fired.append(kw))
        state_repo = StateRepository(bus=bus)

        proposal = StateChangeProposal(
            character_id="char-hero",
            character_name="林轩",
            changes=[
                SetFieldChange(type="set_field", field="goal", value="复仇"),
                SetFieldChange(type="set_field", field="emotion", value="愤怒"),
            ],
        )

        char_dir = proj_dir / "characters" / "char-hero"
        event = state_repo.commit_proposal(
            char_dir, proposal, "scene_001", str(uuid.uuid4()), str(uuid.uuid4()),
        )

        # Verify event written
        assert event is not None
        assert event.event_id == 1
        assert event.changes[0].old == "通过考核"  # old goal from snapshot
        assert event.changes[0].value == "复仇"
        assert event.changes[1].old == "紧张"
        assert event.changes[1].value == "愤怒"

        # Verify events.jsonl has the event
        scene_events = load_events_for_scene(char_dir, "scene_001")
        assert len(scene_events) == 1

        # Verify snapshot updated
        snap = load_snapshot(char_dir)
        assert snap.goal == "复仇"
        assert snap.emotion == "愤怒"
        assert snap.last_event_id == 1

        # Verify domain event emitted
        assert len(events_fired) == 1
        assert events_fired[0]["character_id"] == "char-hero"
        assert events_fired[0]["event_id"] == 1
