"""Canonical projections and Chapter Card edits for Quick Creation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.application.story_bible import StoryBibleApplicationService
from app.storage.models import (
    ChapterCardEditPreview,
    ChapterCardProjection,
    ChapterCardStatus,
    ChapterOutline,
    CharacterTier,
    QuickCharacterProjection,
    QuickStoryProjection,
    StoryArcProjection,
)
from app.storage.project_files import (
    get_active_scene_revision_id,
    load_all_characters,
    load_all_volumes,
    load_planning,
    load_scene_generation_record,
    list_scene_prose_versions,
    load_scene_prose,
    save_volume_outline,
)


class QuickPlanningService:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)

    def story_projection(self) -> QuickStoryProjection:
        characters = [
            QuickCharacterProjection(
                id=character.core.id,
                name=character.core.name,
                identity=character.core.identity,
                personality=character.core.personality,
                long_term_goal=character.core.long_term_goal,
            )
            for character in self._main_characters()
        ]
        overview = StoryBibleApplicationService(
            self.project_dir
        ).load_editor_snapshot().bible.overview
        return QuickStoryProjection(
            arcs=[
                StoryArcProjection(
                    id=volume.id,
                    story_id=volume.story_id,
                    title=volume.title,
                    summary=volume.summary,
                    chapter_cards=[
                        self._card(chapter, volume.id) for chapter in volume.chapters
                    ],
                )
                for volume in load_all_volumes(self.project_dir)
            ],
            main_characters=characters,
            core_setting=overview,
        )

    def chapter_card(self, chapter_id: str) -> ChapterCardProjection:
        chapter, volume_id = self._chapter_with_volume(chapter_id)
        return self._card(chapter, volume_id)

    def preview_card_edit(
        self,
        chapter_id: str,
        edits: dict[str, str] | None = None,
        *,
        title: str | None = None,
        summary: str | None = None,
        ending_hook: str | None = None,
    ) -> ChapterCardEditPreview:
        chapter = self._chapter(chapter_id)
        scene = self._scene(chapter)
        values = {"title": chapter.title, "summary": chapter.summary, "ending_hook": scene.ending_hook}
        values.update(edits or {})
        for key, value in {"title": title, "summary": summary, "ending_hook": ending_hook}.items():
            if value is not None:
                values[key] = value
        changed = [field for field in values if values[field] != {"title": chapter.title, "summary": chapter.summary, "ending_hook": scene.ending_hook}[field]]
        return ChapterCardEditPreview(
            chapter_id=chapter_id,
            changed_fields=changed,
            title=values["title"],
            summary=values["summary"],
            ending_hook=values["ending_hook"],
        )

    def apply_card_edit(self, preview: ChapterCardEditPreview) -> ChapterCardProjection:
        chapter = self._chapter(preview.chapter_id).model_copy(deep=True)
        scene = self._scene(chapter)
        story_affecting = (
            chapter.summary != preview.summary
            or scene.ending_hook != preview.ending_hook
        )
        chapter.title, chapter.summary = preview.title, preview.summary
        scene.ending_hook = preview.ending_hook
        if story_affecting and self._has_prose(chapter):
            chapter.needs_review = True
        self._save_chapter(chapter)
        if story_affecting:
            chapters = [
                item
                for volume in load_all_volumes(self.project_dir)
                for item in volume.chapters
            ]
            start = next(
                index for index, item in enumerate(chapters) if item.id == chapter.id
            )
            for later in chapters[start + 1 :]:
                if self._has_prose(later):
                    later = later.model_copy(update={"needs_review": True})
                    self._save_chapter(later)
        return self._card(chapter)

    def _card(
        self, chapter: ChapterOutline, volume_id: str | None = None
    ) -> ChapterCardProjection:
        scene = self._scene(chapter, required=False)
        return ChapterCardProjection(
            id=chapter.id,
            volume_id=volume_id or chapter.volume_id,
            scene_id=scene.id if scene else "",
            title=chapter.title,
            summary=chapter.summary,
            ending_hook=scene.ending_hook if scene else "",
            status=self._status(chapter),
        )

    def _status(self, chapter: ChapterOutline) -> ChapterCardStatus:
        if chapter.needs_review:
            return ChapterCardStatus.NEEDS_REVIEW
        records = self._records(chapter)
        published = self._has_published_prose(chapter)
        active_revision_id = (
            get_active_scene_revision_id(self.project_dir, self._scene(chapter).id)
            if published
            else ""
        )
        active = next(
            (record for record in records if record.revision_id == active_revision_id),
            None,
        )
        drafts = [record for record in records if record.status == "draft"]
        has_newer_draft = bool(drafts) and (
            active is None
            or max(record.revision_number for record in drafts) > active.revision_number
        )
        if published and has_newer_draft:
            return ChapterCardStatus.NEW_DRAFT
        if not published and self._has_prose(chapter):
            return ChapterCardStatus.DRAFT
        return ChapterCardStatus.APPROVED if published else ChapterCardStatus.UNWRITTEN

    def _records(self, chapter: ChapterOutline) -> list[Any]:
        scene = self._scene(chapter, required=False)
        if scene is None:
            return []
        records = []
        versions = set(list_scene_prose_versions(self.project_dir, chapter.id, scene.id))
        versions.update(
            path.name.split(".")[-3]
            for path in (self.project_dir / "scenes" / chapter.id).glob(f"{scene.id}.v*.gen.json")
        )
        for version in versions:
            if version == "legacy":
                continue
            record = load_scene_generation_record(self.project_dir, scene.id, version=version)
            if record is not None:
                records.append(record)
        return records

    def _has_published_prose(self, chapter: ChapterOutline) -> bool:
        scene = self._scene(chapter, required=False)
        return bool(scene and get_active_scene_revision_id(self.project_dir, scene.id))

    def _has_prose(self, chapter: ChapterOutline) -> bool:
        scene = self._scene(chapter, required=False)
        return bool(
            scene
            and (
                self._records(chapter)
                or list_scene_prose_versions(self.project_dir, chapter.id, scene.id)
                or load_scene_prose(self.project_dir, chapter.id, scene.id)
            )
        )

    def _chapter(self, chapter_id: str) -> ChapterOutline:
        return self._chapter_with_volume(chapter_id)[0]

    def _chapter_with_volume(self, chapter_id: str) -> tuple[ChapterOutline, str]:
        for volume in load_all_volumes(self.project_dir):
            for chapter in volume.chapters:
                if chapter.id == chapter_id:
                    return chapter, volume.id
        raise KeyError(f"Chapter not found: {chapter_id}")

    @staticmethod
    def _scene(chapter: ChapterOutline, *, required: bool = True):
        if len(chapter.scenes) > 1:
            raise ValueError("Quick Creation does not support multi-scene chapters")
        if not chapter.scenes:
            if required:
                raise ValueError("Quick Creation requires exactly one scene per chapter")
            return None
        return chapter.scenes[0]

    def _save_chapter(self, chapter: ChapterOutline) -> None:
        volume = next(
            volume
            for volume in load_all_volumes(self.project_dir)
            if any(item.id == chapter.id for item in volume.chapters)
        )
        volume = volume.model_copy(deep=True)
        chapter.volume_id = volume.id
        volume.chapters = [chapter if item.id == chapter.id else item for item in volume.chapters]
        save_volume_outline(self.project_dir, volume)

    def _main_characters(self) -> list[Any]:
        planning = load_planning(self.project_dir)
        proposal_names = {
            name.casefold()
            for name in (
                planning.approved_proposal.main_characters
                if planning.approved_proposal
                else []
            )
        }
        return [
            character
            for character in load_all_characters(self.project_dir)
            if character.core.tier is CharacterTier.MAJOR
            or character.core.name.casefold() in proposal_names
        ]
