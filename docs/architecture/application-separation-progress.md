# Application separation progress

## Baseline

- `conda activate fourteen; python -m pytest -q`
- 635 passed in 26.23s; no existing failures.

## Checkpoint 0 — Baseline and dependency guard

Status: complete

### Changed
- Added application errors, immutable results, project composition, architecture rules, and an AST dependency test with no allowlist.

### Verified
- `python -m pytest -q tests/test_application_architecture.py` — 2 passed.

### Remaining
- None.

### Risks or compatibility notes
- `notes.md` was already untracked and remains untouched.

## Checkpoint 1 — Character application operations

Status: complete

### Changed
- Added character definition, deletion-impact, reference-unlinking, presence, and concurrent event-sourced state-edit use cases.
- Migrated `CharacterEditorView` while retaining its public `load_project_dir()` wrapper.

### Verified
- Character service, storage, event-sourcing, and UI checks — 86 passed.

### Remaining
- None.

### Risks or compatibility notes
- Existing character files, definition revisions, initial events, and state events keep their prior formats.

## Checkpoint 2 — Story Bible application operations

Status: complete

### Changed
- Added Story Bible/style transactions, typed deletion impact, usage/source queries, AI suggestion lifecycle, and template draft operations.
- Migrated `WorldBibleEditorView` and `BibleEditorView`.

### Verified
- Story Bible service, repository, transaction, usage, assistant, template, and UI checks — 102 passed.

### Remaining
- None.

### Risks or compatibility notes
- Templates remain staged in memory until Save; prose mentions are reported but not rewritten during deletion.

## Checkpoint 3 — Outline application and domain operations

Status: complete

### Changed
- Added complete-outline persistence, stale-volume reconciliation, and pure typed tree operations.
- Migrated `OutlineEditorView`.
- Corrected aggregate saves so removed volumes no longer leave stale YAML files; rollback covers all touched volume files.

### Verified
- Outline application, pure operations, UI, storage, and repository checks — 58 passed.

### Remaining
- None.

### Risks or compatibility notes
- Volume YAML schemas and existing load behavior are unchanged.

## Checkpoint 4 — Shared project application context

Status: complete

### Changed
- `MainWindow` constructs and injects one context per opened or created project.
- Character and Story Bible services are shared with the outline service, and project switches replace the context.

### Verified
- Shared-context and migrated-editor integration checks — 116 passed.

### Remaining
- None.

### Risks or compatibility notes
- Scene generation, approvals, retries, and publication remain unchanged in `MainWindow`.

## Checkpoint 5 — Enforce the boundary

Status: complete

### Changed
- Removed forbidden operational imports from all four target editors.
- Documented the dependency direction and new package structure.

### Verified
- `python -m compileall app tests` — passed.
- Required non-Qt application/domain tests — 36 passed; architecture and shared-context tests bring the new-test total to 39 passed.
- Required migrated UI tests — 115 passed.
- `python -m pytest -q` — 675 passed in 28.34s, with no skips.
- Required forbidden-import `git grep` — no matches.

### Remaining
- None.

### Risks or compatibility notes
- Narrow `load_project_dir()` wrappers remain for existing widget callers and tests.
