"""Timeline-aware storage helpers for scene regeneration."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.storage.character_events import append_events, get_latest_event_id, load_events
from app.storage.character_state import (
    _apply_changes_to_snapshot,
    load_checkpoint,
    load_or_build_snapshot,
    map_snapshot_to_character_state,
    save_checkpoint,
    save_snapshot,
)
from app.storage.models import (
    Character,
    CanonFact,
    CharacterStateEvent,
    CharacterStateSnapshot,
    SceneStateCheckpoint,
    StateChangeProposal,
)
from app.storage.project_files import (
    list_character_ids,
    get_active_scene_revision_id,
    load_canon_facts,
    load_all_characters,
    load_all_volumes,
    load_scene_generation_record,
    save_canon_facts,
    save_scene_generation_record,
    set_active_scene_prose_version,
)
from app.storage.state_repository import _convert_to_stored_change, ensure_initial_state_event

if TYPE_CHECKING:
    from app.events.bus import EventBus


@dataclass(frozen=True)
class ScenePosition:
    scene_id: str
    chapter_id: str
    scene_order: int


def load_character_context_for_scene(
    project_dir: Path,
    scene_id: str,
    character_ids: list[str],
) -> tuple[list[Character], dict[str, dict]]:
    """Load participating characters with state as of before scene_id."""
    participants = set(character_ids)
    characters = [
        char for char in load_all_characters(project_dir)
        if char.core.id in participants
    ]
    found_ids = {char.core.id for char in characters}
    missing = sorted(participants - found_ids)
    if missing:
        raise ValueError("Scene references missing character IDs: " + ", ".join(missing))

    states, read_points = load_character_state_as_of_scene(
        project_dir,
        scene_id,
        [char.core.id for char in characters],
    )

    result: list[Character] = []
    for char in characters:
        snap = states.get(char.core.id)
        if snap is None:
            result.append(char)
            continue
        result.append(Character(
            core=char.core,
            state=map_snapshot_to_character_state(snap),
        ))
    return result, read_points


def load_character_state_as_of_scene(
    project_dir: Path,
    scene_id: str,
    character_ids: list[str],
) -> tuple[dict[str, CharacterStateSnapshot], dict[str, dict]]:
    """Return character snapshots from the timeline point before scene_id."""
    positions = _scene_positions(project_dir)
    current = _find_position(positions, scene_id)
    scene_orders = {pos.scene_id: pos.scene_order for pos in positions}

    snapshots: dict[str, CharacterStateSnapshot] = {}
    read_points: dict[str, dict] = {}
    for character_id in character_ids:
        char_dir = project_dir / "characters" / character_id
        ensure_initial_state_event(char_dir, character_id)
        if current is None:
            snap = load_or_build_snapshot(char_dir, character_id)
            snapshots[character_id] = snap
            read_points[character_id] = _read_point("latest", "", snap.last_event_id, "", 0)
            continue

        if current.scene_order <= 1:
            snap = _replay_snapshot(
                char_dir,
                character_id,
                max_scene_order=0,
                scene_orders=scene_orders,
            )
            snapshots[character_id] = snap
            read_points[character_id] = _read_point("story_start", "", snap.last_event_id, "", 0)
            continue

        previous = positions[current.scene_order - 2]
        checkpoint = load_checkpoint(char_dir, previous.scene_id)
        if (
            checkpoint is not None
            and not checkpoint.invalidated
            and _revision_is_active(project_dir, checkpoint.scene_id, checkpoint.scene_revision_id)
        ):
            snap = checkpoint.snapshot
            snapshots[character_id] = snap
            read_points[character_id] = _read_point(
                "checkpoint",
                checkpoint.checkpoint_id,
                checkpoint.event_id,
                previous.scene_id,
                previous.scene_order,
            )
            continue

        snap = _replay_snapshot(
            char_dir,
            character_id,
            max_scene_order=previous.scene_order,
            scene_orders=scene_orders,
        )
        snapshots[character_id] = snap
        read_points[character_id] = _read_point(
            "replay",
            "",
            snap.last_event_id,
            previous.scene_id,
            previous.scene_order,
        )

    return snapshots, read_points


def mark_downstream_scenes_stale(project_dir: Path, from_scene_order: int) -> list[str]:
    """Mark generated scenes after from_scene_order as stale."""
    stale: list[str] = []
    for pos in _scene_positions(project_dir):
        if pos.scene_order <= from_scene_order:
            continue
        record = load_scene_generation_record(project_dir, pos.scene_id)
        if record is None:
            continue
        record.status = "stale"
        save_scene_generation_record(project_dir, record)
        stale.append(pos.scene_id)
    return stale


def commit_scene_proposal(
    project_dir: Path,
    proposal: StateChangeProposal,
    scene_id: str,
    transaction_id: str,
    request_id: str,
    bus: EventBus | None = None,
    source: str = "ai",
    revision_id: str = "",
) -> CharacterStateEvent | None:
    """Commit a proposal at the scene's timeline position, not log tail order."""
    if not revision_id:
        record = load_scene_generation_record(project_dir, scene_id)
        revision_id = record.revision_id if record else ""
    char_dir = project_dir / "characters" / proposal.character_id
    existing = [
        event for event in load_events(char_dir)
        if event.scene_id == scene_id and event.scene_revision_id == revision_id
    ]
    if existing:
        return max(existing, key=lambda event: event.event_id)
    built = _build_scene_proposal_event(
        project_dir,
        proposal,
        scene_id,
        transaction_id,
        request_id,
        source,
        revision_id,
    )
    if built is None:
        return None
    event, scene_snapshot = built
    append_events(char_dir, [event])
    save_checkpoint(
        char_dir,
        SceneStateCheckpoint(
            scene_id=scene_id,
            scene_revision_id=revision_id,
            scene_order=event.scene_order,
            checkpoint_id=str(uuid.uuid4()),
            event_id=event.event_id,
            character_id=scene_snapshot.character_id,
            created_at=event.created_at,
            snapshot=scene_snapshot,
        ),
    )
    head = _rebuild_current_snapshot(project_dir, proposal.character_id)
    if bus is not None:
        bus.publish("character_state_updated", character_id=head.character_id, event_id=head.last_event_id)
    return event


