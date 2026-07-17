# NovelForge

A local-first desktop application for writing Chinese web novels through a multi-agent AI pipeline.

## Language

**Project Folder (项目文件夹)**:
The directory that contains one novel project's `project.yaml` and standard subfolders for characters, outline, scenes, canon, and exports.
_Avoid_: Project file folder, workspace folder.

**Story Bible (故事设定集)**:
The project's author-controlled story knowledge, organized into Overview, World, Characters, and Writing Style. It grows as the story develops; project creation does not require choosing a complete schema.
_Avoid_: Novel Bible, lore database, setup wizard.

**Progressive Disclosure (渐进式展示)**:
The Story Bible interaction pattern that shows a small useful default and lets authors reveal optional Detail Fields, sections, or Story Elements as needed. It changes presentation and starting effort, not validation or stored story data.
_Avoid_: Mandatory wizard, incomplete-data warning, schema selection.

**Detail Field (详情字段)**:
A predefined attribute that describes story data, such as a character's age, appearance, or hidden motive. A field may be shown or hidden without changing its stored value or whether it is available to context assembly.
_Avoid_: Story Element, custom object, section.

**Story Element (故事元素)**:
A distinct named thing or concept in the Story Bible, such as a character, faction, location, culture, power system, historical event, item, or creature. Unlike a Detail Field, an element can exist independently and can have its own details.
_Avoid_: Detail Field, world field, section.

**Bible Element (设定元素)**:
An independently stored, typed, author-controlled World Story Element: a faction, terminology entry, historical event, power system, or location. Characters remain separate because they have richer Definition, State, and Event models.
_Avoid_: Character, Canon Fact, world section, arbitrary custom field.

**Element Relationship (元素关系)**:
A validated directed link from one Bible Element to another, stored by stable element ID. Inbound and inverse views are derived rather than duplicated in storage.
_Avoid_: Embedded target name, character relationship, duplicated inverse edge.

**Element Revision (元素修订号)**:
The monotonically increasing semantic version of one Bible Element. Saving without a story-content change does not increment it; context assembly records the revision it read.
_Avoid_: Editor Layout version, file timestamp, full revision history.

**Explicit Scene Element (场景显式元素)**:
A Bible Element whose stable ID the author attached to a Scene Outline. It is always included when assembling that scene's generation context.
_Avoid_: Free-text scene location, automatic keyword match, Canon Fact tag.

**Selected Story Element (已选故事元素)**:
A Bible Element included in one scene's generation context because it was explicit, always included, textually relevant, or related by one eligible graph hop. Its revision and selection reasons are recorded for traceability.
_Avoid_: Every stored element, visible editor row, hidden Detail Field.

**Character Importance (角色重要性)**:
The major, supporting, or background classification that controls the character editor's default Detail Fields and how much character data context assembly includes. It guides author effort but does not impose required fields.
_Avoid_: Character type, completeness level, internal tier label in user-facing text.

**Editor Layout (编辑器布局)**:
Project-local UI preferences such as visible Detail Fields and collapsed sections. Stored separately from story data so hiding a populated field never deletes it or excludes it from generation context.
_Avoid_: Character Definition, story schema, prompt selection.

**Unsaved Character Edit (未保存角色编辑)**:
A change in the character editor that has not been persisted. It must be saved, discarded with confirmation, or kept open before switching characters or closing the editor.
_Avoid_: Dirty character, Stale Scene.

**Manual State Override (手动状态覆盖)**:
An explicit author edit to the otherwise read-only Character State view. Recording the override creates a user-sourced State Event so history, replay, invalidation, and snapshots remain consistent.
_Avoid_: Direct state edit, snapshot edit, definition change.

**Story Template (故事模板)**:
A previewable pack of Story Elements and Writing Style values. Applying it uses an explicit merge choice, such as keeping existing values, filling empty values, or replacing selected sections; it does not silently replace the Story Bible.
_Avoid_: Project preset, full-project replacement, mandatory schema.

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
The character checkpoint/event position or Bible Element revision used to assemble a scene prompt. Used to trace the exact story knowledge read by generation and to support precise stale detection later.
_Avoid_: Dependency pointer, generated-with marker.

**Stale Scene (过期场景)**:
A scene whose generation used character state revisions that have since been superseded (e.g., Scene 30 was rewritten, changing hero state; Scene 45 was generated with the old revision). Detected via revision comparison.
_Avoid_: Dirty scene, invalid scene.

**Event Invalidation (事件作废)**:
Marking an existing event as `invalidated: true` after an explicit manual or system rejection. Replay skips invalidated events. Publishing a replacement scene revision does not invalidate old events; active-revision filtering makes them inactive.
_Avoid_: Deletion, removal, tombstone.

## Relationships

- **Story Bible → Progressive Disclosure → Story Elements / Detail Fields**: World knowledge grows through distinct Story Elements; Character Definitions grow through optional Detail Fields. Writing Style keeps compact core controls with expandable advanced sections.
- **Bible Element ↔ Canon Fact**: Bible Elements are reusable knowledge authored in the Story Bible. Canon Facts are scene-derived memory from a Published Scene Revision; neither is migrated into the other.
- **Explicit Scene Element / Relevance / Element Relationship → Selected Story Element**: Context assembly includes explicit and always-included elements, deterministically selects textual matches, then expands no more than one eligible relationship hop.
- **Selected Story Element → Element Revision → Read Point**: Each selected element records the semantic revision and selection reasons used for generation.
- **Character Importance → Editor Defaults / Context Assembly**: Importance changes which Detail Fields appear initially and how character data is compressed for generation. Authors may expose more fields without changing importance.
- **Editor Layout ↔ Story Data**: Editor Layout controls presentation only. Hiding a Detail Field preserves its value, and prompt inclusion follows story-data and context rules rather than UI visibility.
- **Unsaved Character Edit → Character Switching**: Switching characters must first save the edit, explicitly discard it, or cancel the switch.
- **Character Definition ↔ Character State**: Definition is author-controlled profile data. State is an evolving continuity snapshot shown read-only by default, with History as its event record.
- **Manual State Override → State Event → Character State**: A manual override is recorded as a user-sourced event, then replayed into Character State and its snapshots.
- **Story Template → Preview → Merge**: Applying a template previews its changes and uses the chosen merge behavior instead of silently replacing existing story data.
- **State Updater → State Change Proposal → Fact Approval Panel**: The State Updater produces proposals; the author approves them in the panel; approved proposals are committed as State Events.
- **State Event → State Snapshot**: Snapshots are derived by replaying valid (non-invalidated) events from the event log.
- **Scene Checkpoint → Context Assembly**: When generating Scene N, the context assembler reads the checkpoint from Scene N-1 to determine what characters knew at that point.
- **Scene Revision → Read Point → Stale Scene**: A scene revision records the read points used in its prompt; when those read points are superseded, downstream revisions become stale.
- **Scene Publication → Active Revision Selection → Stale Scene Detection**: Publishing a replacement makes older revision-scoped memory inactive and marks downstream scenes that used the previous timeline stale.
- **Draft Scene Revision → Scene Publication → Published Scene Revision**: Saving generation output creates a draft only; publication is the only operation allowed to change canonical prose or timeline memory.
- **Published Scene Revision → Canon Facts / State Events / Checkpoints**: Revision-scoped memory is visible only when its revision matches the active marker. Legacy records without a revision remain readable.
