"""StateRepository — atomic commit pipeline for event-sourced character state.

Wraps load_snapshot → apply changes → append events → save snapshot + checkpoint
with an optional EventBus for live UI updates.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.storage.character_events import append_events, load_events, get_latest_event_id
from app.storage.character_state import (
    load_snapshot,
    save_snapshot,
    save_checkpoint,
    _apply_changes_to_snapshot,
)
from app.storage.models import (
    CharacterStateEvent,
    CharacterStoredChange,
    StateChangeProposal,
    SceneStateCheckpoint,
)

if TYPE_CHECKING:
    from app.events.bus import EventBus


class StateRepository:
    """Commits state changes atomically: events → snapshot → checkpoint → domain event.

    Usage::
        repo = StateRepository(bus=domain_bus)
        event = repo.commit_proposal(char_dir, proposal, scene_id, tx_id, req_id)
    """

    def __init__(self, bus: EventBus | None = None) -> None:
        self.bus = bus

    # ── Commit proposal (from LLM pipeline) ────────────────────────────────

    def commit_proposal(
        self,
        char_dir: Path,
        proposal: StateChangeProposal,
        scene_id: str,
        transaction_id: str,
        request_id: str,
        source: str = "ai",
    ) -> CharacterStateEvent | None:
        """Apply a StateChangeProposal and persist as an event + snapshot + checkpoint.

        Returns the stored event, or None if there are no changes to apply.
        """
        changes = proposal.changes
        if not changes:
            return None

        # Load current snapshot
        snapshot = load_snapshot(char_dir)
        snapshot.character_id = proposal.character_id or snapshot.character_id

        # Build stored changes (filling old values from snapshot)
        stored_changes: list[CharacterStoredChange] = []
        for change in changes:
            sc = _convert_to_stored_change(change, snapshot)
            if sc is not None:
                stored_changes.append(sc)

        if not stored_changes:
            return None

        # Determine next event_id
        next_id = get_latest_event_id(char_dir) + 1

        # Apply changes to snapshot in-place
        assert next_id > snapshot.last_event_id, (
            f"event_id monotonicity violation: next_id={next_id} <= snapshot.last_event_id={snapshot.last_event_id}"
        )
        _apply_changes_to_snapshot(snapshot, stored_changes)
        snapshot.last_event_id = next_id
        snapshot.last_scene_id = scene_id
        snapshot.generated_at = datetime.now(timezone.utc).isoformat()

        # Build the event
        now = datetime.now(timezone.utc).isoformat()
        event = CharacterStateEvent(
            event_id=next_id,
            transaction_id=transaction_id,
            scene_id=scene_id,
            character_id=snapshot.character_id,
            source=source,
            request_id=request_id,
            created_at=now,
            changes=stored_changes,
        )

        # Persist atomically
        append_events(char_dir, [event])
        save_snapshot(char_dir, snapshot)

        # Write scene checkpoint
        checkpoint = SceneStateCheckpoint(
            scene_id=scene_id,
            checkpoint_id=str(uuid.uuid4()),
            event_id=next_id,
            character_id=snapshot.character_id,
            created_at=now,
            snapshot=snapshot,
        )
        save_checkpoint(char_dir, checkpoint)

        # Publish domain event for live UI refresh
        self._publish("character_state_updated", character_id=snapshot.character_id, event_id=next_id)

        return event

    # ── User-initiated manual edit ─────────────────────────────────────────

    def commit_user_edit(
        self,
        char_dir: Path,
        character_id: str,
        changes: list[dict],
        scene_id: str = "",
    ) -> CharacterStateEvent | None:
        """Commit a user-initiated state edit. Accepts dicts with type/field/value/old."""
        if not changes:
            return None

        snapshot = load_snapshot(char_dir)
        snapshot.character_id = character_id or snapshot.character_id

        stored_changes: list[CharacterStoredChange] = []
        for c in changes:
            sc = CharacterStoredChange(
                type=c.get("type", ""),
                field=c.get("field", ""),
                value=c.get("value", ""),
                old=c.get("old", ""),
                fact=c.get("fact", ""),
                target_character_id=c.get("target_character_id", ""),
                relationship=c.get("relationship", ""),
            )
            stored_changes.append(sc)

        next_id = get_latest_event_id(char_dir) + 1
        _apply_changes_to_snapshot(snapshot, stored_changes)
        snapshot.last_event_id = next_id
        snapshot.last_scene_id = scene_id
        snapshot.generated_at = datetime.now(timezone.utc).isoformat()

        now = datetime.now(timezone.utc).isoformat()
        event = CharacterStateEvent(
            event_id=next_id,
            transaction_id=str(uuid.uuid4()),
            scene_id=scene_id,
            character_id=snapshot.character_id,
            source="user",
            request_id=str(uuid.uuid4()),
            created_at=now,
            changes=stored_changes,
        )

        append_events(char_dir, [event])
        save_snapshot(char_dir, snapshot)

        checkpoint = SceneStateCheckpoint(
            scene_id=scene_id,
            checkpoint_id=str(uuid.uuid4()),
            event_id=next_id,
            character_id=snapshot.character_id,
            created_at=now,
            snapshot=snapshot,
        )
        save_checkpoint(char_dir, checkpoint)

        self._publish("character_state_updated", character_id=snapshot.character_id, event_id=next_id)

        return event

    # ── Invalidate event ───────────────────────────────────────────────────

    def invalidate_event(self, char_dir: Path, event_id: int) -> bool:
        """Mark an event as invalidated and rebuild the snapshot from scratch.
        Returns True if the event was found and invalidated."""
        events = load_events(char_dir)
        found = False
        for e in events:
            if e.event_id == event_id and not e.invalidated:
                e.invalidated = True
                found = True
                break

        if not found:
            return False

        # Rewrite events.jsonl with the invalidated flag
        events_file = char_dir / "events.jsonl"
        import json
        with open(events_file, "w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e.model_dump(mode="json"), ensure_ascii=False) + "\n")

        # Rebuild snapshot from valid events
        from app.storage.character_state import build_snapshot
        new_snap = build_snapshot(char_dir, char_dir.name)
        save_snapshot(char_dir, new_snap)

        self._publish("character_state_updated", character_id=new_snap.character_id, event_id=new_snap.last_event_id)
        return True

    # ── Internal helpers ───────────────────────────────────────────────────

    def _publish(self, event_type: str, **payload: object) -> None:
        if self.bus is not None:
            self.bus.publish(event_type, **payload)


def _convert_to_stored_change(
    change,
    snapshot: CharacterStateSnapshot,
) -> CharacterStoredChange | None:
    """Convert a discriminated StateChange to a CharacterStoredChange,
    filling in the old value from the current snapshot."""
    t = change.type
    old_value = ""
    field = ""
    fact = ""
    target_id = ""
    relationship = ""
    value = ""

    if t == "set_field":
        field = change.field
        value = change.value
        old_value = _get_old_scalar(snapshot, field)
    elif t == "relationship_change":
        target_id = change.target_character_id
        relationship = change.relationship
        old_value = snapshot.relationships.get(target_id, "")
    elif t == "knowledge_add":
        fact = change.fact
    elif t == "knowledge_remove":
        fact = change.fact
    elif t == "secret_add":
        fact = change.fact
    elif t == "secret_remove":
        fact = change.fact

    return CharacterStoredChange(
        type=t,
        field=field,
        value=value,
        old=old_value,
        fact=fact,
        target_character_id=target_id,
        relationship=relationship,
    )


def _get_old_scalar(snapshot: CharacterStateSnapshot, field: str) -> str:
    """Get the current value of a scalar field from the snapshot."""
    field_map = {
        "emotion": snapshot.emotion,
        "goal": snapshot.goal,
        "location": snapshot.location,
        "status": snapshot.status,
        "power_level": snapshot.power_level,
    }
    return field_map.get(field, "")
