"""Story Bible, style, template, and suggestion use cases."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from app.application.errors import ApplicationNotFoundError, OperationBlockedError
from app.application.results import (
    ElementDeletionImpact,
    ElementUsageCounts,
    StoryBibleEditorSnapshot,
)
from app.domain.story_usage import ElementUsageSummary, StoryUsageKind, StoryUsageService
from app.pipeline.agents.bible_assistant import BibleAssistantAgent
from app.pipeline.bible_suggestions import BibleSuggestion, apply_bible_suggestions
from app.storage.bible_models import (
    BibleElement,
    BibleElementRelation,
    WorldOverview,
)
from app.storage.bible_repository import WorldBibleService, rollback_files
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.models import CharacterCore, CharacterElementRelation, StyleGuide
from app.storage.project_files import (
    list_character_ids,
    load_all_volumes,
    load_project,
    load_scene_prose,
    save_style_guide,
)
from app.utils.template_merge import (
    StoryTemplate,
    StoryTemplateApplication,
    StoryTemplateReplacePreview,
    TemplateMergeMode,
    apply_story_template,
    merge_style_guide,
    preview_story_template_replace,
)


class StoryBibleApplicationService:
    def __init__(
        self,
        project_dir: Path,
        *,
        provider_factory: Callable[[], object] | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self._bible = WorldBibleService(self.project_dir)
        self._characters = CharacterDefinitionService(self.project_dir)
        self._usage = StoryUsageService(self.project_dir)
        self._provider_factory = provider_factory or self._default_provider

    def load_editor_snapshot(self) -> StoryBibleEditorSnapshot:
        bible = self._bible.load()
        return StoryBibleEditorSnapshot(
            bible=bible,
            style_guide=load_project(self.project_dir).style_guide,
        )

    def load_element(self, element_id: str) -> BibleElement:
        try:
            return self._bible.repository.load(element_id)
        except FileNotFoundError as error:
            raise ApplicationNotFoundError(str(error)) from error

    def save_overview(self, overview: WorldOverview) -> None:
        self._bible.save_overview(overview)
        self._usage.invalidate()

    def save_element(self, element: BibleElement) -> BibleElement:
        saved = self._bible.save_element(element)
        self._usage.invalidate()
        return saved

    def save_snapshot(
        self, overview: WorldOverview, elements: Sequence[BibleElement]
    ) -> tuple[BibleElement, ...]:
        saved = tuple(self._bible.apply_snapshot(overview, list(elements)))
        self._usage.invalidate()
        return saved

    def save_style(self, style: StyleGuide) -> StyleGuide:
        paths = [self.project_dir / "project.yaml", self.project_dir / "style.yaml"]
        with rollback_files(paths):
            save_style_guide(self.project_dir, style)
        return load_project(self.project_dir).style_guide

    def inbound_element_relations(
        self, element_id: str
    ) -> tuple[tuple[BibleElement, BibleElementRelation], ...]:
        return tuple(self._bible.repository.get_inbound_relations(element_id))

    def inbound_character_relations(
        self, element_id: str
    ) -> tuple[tuple[CharacterCore, CharacterElementRelation], ...]:
        return tuple(self._characters.characters_referencing_element(element_id))

    def element_usage(self, element_id: str) -> ElementUsageSummary:
        return self._usage.element_usage(element_id)

    def all_element_usage_counts(self) -> Mapping[str, int]:
        return self._usage.all_element_counts()

    def invalidate_usage(self) -> None:
        self._usage.invalidate()

    def inspect_element_deletion(self, element_id: str) -> ElementDeletionImpact:
        element = self.load_element(element_id)
        scenes = self.element_usage(element_id).scenes
        counts = ElementUsageCounts(
            explicit_outline=sum(
                StoryUsageKind.EXPLICIT_OUTLINE in scene.usage_kinds for scene in scenes
            ),
            generation_context=sum(
                StoryUsageKind.GENERATION_CONTEXT in scene.usage_kinds for scene in scenes
            ),
            prose_mention=sum(
                StoryUsageKind.PROSE_MENTION in scene.usage_kinds for scene in scenes
            ),
        )
        return ElementDeletionImpact(
            element_id=element_id,
            element_name=element.name,
            inbound_element_count=len(self.inbound_element_relations(element_id)),
            outgoing_relationship_count=len(element.relationships),
            inbound_character_count=len(self.inbound_character_relations(element_id)),
            usage_counts=counts,
            is_primary_power_system=(
                self._bible.repository.load_manifest().primary_power_system_id
                == element_id
            ),
        )

    def delete_element(self, element_id: str, *, unlink_references: bool) -> None:
        impact = self.inspect_element_deletion(element_id)
        if impact.requires_unlink and not unlink_references:
            raise OperationBlockedError("Story Element references must be unlinked")
        try:
            self._bible.delete_element(
                element_id, unlink_references=unlink_references
            )
        except ValueError as error:
            raise OperationBlockedError(str(error)) from error
        self._usage.invalidate()

    def scene_outline_source(self, scene_id: str) -> str:
        for volume in load_all_volumes(self.project_dir):
            for chapter in volume.chapters:
                for scene in chapter.scenes:
                    if scene.id == scene_id:
                        return scene.model_dump_json()
        return ""

    def scene_prose_source(self, scene_id: str) -> str:
        for volume in load_all_volumes(self.project_dir):
            for chapter in volume.chapters:
                if any(scene.id == scene_id for scene in chapter.scenes):
                    return load_scene_prose(self.project_dir, chapter.id, scene_id)
        return ""

    async def generate_suggestions(
        self,
        source_text: str,
        *,
        existing_elements: Sequence[BibleElement],
        provider: object | None = None,
    ) -> tuple[BibleSuggestion, ...]:
        provider = provider or self._provider_factory()
        try:
            characters = tuple(
                self._characters.load(character_id)
                for character_id in list_character_ids(self.project_dir)
            )
            return tuple(
                await BibleAssistantAgent().generate(
                    provider,
                    source_text,
                    existing_elements=existing_elements,
                    characters=characters,
                )
            )
        finally:
            await provider.close()

    def apply_suggestions(self, proposals: Sequence[BibleSuggestion]) -> None:
        apply_bible_suggestions(
            self._bible,
            list(proposals),
            character_service=self._characters,
        )
        self._usage.invalidate()

    def preview_template_replace(
        self,
        current_elements: Sequence[BibleElement],
        template: StoryTemplate,
    ) -> StoryTemplateReplacePreview:
        return preview_story_template_replace(list(current_elements), template)

    def apply_template_to_draft(
        self,
        overview: WorldOverview,
        elements: Sequence[BibleElement],
        style: StyleGuide,
        template: StoryTemplate,
        merge_mode: TemplateMergeMode,
    ) -> StoryTemplateApplication:
        return apply_story_template(
            overview, list(elements), style, template, merge_mode
        )

    def merge_template_style(
        self,
        current: StyleGuide,
        template: StyleGuide,
        merge_mode: TemplateMergeMode,
    ) -> StyleGuide:
        return merge_style_guide(current, template, merge_mode)

    @staticmethod
    def _default_provider() -> object:
        from app.providers.config import get_provider_for_step, load_provider_config

        return get_provider_for_step("bible_assistant", load_provider_config())
