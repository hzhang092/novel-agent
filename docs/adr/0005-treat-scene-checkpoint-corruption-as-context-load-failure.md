# Treat scene checkpoint corruption as context load failure

Status: accepted

Scene Checkpoints are derived state, so unrelated corrupt checkpoint files should not block loading current Character State. When a checkpoint is explicitly loaded for context assembly, corruption must surface as a visible failure instead of being treated as a missing checkpoint; rebuilding is allowed only when the source State Events can reproduce that checkpoint.
