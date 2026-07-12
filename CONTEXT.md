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
Approvals belong to the scene that produced them, even if the author selects another scene before confirming.
_Avoid_: Review panel, post-generation review.

**Active Prose Version (当前正文版本)**:
The scene prose version the author has explicitly chosen as the authoritative text for display and export.
_Avoid_: Selected version, current draft, default version.

**Scene Revision (场景修订版)**:
A generated version of one scene's prose and derived state changes. Regenerating a scene creates a new revision; older revisions may be superseded but remain useful for audit and undo.
_Avoid_: Scene version, draft version, rewrite.

**Draft Scene Revision (场景草稿修订版)**:
A Scene Revision that has been saved but not published. It may contain review results and memory proposals, but it cannot affect active prose, canon facts, State Events, checkpoints, export, or downstream staleness.
_Avoid_: Current revision, latest canon.

**Published Scene Revision (已发布场景修订版)**:
The Scene Revision selected by the scene's active marker. Only memory records whose scene revision matches the Published Scene Revision participate in retrieval and state replay.
_Avoid_: Latest revision, generated revision.

**Scene Publication (场景发布)**:
The single operation that makes a Draft Scene Revision canonical. It commits approved memory for that revision, atomically switches the active marker, rebuilds derived state, and marks downstream scenes stale.
_Avoid_: Save, activate, approve facts.

**Scene Checkpoint (场景检查点)**:
A character state snapshot written immediately after a scene is approved. Used during context assembly so Scene N always sees state as of the end of Scene N-1, preserving temporal consistency even when scenes are generated out of order.
_Avoid_: Scene snapshot, state checkpoint.

**Read Point (读取点)**:
The checkpoint or event position used to assemble a scene prompt for a specific character. Used to detect when a later scene was generated from an older timeline.
_Avoid_: Dependency pointer, generated-with marker.

**Stale Scene (过期场景)**:
A scene whose generation used character state revisions that have since been superseded (e.g., Scene 30 was rewritten, changing hero state; Scene 45 was generated with the old revision). Detected via revision comparison.
_Avoid_: Dirty scene, invalid scene.

**Event Invalidation (事件作废)**:
Marking an existing event as `invalidated: true` after an explicit manual or system rejection. Replay skips invalidated events. Publishing a replacement scene revision does not invalidate old events; active-revision filtering makes them inactive.
_Avoid_: Deletion, removal, tombstone.

## Relationships

- **State Updater → State Change Proposal → Fact Approval Panel**: The State Updater produces proposals; the author approves them in the panel; approved proposals are committed as State Events.
- **State Event → State Snapshot**: Snapshots are derived by replaying valid (non-invalidated) events from the event log.
- **Scene Checkpoint → Context Assembly**: When generating Scene N, the context assembler reads the checkpoint from Scene N-1 to determine what characters knew at that point.
- **Scene Revision → Read Point → Stale Scene**: A scene revision records the read points used in its prompt; when those read points are superseded, downstream revisions become stale.
- **Scene Publication → Active Revision Selection → Stale Scene Detection**: Publishing a replacement makes older revision-scoped memory inactive and marks downstream scenes that used the previous timeline stale.
- **Draft Scene Revision → Scene Publication → Published Scene Revision**: Saving generation output creates a draft only; publication is the only operation allowed to change canonical prose or timeline memory.
- **Published Scene Revision → Canon Facts / State Events / Checkpoints**: Revision-scoped memory is visible only when its revision matches the active marker. Legacy records without a revision remain readable.
