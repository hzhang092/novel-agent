# Character State Event Sourcing — Design

**Date:** 2026-06-11
**Status:** Decision-complete, pending implementation plan
**Source:** Grill-with-docs session on character state visibility after approval

## Problem

After approving character state changes in the Fact Approval panel, the updated state is written to disk but the character editor UI does not reflect it. The in-memory cache goes stale. The user must navigate away and back to see changes.

Deeper issue: the current system overwrites `CharacterState` in the character YAML every scene. This loses the history of what changed, when, and why — making continuity checking, rollback, and out-of-order scene regeneration fragile as the novel grows.

## Solution

Event-sourced character state. The character YAML is split into user-authored definition and system-managed state, with an append-only event log as the source of truth.

### Storage layout

```
characters/
└── lin_feng/
    ├── definition.yaml    # user-owned, edited manually
    ├── state.yaml         # system-owned, cached materialized view
    └── events.jsonl       # system-owned, append-only history
```

**definition.yaml** — user-authored canonical facts (name, personality, background, skills, etc.). Corresponds to the existing `CharacterCore` model.

**state.yaml** — machine-managed current state snapshot (emotion, goal, location, relationships, knowledge, secrets, status). Built by replaying events from `events.jsonl`. Carries `last_event_id` and `schema_version` for incremental replay. Never hand-edited.

**events.jsonl** — append-only event log. Each line is one `CharacterStateEvent` (one StateUpdater run per scene). Carries `event_id`, `transaction_id`, `scene_id`, `character_id`, `source`, `request_id`, `schema_version`, `invalidated`, and a `changes` array.

### Event schema

```python
# LLM-facing output schema (discriminated union)
class SetFieldChange(BaseModel):
    type: Literal["set_field"]
    field: Literal["emotion", "goal", "location", "status", "power_level"]
    value: str

class RelationshipChange(BaseModel):
    type: Literal["relationship_change"]
    target_character_id: str
    relationship: str

class KnowledgeAddChange(BaseModel):
    type: Literal["knowledge_add"]
    fact: str

class KnowledgeRemoveChange(BaseModel):
    type: Literal["knowledge_remove"]
    fact: str

class SecretAddChange(BaseModel):
    type: Literal["secret_add"]
    fact: str

class SecretRemoveChange(BaseModel):
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
    character_id: str
    changes: list[StateChange] = Field(default_factory=list)
```

### Stored event record (events.jsonl line)

```json
{
  "event_id": 1843,
  "transaction_id": "uuid",
  "scene_id": "scene_042",
  "character_id": "lin_feng",
  "source": "ai",
  "request_id": "uuid-for-observability",
  "schema_version": 1,
  "invalidated": false,
  "changes": [
    {
      "type": "set_field",
      "field": "goal",
      "old": "become_sect_elder",
      "new": "avenge_master"
    },
    {
      "type": "knowledge_add",
      "fact": "Elder Zhao killed the master"
    }
  ]
}
```

Key design decisions:

- **`old` values are filled by code, not the LLM.** The StateUpdater outputs mutation proposals (new values only). The application layer reads the current snapshot to capture the old value before writing the event. This prevents hallucinated old values, formatting drift, and corrupted history.
- **One event per StateUpdater invocation.** The `changes` array holds all mutations from one pipeline run. Matches the transactional commit boundary.
- **`transaction_id`** groups related events (same pipeline run across multiple characters/entities) for future multi-entity updates without schema changes.
- **`invalidated` flag** marks old events as superseded when a scene is regenerated. Replay skips invalidated events.

### Division of labor

| Responsibility | Owner |
|---|---|
| Determine what changed | LLM (StateUpdaterAgent) |
| Determine previous value | Code (reads snapshot) |
| Validate transition | Code (Pydantic + schema checks) |
| Write event log | Code |
| Update snapshot | Code |

## Snapshot and replay

### state.yaml format

```yaml
character_id: lin_feng
last_scene_id: scene_042
last_event_id: 1843
snapshot_version: 1
generated_at: 2026-06-11T00:00:00Z
location: Qingyun Sect
goal: Avenge Master
emotion: Furious
relationships:
  su_waner: lover
knowledge:
  - Elder Zhao killed the master
secrets: []
status: ""
power_level: ""
```

### Incremental replay

On load, compare `state.yaml.last_event_id` against the latest `event_id` in `events.jsonl`. If they differ, replay only the gap:

```
load state.yaml (snapshot at event 1843)
replay events 1844–1850
write updated state.yaml
```

No full replay unless `state.yaml` is missing or corrupt.

### Schema versioning (snapshot-anchored, lazy migration)

Snapshots carry a `snapshot_version`. Events carry a `schema_version`. Events are never rewritten. Schema migration is bounded:

```
load snapshot (already v2-normalized)
replay only remaining events (v2 or newer)
```

The compatibility surface shrinks to the gap between the last snapshot and "now." When new snapshots are written (post-scene commit), they are always in the latest schema version — the window self-heals.

## Pipeline integration

### Transactional commit

