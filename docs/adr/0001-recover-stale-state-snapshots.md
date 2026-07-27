# Recover stale state snapshots from the event log

Status: accepted

State Events are the source of truth for Character State; State Snapshots are derived materialized state. If a commit appends an event but crashes before saving `state.yaml`, or if `state.yaml` is corrupt, snapshot reads and later commits must rebuild from `events.jsonl` when replay succeeds.

Considered options were always replaying events, incrementally replaying only newer events, adding a flat-file transaction journal, and moving state persistence to SQLite. We chose recovery-on-load because it fixes the append-before-snapshot crash with the smallest change while keeping snapshots useful.

Consequence: `load_or_build_snapshot()` may write a repaired `state.yaml` during load. This does not make event append plus snapshot save truly atomic; it makes stale snapshots recoverable.