def _build_scene_proposal_event(
    project_dir: Path,
    proposal: StateChangeProposal,
    scene_id: str,
    transaction_id: str,
    request_id: str,
    source: str,
    revision_id: str,
) -> tuple[CharacterStateEvent, CharacterStateSnapshot] | None:
    """Build source timeline data without writing derived state."""
    if not proposal.changes:
        return None

    current = find_scene_position(project_dir, scene_id)
    scene_order = current.scene_order if current else 0
    char_dir = project_dir / "characters" / proposal.character_id
    states, _ = load_character_state_as_of_scene(project_dir, scene_id, [proposal.character_id])
    base = states.get(
        proposal.character_id,
        CharacterStateSnapshot(character_id=proposal.character_id),
    )
    base.character_id = proposal.character_id or base.character_id

    stored_changes = []
    for change in proposal.changes:
        stored = _convert_to_stored_change(change, base)
        if stored is not None:
            stored_changes.append(stored)
    if not stored_changes:
        return None

    next_id = get_latest_event_id(char_dir) + 1
    event_seq = _next_event_seq(char_dir, scene_id)
    now = datetime.now(timezone.utc).isoformat()

    scene_snapshot = base.model_copy(deep=True)
    _apply_changes_to_snapshot(scene_snapshot, stored_changes)
    scene_snapshot.character_id = proposal.character_id or scene_snapshot.character_id
    scene_snapshot.last_event_id = next_id
    scene_snapshot.last_scene_id = scene_id
    scene_snapshot.generated_at = now

    event = CharacterStateEvent(
        event_id=next_id,
        transaction_id=transaction_id,
        scene_id=scene_id,
        scene_revision_id=revision_id,
        scene_order=scene_order,
        event_seq=event_seq,
        character_id=scene_snapshot.character_id,
        source=source,
        request_id=request_id,
        created_at=now,
        changes=stored_changes,
    )
    return event, scene_snapshot


def find_scene_position(project_dir: Path, scene_id: str) -> ScenePosition | None:
    return _find_position(_scene_positions(project_dir), scene_id)


