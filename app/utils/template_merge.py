"""Pure Story Template merge operations."""

from collections import Counter
from copy import deepcopy
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.storage.bible_models import (
    BibleElement,
    BibleElementBase,
    BibleElementRelation,
    BibleElementType,
    PowerRealm,
    WorldOverview,
    normalize_text,
)
from app.storage.models import StyleGuide, WorldSetting


class TemplateMergeMode(str, Enum):
    FILL_EMPTY = "fill_empty"
    MERGE = "merge"
    REPLACE = "replace"


class StoryTemplate(BaseModel):
    template_id: str
    name: str
    world_overview: WorldOverview
    elements: list[BibleElement] = Field(default_factory=list)
    style_guide: StyleGuide


class StoryTemplateApplication(BaseModel):
    world_overview: WorldOverview
    elements: list[BibleElement] = Field(default_factory=list)
    style_guide: StyleGuide


class StoryTemplateReplacePreview(BaseModel):
    overview_fields_replaced: int
    elements_replaced: dict[BibleElementType, int] = Field(default_factory=dict)
    unaffected_elements: dict[BibleElementType, int] = Field(default_factory=dict)


def apply_story_template(
    current_overview: WorldOverview,
    current_elements: list[BibleElement],
    current_style: StyleGuide,
    template: StoryTemplate,
    mode: TemplateMergeMode,
) -> StoryTemplateApplication:
    if mode == TemplateMergeMode.FILL_EMPTY:
        overview = _fill_empty(current_overview, template.world_overview)
    elif mode == TemplateMergeMode.MERGE:
        overview = _merge(current_overview, template.world_overview)
    elif mode == TemplateMergeMode.REPLACE:
        overview = template.world_overview.model_copy(deep=True)
    else:
        raise NotImplementedError
    return StoryTemplateApplication(
        world_overview=overview,
        elements=_apply_elements(current_elements, template.elements, mode),
        style_guide=merge_style_guide(current_style, template.style_guide, mode),
    )


def preview_story_template_replace(
    current_elements: list[BibleElement], template: StoryTemplate
) -> StoryTemplateReplacePreview:
    managed_types = {element.element_type for element in template.elements}
    return StoryTemplateReplacePreview(
        overview_fields_replaced=len(WorldOverview.model_fields),
        elements_replaced=dict(
            Counter(element.element_type for element in template.elements)
        ),
        unaffected_elements=dict(
            Counter(
                element.element_type
                for element in current_elements
                if element.element_type not in managed_types
            )
        ),
    )


def merge_world_setting(
    current: WorldSetting,
    template: WorldSetting,
    mode: TemplateMergeMode,
) -> WorldSetting:
    if mode == TemplateMergeMode.FILL_EMPTY:
        return _fill_empty(current, template)
    if mode == TemplateMergeMode.MERGE:
        merged = _merge(current, template)
        return merged.model_copy(
            update={"factions": _merge_factions(current.factions, template.factions)}
        )
    if mode == TemplateMergeMode.REPLACE:
        return template.model_copy(deep=True)
    raise NotImplementedError


def merge_style_guide(
    current: StyleGuide,
    template: StyleGuide,
    mode: TemplateMergeMode,
) -> StyleGuide:
    if mode == TemplateMergeMode.FILL_EMPTY:
        return _fill_empty(current, template)
    if mode == TemplateMergeMode.MERGE:
        merged = _merge(current, template)
        return merged.model_copy(
            update={
                field: _merge_trimmed_strings(
                    getattr(current, field), getattr(template, field)
                )
                for field in (
                    "taboo_patterns",
                    "preferred_patterns",
                    "reference_passages",
                )
            }
        )
    if mode == TemplateMergeMode.REPLACE:
        return template.model_copy(deep=True)
    raise NotImplementedError


