"""Character state snapshot and replay I/O.

Reads/writes state.yaml (materialized snapshot) and checkpoints/<scene_id>.yaml.
"""
from __future__ import annotations

import yaml
from datetime import datetime, timezone
from pathlib import Path

from app.storage.models import (
    CharacterState,
    CharacterStateSnapshot,
    SceneStateCheckpoint,
)
from app.storage.character_events import get_latest_event_id, load_events

STATE_FILE = "state.yaml"
CHECKPOINT_DIR = "checkpoints"


# ── Snapshot I/O ───────────────────────────────────────────────────────────

def save_snapshot(char_dir: Path, snapshot: CharacterStateSnapshot) -> None:
    """Write the current materialized state to state.yaml."""
    char_dir.mkdir(parents=True, exist_ok=True)
    filepath = char_dir / STATE_FILE
    data = snapshot.model_dump(mode="json")
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_snapshot(char_dir: Path) -> CharacterStateSnapshot:
    """Load the cached state snapshot from state.yaml.
    Returns a default snapshot if the file doesn't exist or is empty."""
    filepath = char_dir / STATE_FILE
    if not filepath.exists():
        return CharacterStateSnapshot()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {filepath}: {e}") from e
    if raw is None:
        return CharacterStateSnapshot()
    try:
        return CharacterStateSnapshot.model_validate(raw)
    except Exception as e:
        raise ValueError(f"Invalid state data in {filepath}: {e}") from e


def load_or_build_snapshot(char_dir: Path, character_id: str = "") -> CharacterStateSnapshot:
    """Load cached snapshot if current, otherwise replay events and repair it."""
    try:
        cached = load_snapshot(char_dir)
    except ValueError as e:
        latest_event_id = get_latest_event_id(char_dir)
        if latest_event_id == 0:
            raise e
        cached = CharacterStateSnapshot()
    else:
        latest_event_id = get_latest_event_id(char_dir)
    if (cached.last_event_id > 0 or cached.character_id) and cached.last_event_id >= latest_event_id:
        return cached
    rebuilt = build_snapshot(char_dir, character_id or cached.character_id)
    save_snapshot(char_dir, rebuilt)
    return rebuilt


def build_snapshot(char_dir: Path, character_id: str = "") -> CharacterStateSnapshot:
    """Replay all events from events.jsonl to build the current state snapshot.
    Skips invalidated events. Order is by event_id ascending."""
    events = load_events(char_dir)
    snap = CharacterStateSnapshot(character_id=character_id)
    if not events:
        return snap

    # Sort just in case events were appended out of order
    events.sort(key=lambda e: e.event_id)

    for event in events:
        if event.invalidated:
            continue
        snap.last_event_id = max(snap.last_event_id, event.event_id)
        snap.last_scene_id = event.scene_id or snap.last_scene_id
        snap.character_id = event.character_id or snap.character_id
        _apply_changes_to_snapshot(snap, event.changes)

    return snap


def _apply_changes_to_snapshot(
    snap: CharacterStateSnapshot,
    changes: list,
) -> None:
    """Apply a list of CharacterStoredChange items to a snapshot in-place."""
    for change in changes:
        t = change.type
        if t == "set_field":
            _set_scalar(snap, change.field, change.value)
        elif t == "relationship_change":
            snap.relationships[change.target_character_id] = change.relationship
        elif t == "relationship_remove":
            snap.relationships.pop(change.target_character_id, None)
        elif t == "knowledge_add":
            if change.fact not in snap.knowledge:
                snap.knowledge.append(change.fact)
        elif t == "knowledge_remove":
            if change.fact in snap.knowledge:
                snap.knowledge.remove(change.fact)
        elif t == "secret_add":
            if change.fact not in snap.secrets:
                snap.secrets.append(change.fact)
        elif t == "secret_remove":
            if change.fact in snap.secrets:
                snap.secrets.remove(change.fact)


def _set_scalar(snap: CharacterStateSnapshot, field: str, value: str) -> None:
    """Set a scalar field on the snapshot by name."""
    field_map = {
        "emotion": "emotion",
        "goal": "goal",
        "location": "location",
        "status": "status",
        "power_level": "power_level",
    }
    attr = field_map.get(field)
    if attr:
        setattr(snap, attr, value)


def _none_if_empty(value: str) -> str | None:
    """Return None if value is the empty string, otherwise the value unchanged."""
    return None if value == "" else value


# ── State ↔ Snapshot mapping ───────────────────────────────────────────────

def map_character_state_to_snapshot(state: CharacterState) -> CharacterStateSnapshot:
    """Convert a legacy CharacterState to a CharacterStateSnapshot."""
    return CharacterStateSnapshot(
        character_id=state.character_id,
        last_scene_id=state.last_updated_scene or "",
        emotion=state.current_emotion,
        goal=state.current_goal,
        location=state.current_location,
        status=state.current_status,
        power_level=state.current_power_level if state.current_power_level is not None else "",
        relationships=dict(state.current_relationships),
        knowledge=list(state.current_knowledge),
        secrets=list(state.current_secrets),
    )


def map_snapshot_to_character_state(snap: CharacterStateSnapshot) -> CharacterState:
    """Convert a CharacterStateSnapshot back to a CharacterState."""
    return CharacterState(
        character_id=snap.character_id,
        current_goal=snap.goal,
        current_emotion=snap.emotion,
        current_location=snap.location,
        current_power_level=_none_if_empty(snap.power_level),
        current_relationships=dict(snap.relationships),
        current_knowledge=list(snap.knowledge),
        current_secrets=list(snap.secrets),
        current_status=snap.status,
        last_updated_scene=snap.last_scene_id if snap.last_scene_id else None,
    )


# ── Checkpoint I/O ─────────────────────────────────────────────────────────

def save_checkpoint(char_dir: Path, checkpoint: SceneStateCheckpoint) -> None:
    """Write a scene-level checkpoint to checkpoints/<scene_id>.yaml."""
    cp_dir = char_dir / CHECKPOINT_DIR
    cp_dir.mkdir(parents=True, exist_ok=True)
    filepath = cp_dir / f"{checkpoint.scene_id}.yaml"
    if not checkpoint.created_at:
        checkpoint.created_at = datetime.now(timezone.utc).isoformat()
    data = checkpoint.model_dump(mode="json")
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_checkpoint(char_dir: Path, scene_id: str) -> SceneStateCheckpoint | None:
    """Load a scene-level checkpoint. Returns None if not found."""
    filepath = char_dir / CHECKPOINT_DIR / f"{scene_id}.yaml"
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError:
        return None
    if raw is None:
        return None
    try:
        return SceneStateCheckpoint.model_validate(raw)
    except Exception:
        return None
