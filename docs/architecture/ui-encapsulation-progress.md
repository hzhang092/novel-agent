# UI encapsulation progress

Baseline: 675 tests passed in 36.64 seconds before edits.

## Checkpoint 0 — Baseline audit and architecture guard

Status: complete

### Contracts added

- AST detector for foreign private access under `app/ui`.
- Explicit `MainWindow` guard for raw `SceneWorkspaceView` children and controls.

### Private accesses removed

- None; this checkpoint records the migration baseline.

### Audited violations

| Caller | Callee | Private member | Replacement checkpoint and contract |
| --- | --- | --- | --- |
| `bible_editor.py` | `CharacterEditorView` | `_on_add_character` | 2 — `create_character()` |
| `bible_editor.py` | `WorldBibleEditorView` | `_element_list` | 2 — `show_overview()` |
| `bible_editor.py` | `CharacterEditorView` | `_characters`, `_current_id`, `_gather_core` | 2 — `character_cores_in_memory()` and `selected_character_id` |
| `bible_editor.py` | `WorldBibleEditorView` | `_resolve_dirty_before_switch` | 2 — `prepare_for_navigation()` |
| `bible_element_editor.py` | `KeyValueTable` | `_table` | 1 — `rows()` |
| `character_editor.py` | `KeyValueTable` | `_table` | 1 — `rows()` |
| `character_state_edit_dialog.py` | `KeyValueTable` | `_table` | 1 — `rows()` |
| `world_bible_editor.py` | `BibleElementList` | `_find_item`, `_tree` | 1 — `restore_selection()` |
| `main_window.py` | `OutlineEditorView` | `_select_by_id`, `_refresh_world_elements`, `_project_dir`, `_on_save` | 5 — outline facade |
| `main_window.py` | `BibleEditorView` | `_project_dir`, `_character_tab`, `_world_tab` | 5 — Bible facade |
| `main_window.py` | `SceneWorkspaceView` | `_current_scene_id`, `_current_chapter_id`, `_status_label`, `_next_scene_btn`, `_continue_review_btn` | 5 — workspace facade |
| `main_window.py` | `SceneWorkspaceView` children | `editor`, `trace_panel`, `planner_checkpoint`, `fact_approval` | 4 and 5 — private children and workspace facade |

### Verification

- `python -m pytest -q` — 675 passed before edits.
- `python -m pytest tests/test_ui_encapsulation_architecture.py -q` — 3 passed.

### Remaining violations

- 22 unique private-access baseline entries and four raw workspace child names.
