"""Shared prose selection for post-processing agents."""


def select_prose_excerpt(prose: str) -> str:
    """Return the complete scene so post-processors cannot miss events."""
    return prose
