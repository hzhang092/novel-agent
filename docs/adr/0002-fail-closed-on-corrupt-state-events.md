# Fail closed on corrupt state events

Status: accepted

State Events are the source of truth for Character State, so a corrupt `events.jsonl` means the project state cannot be trusted. Any invalid line invalidates the whole event log; the app should fail closed with a visible error that names the broken file and character instead of opening in degraded mode. Missing optional derived files may be rebuilt, but corrupt source-of-truth files must be surfaced for repair.
