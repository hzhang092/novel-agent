"""Tests for character event log I/O — events.jsonl read/write/query."""

import pytest

from app.storage.character_events import (
    append_events,
    get_latest_event_id,
    load_events,
    load_events_for_scene,
    load_events_since,
)
from app.storage.models import CharacterStateEvent, CharacterStoredChange


def _make_event(event_id: int, scene_id: str = "scene_001") -> CharacterStateEvent:
    return CharacterStateEvent(
        event_id=event_id,
        transaction_id="tx-1",
        scene_id=scene_id,
        character_id="char-1",
        source="ai",
        request_id="req-1",
        changes=[
            CharacterStoredChange(
                type="set_field",
                field="goal",
                old="old_goal",
                value="new_goal",
            )
        ],
    )


def test_event_log_round_trip_and_queries(tmp_path):
    events = [
        _make_event(1, "scene_001"),
        _make_event(2, "scene_002"),
        _make_event(3, "scene_001"),
    ]
    append_events(tmp_path, events)

    assert load_events(tmp_path) == events
    assert load_events_since(tmp_path, since_event_id=1) == events[1:]
    assert load_events_since(tmp_path, since_event_id=0) == events
    assert load_events_for_scene(tmp_path, "scene_001") == [events[0], events[2]]
    assert get_latest_event_id(tmp_path) == 3


def test_empty_event_log_variants(tmp_path):
    assert load_events(tmp_path) == []
    assert get_latest_event_id(tmp_path) == 0

    (tmp_path / "events.jsonl").write_text("", encoding="utf-8")
    assert load_events(tmp_path) == []


@pytest.mark.parametrize(
    ("content", "line"),
    [
        ('{"event_id": 1}\n{bad json}\n', 2),
        ('{"changes": "not a list"}\n', 1),
    ],
)
def test_invalid_event_log_reports_file_and_line(tmp_path, content, line):
    path = tmp_path / "events.jsonl"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        load_events(tmp_path)

    assert str(path) in str(exc.value)
    assert f"line {line}" in str(exc.value)
