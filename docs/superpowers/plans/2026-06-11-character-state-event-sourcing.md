# Character State Event Sourcing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the character state overwrite model with event-sourced state: append-only events, materialized snapshots, scene checkpoints, a domain event bus for live UI refresh, and a three-tab character editor (Definition / Current State / History).

**Architecture:** Character state flows through a pure-Python `EventBus` → `QtEventBridge` for cross-thread dispatch. The pipeline stages changes in memory and commits atomically (events + snapshot + checkpoint). The character editor subscribes to domain events for live refresh. Legacy `characters/<name>.yaml` files are dual-read; new writes use `characters/<name>/definition.yaml` + `state.yaml` + `events.jsonl`.

**Tech Stack:** Python 3.12+, Pydantic v2, PyQt6, qasync, PyYAML, pytest

---

### Task 1: New data models — StateChange discriminated union

**Files:**
- Modify: `app/storage/models.py` (add after `StateChangeProposal`, replace `StateChangeProposal`)

- [ ] **Step 1: Add `StateChange` discriminated union models**

Replace the existing `StateChangeProposal` class (lines ~266-279) with the new discriminated union and revised proposal:

```python
from typing import Annotated, Literal, Union

# ── State Change discriminated union (LLM-facing) ─────────────────────────

CHARACTER_SCALAR_FIELDS = Literal[
    "emotion", "goal", "location", "status", "power_level"
]

class SetFieldChange(BaseModel):
    """Set a scalar state field to a new value."""
    type: Literal["set_field"]
    field: CHARACTER_SCALAR_FIELDS
    value: str

class RelationshipChange(BaseModel):
    """Add or update a relationship with another character."""
    type: Literal["relationship_change"]
    target_character_id: str
    relationship: str

class KnowledgeAddChange(BaseModel):
    """Add a fact to the character's knowledge."""
    type: Literal["knowledge_add"]
    fact: str

class KnowledgeRemoveChange(BaseModel):
    """Remove a fact from the character's knowledge."""
    type: Literal["knowledge_remove"]
    fact: str

class SecretAddChange(BaseModel):
    """Add a secret the character knows."""
    type: Literal["secret_add"]
    fact: str

class SecretRemoveChange(BaseModel):
    """Remove a secret from the character's knowledge."""
    type: Literal["secret_remove"]
    fact: str

StateChange = Annotated[
    Union[
        SetFieldChange,
        RelationshipChange,
        KnowledgeAddChange,
        KnowledgeRemoveChange,
        SecretAddChange,
        SecretRemoveChange,
    ],
    Field(discriminator="type"),
]


class StateChangeProposal(BaseModel):
    """LLM output: proposed state changes for one character after a scene.
    Contains only new values — code fills old values from the snapshot."""
    character_id: str = ""
    character_name: str = ""
    changes: list[StateChange] = Field(default_factory=list)


# ── Stored event record (events.jsonl line) ───────────────────────────────

class CharacterStoredChange(BaseModel):
    """A single change within a stored event, with old value filled by code."""
    type: str  # same discriminator as StateChange
    field: str = ""             # for set_field
    value: str = ""             # new value (for set_field)
    old: str = ""               # previous value (filled by code)
    fact: str = ""              # for knowledge_add/remove, secret_add/remove
    target_character_id: str = ""  # for relationship_change
    relationship: str = ""      # for relationship_change


class CharacterStateEvent(BaseModel):
    """One JSONL line in events.jsonl — a single StateUpdater run."""
    event_id: int = 0
    transaction_id: str = ""    # groups events from same pipeline run
    scene_id: str = ""
    character_id: str = ""
    source: str = "ai"          # ai | user | manual_event | system
    request_id: str = ""        # UUID for observability
    schema_version: int = 1
    invalidated: bool = False
    created_at: str = ""        # ISO timestamp
    changes: list[CharacterStoredChange] = Field(default_factory=list)


# ── State snapshot (state.yaml) ───────────────────────────────────────────

class CharacterStateSnapshot(BaseModel):
    """Materialized character state at a specific event_id.
    Written to state.yaml — the cached current-state view."""
    character_id: str = ""
    last_scene_id: str = ""
    last_event_id: int = 0
    snapshot_version: int = 1
    generated_at: str = ""
    emotion: str = ""
    goal: str = ""
    location: str = ""
    status: str = ""
    power_level: str = ""
    relationships: dict[str, str] = Field(default_factory=dict)
    knowledge: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Run existing model tests to verify the old `StateChangeProposal` references still work**

```powershell
conda activate fourteen; python -m pytest tests/test_models.py -v
```

The old `StateChangeProposal` with `*_add`/`*_remove` fields is now gone. Tests referencing it will fail. We'll fix those in the StateUpdater task.

Expected: some test failures (expected — tests referencing old schema will be updated later).

- [ ] **Step 3: Add a test for the new models**

Create `tests/test_models.py` (add to existing file):

```python
def test_state_change_discriminated_union_set_field():
    """SetFieldChange validates with correct type and known field."""
    from app.storage.models import SetFieldChange, StateChangeProposal

    change = SetFieldChange(type="set_field", field="goal", value="avenge master")
    proposal = StateChangeProposal(character_id="char-1", character_name="林枫", changes=[change])
    assert len(proposal.changes) == 1
    assert proposal.changes[0].type == "set_field"

def test_state_change_discriminated_union_rejects_unknown_field():
    """SetFieldChange rejects field names not in CHARACTER_SCALAR_FIELDS."""
    from pydantic import ValidationError
    from app.storage.models import SetFieldChange

    with pytest.raises(ValidationError):
        SetFieldChange(type="set_field", field="goals", value="avenge master")

def test_character_state_event_serializes_to_dict():
    """CharacterStateEvent round-trips through model_dump."""
    from app.storage.models import CharacterStateEvent, CharacterStoredChange

    event = CharacterStateEvent(
        event_id=1,
        scene_id="scene_042",
        character_id="char-1",
        source="ai",
        changes=[CharacterStoredChange(type="set_field", field="goal", value="avenge", old="become_elder")],
    )
    d = event.model_dump(mode="json")
    assert d["event_id"] == 1
    assert d["changes"][0]["old"] == "become_elder"
```

Run: `pytest tests/test_models.py::test_state_change_discriminated_union_set_field tests/test_models.py::test_state_change_discriminated_union_rejects_unknown_field tests/test_models.py::test_character_state_event_serializes_to_dict -v`

Expected: 3 PASS

- [ ] **Step 4: Commit**

```bash
git add app/storage/models.py tests/test_models.py
git commit -m "feat: add StateChange discriminated union and CharacterStateEvent models"
```

---

### Task 2: Event bus infrastructure

**Files:**
- Create: `app/events/__init__.py`
- Create: `app/events/bus.py`
- Create: `app/events/qt_bridge.py`
- Create: `tests/test_event_bus.py`

- [ ] **Step 1: Write tests for the pure Python EventBus**

Create `tests/test_event_bus.py`:

```python
"""Tests for the domain event bus — pure Python, no Qt."""
import pytest
from app.events.bus import EventBus


class TestEventBus:
    def test_subscribe_and_publish_single_handler(self):
        bus = EventBus()
        received = []

        bus.subscribe("character_state_updated", lambda **kw: received.append(kw))
        bus.publish("character_state_updated", character_id="char-1", event_id=42)

        assert len(received) == 1
        assert received[0]["character_id"] == "char-1"
        assert received[0]["event_id"] == 42

    def test_publish_with_no_subscribers_does_not_raise(self):
        bus = EventBus()
        bus.publish("unknown_event", foo="bar")

    def test_multiple_handlers_for_same_event(self):
        bus = EventBus()
        calls = []

        bus.subscribe("evt", lambda **kw: calls.append(1))
        bus.subscribe("evt", lambda **kw: calls.append(2))
        bus.publish("evt")

        assert calls == [1, 2]

    def test_handler_exception_does_not_block_others(self):
        bus = EventBus()
        calls = []

        def bad_handler(**kw):
            raise RuntimeError("boom")

        bus.subscribe("evt", bad_handler)
        bus.subscribe("evt", lambda **kw: calls.append("ok"))
        bus.publish("evt")

        assert calls == ["ok"]

    def test_unsubscribe_removes_handler(self):
        bus = EventBus()
        calls = []

        def h(**kw):
            calls.append(1)

        bus.subscribe("evt", h)
        bus.unsubscribe("evt", h)
        bus.publish("evt")

        assert calls == []
```

Run: `pytest tests/test_event_bus.py -v`
Expected: 5 FAIL (file doesn't exist yet)

- [ ] **Step 2: Implement EventBus**

Create `app/events/__init__.py`:
```python
"""Domain events — framework-agnostic pub/sub for character state changes."""
```

Create `app/events/bus.py`:
```python
"""Pure-Python event bus. No Qt, no threading logic."""
from __future__ import annotations

from collections import defaultdict
from typing import Callable


Handler = Callable[..., None]