The pipeline stages all state changes in memory during execution. Nothing is written to disk until the full pipeline succeeds (all agents + user approval):

```
StateUpdater (simulate only)
→ Reviewer
→ Fact Extractor
→ User Approval
→ Commit phase:
    append(events.jsonl)
    write(state.yaml)
    emit domain event
```

If any step fails, the in-memory copy is discarded. No partial writes, no duplicate events.

### StateUpdaterAgent prompt design

The prompt is organized as action taxonomy, not schema fields:

1. Classify intent: scalar change → `set_field`, relationship update → `relationship_change`, memory addition → `knowledge_add`, etc.
2. Choose type first, then fill required fields for that type.
3. Explicitly forbid invented field names (the schema `Literal` enum is the closed world).

### Validation and recovery

- **Tier 1**: Pydantic strict validation. On failure, auto-retry (max 2) with a repair prompt: "Fix this JSON to match schema exactly. Do not change semantics."
- **Tier 2**: If retries fail, show raw output + error in the error panel. User clicks Retry.
- No fuzzy auto-correction. The event log must remain deterministic.

### Context assembly — scene checkpoints

When generating Scene N, the context assembler loads the character state checkpoint from Scene N-1 (not the latest snapshot). This ensures correct knowledge boundaries regardless of generation order:

```
load state checkpoint for scene N-1
  → if missing, replay events up to scene N-1
assemble context from that checkpoint
```

On scene approval, write a checkpoint snapshot (`state_scene_042.yaml`). The `state.yaml` is the "head" snapshot (latest). Checkpoints are immutable.

## Timeline and stale detection

### Linear timeline with event invalidation

When a scene is regenerated, its old events are marked `invalidated: true`. New events are appended with the same `scene_id`. State reconstruction skips invalidated events.

### Revision-based stale detection

Each character state has a monotonically increasing `revision` number. Scene metadata records which revisions were used during generation:

```yaml
# scene metadata
scene_045:
  generated_with:
    hero: 84
    mentor: 12
```

After Scene 30 is rewritten, `hero` revision becomes 88. Comparing `generated_with.hero: 84` against `current hero: 88` → scene is stale.

### UI for stale scenes

Show "⚠ 12 scenes may be affected by state changes" with per-scene actions: Review, Regenerate, Ignore. The author decides which downstream scenes to touch.

## UI design

### Event bus (domain events + Qt bridge)

```
Domain Bus (pure Python, no Qt)
    ↓
QtEventBridge (cross-thread marshaling via QMetaObject.invokeMethod)
    ↓
Qt UI subscribers (Bible Editor, Character Sidebar, future views)
```

The bus publishes `character_state_updated(character_id, event_id)`. Subscribers compare the event's `event_id` against their loaded version and reload only if stale. A version check on tab focus serves as secondary safety net.

### Current State tab

- Read-only by default. Shows the derived snapshot from `state.yaml`.
- "Edit State" button switches to editable mode.
- On save, creates a `source: "user"` event (manual override), applies it, updates snapshot, emits domain event.
- No direct writes to `state.yaml` — every change becomes an event.

### History tab

Two views via segmented control:

- **当前场景** (default when a scene is selected): scene diff view. Shows all changes from the current scene's events, grouped by character, with old→new values.
- **全部历史** (default when no scene selected): full timeline, reverse chronological, grouped by scene into expandable cards. Source badges ([AI], [User], [Manual]) on each change.

Backed by a single query API: `get_character_events(character_id, scene_id=None, source=None)`.

### Event source tracking

Every event carries a `source` field:

| Source | Meaning |
|---|---|
| `ai` | Generated by StateUpdaterAgent |
| `user` | Author override via State tab edit |
| `manual_event` | Author-added story event (off-screen knowledge gain, etc.) |
| `system` | Migration, repair, or automated reconciliation |

## Migration from legacy format

### Dual-read loader

The loader reads both legacy `characters/<name>.yaml` (flat file with core+state) and new `characters/<name>/definition.yaml` + `state.yaml`. On save, always writes new format only.

### One-time migration tool

- Triggered from UI or on project open if legacy files detected.
- Creates `.backups/migration-YYYY-MM-DD/` with copies of original files.
- Converts each `characters/<name>.yaml` → per-character directory with `definition.yaml`, `state.yaml`, and an empty `events.jsonl` containing a synthetic `source: "system"` migration event.
- Validates equivalence: load old → load new → assert equal.
- Removes old file only after validation passes (or leaves `.bak`).

### Deprecation timeline

- v0.8: Read both, write new. Migration optional.
- v0.9: Read both, write new. Loud warning for legacy projects on open.
- v1.0: Migration required before editing.
- v2.0: Drop legacy format support.

## Out of scope for this design

- Branching timelines / narrative version control (deferred to v3)
- Global world event store spanning characters, factions, locations, items (per-character events are the v1 stepping stone)
- Multi-entity StateUpdater runs (single character per run in v1; `transaction_id` is forward-looking)
- Snapshot checkpoint pruning / cleanup (all checkpoints retained in v1)
- File watcher for external modification detection (event bus + version check on focus is sufficient for v1)
