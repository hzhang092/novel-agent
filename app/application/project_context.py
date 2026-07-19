"""Project-scoped application-service composition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.application.characters import CharacterApplicationService
from app.application.outlines import OutlineApplicationService
from app.application.story_bible import StoryBibleApplicationService


@dataclass
class ProjectApplicationContext:
    project_dir: Path
    characters: CharacterApplicationService
    story_bible: StoryBibleApplicationService
    outlines: OutlineApplicationService


def build_project_application(
    project_dir: Path,
    *,
    event_bus: object | None = None,
    provider_factory: Callable[[], object] | None = None,
) -> ProjectApplicationContext:
    project_dir = Path(project_dir)
    characters = CharacterApplicationService(project_dir, event_bus=event_bus)
    story_bible = StoryBibleApplicationService(
        project_dir, provider_factory=provider_factory
    )
    return ProjectApplicationContext(
        project_dir=project_dir,
        characters=characters,
        story_bible=story_bible,
        outlines=OutlineApplicationService(
            project_dir,
            characters=characters,
            story_bible=story_bible,
        ),
    )
