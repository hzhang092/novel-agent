"""Character editor use cases."""

from __future__ import annotations

import logging
from pathlib import Path

from app.application.errors import (
    ApplicationNotFoundError,
    ApplicationValidationError,
    ConcurrentModificationError,
    OperationBlockedError,
)
from app.application.results import (
    CharacterDeletionImpact,
    CharacterReference,
    CharacterStateEditSession,
    SceneReference,
)
from app.domain.story_usage import SceneUsage, StoryUsageService
from app.storage.bible_models import BibleElement
from app.storage.bible_repository import BibleElementRepository, rollback_files
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.character_events import get_latest_event_id
from app.storage.models import (
    Character,
    CharacterCore,
    CharacterState,
)
from app.storage.project_files import (
    delete_character as delete_stored_character,
    list_character_ids,
    load_all_characters,
    load_all_volumes,
    load_character,
    save_character,
)
from app.storage.state_repository import commit_character_state_edit

logger = logging.getLogger(__name__)


class CharacterApplicationService:
    def __init__(self, project_dir: Path, *, event_bus: object | None = None) -> None:
        self.project_dir = Path(project_dir)
        self._event_bus = event_bus
        self._definitions: CharacterDefinitionService | None = None
        self._usage = StoryUsageService(self.project_dir)

    def set_event_bus(self, event_bus: object) -> None:
        self._event_bus = event_bus

    def list_characters(self) -> tuple[Character, ...]:
        characters = []
        for character_id in list_character_ids(self.project_dir):
            try:
                characters.append(load_character(self.project_dir, character_id))
            except (FileNotFoundError, ValueError) as error:
                logger.warning("Skipping malformed character %s: %s", character_id, error)
        return tuple(characters)

    def load_character(self, character_id: str) -> Character:
        try:
            return load_character(self.project_dir, character_id)
        except FileNotFoundError as error:
            raise ApplicationNotFoundError(str(error)) from error

    def list_bible_elements(self) -> tuple[BibleElement, ...]:
        try:
            return tuple(BibleElementRepository(self.project_dir).load_all())
        except FileNotFoundError:
            return ()

    def character_presence(self, character_id: str) -> tuple[SceneUsage, ...]:
        return tuple(self._usage.character_presence(character_id))

    def save_definition(self, core: CharacterCore) -> Character:
        if not core.name.strip():
            raise ApplicationValidationError("Character name is required")

        char_dir = self.project_dir / "characters" / core.id
        try:
            existing = load_character(self.project_dir, core.id)
        except FileNotFoundError:
            existing = None

        try:
            if (char_dir / "definition.yaml").exists():
                self._definition_service().save(core)
            else:
                state = existing.state if existing is not None else CharacterState(character_id=core.id)
                paths = [
                    char_dir / "definition.yaml",
                    char_dir / "events.jsonl",
                    char_dir / "state.yaml",
                ]
                with rollback_files(paths):
                    save_character(self.project_dir, Character(core=core, state=state))
        except ValueError as error:
            raise ApplicationValidationError(str(error)) from error
        return self.load_character(core.id)

    def inspect_deletion(self, character_id: str) -> CharacterDeletionImpact:
        character = self.load_character(character_id)
        pov_scenes = []
        participant_scenes = []
        for volume in load_all_volumes(self.project_dir):
            for chapter in volume.chapters:
                for scene in chapter.scenes:
                    reference = SceneReference(
                        scene_id=scene.id,
                        chapter_id=chapter.id,
                        name=scene.title or scene.id,
                    )
                    if scene.pov_character_id == character_id:
                        pov_scenes.append(reference)
                    if character_id in scene.participating_character_ids:
                        participant_scenes.append(reference)
        relationship_characters = tuple(
            CharacterReference(item.core.id, item.core.name or item.core.id)
            for item in load_all_characters(self.project_dir)
            if item.core.id != character_id
            and character_id in item.state.current_relationships
        )
        return CharacterDeletionImpact(
            character_id=character_id,
            character_name=character.core.name,
            pov_scenes=tuple(pov_scenes),
            participant_scenes=tuple(participant_scenes),
            relationship_characters=relationship_characters,
        )

    def delete_character(
        self, character_id: str, *, unlink_references: bool
    ) -> None:
        impact = self.inspect_deletion(character_id)
        if impact.is_blocked:
            raise OperationBlockedError("Character is still used as a scene POV")
        if impact.requires_unlink and not unlink_references:
            raise OperationBlockedError("Character references must be unlinked")
        try:
            delete_stored_character(
                self.project_dir,
                character_id,
                unlink_references=unlink_references,
            )
        except ValueError as error:
            raise OperationBlockedError(str(error)) from error

    def begin_state_edit(self, character_id: str) -> CharacterStateEditSession:
        character = self.load_character(character_id)
        return CharacterStateEditSession(
            character_id=character_id,
            original_state=character.state.model_copy(deep=True),
            opened_at_event_id=get_latest_event_id(self._character_dir(character_id)),
        )

    def commit_state_edit(
        self,
        session: CharacterStateEditSession,
        proposed_state: CharacterState,
        *,
        scene_id: str,
    ) -> CharacterState | None:
        if proposed_state.character_id != session.character_id:
            raise ApplicationValidationError("Character state belongs to another character")
        char_dir = self._character_dir(session.character_id)
        if get_latest_event_id(char_dir) != session.opened_at_event_id:
            raise ConcurrentModificationError("Character state changed while it was being edited")
        event = commit_character_state_edit(
            char_dir,
            session.original_state,
            proposed_state,
            scene_id=scene_id,
            bus=self._event_bus,
            source="manual_event",
        )
        if event is None:
            return None
        return self.load_character(session.character_id).state

    def _character_dir(self, character_id: str) -> Path:
        return self.project_dir / "characters" / character_id

    def _definition_service(self) -> CharacterDefinitionService:
        if self._definitions is None:
            self._definitions = CharacterDefinitionService(self.project_dir)
        return self._definitions
