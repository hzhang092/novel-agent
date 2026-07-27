# Local scene regeneration marks downstream scenes stale

Status: accepted

Regenerating an earlier scene creates a new Scene Revision for that scene only. Later scene prose is preserved and marked stale instead of being rewritten automatically, while state events and checkpoints are recomputed or invalidated by timeline order so storage remains consistent. Cascade regeneration can be added later as an explicit user action because silently rewriting downstream prose is destructive for authors.
