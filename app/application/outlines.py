"""Outline editor persistence and queries."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.application.characters import CharacterApplicationService
from app.application.results import OutlineEditorSnapshot
from app.application.story_bible import StoryBibleApplicationService
from app.storage.bible_repository import rollback_files
from app.storage.models import VolumeOutline
from app.storage.project_files import (
    delete_volume_outline,
    list_volume_ids,
    load_all_volumes,
    save_volume_outline,
)


class OutlineApplicationService:
    def __init__(
        self,
        project_dir: Path,
        *,
        characters: CharacterApplicationService | None = None,
        story_bible: StoryBibleApplicationService | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self._characters = characters or CharacterApplicationService(self.project_dir)
        self._story_bible = story_bible

    def load_editor_snapshot(self) -> OutlineEditorSnapshot:
        bible_elements = ()
        if (self.project_dir / "bible" / "manifest.yaml").exists():
            if self._story_bible is None:
                self._story_bible = StoryBibleApplicationService(self.project_dir)
            bible_elements = tuple(
                self._story_bible.load_editor_snapshot().bible.elements
            )
        return OutlineEditorSnapshot(
            volumes=tuple(load_all_volumes(self.project_dir)),
            characters=self._characters.list_characters(),
            bible_elements=bible_elements,
        )

    def save_outline(
        self, volumes: Sequence[VolumeOutline]
    ) -> tuple[VolumeOutline, ...]:
        target_ids = [volume.id for volume in volumes]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("Outline contains duplicate volume IDs")
        current_ids = set(list_volume_ids(self.project_dir))
        touched = [
            self.project_dir / "outline" / f"{volume_id}.yaml"
            for volume_id in current_ids | set(target_ids)
        ]
        with rollback_files(touched):
            for volume in volumes:
                save_volume_outline(self.project_dir, volume)
            for stale_id in current_ids - set(target_ids):
                delete_volume_outline(self.project_dir, stale_id)
        return tuple(volume.model_copy(deep=True) for volume in volumes)

    def chapter_for_scene(self, scene_id: str) -> str | None:
        for volume in load_all_volumes(self.project_dir):
            for chapter in volume.chapters:
                if any(scene.id == scene_id for scene in chapter.scenes):
                    return chapter.id
        return None

    def scene_element_ids(self, scene_id: str) -> frozenset[str]:
        for volume in load_all_volumes(self.project_dir):
            for chapter in volume.chapters:
                for scene in chapter.scenes:
                    if scene.id == scene_id:
                        return frozenset(scene.world_element_ids)
        return frozenset()