def _scene_positions(project_dir: Path) -> list[ScenePosition]:
    positions: list[ScenePosition] = []
    scene_order = 0
    for volume in load_all_volumes(project_dir):
        for chapter in volume.chapters:
            for scene in chapter.scenes:
                scene_order += 1
                positions.append(ScenePosition(scene.id, chapter.id, scene_order))
    return positions


def _find_position(positions: list[ScenePosition], scene_id: str) -> ScenePosition | None:
    for pos in positions:
        if pos.scene_id == scene_id:
            return pos
    return None


def _read_point(
    source: str,
    checkpoint_id: str,
    max_event_id: int,
    scene_id: str,
    scene_order: int,
) -> dict:
    return {
        "source": source,
        "checkpoint_id": checkpoint_id,
        "max_event_id": max_event_id,
        "scene_id": scene_id,
        "scene_order": scene_order,
    }


def _replay_snapshot(
    char_dir: Path,
    character_id: str,
    max_scene_order: int,
    scene_orders: dict[str, int],
) -> CharacterStateSnapshot:
    snap = CharacterStateSnapshot(character_id=character_id)
    all_events = load_events(char_dir)
    active_revisions = {
        scene_id: get_active_scene_revision_id(char_dir.parent.parent, scene_id)
        for scene_id in {
            event.scene_id for event in all_events if event.scene_revision_id
        }
    }
    events = [
        event for event in all_events
        if not event.invalidated
        and (
            not event.scene_revision_id
            or active_revisions.get(event.scene_id) == event.scene_revision_id
        )
        and _event_scene_order(event, scene_orders) <= max_scene_order
    ]
    events.sort(key=lambda event: (
        _event_scene_order(event, scene_orders),
        event.event_seq if event.event_seq > 0 else event.event_id,
        event.event_id,
    ))
    for event in events:
        snap.last_event_id = max(snap.last_event_id, event.event_id)
        snap.last_scene_id = event.scene_id or snap.last_scene_id
        snap.character_id = event.character_id or snap.character_id
        _apply_changes_to_snapshot(snap, event.changes)
    return snap


def _event_scene_order(event: CharacterStateEvent, scene_orders: dict[str, int]) -> int:
    if not event.scene_id:
        return 0
    if event.scene_order > 0:
        return event.scene_order
    return scene_orders.get(event.scene_id, event.event_id)


def _next_event_seq(char_dir: Path, scene_id: str) -> int:
    return max(
        (event.event_seq for event in load_events(char_dir) if event.scene_id == scene_id),
        default=0,
    ) + 1


def _invalidate_checkpoints_from(project_dir: Path, from_scene_order: int) -> None:
    positions = [pos for pos in _scene_positions(project_dir) if pos.scene_order >= from_scene_order]
    for character_id in list_character_ids(project_dir):
        char_dir = project_dir / "characters" / character_id
        for pos in positions:
            checkpoint = load_checkpoint(char_dir, pos.scene_id)
            if checkpoint is None or checkpoint.invalidated:
                continue
            checkpoint.invalidated = True
            save_checkpoint(char_dir, checkpoint)


def _rebuild_all_current_snapshots(project_dir: Path) -> None:
    for character_id in list_character_ids(project_dir):
        _rebuild_current_snapshot(project_dir, character_id)


def _rebuild_current_snapshot(project_dir: Path, character_id: str) -> CharacterStateSnapshot:
    char_dir = project_dir / "characters" / character_id
    events = load_events(char_dir)
    if not events:
        return load_or_build_snapshot(char_dir, character_id)
    scene_orders = {pos.scene_id: pos.scene_order for pos in _scene_positions(project_dir)}
    max_order = max((_event_scene_order(event, scene_orders) for event in events), default=0)
    snap = _replay_snapshot(char_dir, character_id, max_order, scene_orders)
    save_snapshot(char_dir, snap)
    return snap


def _revision_is_active(project_dir: Path, scene_id: str, revision_id: str) -> bool:
    if not revision_id:
        return True
    return get_active_scene_revision_id(project_dir, scene_id) == revision_id


def _remove_revision_events(project_dir: Path, scene_id: str, revision_id: str) -> None:
    for character_id in list_character_ids(project_dir):
        char_dir = project_dir / "characters" / character_id
        events = load_events(char_dir)
        kept = [
            event for event in events
            if not (
                event.scene_id == scene_id
                and event.scene_revision_id == revision_id
            )
        ]
        if len(kept) == len(events):
            continue
        _save_events(char_dir, kept)