def _apply_elements(
    current: list[BibleElement],
    template: list[BibleElement],
    mode: TemplateMergeMode,
) -> list[BibleElement]:
    template_key_counts = Counter(_element_key(element) for element in template)
    if any(count > 1 for count in template_key_counts.values()):
        raise ValueError("Duplicate template elements share the same identity")
    ambiguous = {
        key
        for key, count in Counter(_element_key(element) for element in current).items()
        if count > 1 and key in template_key_counts
    }
    if ambiguous:
        raise ValueError("Ambiguous project elements match the same template identity")
    current_by_key = {_element_key(element): element for element in current}
    used_ids = {element.id for element in current}
    target_ids: dict[str, str] = {}
    for incoming in template:
        existing = current_by_key.get(_element_key(incoming))
        if existing is not None:
            target_ids[incoming.id] = existing.id
            continue
        new_id = str(uuid4())
        while new_id in used_ids:
            new_id = str(uuid4())
        used_ids.add(new_id)
        target_ids[incoming.id] = new_id

    prepared = [
        _copy_template_element(
            incoming,
            target_ids,
            current_by_key.get(_element_key(incoming)),
            preserve_existing_metadata=mode == TemplateMergeMode.REPLACE,
        )
        for incoming in template
    ]
    prepared_by_key = {_element_key(element): element for element in prepared}

    if mode in (TemplateMergeMode.FILL_EMPTY, TemplateMergeMode.MERGE):
        result = []
        for existing in current:
            incoming = prepared_by_key.get(_element_key(existing))
            if incoming is None:
                result.append(existing.model_copy(deep=True))
            elif mode == TemplateMergeMode.FILL_EMPTY:
                result.append(_fill_empty_element(existing, incoming))
            else:
                result.append(_merge_element(existing, incoming))
        existing_keys = {_element_key(element) for element in current}
        result.extend(
            element for element in prepared if _element_key(element) not in existing_keys
        )
        return result

    if mode == TemplateMergeMode.REPLACE:
        managed_types = {element.element_type for element in template}
        retained = [
            element.model_copy(deep=True)
            for element in current
            if element.element_type not in managed_types
        ]
        result = retained + prepared
        valid_ids = {element.id for element in result}
        return [
            _validated_element_copy(
                element,
                relationships=[
                    relation
                    for relation in element.relationships
                    if relation.target_element_id in valid_ids
                ],
            )
            for element in result
        ]
    raise NotImplementedError


def _copy_template_element(
    element: BibleElementBase,
    target_ids: dict[str, str],
    existing: BibleElementBase | None,
    *,
    preserve_existing_metadata: bool,
) -> BibleElement:
    updates = {
        "id": target_ids[element.id],
        "relationships": [
            relation.model_copy(
                update={
                    "target_element_id": target_ids.get(
                        relation.target_element_id, relation.target_element_id
                    )
                }
            )
            for relation in element.relationships
        ],
    }
    if preserve_existing_metadata and existing is not None:
        updates.update(
            revision=existing.revision,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )
    return _validated_element_copy(element, **updates)


def _fill_empty_element(
    existing: BibleElementBase, incoming: BibleElementBase
) -> BibleElement:
    protected = {
        "id",
        "element_type",
        "name",
        "tags",
        "importance",
        "always_include",
        "revision",
        "relationships",
        "created_at",
        "updated_at",
    }
    updates = {
        field: deepcopy(getattr(incoming, field))
        for field in type(existing).model_fields
        if field not in protected and getattr(existing, field) in (None, "", [], {})
    }
    return _validated_element_copy(existing, **updates)


def _merge_element(
    existing: BibleElementBase, incoming: BibleElementBase
) -> BibleElement:
    protected = {
        "id",
        "element_type",
        "name",
        "revision",
        "created_at",
        "updated_at",
        "relationships",
    }
    updates = {}
    for field in type(existing).model_fields:
        if field in protected:
            continue
        current_value = getattr(existing, field)
        incoming_value = getattr(incoming, field)
        if isinstance(current_value, list):
            updates[field] = _merge_element_lists(current_value, incoming_value)
        elif current_value in (None, ""):
            updates[field] = deepcopy(incoming_value)
        else:
            updates[field] = current_value
    updates["relationships"] = _merge_relationships(
        existing.relationships, incoming.relationships
    )
    return _validated_element_copy(existing, **updates)


