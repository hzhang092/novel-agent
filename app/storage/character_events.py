"""Event log I/O for characters/<name>/events.jsonl.

Each line is a JSON-serialized CharacterStateEvent. Append-only.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.storage.models import CharacterStateEvent

EVENTS_FILE = "events.jsonl"


def append_events(char_dir: Path, events: list[CharacterStateEvent]) -> None:
    """Append one or more events to the character's event log."""
    char_dir.mkdir(parents=True, exist_ok=True)
    filepath = char_dir / EVENTS_FILE
    with open(filepath, "a", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")


def load_events(char_dir: Path) -> list[CharacterStateEvent]:
    """Load all events from the character's event log. Skips invalid JSON lines."""
    filepath = char_dir / EVENTS_FILE
    if not filepath.exists():
        return []
    events: list[CharacterStateEvent] = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(CharacterStateEvent.model_validate(json.loads(line)))
            except (json.JSONDecodeError, Exception):
                continue
    return events


def load_events_since(char_dir: Path, since_event_id: int) -> list[CharacterStateEvent]:
    """Load events with event_id > since_event_id."""
    all_events = load_events(char_dir)
    return [e for e in all_events if e.event_id > since_event_id]


def load_events_for_scene(char_dir: Path, scene_id: str) -> list[CharacterStateEvent]:
    """Load events for a specific scene."""
    all_events = load_events(char_dir)
    return [e for e in all_events if e.scene_id == scene_id]


def get_latest_event_id(char_dir: Path) -> int:
    """Return the maximum event_id in the log, or 0 if empty."""
    all_events = load_events(char_dir)
    return max((e.event_id for e in all_events), default=0)
