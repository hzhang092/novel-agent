"""Derived Story Bible usage from the project's canonical files."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re

from app.storage.bible_models import BibleElementType, normalize_text
from app.storage.bible_repository import WorldBibleService
from app.storage.project_files import (
    load_all_volumes,
    load_scene_active_marker,
    load_scene_generation_record,
    load_scene_prose,
)


class StoryUsageKind(str, Enum):
    EXPLICIT_OUTLINE = "explicit_outline"
    GENERATION_CONTEXT = "generation_context"
    PROSE_MENTION = "prose_mention"
    CHARACTER_PRESENCE = "character_presence"


@dataclass(frozen=True)
class SceneUsage:
    scene_id: str
    chapter_id: str
    scene_order: int
    scene_title: str
    usage_kinds: frozenset[StoryUsageKind]
    selection_reasons: tuple[str, ...] = ()
    matched_alias: str = ""
    generated_element_revision: int | None = None
    current_element_revision: int | None = None
    location_label: str = ""
    location_reason: str = ""


@dataclass(frozen=True)
class ElementUsageSummary:
    element_id: str
    scenes: tuple[SceneUsage, ...]


def _matched_name_or_alias(prose: str, name: str, aliases: list[str]) -> str:
    normalized_prose = normalize_text(prose)
    for value in (name, *aliases):
        term = normalize_text(value)
        if not term or (value != name and len(term) == 1):
            continue
        if any("\u4e00" <= char <= "\u9fff" for char in term):
            matched = term in normalized_prose
        else:
            matched = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized_prose) is not None
        if matched:
            return value
    return ""


def _record_is_active(record, marker: dict[str, str]) -> bool:
    if record is None or record.status == "draft":
        return False
    if revision_id := marker.get("revision_id"):
        return record.revision_id == revision_id
    if (version := marker.get("version", "")).startswith("v") and version[1:].isdigit():
        return record.revision_number == int(version[1:])
    return record.status == "current"


class StoryUsageService:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)

    def element_usage(self, element_id: str) -> ElementUsageSummary:
        element = WorldBibleService(self.project_dir).load()
        current = next(item for item in element.elements if item.id == element_id)
        usages: list[SceneUsage] = []
        scene_order = 0
        location_names = {
            normalize_text(value) for value in (current.name, *current.aliases)
        }
        for volume in load_all_volumes(self.project_dir):
            for chapter in volume.chapters:
                for scene in chapter.scenes:
                    scene_order += 1
                    kinds: set[StoryUsageKind] = set()
                    if element_id in scene.world_element_ids:
                        kinds.add(StoryUsageKind.EXPLICIT_OUTLINE)
                    record = load_scene_generation_record(self.project_dir, scene.id)
                    marker = load_scene_active_marker(
                        self.project_dir, chapter.id, scene.id
                    )
                    read_point = (
                        record.generated_with.get("bible_elements", {}).get(element_id)
                        if _record_is_active(record, marker)
                        else None
                    )
                    if read_point is not None:
                        kinds.add(StoryUsageKind.GENERATION_CONTEXT)
                    participants = {
                        scene.pov_character_id,
                        *scene.participating_character_ids,
                    } - {""}
                    location_matches = (
                        normalize_text(scene.location) in location_names
                        if scene.location
                        else False
                    )
                    if (
                        current.element_type == BibleElementType.LOCATION
                        and participants
                        and (
                            element_id in scene.world_element_ids
                            or read_point is not None
                            or location_matches
                        )
                    ):
                        kinds.add(StoryUsageKind.CHARACTER_PRESENCE)
                    matched_alias = _matched_name_or_alias(
                        load_scene_prose(self.project_dir, chapter.id, scene.id),
                        current.name,
                        current.aliases,
                    )
                    if matched_alias:
                        kinds.add(StoryUsageKind.PROSE_MENTION)
                    if not kinds:
                        continue
                    usages.append(SceneUsage(
                        scene.id,
                        chapter.id,
                        scene_order,
                        scene.title,
                        frozenset(kinds),
                        tuple(read_point.get("selection_reasons", ())) if read_point else (),
                        matched_alias,
                        generated_element_revision=(
                            read_point.get("revision") if read_point else None
                        ),
                        current_element_revision=current.revision,
                    ))
        return ElementUsageSummary(element_id, tuple(usages))

    def character_presence(self, character_id: str) -> list[SceneUsage]:
        locations = [
            element
            for element in WorldBibleService(self.project_dir).load().elements
            if element.element_type == BibleElementType.LOCATION
        ]
        locations_by_id = {element.id: element for element in locations}
        locations_by_name = {
            normalize_text(name): element
            for element in locations
            for name in (element.name, *element.aliases)
        }
        usages: list[SceneUsage] = []
        scene_order = 0
        for volume in load_all_volumes(self.project_dir):
            for chapter in volume.chapters:
                for scene in chapter.scenes:
                    scene_order += 1
                    participants = {
                        scene.pov_character_id,
                        *scene.participating_character_ids,
                    }
                    if character_id not in participants:
                        continue
                    location = next(
                        (
                            locations_by_id[element_id]
                            for element_id in scene.world_element_ids
                            if element_id in locations_by_id
                        ),
                        None,
                    )
                    reason = "Explicit location element" if location else ""
                    if location is None and scene.location:
                        location = locations_by_name.get(normalize_text(scene.location))
                        if location is not None:
                            reason = "Matched scene location text"
                    if location is None:
                        record = load_scene_generation_record(self.project_dir, scene.id)
                        marker = load_scene_active_marker(
                            self.project_dir, chapter.id, scene.id
                        )
                        generated_ids = (
                            record.generated_with.get("bible_elements", {})
                            if _record_is_active(record, marker)
                            else {}
                        )
                        location = next(
                            (
                                locations_by_id[element_id]
                                for element_id in generated_ids
                                if element_id in locations_by_id
                            ),
                            None,
                        )
                        if location is not None:
                            reason = "Generation-context location"
                    usages.append(SceneUsage(
                        scene.id,
                        chapter.id,
                        scene_order,
                        scene.title,
                        frozenset({StoryUsageKind.CHARACTER_PRESENCE}),
                        location_label=location.name if location else scene.location,
                        location_reason=reason,
                    ))
        return usages

    def location_presence(self, location_id: str) -> list[SceneUsage]:
        current = next(
            element
            for element in WorldBibleService(self.project_dir).load().elements
            if element.id == location_id
        )
        usages: list[SceneUsage] = []
        scene_order = 0
        location_names = {
            normalize_text(value) for value in (current.name, *current.aliases)
        }
        for volume in load_all_volumes(self.project_dir):
            for chapter in volume.chapters:
                for scene in chapter.scenes:
                    scene_order += 1
                    participants = {
                        scene.pov_character_id,
                        *scene.participating_character_ids,
                    } - {""}
                    location_matches = (
                        normalize_text(scene.location) in location_names
                        if scene.location
                        else False
                    )
                    record = load_scene_generation_record(self.project_dir, scene.id)
                    marker = load_scene_active_marker(
                        self.project_dir, chapter.id, scene.id
                    )
                    read_point = (
                        record.generated_with.get("bible_elements", {}).get(location_id)
                        if _record_is_active(record, marker)
                        else None
                    )
                    if not participants or (
                        location_id not in scene.world_element_ids
                        and not location_matches
                        and read_point is None
                    ):
                        continue
                    usages.append(SceneUsage(
                        scene.id,
                        chapter.id,
                        scene_order,
                        scene.title,
                        frozenset({StoryUsageKind.CHARACTER_PRESENCE}),
                        tuple(read_point.get("selection_reasons", ())) if read_point else (),
                        generated_element_revision=(
                            read_point.get("revision") if read_point else None
                        ),
                        current_element_revision=current.revision,
                    ))
        return usages

    def all_element_counts(self) -> dict[str, int]:
        return {
            element.id: len(self.element_usage(element.id).scenes)
            for element in WorldBibleService(self.project_dir).load().elements
        }
