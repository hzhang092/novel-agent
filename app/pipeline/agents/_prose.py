"""Shared prose selection for post-processing agents."""

PROSE_LIMIT = 6000


def select_prose_excerpt(prose: str) -> str:
    """Keep complete prose when possible, otherwise preserve both ends."""
    if len(prose) <= PROSE_LIMIT:
        return prose

    half = PROSE_LIMIT // 2
    return (
        f"{prose[:half]}\n\n"
        f"... (中间省略，正文共 {len(prose)} 字) ...\n\n"
        f"{prose[-half:]}"
    )
