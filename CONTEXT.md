# NovelForge

A local-first desktop application for writing Chinese web novels through a multi-agent AI pipeline.

## Language

**Project Folder (项目文件夹)**:
The directory that contains one novel project's `project.yaml` and standard subfolders for characters, outline, scenes, canon, and exports.
_Avoid_: Project file folder, workspace folder.

**Character Definition (角色基本设定)**:
Immutable or slowly-changing character traits set by the author: name, personality, background, appearance, skills, weaknesses, speech style.
_Avoid_: Character card, character core, static traits.

**Character State (角色当前状态)**:
The current, mutable snapshot of a character's condition derived from all events up to the current scene: emotion, goal, location, relationships, knowledge, secrets, status, power level.
_Avoid_: Dynamic traits, live state.

**State Event (状态事件)**:
A record of one or more state mutations produced by a single StateUpdater run or manual author edit. Stored append-only in `events.jsonl`. Each event is linked to a scene and carries its source (AI, user, manual, system).
_Avoid_: State change, mutation, delta.

**State Snapshot (状态快照)**:
A materialized, schema-versioned checkpoint of character state at a specific event ID. Used as the replay starting point so only events after the snapshot need to be replayed. Stored in `state.yaml`.
_Avoid_: Cache, materialized view.

**State Updater (状态更新器)**:
The pipeline agent that reads generated prose and infers what character state fields changed. Outputs a `StateChangeProposal` (mutation intentions, not full events). Does not determine old values.
_Avoid_: State tracker, character updater.

**State Change Proposal (状态变更建议)**:
The structured output of the StateUpdater agent — a list of typed state changes (set_field, relationship_change, knowledge_add, etc.) with new values only. Validated by Pydantic against a discriminated union schema. Old values are filled by code when writing the actual State Event.
_Avoid_: Diff, patch, mutation.

**Fact Approval Panel (设定审批面板)**:
The post-generation UI where the author reviews and approves or rejects extracted canon facts and state change proposals. Approved proposals become events in the event log.
_Avoid_: Review panel, post-generation review.

**Active Prose Version (当前正文版本)**:
The scene prose version the author has explicitly chosen as the authoritative text for display and export.
_Avoid_: Selected version, current draft, default version.

**Scene Checkpoint (场景检查点)**:
A character state snapshot written immediately after a scene is approved. Used during context assembly so Scene N always sees state as of the end of Scene N-1, preserving temporal consistency even when scenes are generated out of order.
_Avoid_: Scene snapshot, state checkpoint.

**Stale Scene (过期场景)**:
A scene whose generation used character state revisions that have since been superseded (e.g., Scene 30 was rewritten, changing hero state; Scene 45 was generated with the old revision). Detected via revision comparison.
_Avoid_: Dirty scene, invalid scene.

**Event Invalidation (事件作废)**:
Marking an existing event as `invalidated: true` when its source scene is regenerated. Replay skips invalidated events. New events for the regenerated scene are appended separately.
_Avoid_: Deletion, removal, tombstone.

## Relationships

- **State Updater → State Change Proposal → Fact Approval Panel**: The State Updater produces proposals; the author approves them in the panel; approved proposals are committed as State Events.
- **State Event → State Snapshot**: Snapshots are derived by replaying valid (non-invalidated) events from the event log.
- **Scene Checkpoint → Context Assembly**: When generating Scene N, the context assembler reads the checkpoint from Scene N-1 to determine what characters knew at that point.
- **Scene Regeneration → Event Invalidation → Stale Scene Detection**: Regenerating a scene invalidates its old events; revision comparison identifies downstream scenes that used now-stale state.
