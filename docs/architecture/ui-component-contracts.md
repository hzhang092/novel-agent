# UI component contracts

NovelForge UI components communicate across composition boundaries through public
semantic methods, read-only properties, and Qt signals. A parent owns the children
it constructs and coordinates sibling interactions.

## Boundary rules

- Parent to child: call a public method or read a public property.
- Child to parent: emit a Qt signal.
- Sibling to sibling: ask the common parent to coordinate the action.
- A component may use its own private fields and event handlers.
- Production code under `app/ui` may not access another object's single-underscore
  member.

For example, Bible scene navigation is
`BibleEditorView.scene_requested` -> `MainWindow` ->
`OutlineEditorView.activate_scene()`. World-element refresh is
`BibleEditorView.elements_changed` -> `MainWindow` ->
`OutlineEditorView.refresh_world_elements()`.

Choose a method for an operation requested by the owner, a read-only property for
stable state the owner needs to inspect, and a signal for user intent reported
upward. Button handlers remain private because they translate a concrete UI event
into those semantic operations. Composite widgets keep raw children private so an
owner cannot depend on layout, controls, or a child's persistence mechanics.

## Reusable widgets

`KeyValueTable` owns its `QTableWidget`. Consumers use `rows()` for normalized,
copied data and `row_count()` for size.

`BibleElementList.select_element()` performs a normal selection and returns whether
the element exists. `restore_selection()` performs a silent restoration and keeps
the list's selection bookkeeping consistent. Callers never find or select tree
items themselves.

## Bible editor tree

`CharacterEditorView` provides:

- `create_character()` for the add-character workflow.
- `character_cores_in_memory()` for immutable snapshots, including unsaved edits.
- `selected_character_id` for read-only selection state.
- `reload()` for storage refresh.

`WorldBibleEditorView` provides `show_overview()` and
`prepare_for_navigation()`. The latter owns dirty-state resolution before another
Bible tab opens.

`BibleEditorView` is the public facade used outside the Bible component tree. It
provides `is_loaded`, `is_dirty`, `save_all()`, `reload()`, `reload_characters()`,
`set_event_bus()`, `set_current_scene_context()`, `refresh_usage()`, and
`open_character()`. Its children remain private.

## Outline editor

`OutlineEditorView` provides `is_loaded`, `save()`,
`refresh_world_elements()`, `activate_scene()`, and `select_next_scene()`.
`activate_scene()` validates that the requested ID is a scene and emits
`scene_selected` exactly once, including when the scene is already selected.

MainWindow uses `save()` for navigation autosave and `activate_scene()` for Bible
usage navigation. It does not call outline event handlers or manipulate tree items.

## Scene workspace

`SceneWorkspaceView` owns the prose editor, trace panel, planner checkpoint, fact
approval panel, and context preview. These widgets are private.

The workspace facade covers:

- Scene state: `current_scene_id`, `current_chapter_id`, `is_showing_scene()`,
  `set_scene()`, and `clear_scene()`.
- Prose: `set_prose_text()`, `prose_text()`, `append_prose()`,
  `prose_is_modified()`, `set_prose_versions()`, and `current_prose_version()`.
- Generation: `begin_generation()`, `set_generating()`, trace methods, planner
  methods, review methods, and status/navigation methods.
- Context and approval: `show_context()`, `clear_context()`,
  `show_fact_approval()`, `hide_fact_approval()`, and read-only workflow state.

The workspace forwards semantic signals: `generate_requested`, `retry_requested`,
`next_scene_requested`, `continue_review_requested`, `prose_version_selected`,
`publish_version_requested`, `plan_approved`, `plan_rejected`, and
`approval_batch_approved`.

## Mutable data ownership

Components do not return live mutable collections across a boundary.
`KeyValueTable.rows()` returns new lists, and
`CharacterEditorView.character_cores_in_memory()` returns a tuple of deep-copied
models. Signals carrying lists or dictionaries describe an action; the receiving
parent validates or persists that payload instead of treating child storage as
shared state.

## Signal lifecycle

MainWindow connects ordinary view signals once in `_connect_view_signals()` during
UI construction. Opening or creating a project binds services and loads data; it
does not reconnect signals. No broad `disconnect()` call is used for ordinary view
signals, so unrelated listeners are preserved and repeated project operations do
not duplicate callbacks.

## Testing policy

- Component tests may inspect a component's own private state when required to
  verify its internal rendering or control behavior.
- Integration tests patch and assert public semantic methods, properties, and
  signals. They do not traverse from MainWindow through a child to a grandchild.
- Selection tests cover invalid IDs, reselection, signal counts, and silent restore.
- Navigation tests cover save/cancel/discard, outline autosave, event-bus binding,
  plan decisions, next-scene boundaries, recovery, versioning, and publication.

## Enforcement

`tests/test_ui_encapsulation_architecture.py` parses every Python module under
`app/ui` with `ast`. It rejects any single-underscore attribute access whose direct
receiver is not `self` or `cls`. The test has no allowlist. A second assertion
rejects MainWindow access to known SceneWorkspace implementation members, including
raw children and concrete controls.

When adding a cross-component interaction, add or extend a semantic method,
read-only property, or signal. Do not weaken the guard.