def _merge_element_lists(current: list, incoming: list) -> list:
    if all(isinstance(value, PowerRealm) for value in [*current, *incoming]):
        result = [value.model_copy(deep=True) for value in current]
        by_name = {
            normalize_text(value.name): index for index, value in enumerate(result)
        }
        for realm in incoming:
            index = by_name.get(normalize_text(realm.name))
            if index is None:
                by_name[normalize_text(realm.name)] = len(result)
                result.append(realm.model_copy(deep=True))
            else:
                result[index] = result[index].model_copy(
                    update={
                        "abilities": _stable_merge(
                            result[index].abilities, realm.abilities
                        )
                    }
                )
        return result
    return _stable_merge(current, incoming)


def _merge_relationships(
    current: list[BibleElementRelation], incoming: list[BibleElementRelation]
) -> list[BibleElementRelation]:
    result = [relation.model_copy(deep=True) for relation in current]
    keys = {(relation.kind, relation.target_element_id) for relation in result}
    for relation in incoming:
        key = (relation.kind, relation.target_element_id)
        if key not in keys:
            keys.add(key)
            result.append(relation.model_copy(deep=True))
    return result


def _stable_merge(current: list, incoming: list) -> list:
    result = deepcopy(current)
    result.extend(deepcopy(value) for value in incoming if value not in result)
    return result


def _validated_element_copy(element: BibleElementBase, **updates) -> BibleElement:
    data = element.model_dump(mode="python")
    data.update(updates)
    return type(element).model_validate(data)


def _element_key(element: BibleElementBase) -> tuple[BibleElementType, str]:
    return element.element_type, normalize_text(element.name)


def _fill_empty(current, template):
    return current.model_copy(
        update={
            name: deepcopy(getattr(template, name))
            for name in type(current).model_fields
            if getattr(current, name) in (None, "", [], {})
        },
        deep=True,
    )


def _merge(current, template):
    updates = {}
    for name in type(current).model_fields:
        existing = getattr(current, name)
        incoming = getattr(template, name)
        if isinstance(existing, BaseModel) and isinstance(incoming, BaseModel):
            value = _merge(existing, incoming)
        elif existing is None:
            value = deepcopy(incoming)
        elif isinstance(existing, str):
            value = existing or incoming
        elif isinstance(existing, list):
            value = deepcopy(existing)
            # ponytail: editor lists are small; use keyed lookup if templates grow large.
            value.extend(deepcopy(item) for item in incoming if item not in value)
        elif isinstance(existing, dict):
            value = deepcopy(existing)
            value.update(
                (key, deepcopy(item))
                for key, item in incoming.items()
                if key not in value
            )
        else:
            value = existing
        updates[name] = value
    return current.model_copy(update=updates, deep=True)


def _merge_factions(current, template):
    by_name = {_faction_name(faction): faction for faction in template}
    result = []
    existing_names = set()
    for faction in current:
        name = _faction_name(faction)
        existing_names.add(name)
        merged = deepcopy(faction)
        incoming = by_name.get(name, {})
        for field in ("description", "goals"):
            if not merged.get(field) and incoming.get(field):
                merged[field] = incoming[field]
        result.append(merged)

    for faction in template:
        name = _faction_name(faction)
        if name not in existing_names:
            result.append(deepcopy(faction))
            existing_names.add(name)
    return result


def _faction_name(faction):
    return faction.get("name", "").strip().casefold()


def _merge_trimmed_strings(current, template):
    result = [item.strip() for item in current if item.strip()]
    for item in template:
        item = item.strip()
        if item and item not in result:
            result.append(item)
    return result
