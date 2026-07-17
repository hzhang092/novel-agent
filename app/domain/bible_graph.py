"""Derived views and safe unlink helpers for the Bible Element graph."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.bible_relation_catalog import relation_definition
from app.storage.bible_models import BibleElement
from app.storage.models import VolumeOutline


@dataclass(frozen=True)
class BibleRelationView:
    source_id: str
    target_id: str
    label: str
    note: str
    inbound: bool


def relation_views(
    elements: list[BibleElement], element_id: str
) -> list[BibleRelationView]:
    if element_id not in {element.id for element in elements}:
        raise KeyError(element_id)
    result: list[BibleRelationView] = []
    for source in elements:
        for relation in source.relationships:
            definition = relation_definition(relation.kind)
            if source.id == element_id:
                result.append(BibleRelationView(
                    source.id,
                    relation.target_element_id,
                    definition.label,
                    relation.note,
                    False,
                ))
            elif relation.target_element_id == element_id:
                result.append(BibleRelationView(
                    source.id,
                    element_id,
                    definition.inverse_label,
                    relation.note,
                    True,
                ))
    return result


def related_element_ids(
    elements: list[BibleElement], selected_ids: set[str]
) -> set[str]:
    related: set[str] = set()
    for source in elements:
        for relation in source.relationships:
            if not relation_definition(relation.kind).expand_in_context:
                continue
            if source.id in selected_ids:
                related.add(relation.target_element_id)
            if relation.target_element_id in selected_ids:
                related.add(source.id)
    return related - selected_ids


def unlink_element_relations(
    elements: list[BibleElement], element_id: str
) -> list[BibleElement]:
    return [
        element.model_copy(update={
            "relationships": [
                relation
                for relation in element.relationships
                if relation.target_element_id != element_id
            ]
        })
        for element in elements
        if element.id != element_id
    ]


def unlink_scene_references(
    volumes: list[VolumeOutline], element_id: str
) -> list[VolumeOutline]:
    result = [volume.model_copy(deep=True) for volume in volumes]
    for volume in result:
        for chapter in volume.chapters:
            for scene in chapter.scenes:
                scene.world_element_ids = [
                    stored_id
                    for stored_id in scene.world_element_ids
                    if stored_id != element_id
                ]
    return result
