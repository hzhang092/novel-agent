"""Immutable query results shared by project editing services."""

from __future__ import annotations

from dataclasses import dataclass

from app.storage.bible_models import BibleElement, WorldBible
from app.storage.models import Character, CharacterState, StyleGuide, VolumeOutline


@dataclass(frozen=True)
class SceneReference:
    scene_id: str
    chapter_id: str
    name: str


@dataclass(frozen=True)
class CharacterReference:
    character_id: str
    name: str


@dataclass(frozen=True)
class CharacterDeletionImpact:
    character_id: str
    character_name: str
    pov_scenes: tuple[SceneReference, ...]
    participant_scenes: tuple[SceneReference, ...]
    relationship_characters: tuple[CharacterReference, ...]

    @property
    def is_blocked(self) -> bool:
        return bool(self.pov_scenes)

    @property
    def requires_unlink(self) -> bool:
        return bool(self.participant_scenes or self.relationship_characters)


@dataclass(frozen=True)
class ElementUsageCounts:
    explicit_outline: int
    generation_context: int
    prose_mention: int


@dataclass(frozen=True)
class ElementDeletionImpact:
    element_id: str
    element_name: str
    inbound_element_count: int
    outgoing_relationship_count: int
    inbound_character_count: int
    usage_counts: ElementUsageCounts
    is_primary_power_system: bool

    @property
    def requires_unlink(self) -> bool:
        return bool(
            self.inbound_element_count
            or self.inbound_character_count
            or self.usage_counts.explicit_outline
        )


@dataclass(frozen=True)
class CharacterStateEditSession:
    character_id: str
    original_state: CharacterState
    opened_at_event_id: int


@dataclass(frozen=True)
class StoryBibleEditorSnapshot:
    bible: WorldBible
    style_guide: StyleGuide


@dataclass(frozen=True)
class OutlineEditorSnapshot:
    volumes: tuple[VolumeOutline, ...]
    characters: tuple[Character, ...]
    bible_elements: tuple[BibleElement, ...]