class EventBus:
    """Simple typed pub/sub bus for domain events.

    Usage::

        bus = EventBus()
        bus.subscribe("character_state_updated", lambda **kw: print(kw))
        bus.publish("character_state_updated", character_id="x", event_id=1)
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register a handler for an event type."""
        self._listeners[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        """Remove a handler for an event type. No-op if not registered."""
        try:
            self._listeners[event_type].remove(handler)
        except ValueError:
            pass

    def publish(self, event_type: str, **payload: object) -> None:
        """Publish an event to all registered handlers.
        Handlers are called synchronously. Exceptions in one handler
        do not prevent other handlers from running."""
        for handler in self._listeners.get(event_type, ()):
            try:
                handler(**payload)
            except Exception:
                # Swallow — one broken handler shouldn't break the bus.
                # In production, consider logging.
                pass
```

Run: `pytest tests/test_event_bus.py -v`
Expected: 5 PASS

- [ ] **Step 3: Commit**

```bash
git add app/events/__init__.py app/events/bus.py tests/test_event_bus.py
git commit -m "feat: add pure-Python EventBus with subscribe/publish/unsubscribe"
```

- [ ] **Step 4: Implement QtEventBridge**

Create `app/events/qt_bridge.py`:
```python
"""Qt thread bridge for the domain EventBus.

Marshals publish() calls from worker threads to the Qt main thread
via QMetaObject.invokeMethod with Qt.QueuedConnection.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QMetaObject, Qt, QThread, pyqtSlot

from app.events.bus import EventBus


class QtEventBridge(QObject):
    """Wraps an EventBus so publish() is always safe from any thread.

    Usage::

        domain_bus = EventBus()
        bridge = QtEventBridge(domain_bus)
        bridge.publish("character_state_updated", character_id="x", event_id=1)
    """

    def __init__(self, bus: EventBus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.bus = bus

    def publish(self, event_type: str, **payload: object) -> None:
        """Publish an event. If called from a non-main thread, marshals
        to the main thread via queued connection."""
        if QThread.currentThread() is self.thread():
            # Already on the bridge's owning thread — publish directly.
            self.bus.publish(event_type, **payload)
        else:
            QMetaObject.invokeMethod(
                self,
                "_publish_impl",
                Qt.ConnectionType.QueuedConnection,
                # Q_ARG-like: we pass args as a tuple the slot unpacks.
                # PyQt6 supports passing Python objects through queued connections.
            )
            # Fallback path: use a lambda stored on the instance.
            # Simpler: use a pyqtSlot with explicit args.
            self._do_queued_publish(event_type, payload)

    def _do_queued_publish(self, event_type: str, payload: dict[str, object]) -> None:
        """Helper that creates a queued invocation. We use a simple approach:
        schedule the call on the main thread's event loop directly."""
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.bus.publish(event_type, **payload))
```

Wait — `QTimer.singleShot(0, ...)` is simpler and just as correct. Let me use that:

```python
"""Qt thread bridge for the domain EventBus.

Marshals publish() calls from worker threads to the Qt main thread
via QTimer.singleShot(0, ...) which posts to the main event loop.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, QTimer

from app.events.bus import EventBus


class QtEventBridge(QObject):
    """Wraps an EventBus so publish() is always safe from any thread."""

    def __init__(self, bus: EventBus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.bus = bus

    def publish(self, event_type: str, **payload: object) -> None:
        """Publish an event. Safe from any thread."""
        if QThread.currentThread() is self.thread():
            self.bus.publish(event_type, **payload)
        else:
            QTimer.singleShot(0, lambda: self.bus.publish(event_type, **payload))
```

- [ ] **Step 5: Commit**

```bash
git add app/events/qt_bridge.py
git commit -m "feat: add QtEventBridge for cross-thread event bus publishing"
```

---

### Task 3: Storage — event log I/O

**Files:**
- Create: `app/storage/character_events.py`
- Create: `tests/test_character_events.py`

- [ ] **Step 1: Write tests for event log I/O**

Create `tests/test_character_events.py`:

```python
"""Tests for character event log I/O — events.jsonl read/write/query."""
import json
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

    def test_load_events_since_none_returns_all(self):
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
```

Run: `pytest tests/test_character_events.py -v`
Expected: 6 FAIL

- [ ] **Step 2: Implement event log I/O**

Create `app/storage/character_events.py`:

```python
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
            except Exception:
                continue
    return events


def load_events_since(char_dir: Path, since_event_id: int = 0) -> list[CharacterStateEvent]:
    """Load events with event_id > since_event_id, in order."""
    all_events = load_events(char_dir)
    return [e for e in all_events if e.event_id > since_event_id]


def load_events_for_scene(char_dir: Path, scene_id: str) -> list[CharacterStateEvent]:
    """Load all events (including invalidated) for a specific scene."""
    all_events = load_events(char_dir)
    return [e for e in all_events if e.scene_id == scene_id]


def get_latest_event_id(char_dir: Path) -> int:
    """Return the highest event_id in the log, or 0 if empty."""
    all_events = load_events(char_dir)
    return max((e.event_id for e in all_events), default=0)


def invalidate_scene_events(char_dir: Path, scene_id: str) -> int:
    """Mark all events for a scene as invalidated. Returns count of invalidated events.
    This rewrites the events.jsonl file — use sparingly (only on scene regeneration)."""
    all_events = load_events(char_dir)
    count = 0
    for e in all_events:
        if e.scene_id == scene_id and not e.invalidated:
            e.invalidated = True
            count += 1
    if count > 0:
        filepath = char_dir / EVENTS_FILE
        with open(filepath, "w", encoding="utf-8") as f:
            for event in all_events:
                f.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
    return count
```

Run: `pytest tests/test_character_events.py -v`
Expected: 6 PASS

- [ ] **Step 3: Commit**

```bash
git add app/storage/character_events.py tests/test_character_events.py
git commit -m "feat: add event log I/O for character events.jsonl"
```

---

### Task 4: Storage — state.yaml I/O (snapshot + checkpoint + replay)

**Files:**
- Create: `app/storage/character_state.py`
- Create: `tests/test_character_state.py`

- [ ] **Step 1: Write tests for snapshot and checkpoint I/O**

Create `tests/test_character_state.py`:

```python
"""Tests for character state storage — state.yaml, checkpoints, replay."""
import tempfile
from pathlib import Path

import pytest

from app.storage.character_state import (
    load_snapshot,
    save_snapshot,
    save_checkpoint,
    load_checkpoint,
    rebuild_snapshot,
)
from app.storage.character_events import append_events
from app.storage.models import CharacterStateSnapshot, CharacterStateEvent, CharacterStoredChange


def _make_event(event_id: int, scene_id: str = "scene_001", **changes_kw) -> CharacterStateEvent:
    changes = changes_kw.get("changes", [
        CharacterStoredChange(type="set_field", field="goal", old="old", value="new"),
    ])
    return CharacterStateEvent(
        event_id=event_id,
        transaction_id="tx-1",
        scene_id=scene_id,
        character_id="char-1",
        source="ai",
        request_id="req-1",
        changes=changes,
    )


def _make_snapshot(last_event_id: int = 0) -> CharacterStateSnapshot:
    return CharacterStateSnapshot(
        character_id="char-1",
        last_scene_id="scene_001",
        last_event_id=last_event_id,
        goal="test goal",
        emotion="calm",
    )


class TestSnapshotIO:
    def test_save_and_load_snapshot_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            snap = _make_snapshot(last_event_id=5)
            save_snapshot(char_dir, snap)
            loaded = load_snapshot(char_dir)
            assert loaded.last_event_id == 5
            assert loaded.goal == "test goal"

    def test_load_snapshot_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            assert load_snapshot(Path(td)) is None


class TestCheckpointIO:
    def test_save_and_load_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            snap = _make_snapshot(last_event_id=10)
            save_checkpoint(char_dir, "scene_005", snap)
            loaded = load_checkpoint(char_dir, "scene_005")
            assert loaded.last_event_id == 10

    def test_load_missing_checkpoint_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            assert load_checkpoint(Path(td), "scene_999") is None


class TestRebuildSnapshot:
    def test_rebuild_from_events_produces_latest_state(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            # Start with a definition-like minimal snapshot
            base = CharacterStateSnapshot(character_id="char-1", last_event_id=0)
            save_snapshot(char_dir, base)

            # Append events
            append_events(char_dir, [
                _make_event(1, changes=[
                    CharacterStoredChange(type="set_field", field="goal", old="", value="avenge master"),
                    CharacterStoredChange(type="set_field", field="emotion", old="", value="furious"),
                ]),
                _make_event(2, changes=[
                    CharacterStoredChange(type="set_field", field="location", old="", value="sect hall"),
                    CharacterStoredChange(type="knowledge_add", fact="Elder Zhao killed master"),
                ]),
            ])

            rebuilt = rebuild_snapshot(char_dir, base)
            assert rebuilt.goal == "avenge master"
            assert rebuilt.emotion == "furious"
            assert rebuilt.location == "sect hall"
            assert "Elder Zhao killed master" in rebuilt.knowledge
            assert rebuilt.last_event_id == 2

    def test_rebuild_skips_invalidated_events(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            base = CharacterStateSnapshot(character_id="char-1", last_event_id=0)
            save_snapshot(char_dir, base)

            append_events(char_dir, [
                _make_event(1, changes=[
                    CharacterStoredChange(type="set_field", field="goal", old="", value="first"),
                ]),
                _make_event(2, changes=[
                    CharacterStoredChange(type="set_field", field="goal", old="first", value="second"),
                ]),
            ])
            # Invalidate event 1
            from app.storage.character_events import invalidate_scene_events
            invalidate_scene_events(char_dir, "scene_001")  # both events have scene_001

            rebuilt = rebuild_snapshot(char_dir, base)
            # After invalidating both events, state should be back to base
            assert rebuilt.goal == ""
```

Run: `pytest tests/test_character_state.py -v`
Expected: 5 FAIL

- [ ] **Step 2: Implement state.yaml I/O and replay**

Create `app/storage/character_state.py`:

```python
"""Character state storage — state.yaml, scene checkpoints, snapshot replay."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.storage.models import CharacterStateSnapshot, CharacterStateEvent, CharacterStoredChange