def _save_events(char_dir: Path, events: list[CharacterStateEvent]) -> None:
    events_file = char_dir / "events.jsonl"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=char_dir, delete=False
        ) as fh:
            temp_path = Path(fh.name)
            for event in events:
                fh.write(
                    json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
                    + "\n"
                )
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, events_file)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _scope_legacy_scene_memory(
    project_dir: Path, scene_id: str, revision_id: str
) -> None:
    facts = load_canon_facts(project_dir, active_only=False)
    changed = False
    for fact in facts:
        if fact.source_scene_id == scene_id and not fact.source_scene_revision_id:
            fact.source_scene_revision_id = revision_id
            changed = True
    if changed:
        save_canon_facts(project_dir, facts)

    for character_id in list_character_ids(project_dir):
        char_dir = project_dir / "characters" / character_id
        events = load_events(char_dir)
        changed = False
        for event in events:
            if event.scene_id == scene_id and not event.scene_revision_id:
                event.scene_revision_id = revision_id
                changed = True
        if changed:
            _save_events(char_dir, events)


def _revision_events(
    project_dir: Path, scene_id: str, revision_id: str
) -> list[CharacterStateEvent]:
    return [
        event
        for character_id in list_character_ids(project_dir)
        for event in load_events(project_dir / "characters" / character_id)
        if event.scene_id == scene_id and event.scene_revision_id == revision_id
    ]


def _stage_revision_events(
    project_dir: Path,
    scene_id: str,
    revision_id: str,
    proposals: list[StateChangeProposal],
) -> list[CharacterStateEvent]:
    _remove_revision_events(project_dir, scene_id, revision_id)
    transaction_id = str(uuid.uuid4())
    events: list[CharacterStateEvent] = []
    for proposal in proposals:
        built = _build_scene_proposal_event(
            project_dir,
            proposal,
            scene_id,
            transaction_id,
            str(uuid.uuid4()),
            "ai",
            revision_id,
        )
        if built is None:
            continue
        event, _ = built
        append_events(project_dir / "characters" / proposal.character_id, [event])
        events.append(event)
    return events


def publish_scene_revision(
    project_dir: Path,
    scene_id: str,
    revision_id: str,
    approved_facts: list[dict],
    approved_state_changes: list[dict],
    bus: EventBus | None = None,
) -> None:
    """Publish one reviewed revision; this is the only canon mutation seam."""
    record = load_scene_generation_record(project_dir, scene_id, revision_id=revision_id)
    if record is None:
        raise ValueError(f"Unknown scene revision: {revision_id}")
    if not record.review_overridden and not (record.review or {}).get("overall_pass", False):
        raise ValueError("Scene revision must pass review or be explicitly overridden")
    position = find_scene_position(project_dir, scene_id)
    if position is None:
        raise ValueError(f"Scene not found in outline: {scene_id}")

    previous = load_scene_generation_record(project_dir, scene_id)
    active_revision_id = get_active_scene_revision_id(project_dir, scene_id)
    if record.published_at is None and record.status != "draft":
        raise ValueError("Legacy published revision has no reusable approved memory")
    if record.published_at is not None:
        if (
            approved_facts != record.approved_facts
            or approved_state_changes != record.approved_state_change_proposals
        ):
            raise ValueError("Published scene revision memory is immutable")
        if active_revision_id == revision_id:
            return
        published_events = _revision_events(project_dir, scene_id, revision_id)
    else:
        if active_revision_id == revision_id:
            raise ValueError("Active legacy revision cannot be republished without metadata")
        staged_facts = [
            CanonFact(
                description=fact.get("description", ""),
                category=fact.get("category", "world"),
                source_scene_id=scene_id,
                source_scene_revision_id=revision_id,
                importance=fact.get("importance", 3),
                tags=fact.get("tags", []),
            )
            for fact in approved_facts
            if fact.get("description")
        ]
        proposals = [
            StateChangeProposal.model_validate(proposal)
            for proposal in approved_state_changes
        ]

    if active_revision_id and active_revision_id != revision_id:
        _scope_legacy_scene_memory(project_dir, scene_id, active_revision_id)
    if record.published_at is None:
        record.approved_facts = approved_facts
        record.approved_state_change_proposals = approved_state_changes
        save_scene_generation_record(project_dir, record)

        all_facts = [
            fact for fact in load_canon_facts(project_dir, active_only=False)
            if fact.source_scene_revision_id != revision_id
        ]
        all_facts.extend(staged_facts)
        save_canon_facts(project_dir, all_facts)
        published_events = _stage_revision_events(
            project_dir, scene_id, revision_id, proposals
        )

    previous_revision_id = previous.revision_id if previous is not None else ""
    _write_publication_journal(
        project_dir, scene_id, revision_id, previous_revision_id
    )

    set_active_scene_prose_version(
        project_dir,
        position.chapter_id,
        scene_id,
        f"v{record.revision_number}",
        revision_id,
    )
    _finish_publication(project_dir, record, previous_revision_id)
    if bus is not None:
        for event in published_events:
            bus.publish(
                "character_state_updated",
                character_id=event.character_id,
                event_id=event.event_id,
            )


