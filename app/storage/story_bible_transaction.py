"""One rollback boundary for mixed Story Bible writes."""

from __future__ import annotations

from collections.abc import Iterable

from app.storage.bible_repository import rollback_files
from app.storage.models import CharacterCore


class StoryBibleTransaction:
    def __init__(self, bible_service, character_service=None) -> None:
        self.bible_service = bible_service
        self.character_service = character_service

    def apply(self, overview, elements, characters: Iterable[CharacterCore] = ()):
        characters = list(characters)
        element_paths = [
            self.bible_service.repository.elements_dir / f"{element.id}.yaml"
            for element in elements
        ]
        paths = self.bible_service._transaction_paths(element_paths)
        if self.character_service is not None:
            paths.extend(
                self.character_service.definition_path(core.id)
                for core in characters
            )
        with rollback_files(paths):
            saved = self.bible_service.apply_snapshot(overview, elements)
            if self.character_service is not None:
                for core in characters:
                    self.character_service.save(core)
        return saved
