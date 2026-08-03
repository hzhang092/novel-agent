"""Application seams for Quick Creation projections and safe replanning."""

from __future__ import annotations

import json
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.application.errors import ConcurrentModificationError, OperationBlockedError
from app.application.characters import CharacterApplicationService
from app.application.story_bible import StoryBibleApplicationService
from app.application.story_designer import StoryDesignerService
from app.providers.base import LLMProvider
from app.storage.models import (
    ActiveReplanDraft,
    ActiveStoryPatchDraft,
    ChapterCardEditPreview,
    ChapterCardProjection,
    ChapterCardStatus,
    ChapterOutline,
    CharacterTier,
    QuickCharacterProjection,
    QuickStoryProjection,
    ReplanPreview,
    StoryArcProjection,
    StoryBrief,
    StoryBriefDrift,
    StoryPatchPreview,
)
from app.storage.project_files import (
    get_active_scene_revision_id,
    load_all_characters,
    load_all_volumes,
    load_canon_facts,
    load_planning,
    load_scene_generation_record,
    list_scene_prose_versions,
    load_scene_prose,
    load_scene_summaries,
    save_planning,
    save_volume_outline,
)


class QuickPlanningService:
    def __init__(
        self,
        project_dir: Path,
        *,
        provider_factory: Callable[[], LLMProvider] | None = None,
        run_guard: Any | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self._designer = StoryDesignerService(
            self.project_dir,
            provider_factory=provider_factory,
            run_guard=run_guard,
        )

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
        chapter.title, chapter.summary = preview.title, preview.summary
        scene.ending_hook = preview.ending_hook
        self._save_chapter(chapter)
        return self._card(chapter)

    def save_brief(self, brief: StoryBrief) -> StoryBrief:
        return self._designer.save_brief(brief)

    def record_brief_baseline(self) -> StoryBrief:
        planning = load_planning(self.project_dir)
        if planning.story_brief is None:
            raise OperationBlockedError("A Story Brief is required")
        planning.approved_brief = planning.story_brief.model_copy(deep=True)
        save_planning(self.project_dir, planning)
        return planning.approved_brief

    def brief_drift(self) -> StoryBriefDrift:
        planning = load_planning(self.project_dir)
        baseline = planning.approved_brief
        current = planning.story_brief
        if baseline is None or current is None:
            return StoryBriefDrift()
        old, new = baseline.model_dump(), current.model_dump()
        return StoryBriefDrift(
            changed_fields=[field for field in old if old[field] != new[field] and field != "revision"]
        )

    async def generate_story_patch(self, instruction: str) -> ActiveStoryPatchDraft:
        base_revision = self._canon_revision()
        response = await self._designer.generate_structured(
            self._story_patch_messages(instruction), StoryPatchPreview
        )
        draft = ActiveStoryPatchDraft.model_validate(response.model_dump())
        if base_revision != self._canon_revision():
            raise ConcurrentModificationError("The story changed while generating the patch")
        draft.base_revision = base_revision
        self._validate_story_patch(draft)
        planning = load_planning(self.project_dir)
        planning.active_draft = draft
        save_planning(self.project_dir, planning)
        return draft

    def apply_story_patch(self, draft: StoryPatchPreview) -> None:
        self._assert_current_draft(draft, ActiveStoryPatchDraft)
        self._validate_story_patch(draft)
        characters = {
            character.core.id: character.core.model_copy(deep=True)
            for character in load_all_characters(self.project_dir)
        }
        overview = StoryBibleApplicationService(
            self.project_dir
        ).load_editor_snapshot().bible.overview.model_copy(deep=True)
        changed_characters = set()
        overview_changed = False
        for operation in draft.operations:
            if operation.target == "character":
                setattr(
                    characters[operation.target_id],
                    operation.field,
                    operation.value,
                )
                changed_characters.add(operation.target_id)
            else:
                setattr(overview, operation.field, operation.value)
                overview_changed = True
        character_service = CharacterApplicationService(self.project_dir)
        for character_id in changed_characters:
            character_service.save_definition(characters[character_id])
        if overview_changed:
            StoryBibleApplicationService(self.project_dir).save_overview(overview)
        self._mark_prose_from(0)
        self._clear_active_draft()

    def cancel_story_patch(self, draft: StoryPatchPreview) -> None:
        self._assert_current_draft(draft, ActiveStoryPatchDraft)
        self._clear_active_draft(ActiveStoryPatchDraft)

    def preview_replan(self) -> ReplanPreview:
        chapters = [chapter for volume in load_all_volumes(self.project_dir) for chapter in volume.chapters]
        published = [chapter.id for chapter in chapters if self._has_published_prose(chapter)]
        future = [chapter.id for chapter in chapters if chapter.id not in published]
        return ReplanPreview(
            base_revision=self._canon_revision(),
            future_chapter_ids=future,
        )

    async def generate_replan(self, instruction: str = "") -> ActiveReplanDraft:
        base = self.preview_replan()
        published = self._published_chapter_ids()
        response = await self._designer.generate_structured(
            self._replan_messages(base, published, instruction), ReplanPreview
        )
        draft = ActiveReplanDraft.model_validate(response.model_dump())
        draft.base_revision = base.base_revision
        draft.future_chapter_ids = base.future_chapter_ids
        operation_targets = {
            operation.get("chapter_id", "") for operation in draft.operations
        }
        draft.published_chapter_ids = [
            chapter_id
            for chapter_id in published
            if chapter_id in set(draft.published_chapter_ids) | operation_targets
        ]
        draft.downstream_review_chapter_ids = self._review_ids_from(
            set(draft.published_chapter_ids)
        )
        planning = load_planning(self.project_dir)
        planning.active_draft = draft
        save_planning(self.project_dir, planning)
        return draft

    async def replan(self, instruction: str = "") -> ActiveReplanDraft:
        return await self.generate_replan(instruction)

    def apply_replan(
        self,
        preview: ReplanPreview,
        *,
        confirm_published: bool = False,
    ) -> ReplanPreview:
        planning = load_planning(self.project_dir)
        if isinstance(planning.active_draft, ActiveReplanDraft):
            self._assert_current_draft(preview, ActiveReplanDraft)
        elif preview.base_revision != self._canon_revision():
            raise ConcurrentModificationError("The story changed; regenerate the replan")
        if preview.published_chapter_ids and not confirm_published:
            raise OperationBlockedError("Published chapter changes require extra confirmation")
        published = set(self._published_chapter_ids())
        proposed_published = set(preview.published_chapter_ids)
        if any(
            operation.get("chapter_id") in published
            and operation.get("chapter_id") not in proposed_published
            and operation.get("field") != "title"
            for operation in preview.operations
        ):
            raise OperationBlockedError("Published chapter changes must be separated for confirmation")
        story_affecting = preview.story_affecting and any(
            operation.get("field") != "title" for operation in preview.operations
        )
        for operation in preview.operations:
            chapter_id = operation.get("chapter_id", "")
            field = operation.get("field", "")
            if chapter_id and field in {"title", "summary"}:
                chapter = self._chapter(chapter_id).model_copy(deep=True)
                setattr(chapter, field, operation.get("value", ""))
                if story_affecting and self._has_prose(chapter):
                    chapter.needs_review = True
                self._save_chapter(chapter)
        if story_affecting:
            self._mark_affected_chapters(preview)
        self._clear_active_draft(ActiveReplanDraft)
        return preview

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

    def _mark_affected_chapters(self, preview: ReplanPreview) -> None:
        chapters = [chapter for volume in load_all_volumes(self.project_dir) for chapter in volume.chapters]
        touched = {
            operation.get("chapter_id", "")
            for operation in preview.operations
            if operation.get("field") != "title"
        }
        if not touched:
            return
        start = next((index for index, chapter in enumerate(chapters) if chapter.id in touched), len(chapters))
        self._mark_prose_from(start)

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

    def _published_chapter_ids(self) -> list[str]:
        return [
            chapter.id
            for volume in load_all_volumes(self.project_dir)
            for chapter in volume.chapters
            if self._has_published_prose(chapter)
        ]

    def _review_ids_from(self, touched: set[str]) -> list[str]:
        chapters = [
            chapter
            for volume in load_all_volumes(self.project_dir)
            for chapter in volume.chapters
        ]
        start = next(
            (index for index, chapter in enumerate(chapters) if chapter.id in touched),
            len(chapters),
        )
        return [
            chapter.id for chapter in chapters[start:] if self._has_prose(chapter)
        ]

    def _mark_prose_from(self, start: int) -> None:
        chapters = [
            chapter
            for volume in load_all_volumes(self.project_dir)
            for chapter in volume.chapters
        ]
        for chapter in chapters[start:]:
            if self._has_prose(chapter):
                updated = chapter.model_copy(deep=True)
                updated.needs_review = True
                self._save_chapter(updated)

    def _canon_payload(self) -> dict[str, Any]:
        bible = StoryBibleApplicationService(
            self.project_dir
        ).load_editor_snapshot()
        planning = load_planning(self.project_dir)
        return {
            "bible": bible.bible.model_dump(mode="json"),
            "style": bible.style_guide.model_dump(mode="json"),
            "characters": [
                character.model_dump(mode="json")
                for character in load_all_characters(self.project_dir)
            ],
            "outline": [
                volume.model_dump(mode="json")
                for volume in load_all_volumes(self.project_dir)
            ],
            "summaries": [
                summary.model_dump(mode="json")
                for summary in load_scene_summaries(self.project_dir)
            ],
            "canon_facts": [
                fact.model_dump(mode="json")
                for fact in load_canon_facts(self.project_dir)
            ],
            "direction": {
                "brief": (
                    planning.story_brief.model_dump(mode="json")
                    if planning.story_brief
                    else None
                ),
                "approved_proposal": (
                    planning.approved_proposal.model_dump(mode="json")
                    if planning.approved_proposal
                    else None
                ),
            },
        }

    def _canon_revision(self) -> int:
        encoded = json.dumps(
            self._canon_payload(), ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        checksum = zlib.crc32(encoded)
        # ponytail: full scene scan is simplest; add a revision manifest only if profiling demands it.
        scenes_dir = self.project_dir / "scenes"
        if scenes_dir.exists():
            for path in sorted(item for item in scenes_dir.rglob("*") if item.is_file()):
                checksum = zlib.crc32(
                    path.relative_to(self.project_dir).as_posix().encode("utf-8"),
                    checksum,
                )
                checksum = zlib.crc32(path.read_bytes(), checksum)
        return max(1, checksum)

    def _assert_current_draft(self, draft, draft_type: type) -> None:
        planning = load_planning(self.project_dir)
        if (
            not isinstance(planning.active_draft, draft_type)
            or planning.active_draft.base_revision != draft.base_revision
            or planning.active_draft.model_dump(mode="json")
            != draft.model_dump(mode="json")
            or draft.base_revision != self._canon_revision()
        ):
            raise ConcurrentModificationError("The story changed; regenerate the patch")

    def _clear_active_draft(self, draft_type: type | None = None) -> None:
        planning = load_planning(self.project_dir)
        if draft_type is None or isinstance(planning.active_draft, draft_type):
            planning.active_draft = None
            save_planning(self.project_dir, planning)

    def _validate_story_patch(self, draft: StoryPatchPreview) -> None:
        characters = {
            character.core.id: character.core
            for character in self._main_characters()
        }
        character_fields = {
            "name",
            "identity",
            "personality",
            "background",
            "long_term_goal",
        }
        overview_fields = {
            "geography",
            "rules",
            "taboos",
            "technology_level",
            "social_structure",
        }
        for operation in draft.operations:
            if operation.target == "character" and (
                operation.target_id not in characters
                or operation.field not in character_fields
                or (
                    operation.value is not None
                    and not isinstance(operation.value, str)
                )
            ):
                raise ValueError("Quick Story can only patch routine fields on main characters")
            if operation.target == "overview" and (
                operation.field not in overview_fields
                or (
                    operation.field in {"rules", "taboos"}
                    and not isinstance(operation.value, list)
                )
                or (
                    operation.field not in {"rules", "taboos"}
                    and not isinstance(operation.value, str)
                )
            ):
                raise ValueError("Quick Story can only patch core setting overview fields")

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

    def _story_patch_messages(self, instruction: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "Return only StoryPatchPreview. Only patch routine main-character "
                    "fields or the core World Overview. Never patch relationships, "
                    "custom fields, character state, or power-system details."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "current_story": self.story_projection().model_dump(
                            mode="json"
                        ),
                        "instruction": instruction,
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    @staticmethod
    def _replan_messages(
        base: ReplanPreview, published: list[str], instruction: str
    ) -> list[dict[str, str]]:
        return [{"role": "system", "content": "Return only ReplanPreview. Keep current canon as truth. Default operations to future unpublished chapters. Put every proposed published-chapter target in published_chapter_ids for separate confirmation."}, {"role": "user", "content": json.dumps({"base": base.model_dump(), "published_chapter_ids": published, "instruction": instruction}, ensure_ascii=False)}]

BriefDrift = StoryBriefDrift