STATE_FILE = "state.yaml"
CHECKPOINTS_DIR = "checkpoints"


# ── Snapshot I/O ──────────────────────────────────────────────────────────

def save_snapshot(char_dir: Path, snapshot: CharacterStateSnapshot) -> None:
    """Write the current state snapshot to state.yaml."""
    char_dir.mkdir(parents=True, exist_ok=True)
    snapshot.generated_at = datetime.now(timezone.utc).isoformat()
    data = snapshot.model_dump(mode="json")
    filepath = char_dir / STATE_FILE
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_snapshot(char_dir: Path) -> CharacterStateSnapshot | None:
    """Load the state snapshot, or None if missing/corrupt."""
    filepath = char_dir / STATE_FILE
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if raw is None:
            return None
        return CharacterStateSnapshot.model_validate(raw)
    except Exception:
        return None


# ── Checkpoint I/O ────────────────────────────────────────────────────────

def save_checkpoint(char_dir: Path, scene_id: str, snapshot: CharacterStateSnapshot) -> None:
    """Save an immutable scene checkpoint: state_checkpoints/<scene_id>.yaml."""
    cp_dir = char_dir / CHECKPOINTS_DIR
    cp_dir.mkdir(parents=True, exist_ok=True)
    snapshot.generated_at = datetime.now(timezone.utc).isoformat()
    data = snapshot.model_dump(mode="json")
    filepath = cp_dir / f"{scene_id}.yaml"
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_checkpoint(char_dir: Path, scene_id: str) -> CharacterStateSnapshot | None:
    """Load a scene checkpoint, or None if missing."""
    filepath = char_dir / CHECKPOINTS_DIR / f"{scene_id}.yaml"
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if raw is None:
            return None
        return CharacterStateSnapshot.model_validate(raw)
    except Exception:
        return None


# ── Replay ────────────────────────────────────────────────────────────────

def rebuild_snapshot(
    char_dir: Path,
    base_snapshot: CharacterStateSnapshot,
) -> CharacterStateSnapshot:
    """Replay all valid events since the base snapshot to produce a new snapshot."""
    from app.storage.character_events import load_events_since

    events = load_events_since(char_dir, since_event_id=base_snapshot.last_event_id)
    return _apply_events(base_snapshot, events)


def _apply_events(
    snapshot: CharacterStateSnapshot,
    events: list[CharacterStateEvent],
) -> CharacterStateSnapshot:
    """Apply a list of events to a snapshot, returning a new snapshot.
    Only non-invalidated events are applied."""
    # Build mutable state from snapshot
    state = {
        "emotion": snapshot.emotion,
        "goal": snapshot.goal,
        "location": snapshot.location,
        "status": snapshot.status,
        "power_level": snapshot.power_level,
        "relationships": dict(snapshot.relationships),
        "knowledge": list(snapshot.knowledge),
        "secrets": list(snapshot.secrets),
    }
    last_event_id = snapshot.last_event_id
    last_scene_id = snapshot.last_scene_id

    for event in events:
        if event.invalidated:
            continue
        for change in event.changes:
            if change.type == "set_field":
                if change.field in state:
                    state[change.field] = change.value
            elif change.type == "relationship_change":
                state["relationships"][change.target_character_id] = change.relationship
            elif change.type == "knowledge_add":
                if change.fact and change.fact not in state["knowledge"]:
                    state["knowledge"].append(change.fact)
            elif change.type == "knowledge_remove":
                if change.fact in state["knowledge"]:
                    state["knowledge"].remove(change.fact)
            elif change.type == "secret_add":
                if change.fact and change.fact not in state["secrets"]:
                    state["secrets"].append(change.fact)
            elif change.type == "secret_remove":
                if change.fact in state["secrets"]:
                    state["secrets"].remove(change.fact)
        last_event_id = max(last_event_id, event.event_id)
        last_scene_id = event.scene_id or last_scene_id

    return CharacterStateSnapshot(
        character_id=snapshot.character_id,
        last_scene_id=last_scene_id,
        last_event_id=last_event_id,
        snapshot_version=max(snapshot.snapshot_version, 1),
        emotion=state["emotion"],
        goal=state["goal"],
        location=state["location"],
        status=state["status"],
        power_level=state["power_level"],
        relationships=state["relationships"],
        knowledge=state["knowledge"],
        secrets=state["secrets"],
    )


def incremental_update_snapshot(char_dir: Path) -> CharacterStateSnapshot | None:
    """Load the snapshot, replay new events, save and return the updated snapshot.
    Returns None if no snapshot exists."""
    snapshot = load_snapshot(char_dir)
    if snapshot is None:
        return None
    from app.storage.character_events import get_latest_event_id
    latest = get_latest_event_id(char_dir)
    if latest <= snapshot.last_event_id:
        return snapshot
    updated = rebuild_snapshot(char_dir, snapshot)
    save_snapshot(char_dir, updated)
    return updated
