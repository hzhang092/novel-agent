# Project editing application layer

The project editors follow one dependency direction:

```text
Qt editor → app/application → storage/domain/pipeline adapters → project files
```

Qt editors own controls, dialogs, selection, dirty state, and unsaved drafts. They do not import operational storage, provider, or pipeline modules. `EditorLayoutStore` and the pure models in `app.storage.models` and `app.storage.bible_models` remain allowed historical exceptions.

Application services are project-scoped and Qt-independent:

- `CharacterApplicationService` owns character definitions, deletion impact, reference unlinking, presence queries, and concurrent event-sourced state edits.
- `StoryBibleApplicationService` owns Story Bible/style writes, deletion impact, usage queries, templates, suggestion providers, and transactional suggestion application.
- `OutlineApplicationService` owns complete-outline persistence and outline queries. Pure tree changes live in `app.domain.outline_operations`.
- `ProjectApplicationContext` constructs one shared service set per open project.

Storage retains file formats, atomic replacement, rollback primitives, legacy compatibility, and low-level repositories. Scene generation and publication remain in `MainWindow`; their asynchronous lifecycle is intentionally deferred to a separate refactor.