def recover_pending_publication(project_dir: Path) -> None:
    """Finish derived updates after an interrupted active-marker swap."""
    path = project_dir / ".publish.pending.json"
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as fh:
        pending = json.load(fh)
    scene_id = pending.get("scene_id", "")
    revision_id = pending.get("revision_id", "")
    if get_active_scene_revision_id(project_dir, scene_id) != revision_id:
        path.unlink(missing_ok=True)
        return
    record = load_scene_generation_record(project_dir, scene_id, revision_id=revision_id)
    if record is None:
        raise ValueError(f"Pending publication revision is missing: {revision_id}")
    _finish_publication(
        project_dir, record, pending.get("previous_revision_id", "")
    )


def _finish_publication(project_dir: Path, record, previous_revision_id: str) -> None:
    if previous_revision_id and previous_revision_id != record.revision_id:
        previous = load_scene_generation_record(
            project_dir, record.scene_id, revision_id=previous_revision_id
        )
        if previous is not None:
            previous.status = "superseded"
            save_scene_generation_record(project_dir, previous)
    record.status = "current"
    record.published_at = datetime.now(timezone.utc)
    save_scene_generation_record(project_dir, record)
    position = find_scene_position(project_dir, record.scene_id)
    if position is not None:
        _rebuild_scene_checkpoints(project_dir, record.scene_id)
        _invalidate_checkpoints_from(project_dir, position.scene_order + 1)
        mark_downstream_scenes_stale(project_dir, position.scene_order)
    _rebuild_all_current_snapshots(project_dir)
    (project_dir / ".publish.pending.json").unlink(missing_ok=True)


def _rebuild_scene_checkpoints(project_dir: Path, scene_id: str) -> None:
    position = find_scene_position(project_dir, scene_id)
    if position is None:
        return
    revision_id = get_active_scene_revision_id(project_dir, scene_id)
    scene_orders = {pos.scene_id: pos.scene_order for pos in _scene_positions(project_dir)}
    now = datetime.now(timezone.utc).isoformat()
    for character_id in list_character_ids(project_dir):
        char_dir = project_dir / "characters" / character_id
        if not any(
            event.scene_id == scene_id and event.scene_revision_id == revision_id
            for event in load_events(char_dir)
        ):
            continue
        snapshot = _replay_snapshot(
            char_dir, character_id, position.scene_order, scene_orders
        )
        save_checkpoint(
            char_dir,
            SceneStateCheckpoint(
                scene_id=scene_id,
                scene_revision_id=revision_id,
                scene_order=position.scene_order,
                checkpoint_id=str(uuid.uuid4()),
                event_id=snapshot.last_event_id,
                character_id=character_id,
                created_at=now,
                snapshot=snapshot,
            ),
        )


def _write_publication_journal(
    project_dir: Path,
    scene_id: str,
    revision_id: str,
    previous_revision_id: str,
) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=project_dir,
            prefix=".publish.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            temp_path = Path(fh.name)
            json.dump(
                {
                    "scene_id": scene_id,
                    "revision_id": revision_id,
                    "previous_revision_id": previous_revision_id,
                },
                fh,
            )
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, project_dir / ".publish.pending.json")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