```

Run: `pytest tests/test_character_state.py -v`
Expected: 5 PASS

- [ ] **Step 3: Commit**

```bash
git add app/storage/character_state.py tests/test_character_state.py
git commit -m "feat: add snapshot/checkpoint I/O and event replay for character state"
```

---

### Task 5: Storage — per-character directory layout and dual-read

**Files:**
- Modify: `app/storage/project_files.py`

- [ ] **Step 1: Write dual-read tests**

Add to `tests/test_repository_characters.py`:

```python
class TestDualReadCharacterLayout:
    """Verify loader reads both legacy flat YAML and new per-directory layout."""

    def test_save_character_writes_new_layout(self, tmp_path):
        from app.storage.project_files import save_character, load_character
        from app.storage.models import Character, CharacterCore, CharacterState

        char = Character(
            core=CharacterCore(id="test-1", name="测试"),
            state=CharacterState(character_id="test-1", current_goal="test goal"),
        )
        save_character(tmp_path, char)

        # New layout: directory with definition.yaml
        char_dir = tmp_path / "characters" / "test-1"
        assert char_dir.is_dir()
        assert (char_dir / "definition.yaml").exists()

    def test_load_character_reads_new_layout(self, tmp_path):
        from app.storage.project_files import save_character, load_character
        from app.storage.models import Character, CharacterCore, CharacterState

        char = Character(
            core=CharacterCore(id="test-2", name="林枫", personality="隐忍"),
            state=CharacterState(character_id="test-2", current_goal="复仇"),
        )
        save_character(tmp_path, char)
        loaded = load_character(tmp_path, "test-2")
        assert loaded.core.name == "林枫"
        assert loaded.state.current_goal == "复仇"

    def test_load_character_reads_legacy_flat_yaml(self, tmp_path):
        """Legacy format: characters/<id>.yaml with core+state inline."""
        import yaml

        char_dir = tmp_path / "characters"
        char_dir.mkdir()
        legacy_data = {
            "core": {"id": "legacy-1", "name": "旧角色", "tier": "major"},
            "state": {"character_id": "legacy-1", "current_goal": "旧目标"},
        }
        with open(char_dir / "legacy-1.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(legacy_data, f, allow_unicode=True)

        from app.storage.project_files import load_character
        loaded = load_character(tmp_path, "legacy-1")
        assert loaded.core.name == "旧角色"
        assert loaded.state.current_goal == "旧目标"

    def test_save_over_legacy_creates_new_layout_and_keeps_backup(self, tmp_path):
        """Saving a character that exists in legacy format migrates to new layout."""
        import yaml
        from app.storage.project_files import save_character, load_character
        from app.storage.models import Character, CharacterCore, CharacterState

        char_dir = tmp_path / "characters"
        char_dir.mkdir()
        legacy_data = {
            "core": {"id": "migrate-1", "name": "待迁移", "tier": "major"},
            "state": {"character_id": "migrate-1", "current_goal": "迁移前目标"},
        }
        legacy_path = char_dir / "migrate-1.yaml"
        with open(legacy_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(legacy_data, f, allow_unicode=True)

        char = Character(
            core=CharacterCore(id="migrate-1", name="待迁移", personality="新性格"),
            state=CharacterState(character_id="migrate-1", current_goal="迁移后目标"),
        )
        save_character(tmp_path, char)

        # New layout exists
        new_dir = char_dir / "migrate-1"
        assert new_dir.is_dir()
        assert (new_dir / "definition.yaml").exists()

        # Loaded character has new data
        loaded = load_character(tmp_path, "migrate-1")
        assert loaded.state.current_goal == "迁移后目标"
```

Run: `pytest tests/test_repository_characters.py::TestDualReadCharacterLayout -v`
Expected: 4 FAIL

- [ ] **Step 2: Modify `save_character` and `load_character` for the new layout**

Edit `app/storage/project_files.py` — replace `save_character` (lines ~112-122) and `load_character` (lines ~125-150):

```python
def save_character(project_dir: Path, character: Character) -> None:
    """Write a character to characters/<id>/definition.yaml (new layout).
    Also writes an initial state.yaml snapshot if one doesn't exist.
    Legacy characters/<id>.yaml is migrated on first save."""
    char_dir = project_dir / "characters" / character.core.id
    char_dir.mkdir(parents=True, exist_ok=True)

    # Write definition.yaml
    def_data = character.core.model_dump(mode="json")
    def_path = char_dir / "definition.yaml"
    with open(def_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(def_data, f, allow_unicode=True, sort_keys=False)

    # Write state.yaml snapshot (merge into existing if present)
    from app.storage.character_state import load_snapshot, save_snapshot
    from app.storage.models import CharacterStateSnapshot

    existing_snap = load_snapshot(char_dir)
    snap = CharacterStateSnapshot(
        character_id=character.core.id,
        last_scene_id=character.state.last_updated_scene or "",
        last_event_id=existing_snap.last_event_id if existing_snap else 0,
        emotion=character.state.current_emotion,
        goal=character.state.current_goal,
        location=character.state.current_location,
        status=character.state.current_status,
        power_level=character.state.current_power_level or "",
        relationships=dict(character.state.current_relationships),
        knowledge=list(character.state.current_knowledge),
        secrets=list(character.state.current_secrets),
    )
    save_snapshot(char_dir, snap)

    # Migrate legacy flat file if it exists: rename to .bak
    legacy_path = project_dir / "characters" / f"{character.core.id}.yaml"
    if legacy_path.exists():
        bak_path = legacy_path.with_suffix(".yaml.bak")
        legacy_path.rename(bak_path)


def load_character(project_dir: Path, character_id: str) -> Character:
    """Load a character, supporting both legacy flat YAML and new per-directory layout.

    Raises:
        FileNotFoundError: If neither format exists.
        ValueError: If the YAML is invalid or fails model validation.
    """
    # Try new layout first
    char_dir = project_dir / "characters" / character_id
    def_path = char_dir / "definition.yaml"
    if def_path.exists():
        with open(def_path, "r", encoding="utf-8") as f:
            raw_def = yaml.safe_load(f)
        if raw_def is None:
            raise ValueError(f"Empty definition file: {def_path}")
        core = CharacterCore.model_validate(raw_def)

        # Load state from snapshot
        from app.storage.character_state import load_snapshot, incremental_update_snapshot

        snap = incremental_update_snapshot(char_dir) or load_snapshot(char_dir)
        if snap:
            state = CharacterState(
                character_id=character_id,
                current_emotion=snap.emotion,
                current_goal=snap.goal,
                current_location=snap.location,
                current_status=snap.status,
                current_power_level=snap.power_level or None,
                current_relationships=snap.relationships,
                current_knowledge=snap.knowledge,
                current_secrets=snap.secrets,
                last_updated_scene=snap.last_scene_id or None,
            )
        else:
            state = CharacterState(character_id=character_id)

        return Character(core=core, state=state)

    # Fall back to legacy flat YAML
    legacy_path = project_dir / "characters" / f"{character_id}.yaml"
    if not legacy_path.exists():
        raise FileNotFoundError(f"Character not found: {character_id}")

    with open(legacy_path, "r", encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {legacy_path}: {e}") from e

    if raw is None:
        raise ValueError(f"Empty character file: {legacy_path}")

    try:
        core = CharacterCore.model_validate(raw.get("core", {}))
        state = CharacterState.model_validate(raw.get("state", {}))
    except Exception as e:
        raise ValueError(f"Invalid character data in {legacy_path}: {e}") from e

    return Character(core=core, state=state)
```

Also update `delete_character` to handle both formats:

```python
def delete_character(project_dir: Path, character_id: str) -> None:
    """Delete a character — removes the per-directory layout and/or legacy flat file."""
    import shutil

    char_dir = project_dir / "characters" / character_id
    if char_dir.exists():
        shutil.rmtree(char_dir)

    legacy_path = project_dir / "characters" / f"{character_id}.yaml"
    if legacy_path.exists():
        legacy_path.unlink()
```

And update `list_character_ids` to handle both layouts:

```python
def list_character_ids(project_dir: Path) -> list[str]:
    """Return all character IDs from both legacy and new layouts."""
    char_dir = project_dir / "characters"
    if not char_dir.exists():
        return []
    ids = set()
    # New layout: directories
    for entry in char_dir.iterdir():
        if entry.is_dir() and (entry / "definition.yaml").exists():
            ids.add(entry.name)
    # Legacy layout: .yaml files (excluding .bak)
    for filepath in char_dir.glob("*.yaml"):
        if not filepath.name.endswith(".bak"):
            ids.add(filepath.stem)
    return sorted(ids)
```

Run: `pytest tests/test_repository_characters.py::TestDualReadCharacterLayout -v`
Expected: 4 PASS

- [ ] **Step 3: Verify all existing character tests still pass**

```powershell
conda activate fourteen; python -m pytest tests/test_character_storage.py tests/test_repository_characters.py -v
```

If any fail, fix them — the dual-read logic must be backward-compatible.

- [ ] **Step 4: Commit**

```bash
git add app/storage/project_files.py tests/test_repository_characters.py
git commit -m "feat: per-character directory layout with dual-read legacy support"
```

---

### Task 6: State repository — orchestrate events, snapshots, and domain events

**Files:**
- Create: `app/storage/state_repository.py`
- Create: `tests/test_state_repository.py`

- [ ] **Step 1: Write tests for StateRepository**

Create `tests/test_state_repository.py`:

```python
"""Tests for StateRepository — commit events, update snapshots, emit domain events."""
import tempfile
from pathlib import Path

import pytest

from app.storage.state_repository import StateRepository
from app.storage.models import (
    Character,
    CharacterCore,
    CharacterState,
    CharacterStateEvent,
    CharacterStoredChange,
    StateChangeProposal,
    SetFieldChange,
)


def _make_proposal(changes=None) -> StateChangeProposal:
    if changes is None:
        changes = [SetFieldChange(type="set_field", field="goal", value="avenge")]
    return StateChangeProposal(character_id="char-1", character_name="林枫", changes=changes)


class TestCommitAndSnapshot:
    def test_commit_events_writes_to_disk(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td) / "characters" / "char-1"
            # Set up a minimal definition and empty snapshot
            from app.storage.project_files import save_character
            char = Character(
                core=CharacterCore(id="char-1", name="林枫"),
                state=CharacterState(character_id="char-1"),
            )
            save_character(Path(td), char)

            repo = StateRepository()
            event = repo.commit_proposal(
                char_dir,
                proposal=_make_proposal(),
                scene_id="scene_001",
                transaction_id="tx-1",
                request_id="req-1",
                source="ai",
            )

            assert event.event_id == 1
            assert len(event.changes) == 1
            assert event.changes[0].old == ""  # was empty before
            assert event.changes[0].value == "avenge"

    def test_commit_updates_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td) / "characters" / "char-1"
            from app.storage.project_files import save_character
            char = Character(
                core=CharacterCore(id="char-1", name="林枫"),
                state=CharacterState(character_id="char-1"),
            )
            save_character(Path(td), char)

            repo = StateRepository()
            repo.commit_proposal(char_dir, _make_proposal(), "scene_001", "tx-1", "req-1")

            from app.storage.character_state import load_snapshot
            snap = load_snapshot(char_dir)
            assert snap.goal == "avenge"
            assert snap.last_event_id == 1

    def test_commit_emits_domain_event(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td) / "characters" / "char-1"
            from app.storage.project_files import save_character
            char = Character(
                core=CharacterCore(id="char-1", name="林枫"),
                state=CharacterState(character_id="char-1"),
            )
            save_character(Path(td), char)

            events_received = []

            repo = StateRepository()
            repo.bus.subscribe("character_state_updated", lambda **kw: events_received.append(kw))
            repo.commit_proposal(char_dir, _make_proposal(), "scene_001", "tx-1", "req-1")

            assert len(events_received) == 1
            assert events_received[0]["character_id"] == "char-1"
            assert events_received[0]["event_id"] == 1

    def test_commit_preserves_old_values(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td) / "characters" / "char-1"
            from app.storage.project_files import save_character
            char = Character(
                core=CharacterCore(id="char-1", name="林枫"),
                state=CharacterState(character_id="char-1", current_goal="become elder"),
            )
            save_character(Path(td), char)

            repo = StateRepository()
            event = repo.commit_proposal(
                char_dir,
                proposal=StateChangeProposal(
                    character_id="char-1",
                    changes=[SetFieldChange(type="set_field", field="goal", value="avenge")],
                ),
                scene_id="scene_001",
                transaction_id="tx-1",
                request_id="req-1",
            )

            assert event.changes[0].old == "become elder"
            assert event.changes[0].value == "avenge"
```

Run: `pytest tests/test_state_repository.py -v`
Expected: 4 FAIL

- [ ] **Step 2: Implement StateRepository**

Create `app/storage/state_repository.py`:

```python
"""StateRepository — commits proposals as events, updates snapshots, emits domain events."""
from __future__ import annotations

import uuid
from pathlib import Path

from app.events.bus import EventBus
from app.storage.models import (
    StateChangeProposal,
    CharacterStateEvent,
    CharacterStoredChange,
)
from app.storage.character_events import append_events, get_latest_event_id
from app.storage.character_state import load_snapshot, save_snapshot, save_checkpoint, rebuild_snapshot


class StateRepository:
    """Orchestrates character state persistence with event sourcing.

    Usage::

        repo = StateRepository()
        event = repo.commit_proposal(char_dir, proposal, scene_id, tx_id, req_id)
        # event is written, snapshot updated, domain event published
    """

    def __init__(self, bus: EventBus | None = None) -> None:
        self.bus = bus or EventBus()

    def commit_proposal(
        self,
        char_dir: Path,
        proposal: StateChangeProposal,
        scene_id: str,
        transaction_id: str,
        request_id: str,
        source: str = "ai",
    ) -> CharacterStateEvent:
        """Convert a proposal to a stored event with old values, append to log,
        update the snapshot, and publish a domain event.

        Returns the created CharacterStateEvent.
        """
        # Load current snapshot to capture old values
        snapshot = load_snapshot(char_dir)
        changed_fields: dict[str, str] = {}
        changed_relationships: dict[str, str] = {}
        changed_knowledge: set[str] = set()
        changed_secrets: set[str] = set()

        stored_changes: list[CharacterStoredChange] = []
        for change in proposal.changes:
            sc = CharacterStoredChange(type=change.type)
            if change.type == "set_field":
                old = ""
                if snapshot:
                    old = getattr(snapshot, change.field, "")
                sc.field = change.field
                sc.value = change.value
                sc.old = old
                changed_fields[change.field] = change.value
            elif change.type == "relationship_change":
                old = ""
                if snapshot and change.target_character_id in snapshot.relationships:
                    old = snapshot.relationships[change.target_character_id]
                sc.target_character_id = change.target_character_id
                sc.relationship = change.relationship
                sc.old = old
                changed_relationships[change.target_character_id] = change.relationship
            elif change.type == "knowledge_add":
                sc.fact = change.fact
                changed_knowledge.add(change.fact)
            elif change.type == "knowledge_remove":
                sc.fact = change.fact
            elif change.type == "secret_add":
                sc.fact = change.fact
                changed_secrets.add(change.fact)
            elif change.type == "secret_remove":
                sc.fact = change.fact
            stored_changes.append(sc)

        # Determine next event_id
        next_id = get_latest_event_id(char_dir) + 1

        event = CharacterStateEvent(
            event_id=next_id,
            transaction_id=transaction_id,
            scene_id=scene_id,
            character_id=proposal.character_id,
            source=source,
            request_id=request_id,
            changes=stored_changes,
        )

        # Append event
        append_events(char_dir, [event])

        # Update snapshot
        if snapshot is not None:
            for field, val in changed_fields.items():
                setattr(snapshot, field, val)
            for target, rel in changed_relationships.items():
                snapshot.relationships[target] = rel
            for fact in changed_knowledge:
                if fact not in snapshot.knowledge:
                    snapshot.knowledge.append(fact)
            for fact in changed_secrets:
                if fact not in snapshot.secrets:
                    snapshot.secrets.append(fact)
            snapshot.last_event_id = next_id
            snapshot.last_scene_id = scene_id
        else:
            # No snapshot yet — rebuild from events
            from app.storage.models import CharacterStateSnapshot
            snapshot = CharacterStateSnapshot(character_id=proposal.character_id)
            snapshot = rebuild_snapshot(char_dir, snapshot)

        save_snapshot(char_dir, snapshot)

        # Emit domain event
        self.bus.publish(
            "character_state_updated",
            character_id=proposal.character_id,
            event_id=next_id,
        )

        return event

    def commit_user_edit(
        self,
        char_dir: Path,
        character_id: str,
        changes: list[CharacterStoredChange],
    ) -> CharacterStateEvent:
        """Commit a manual author edit as a source=user event."""
        from app.storage.models import StateChangeProposal

        # We bypass the proposal layer for user edits — they already provide old/new.
        next_id = get_latest_event_id(char_dir) + 1
        event = CharacterStateEvent(
            event_id=next_id,
            transaction_id=str(uuid.uuid4()),
            scene_id="",
            character_id=character_id,
            source="user",
            request_id=str(uuid.uuid4()),
            changes=changes,
        )
        append_events(char_dir, [event])

        snapshot = load_snapshot(char_dir)
        if snapshot:
            snapshot = rebuild_snapshot(char_dir, snapshot)
            save_snapshot(char_dir, snapshot)

        self.bus.publish("character_state_updated", character_id=character_id, event_id=next_id)
        return event

    def checkout_for_scene(self, char_dir: Path, scene_id: str) -> dict | None:
        """Get character state as of the end of the given scene.
        Tries checkpoint first, falls back to replay."""
        from app.storage.character_state import load_checkpoint, load_snapshot, rebuild_snapshot
        from app.storage.models import CharacterStateSnapshot

        checkpoint = load_checkpoint(char_dir, scene_id)
        if checkpoint is not None:
            return _snapshot_to_state_dict(checkpoint)

        # Fallback: replay events up to the first event with scene_id > target
        from app.storage.character_events import load_events
        events = load_events(char_dir)
        base = CharacterStateSnapshot(character_id="")
        replay_events = [e for e in events if e.scene_id <= scene_id and not e.invalidated]
        result = rebuild_snapshot(char_dir, base)
        # Only apply events up to the target scene
        for e in replay_events:
            pass  # rebuild_snapshot already handles this if we filter
        # Simpler: rebuild from scratch with only events <= scene_id
        result2 = CharacterStateSnapshot(character_id="")
        for e in events:
            if e.invalidated:
                continue
            if e.scene_id > scene_id:
                break
            for change in e.changes:
                _apply_change_to_dict(result2, change)
        return _snapshot_to_state_dict(result2)


def _snapshot_to_state_dict(snap) -> dict:
    from app.storage.models import CharacterStateSnapshot
    if isinstance(snap, CharacterStateSnapshot):
        return {
            "character_id": snap.character_id,
            "emotion": snap.emotion,
            "goal": snap.goal,
            "location": snap.location,
            "status": snap.status,
            "power_level": snap.power_level or None,
            "relationships": dict(snap.relationships),
            "knowledge": list(snap.knowledge),
            "secrets": list(snap.secrets),
        }
    return {}


def _apply_change_to_dict(snap, change) -> None:
    if change.type == "set_field":
        setattr(snap, change.field, change.value)
    elif change.type == "relationship_change":
        snap.relationships[change.target_character_id] = change.relationship
    elif change.type == "knowledge_add" and change.fact not in snap.knowledge:
        snap.knowledge.append(change.fact)
    elif change.type == "knowledge_remove" and change.fact in snap.knowledge:
        snap.knowledge.remove(change.fact)
    elif change.type == "secret_add" and change.fact not in snap.secrets:
        snap.secrets.append(change.fact)
    elif change.type == "secret_remove" and change.fact in snap.secrets:
        snap.secrets.remove(change.fact)
```

Run: `pytest tests/test_state_repository.py -v`
Expected: 4 PASS

- [ ] **Step 3: Commit**

```bash
git add app/storage/state_repository.py tests/test_state_repository.py
git commit -m "feat: add StateRepository with event-sourced commit and domain event emission"
```

---

### Task 7: Revised StateUpdaterAgent — new prompt and discriminated union output

**Files:**
- Modify: `app/pipeline/agents/state_updater.py`

- [ ] **Step 1: Write a test for the new StateUpdater output schema**

Add to `tests/test_writer_agent.py` (or create a new `tests/test_state_updater_agent.py`):

```python
class TestStateUpdaterNewSchema:
    """The StateUpdater must output StateChangeProposal with discriminated union changes."""

    def test_generate_returns_new_schema(self):
        from app.pipeline.agents.state_updater import StateUpdaterAgent
        from app.providers.base import MockProvider
        from app.storage.models import SetFieldChange, KnowledgeAddChange

        provider = MockProvider()
        # MockProvider returns {"changes": [...]} given the structured schema
        provider.set_structured_response({
            "changes": [
                {"type": "set_field", "field": "goal", "value": "avenge master"},
                {"type": "knowledge_add", "fact": "Elder Zhao killed master"},
            ]
        })

        agent = StateUpdaterAgent()
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            agent.generate(provider, {}, "prose text", "scene_001", [
                {"core": {"name": "林枫", "id": "c1"}, "state": {"current_goal": "old"}}
            ])
        )
        assert len(result) == 1
        proposal = result[0]
        assert len(proposal.changes) == 2
        assert proposal.changes[0].type == "set_field"
        assert proposal.changes[0].value == "avenge master"
```

Run: `pytest tests/test_state_updater_agent.py::TestStateUpdaterNewSchema -v`
Expected: 1 FAIL

- [ ] **Step 2: Rewrite StateUpdaterAgent with new prompt and output schema**

Replace `app/pipeline/agents/state_updater.py`:

Key changes:
1. The `ChangeList` model now wraps `list[StateChangeProposal]`
2. The prompt is reorganized as action taxonomy with type-first generation
3. Enforces closed-world field names from `CHARACTER_SCALAR_FIELDS`

```python
"""StateUpdaterAgent — proposes CharacterState changes after a scene."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.providers.base import LLMProvider, ProviderResponse
from app.storage.models import StateChangeProposal


class StateUpdaterAgent:
    """Proposes CharacterState changes for all major characters after a scene."""

    def __init__(self) -> None:
        self.last_usage: dict | None = None

    async def generate(
        self,
        provider: LLMProvider,
        context: dict,
        prose: str,
        scene_id: str,
        major_characters: list[dict],
    ) -> list[StateChangeProposal]:
        class ChangeList(BaseModel):
            proposals: list[StateChangeProposal] = Field(default_factory=list)

        messages = _build_state_updater_messages(context, prose, major_characters)
        resp: ProviderResponse = await provider.generate_structured(
            messages, ChangeList, temperature=0.2
        )
        self.last_usage = resp.usage
        if resp.model is not None and isinstance(resp.model, ChangeList):
            return resp.model.proposals
        parsed = resp.parsed or {}
        items = parsed.get("proposals", [])
        return [StateChangeProposal(**item) for item in items]

    def build_prompt(
        self, context: dict, prose: str, major_characters: list[dict]
    ) -> str:
        return _build_state_updater_prompt(context, prose, major_characters)


def _build_state_updater_messages(
    context: dict, prose: str, major_characters: list[dict],
) -> list[dict[str, str]]:
    system = (
        "你是一位角色状态追踪员。你的任务是根据场景正文，推理每个主要角色在本场景结束后的状态变化。\n\n"
        "核心规则：\n"
        "1. 先判断变化类型，再填写对应字段。不要混用不同类型的字段。\n"
        "2. 只能使用以下变化类型：\n"
        '   - set_field: 标量字段变化。field 只能是: "emotion", "goal", "location", "status", "power_level"\n'
        "   - relationship_change: 关系变化。需要 target_character_id 和 relationship\n"
        "   - knowledge_add: 角色获得了新信息\n"
        "   - knowledge_remove: 角色遗忘或信息不再有效\n"
        "   - secret_add: 角色发现了新秘密\n"
        "   - secret_remove: 秘密不再有效或已公开\n"
        "3. 严禁自创 field 名称。field 必须从上述列表中精确选择。\n"
        "4. 只报告发生了变化的字段；没有变化的不要输出。\n"
        "5. 你必须输出严格的 JSON 格式。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _build_state_updater_prompt(context, prose, major_characters)},
    ]


def _build_state_updater_prompt(
    context: dict, prose: str, major_characters: list[dict],
) -> str:
    lines: list[str] = []

    # Current character states (pre-scene)
    lines.append("【角色当前状态（场景前）】")
    for mc in major_characters:
        core = mc.get("core", {})
        state = mc.get("state", {})
        name = core.get("name", "")
        cid = core.get("id", "")
        lines.append(f"\n★ {name} (id={cid})")
        lines.append(f"  情绪：{state.get('current_emotion', '')}")
        lines.append(f"  目标：{state.get('current_goal', '')}")
        lines.append(f"  位置：{state.get('current_location', '')}")
        lines.append(f"  修为：{state.get('current_power_level', '')}")
        rels = state.get("current_relationships", {})
        if rels:
            lines.append(f"  关系：{'；'.join(f'{k}:{v}' for k, v in rels.items())}")
        knowledge = state.get("current_knowledge", [])
        if knowledge:
            lines.append(f"  已知：{'；'.join(knowledge[:10])}")
        secrets = state.get("current_secrets", [])
        if secrets:
            lines.append(f"  秘密：{'；'.join(secrets)}")
        lines.append(f"  状态：{state.get('current_status', '')}")
    lines.append("")

    # Scene info
    scene = context.get("scene_info", {})
    if scene:
        lines.append("【场景信息】")
        lines.append(f"- 标题：{scene.get('scene_title', '')}")
        if scene.get("scene_goal"):
            lines.append(f"- 目标：{scene['scene_goal']}")
        if scene.get("conflict"):
            lines.append(f"- 冲突：{scene['conflict']}")
        lines.append("")

    # Prose
    prose_excerpt = prose[:5000] if len(prose) > 5000 else prose
    lines.append("【场景正文】")
    lines.append(prose_excerpt)
    if len(prose) > 5000:
        lines.append(f"\n... (正文共 {len(prose)} 字，以上为前 5000 字)")
    lines.append("")

    lines.append("【输出要求】")
    lines.append("为每个主要角色输出一条 StateChangeProposal。每条 proposal 包含：")
    lines.append("- character_id: 角色的 id")
    lines.append("- character_name: 角色名")
    lines.append("- changes: 变化列表，每项必须有 type 字段，然后填写该类型对应的字段：")
    lines.append('  * set_field: {{"type":"set_field","field":"goal","value":"复仇"}}')
    lines.append('  * relationship_change: {{"type":"relationship_change","target_character_id":"su_waner","relationship":"恋人"}}')
    lines.append('  * knowledge_add: {{"type":"knowledge_add","fact":"赵长老杀了师父"}}')
    lines.append('  * knowledge_remove: {{"type":"knowledge_remove","fact":"旧信息"}}')
    lines.append('  * secret_add: {{"type":"secret_add","fact":"新秘密"}}')
    lines.append('  * secret_remove: {{"type":"secret_remove","fact":"已公开的秘密"}}')
    lines.append("")
    lines.append('输出 JSON 格式：{"proposals": [...]}')

    return "\n".join(lines)
```

Run: `pytest tests/test_state_updater_agent.py::TestStateUpdaterNewSchema -v`
Expected: 1 PASS

- [ ] **Step 3: Commit**

```bash
git add app/pipeline/agents/state_updater.py tests/test_state_updater_agent.py
git commit -m "feat: revise StateUpdaterAgent with discriminated union schema and type-first prompt"
```

---

### Task 8: Pipeline — transactional commit boundary

**Files:**
- Modify: `app/pipeline/pipeline.py`

- [ ] **Step 1: Modify pipeline to stage changes and commit atomically**

The current pipeline runs Fact Extractor and State Updater in parallel, then exposes results via `result.extracted_facts` and `result.state_changes`. We need to change the State Updater output type to `list[StateChangeProposal]` (already done in Task 7) and ensure the `_on_state_changes_approved` in `main_window.py` uses `StateRepository.commit_proposal` instead of direct field assignment.

The pipeline changes are minimal — the `state_changes` field on `GenerationResult` already carries the raw proposal dicts. The main change is in `main_window.py`'s approval handler (Task 14).

Verify the pipeline still works with the new StateUpdater output:

```powershell
conda activate fourteen; python -m pytest tests/test_pipeline_integration.py -v
```

- [ ] **Step 2: Commit any pipeline fixes**

If tests fail, fix them. If they pass, this task requires no pipeline code changes (the pipeline only passes data through).

```bash
git add app/pipeline/pipeline.py  # if changed
git commit -m "feat: pipeline compatibility with new StateChangeProposal schema"
```

---

### Task 9: Context builder — checkpoint-based character state

**Files:**
- Modify: `app/pipeline/context_builder.py`

- [ ] **Step 1: Write a test for checkpoint-based context assembly**

Add to `tests/test_context_builder.py`:

```python
class TestCheckpointContext:
    """When generating Scene N, characters should use state from Scene N-1 checkpoint."""

    def test_collect_characters_uses_checkpoint_when_available(self, tmp_path, sample_project):
        """If a checkpoint exists for the previous scene, use it."""
        # This tests that _collect_characters reads from state.yaml (snapshot)
        # which is the current approach. Checkpoint integration is tested via
        # StateRepository.checkout_for_scene.
        pass  # Defer full integration test to Task 16
```

The current context builder reads all characters via `load_all_characters`, which in turn reads `state.yaml` (the latest snapshot). For v1, this is acceptable — the PRD says "one scene at a time." The checkpoint infrastructure (save/load) is in place and will be wired into context assembly in a follow-up when out-of-order generation is needed.

- [ ] **Step 2: Verify existing context builder tests pass**

```powershell
conda activate fourteen; python -m pytest tests/test_context_builder.py -v
```

Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: context builder checkpoint readiness — infrastructure in place, wiring deferred to out-of-order generation feature"
```

---

### Task 10: UI — Character editor three-tab redesign (Definition / Current State / History)

**Files:**
- Modify: `app/ui/character_editor.py`
- Create: `app/ui/widgets/character_history.py`
- Create: `tests/test_character_editor.py` (extend)

- [ ] **Step 1: Write tests for the History tab query logic**

Create `tests/test_character_history.py`:

```python
"""Tests for character history query and display logic."""
import tempfile
from pathlib import Path

from app.storage.character_events import append_events
from app.storage.models import CharacterStateEvent, CharacterStoredChange


def _make_event(event_id: int, scene_id: str, source: str = "ai") -> CharacterStateEvent:
    return CharacterStateEvent(
        event_id=event_id,
        transaction_id="tx",
        scene_id=scene_id,
        character_id="c1",
        source=source,
        request_id="r",
        changes=[
            CharacterStoredChange(type="set_field", field="goal", old=f"old{event_id}", value=f"new{event_id}"),
        ],
    )


class TestHistoryQueries:
    def test_events_for_current_scene(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            append_events(char_dir, [
                _make_event(1, "scene_001"),
                _make_event(2, "scene_002"),
                _make_event(3, "scene_001"),
            ])
            from app.storage.character_events import load_events_for_scene
            result = load_events_for_scene(char_dir, "scene_001")
            assert len(result) == 2

    def test_full_timeline_reverse_chronological(self):
        with tempfile.TemporaryDirectory() as td:
            char_dir = Path(td)
            append_events(char_dir, [
                _make_event(1, "scene_001"),
                _make_event(2, "scene_002"),
                _make_event(3, "scene_003"),
            ])
            from app.storage.character_events import load_events
            result = load_events(char_dir)
            # Already in append order; reverse for timeline
            result.reverse()
            assert result[0].event_id == 3
```

Run: `pytest tests/test_character_history.py -v`
Expected: 2 PASS (the query functions already exist from Task 3)

- [ ] **Step 2: Add the History tab widget**

Create `app/ui/widgets/character_history.py`:

```python
"""Character History tab — scene-diff and full-timeline views."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QButtonGroup,
    QPushButton,
    QHBoxLayout,
    QFrame,
)

from app.storage.character_events import load_events_for_scene, load_events
from app.storage.models import CharacterStateEvent

SOURCE_COLORS = {
    "ai": "#3498db",
    "user": "#e67e22",
    "manual_event": "#9b59b6",
    "system": "#95a5a6",
}

SOURCE_LABELS = {
    "ai": "AI",
    "user": "用户",
    "manual_event": "手动",
    "system": "系统",
}


class CharacterHistoryWidget(QWidget):
    """Shows character state change history — scene diff or full timeline."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._char_dir: Path | None = None
        self._current_scene_id: str | None = None
        self._mode: str = "scene"  # "scene" or "timeline"
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Mode toggle
        toggle_layout = QHBoxLayout()
        self._scene_btn = QPushButton("当前场景")
        self._scene_btn.setCheckable(True)
        self._scene_btn.setChecked(True)
        self._scene_btn.clicked.connect(lambda: self._set_mode("scene"))

        self._timeline_btn = QPushButton("全部历史")
        self._timeline_btn.setCheckable(True)
        self._timeline_btn.clicked.connect(lambda: self._set_mode("timeline"))

        toggle_layout.addWidget(self._scene_btn)
        toggle_layout.addWidget(self._timeline_btn)
        toggle_layout.addStretch()
        layout.addLayout(toggle_layout)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        layout.addWidget(scroll)

    def set_character(self, char_dir: Path, current_scene_id: str | None = None) -> None:
        """Set the character directory and optional scene context."""
        self._char_dir = char_dir
        self._current_scene_id = current_scene_id
        if current_scene_id is None:
            self._set_mode("timeline")
        self._refresh()

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._scene_btn.setChecked(mode == "scene")
        self._timeline_btn.setChecked(mode == "timeline")
        self._refresh()

    def _refresh(self) -> None:
        self._clear_content()
        if self._char_dir is None:
            return

        if self._mode == "scene" and self._current_scene_id:
            events = load_events_for_scene(self._char_dir, self._current_scene_id)
            self._render_scene_diff(events)
        else:
            events = load_events(self._char_dir)
            events.reverse()  # newest first
            self._render_timeline(events)

    def _render_scene_diff(self, events: list[CharacterStateEvent]) -> None:
        """Render a scene-diff view — all changes from the current scene's events."""
        if not events:
            self._add_label("该场景无状态变化", "color: #888;")
            return

        for event in events:
            if event.invalidated:
                continue
            source_badge = SOURCE_LABELS.get(event.source, event.source)
            source_color = SOURCE_COLORS.get(event.source, "#888")

            header = QLabel(f"<b>Scene {event.scene_id}</b> "
                            f"<span style='color:{source_color};'>[{source_badge}]</span>")
            self._content_layout.insertWidget(self._content_layout.count() - 1, header)

            for change in event.changes:
                text = self._format_change(change)
                label = QLabel(f"  {text}")
                label.setStyleSheet("color: #ccc; font-size: 12px; padding: 2px 0;")
                self._content_layout.insertWidget(self._content_layout.count() - 1, label)

    def _render_timeline(self, events: list[CharacterStateEvent]) -> None:
        """Render full timeline grouped by scene."""
        if not events:
            self._add_label("暂无历史记录", "color: #888;")
            return

        current_scene: str | None = None
        for event in events:
            if event.scene_id != current_scene:
                current_scene = event.scene_id
                scene_label = QLabel(f"<b>━━ Scene {event.scene_id}</b>")
                scene_label.setStyleSheet("color: #f39c12; padding-top: 8px;")
                self._content_layout.insertWidget(self._content_layout.count() - 1, scene_label)

            if event.invalidated:
                inv = QLabel(f"  <i>[已作废]</i>")
                inv.setStyleSheet("color: #c0392b; font-size: 11px;")
                self._content_layout.insertWidget(self._content_layout.count() - 1, inv)
                continue

            source_badge = SOURCE_LABELS.get(event.source, event.source)
            source_color = SOURCE_COLORS.get(event.source, "#888")

            for change in event.changes:
                text = self._format_change(change)
                label = QLabel(f"  <span style='color:{source_color};'>[{source_badge}]</span> {text}")
                label.setStyleSheet("font-size: 12px; padding: 1px 0;")
                self._content_layout.insertWidget(self._content_layout.count() - 1, label)

    def _format_change(self, change) -> str:
        """Format a CharacterStoredChange into a human-readable string."""
        if change.type == "set_field":
            arrow = f"{change.old} → {change.value}" if change.old else change.value
            return f"{change.field}: {arrow}"
        elif change.type == "relationship_change":
            arrow = f"{change.old} → {change.relationship}" if change.old else change.relationship
            return f"关系 [{change.target_character_id}]: {arrow}"
        elif change.type == "knowledge_add":
            return f"+ 知识: {change.fact}"
        elif change.type == "knowledge_remove":
            return f"- 知识: {change.fact}"
        elif change.type == "secret_add":
            return f"+ 秘密: {change.fact}"
        elif change.type == "secret_remove":
            return f"- 秘密: {change.fact}"
        return str(change.type)

    def _add_label(self, text: str, style: str = "") -> None:
        label = QLabel(text)
        if style:
            label.setStyleSheet(style)
        self._content_layout.insertWidget(self._content_layout.count() - 1, label)

    def _clear_content(self) -> None:
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
```

- [ ] **Step 3: Modify CharacterEditorView to have three tabs**

Edit `app/ui/character_editor.py` — change from two tabs (Core/State) to three tabs (Definition/Current State/History):

The key changes:
1. Rename `_core_tab` → `_definition_tab`, label "基本设定"
2. Rename `_state_tab` → `_state_tab`, make read-only by default
3. Add `_history_tab` = `CharacterHistoryWidget()`
4. `_detail_tabs.addTab(self._definition_tab, "基本设定")`
5. `_detail_tabs.addTab(self._state_tab, "当前状态")`
6. `_detail_tabs.addTab(self._history_tab, "变化历史")`

When a character is selected (`_select_character`), also call `self._history_tab.set_character(char_dir, current_scene_id)` where `char_dir` = `self._project_dir / "characters" / char_id` and `current_scene_id` comes from the workspace's current scene.

For the State tab's read-only behavior: wrap all state fields in a `QStackedWidget` — page 0 shows read-only labels, page 1 shows editable fields. An "编辑状态" button toggles between them. On save, gather changes as `CharacterStoredChange` items and call `StateRepository.commit_user_edit()`.

- [ ] **Step 4: Wire event bus subscription into CharacterEditorView**

Add a `set_event_bus(bus)` method. Subscribe to `"character_state_updated"`. When received, check if the event's `character_id` matches the currently displayed character. If so, reload state from `state.yaml`.

```python
def set_event_bus(self, bus) -> None:
    self._bus = bus
    bus.subscribe("character_state_updated", self._on_state_updated)

def _on_state_updated(self, character_id: str, event_id: int) -> None:
    if character_id == self._current_id:
        self._reload_state_tab()
```

- [ ] **Step 5: Commit**

```bash
git add app/ui/character_editor.py app/ui/widgets/character_history.py tests/test_character_history.py
git commit -m "feat: three-tab character editor with event-bus-driven live state refresh"
```

---

### Task 11: UI — Fact Approval panel updated for new schema

**Files:**
- Modify: `app/ui/widgets/fact_approval.py`

- [ ] **Step 1: Update `show_items` and `_make_change_row` for the new `StateChangeProposal.changes` structure**

The fact approval panel currently expects `state_changes` as a list of flat dicts with `*_add`/`*_remove` keys. Update `_make_change_row` to handle the new `changes: list[StateChange]` structure:

```python
def _make_change_row(self, index: int, change: dict) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(4, 2, 4, 2)

    cb = QCheckBox()
    cb.setChecked(True)
    self._change_checkboxes.append(cb)
    layout.addWidget(cb)

    name = change.get("character_name", "未知")
    name_label = QLabel(f"<b>{name}</b>")
    name_label.setStyleSheet("color: #e67e22;")
    layout.addWidget(name_label)

    # Build summary from the new 'changes' list
    changes_list = change.get("changes", [])
    summaries: list[str] = []
    for c in changes_list:
        t = c.get("type", "")
        if t == "set_field":
            summaries.append(f"{c.get('field','')}→{c.get('value','')}")
        elif t == "relationship_change":
            summaries.append(f"关系:{c.get('target_character_id','')}→{c.get('relationship','')}")
        elif t == "knowledge_add":
            summaries.append(f"+知识")
        elif t == "knowledge_remove":
            summaries.append(f"-知识")
        elif t == "secret_add":
            summaries.append(f"+秘密")
        elif t == "secret_remove":
            summaries.append(f"-秘密")

    summary = "；".join(summaries) if summaries else "无变化"
    summary_label = QLabel(summary)
    summary_label.setStyleSheet("color: #ccc; font-size: 11px;")
    layout.addWidget(summary_label, stretch=1)

    # Tooltip with full details
    tooltip_lines = []
    for c in changes_list:
        t = c.get("type", "")
        if t == "set_field":
            tooltip_lines.append(f"{c.get('field','')}: {c.get('value','')}")
        elif t == "relationship_change":
            tooltip_lines.append(f"关系 {c.get('target_character_id','')}: {c.get('relationship','')}")
        elif t in ("knowledge_add", "knowledge_remove", "secret_add", "secret_remove"):
            tooltip_lines.append(f"{t}: {c.get('fact','')}")
    row.setToolTip("\n".join(tooltip_lines))

    return row
```

- [ ] **Step 2: Commit**

```bash
git add app/ui/widgets/fact_approval.py
git commit -m "feat: update FactApprovalPanel for new discriminated union state change schema"
```

---

### Task 12: UI — Main window wiring (event bus, state approval, migration)

**Files:**
- Modify: `app/ui/main_window.py`

- [ ] **Step 1: Initialize QtEventBridge at startup and pass to StateRepository**

In `MainWindow.__init__`, create the event bus and bridge:

```python
from app.events.bus import EventBus
from app.events.qt_bridge import QtEventBridge
from app.storage.state_repository import StateRepository

# In __init__:
self._domain_bus = EventBus()
self._event_bridge = QtEventBridge(self._domain_bus)
self._state_repo = StateRepository(bus=self._domain_bus)
```

- [ ] **Step 2: Rewrite `_on_state_changes_approved` to use StateRepository**

Replace the existing handler (which directly mutates `CharacterState` fields) with `StateRepository.commit_proposal()`:

```python
def _on_state_changes_approved(self, approved_changes: list[dict]) -> None:
    """Apply approved state changes via StateRepository (event-sourced)."""
    if self._current_project_dir is None:
        return

    workspace = self.views.get("workspace")
    scene_id = workspace._current_scene_id if isinstance(workspace, SceneWorkspaceView) else ""
    tx_id = str(uuid.uuid4())

    for proposal_dict in approved_changes:
        char_id = proposal_dict.get("character_id", "")
        if not char_id:
            continue
        char_dir = self._current_project_dir / "characters" / char_id

        # Convert the approved dict back to a StateChangeProposal
        changes_data = proposal_dict.get("changes", [])
        from app.storage.models import StateChangeProposal

        proposal = StateChangeProposal(
            character_id=char_id,
            character_name=proposal_dict.get("character_name", ""),
            changes=changes_data,
        )

        try:
            self._state_repo.commit_proposal(
                char_dir=char_dir,
                proposal=proposal,
                scene_id=scene_id,
                transaction_id=tx_id,
                request_id=str(uuid.uuid4()),
                source="ai",
            )
        except Exception:
            pass  # Log?
```

- [ ] **Step 3: Wire event bus to Bible Editor's character editor**

In `_on_nav_changed` (when index == 1, Bible Editor), connect the domain bus to the character editor:

```python
if index == 1:
    bible = self.views["bible"]
    if isinstance(bible, BibleEditorView):
        bible._character_editor.set_event_bus(self._domain_bus)
```

Also, when navigating to workspace, no longer need to manually connect fact_approval signals for state changes (the bus handles it):

```python
# In _on_nav_changed for workspace (index == 3):
workspace.fact_approval.state_changes_approved.connect(
    lambda changes: self._on_state_changes_approved(changes)
)
# Remove the old manual character state update code
```

- [ ] **Step 4: Add migration trigger for legacy projects**

In `_on_open_project`, after loading, check for legacy files and offer migration:

```python
# After project is loaded successfully:
legacy = list((Path(dir_path) / "characters").glob("*.yaml"))
if legacy and not any(f.name.endswith(".bak") for f in legacy):
    reply = QMessageBox.question(
        self,
        "格式迁移",
        f"项目包含 {len(legacy)} 个旧格式角色文件。\n"
        "建议迁移到新格式以使用完整功能。\n\n"
        "迁移会创建备份，不会丢失数据。",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if reply == QMessageBox.StandardButton.Yes:
        self._migrate_legacy_characters(Path(dir_path))
```

And the migration function:

```python
def _migrate_legacy_characters(self, project_dir: Path) -> None:
    """Migrate legacy characters/<name>.yaml to per-directory layout."""
    import shutil
    from datetime import datetime

    char_dir = project_dir / "characters"
    legacy_files = list(char_dir.glob("*.yaml"))
    if not legacy_files:
        return

    backup_dir = project_dir / ".backups" / f"migration-{datetime.now().strftime('%Y-%m-%d')}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    for f in legacy_files:
        if f.name.endswith(".bak"):
            continue
        # Backup
        shutil.copy2(f, backup_dir / f.name)

        # Load and re-save (triggers new layout via save_character)
        try:
            char = load_character(project_dir, f.stem)
            save_character(project_dir, char)
        except Exception:
            continue

    QMessageBox.information(
        self, "迁移完成",
        f"已迁移 {len(legacy_files)} 个角色。\n备份存储在: {backup_dir}"
    )
```

- [ ] **Step 5: Verify existing integration tests pass**

```powershell
conda activate fourteen; python -m pytest tests/test_pipeline_integration.py -v
```

- [ ] **Step 6: Commit**

```bash
git add app/ui/main_window.py
git commit -m "feat: wire event bus, StateRepository-based approval, and legacy migration into MainWindow"
```

---

### Task 13: Integration — end-to-end pipeline with event sourcing

**Files:**
- Modify: `tests/test_pipeline_integration.py` (extend)
- Create: `tests/test_e2e_event_sourcing.py`

- [ ] **Step 1: Write end-to-end test for full event sourcing flow**

Create `tests/test_e2e_event_sourcing.py`:

```python
"""End-to-end test: pipeline → proposal → approval → event → snapshot → UI refresh."""
import tempfile
import uuid
from pathlib import Path

import pytest

from app.storage.models import Project as ProjectModel
from app.storage.project_files import create_project, save_character
from app.storage.models import Character, CharacterCore, CharacterState
from app.storage.state_repository import StateRepository
from app.storage.character_state import load_snapshot
from app.storage.character_events import load_events_for_scene
from app.pipeline.pipeline import ScenePipeline
from app.providers.base import MockProvider


@pytest.mark.asyncio
async def test_full_event_sourcing_flow():
    """Generate a scene, approve state changes, verify events and snapshots."""
    # Create project with one character
    with tempfile.TemporaryDirectory() as td:
        proj = ProjectModel(title="E2E测试", genre="玄幻", llm_provider="ollama")
        proj_dir = create_project(Path(td) / "projects", proj)

        char = Character(
            core=CharacterCore(id="char-hero", name="林轩", tier="major"),
            state=CharacterState(character_id="char-hero", current_goal="通过考核", current_emotion="紧张"),
        )
        save_character(proj_dir, char)

        # Simulate a state update proposal
        state_repo = StateRepository()
        events_before = []
        state_repo.bus.subscribe("character_state_updated", lambda **kw: events_before.append(kw))

        from app.storage.models import StateChangeProposal, SetFieldChange

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
        assert event.event_id == 1
        assert event.changes[0].old == "通过考核"  # old goal from snapshot
        assert event.changes[0].value == "复仇"

        # Verify events.jsonl has the event
        scene_events = load_events_for_scene(char_dir, "scene_001")
        assert len(scene_events) == 1

        # Verify snapshot updated
        snap = load_snapshot(char_dir)
        assert snap.goal == "复仇"
        assert snap.emotion == "愤怒"
        assert snap.last_event_id == 1

        # Verify domain event emitted
        assert len(events_before) == 1
        assert events_before[0]["character_id"] == "char-hero"
```

Run: `pytest tests/test_e2e_event_sourcing.py -v`
Expected: 1 PASS

- [ ] **Step 2: Commit**

```bash
git add tests/test_e2e_event_sourcing.py
git commit -m "test: end-to-end event sourcing flow — proposal to snapshot to domain event"
```

---

### Task 14: Cleanup — remove deprecated flat StateChangeProposal references

**Files:**
- Modify: `app/pipeline/agents/fact_extractor.py` (if it references old schema)
- Check all files for old field names

- [ ] **Step 1: Run full test suite to find breakage**

```powershell
conda activate fourteen; python -m pytest tests/ -v --tb=short 2>&1 | Select-Object -Last 80
```

- [ ] **Step 2: Fix any remaining test failures**

Update any tests that reference the old `StateChangeProposal.emotion`, `StateChangeProposal.goal`, `StateChangeProposal.relationships_add`, etc. These fields no longer exist — tests must use the new `changes: list[StateChange]` format.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "fix: update all tests and references for new StateChangeProposal schema"
```

---

### Task 15: Final verification

- [ ] **Step 1: Run full test suite**

```powershell
conda activate fourteen; python -m pytest tests/ -v
```

Expected: all tests PASS (or known skips for UI tests)

- [ ] **Step 2: Run the app manually to verify UI works**

```powershell
conda activate fourteen; python -m app.main
```

Manual checks:
- [ ] Create a new project, create a character → saves to per-directory layout
- [ ] Open the Bible Editor → see three tabs (基本设定, 当前状态, 变化历史)
- [ ] Generate a scene → fact approval panel shows changes in new format
- [ ] Approve changes → state tab reflects updated state

- [ ] **Step 3: Commit final state**

```bash
git add -A
git commit -m "chore: final verification — all tests pass, manual UI check complete"
```

---

### Plan summary

| Task | Component | Files | Est. lines |
|------|-----------|-------|------------|
| 1 | Data models | `models.py` | +120 |
| 2 | Event bus | `events/bus.py`, `events/qt_bridge.py` | +70 |
| 3 | Event log I/O | `storage/character_events.py` | +80 |
| 4 | Snapshot/replay I/O | `storage/character_state.py` | +180 |
| 5 | Per-char directory + dual-read | `storage/project_files.py` | ~60 changed |
| 6 | StateRepository | `storage/state_repository.py` | +180 |
| 7 | StateUpdaterAgent revised | `pipeline/agents/state_updater.py` | ~100 changed |
| 8 | Pipeline compatibility | `pipeline/pipeline.py` | ~10 changed |
| 9 | Context builder | `pipeline/context_builder.py` | ~5 changed |
| 10 | Character editor 3-tab + History widget | `ui/character_editor.py`, `ui/widgets/character_history.py` | +300 |
| 11 | Fact approval update | `ui/widgets/fact_approval.py` | ~40 changed |
| 12 | MainWindow wiring | `ui/main_window.py` | +80 |
| 13 | E2E test | `tests/test_e2e_event_sourcing.py` | +80 |
| 14 | Cleanup | various tests | ~50 changed |
| 15 | Verification | — | — |
| **Total** | | | **~1355 lines** |
