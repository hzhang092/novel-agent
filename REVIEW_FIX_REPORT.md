# Phase 1–4 review verification and fixes

Date: 2026-07-17

The supplied review says it contains seven issues, but the objective file only
includes six findings, numbered 2 through 7. This report covers every supplied
finding.

## Verification status

| Finding | Status | Before | After |
| --- | --- | --- | --- |
| Unsaved Bible changes during project transitions | Confirmed and fixed | New/Open/window close bypass the Bible dirty check; sidebar departure only attempts an automatic save. | A shared Save/Discard/Cancel guard now covers navigation, New, Open, and window close. Cancel leaves World, Style, and Character edits in place; a failed save also blocks the transition. |
| Template Replace dangling character links | Confirmed and fixed | Snapshot removal unlinks scenes but leaves Character Definitions pointing at removed elements. | Snapshot application now fails before writing if removed elements have inbound Character Definition links, listing the affected characters and element IDs. |
| Referenced character deletion | Confirmed and fixed | Deletion removes files without checking scene POV/participants or relationship state. | POV references block deletion until the outline is changed. Participant and relationship references are named in the confirmation and can be explicitly unlinked. Outline updates, relationship events, and deletion share a rollback scope. |
| Supporting-character prompt data | Confirmed and fixed | Compaction preserves generation-enabled fields and Story Connections, but the Writer omits them. | The Writer now renders supporting personality, generation-enabled custom fields, and resolved Story Connections; excluded fields remain absent. |
| Bible element path traversal | Confirmed and fixed | Unrestricted IDs are interpolated directly into paths and loaded YAML identity is not checked. | IDs are restricted to safe path segments, resolved paths must remain under `bible/elements`, and loaded YAML IDs must match the requested manifest ID. |
| World usage indexing | Confirmed and fixed | `all_element_counts()` performs one complete scene/file scan per element, then selection scans again. | A cached usage index now loads each scene record, marker, and prose once per rebuild; selected-element details reuse the same index. Bible mutations and re-entry after outline/writing edits invalidate it. |

## Verification commands

Initial focused reproduction command:

```powershell
conda activate fourteen; python -m pytest <nine focused node IDs> -q
```

Observed before fixes: all six supplied findings reproduced. Dirty navigation,
project opening, and close cancellation failed; snapshot replacement did not
reject a character-linked removal; supporting prompt fields were absent; unsafe
IDs were accepted; and two elements caused two reads of every scene artifact.
The character-deletion harness initially had a missing test import, which was
corrected before judging that finding.

Security fix verification:

```text
python -m pytest tests/test_bible_repository.py tests/test_bible_models.py -q
14 passed
```

Supporting-character prompt fix verification:

```text
python -m pytest tests/test_writer_agent.py tests/test_character_context.py -q
13 passed
```

Template replacement fix verification:

```text
python -m pytest tests/test_world_bible_service.py tests/test_bible_template_integration.py tests/test_template_merge.py -q
32 passed
```

Usage-index fix verification:

```text
python -m pytest tests/test_story_usage.py tests/test_world_bible_editor.py tests/test_story_usage_panel.py -q
27 passed
```

Dirty-transition fix verification:

```text
python -m pytest tests/test_main_window_bible_navigation.py -q
16 passed
```

Character-deletion fix verification:

```text
python -m pytest tests/test_character_storage.py tests/test_character_editor.py tests/test_repository_characters.py -q
57 passed
```

Combined affected-area verification:

```text
python -m pytest <14 affected test modules> -q
159 passed
```

Full-suite verification:

```text
python -m pytest -q
629 passed
```

## Deliberate scope decisions

- Template replacement blocks removal when Character Definitions still point at
  an element. It does not silently rewrite character data.
- POV character deletion is blocked rather than guessing a replacement.
- The usage index remains synchronous because the measured redundant I/O was
  removed. Debouncing or a background thread is not added without evidence that
  one indexed pass still causes visible UI delay.
- The objective's extra suggestions about legacy migration and prompt snapshots
  were not separate reported findings, so they were not expanded into unrelated
  refactors.
