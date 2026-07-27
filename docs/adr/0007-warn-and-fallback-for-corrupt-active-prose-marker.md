# Warn and fallback for corrupt active prose marker

Status: accepted

Active Prose Version markers are pointers to prose files, not the prose itself. If a `*.active.yaml` marker is corrupt, scene loading should fall back to the latest available prose with a visible warning instead of failing or returning empty content.
