"""Pure Story Template merge operations."""

from copy import deepcopy
from enum import Enum

from pydantic import BaseModel

from app.storage.models import StyleGuide, WorldSetting


class TemplateMergeMode(str, Enum):
    FILL_EMPTY = "fill_empty"
    MERGE = "merge"
    REPLACE = "replace"


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
