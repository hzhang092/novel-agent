# Publish scene revisions through one canonical seam

Status: accepted

Generated prose is stored as a Draft Scene Revision and cannot change canon. `publish_scene_revision` is the only interface allowed to activate prose, expose revision-scoped facts and State Events, rebuild derived state, or mark downstream scenes stale.

The active scene marker contains the prose version and revision ID and is replaced atomically. Facts, events, and checkpoints may be staged before that replacement, but retrieval ignores them unless their revision matches the active marker. A small pending-publication journal completes derived rebuilds after an interrupted post-commit operation. Existing version-only markers, legacy generation records, and facts without revision IDs remain readable and are upgraded only when rewritten.
