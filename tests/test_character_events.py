"""Tests for character event log I/O — events.jsonl read/write/query."""
import tempfile
from pathlib import Path

import pytest

from app.storage.character_events import (
    append_events,
    load_events,
    load_events_since,
    load_events_for_scene,
    get_latest_event_id,
)
from app.storage.models import CharacterStateEvent, CharacterStoredChange


def _make_event(event_id: int, scene_id: str = "scene_001", invalidated: bool = False) -> CharacterStateEvent:
    return CharacterStateEvent(
        event_id=event_id,
        transaction_id="tx-1",
        scene_id=scene_id,
        character_id="char-1",
        source="ai",
        request_id="req-1",
        changes=[CharacterStoredChange(type="set_field", field="goal", old="old_goal", value="new_goal")],
        invalidated=invalidated,
    )


class TestAppendAndLoad:
    def test_append_then_load_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            events = [_make_event(1), _make_event(2)]
            append_events(char_dir, events)

            loaded = load_events(char_dir)
            assert len(loaded) == 2
            assert loaded[0].event_id == 1
            assert loaded[1].event_id == 2

    def test_load_empty_dir_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as td:
            loaded = load_events(Path(td))
            assert loaded == []


class TestLoadSince:
    def test_load_events_since_returns_only_newer(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            append_events(char_dir, [_make_event(1), _make_event(2), _make_event(3)])
            result = load_events_since(char_dir, since_event_id=1)
            assert len(result) == 2
            assert result[0].event_id == 2
            assert result[1].event_id == 3

    def test_load_events_since_zero_returns_all(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            append_events(char_dir, [_make_event(1), _make_event(2)])
            result = load_events_since(char_dir, since_event_id=0)
            assert len(result) == 2


class TestLoadForScene:
    def test_load_events_for_scene_filters_by_scene_id(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            append_events(char_dir, [
                _make_event(1, scene_id="scene_001"),
                _make_event(2, scene_id="scene_002"),
                _make_event(3, scene_id="scene_001"),
            ])
            result = load_events_for_scene(char_dir, scene_id="scene_001")
            assert len(result) == 2
            assert all(e.scene_id == "scene_001" for e in result)


class TestLatestEventId:
    def test_latest_event_id_returns_max(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            append_events(char_dir, [_make_event(5), _make_event(10)])
            assert get_latest_event_id(char_dir) == 10

    def test_latest_event_id_empty_dir_returns_zero(self):
        with tempfile.TemporaryDirectory() as td:
            assert get_latest_event_id(Path(td)) == 0
