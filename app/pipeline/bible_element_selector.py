"""Deterministic relevance selection for World Bible elements."""

from dataclasses import dataclass

from app.domain.bible_relation_catalog import relation_definition
from app.storage.bible_models import BibleElement, normalize_text


_SCENE_TEXT_FIELDS = (
    "scene_title",
    "location",
    "scene_goal",
    "conflict",
    "required_plot_beats",
    "emotional_turn",
    "ending_hook",
    "constraints",
    "participating_characters",
)
_NON_DETAIL_FIELDS = {
    "id",
    "element_type",
    "name",
    "aliases",
    "tags",
    "importance",
    "always_include",
    "revision",
    "relationships",
    "created_at",
    "updated_at",
}


@dataclass(frozen=True)
class SelectedBibleElement:
    element: BibleElement
    score: int
    reasons: tuple[str, ...]


class BibleElementSelector:
    def select(
        self,
        elements: list[BibleElement],
        scene: dict,
        *,
        max_auto_elements: int = 12,
    ) -> list[SelectedBibleElement]:
        explicit_ids = set(scene.get("world_element_ids", []))
        unique: list[BibleElement] = []
        seen: set[str] = set()
        for element in elements:
            if element.id not in seen:
                seen.add(element.id)
                unique.append(element)

        scores = {element.id: 0 for element in unique}
        reasons = {element.id: [] for element in unique}
        text_matched: set[str] = set()

        for element in unique:
            if element.id in explicit_ids:
                scores[element.id] = 1000
                reasons[element.id].append("explicit_scene_reference")
            if element.always_include:
                scores[element.id] = max(
                    scores[element.id], 800 + element.importance * 10
                )
                reasons[element.id].append("always_include")

        scene_values = _scene_text_values(scene)
        for element in unique:
            base_score, match_reasons = _text_match(element, scene_values)
            if not base_score:
                continue
            text_matched.add(element.id)
            scores[element.id] = max(
                scores[element.id], base_score + element.importance * 10
            )
            reasons[element.id].extend(match_reasons)

        related: set[str] = set()
        by_id = {element.id: element for element in unique}
        inbound: dict[str, list[tuple[BibleElement, object]]] = {}
        for source in unique:
            for relation in source.relationships:
                inbound.setdefault(relation.target_element_id, []).append((source, relation))

        base_ids = explicit_ids | {
            element.id for element in unique if element.always_include
        } | text_matched
        for source in unique:
            if source.id not in base_ids:
                continue
            neighbors = [
                (by_id.get(relation.target_element_id), relation)
                for relation in source.relationships
            ]
            neighbors.extend(inbound.get(source.id, []))
            for target, relation in neighbors:
                if target is None or not relation_definition(relation.kind).expand_in_context:
                    continue
                related.add(target.id)
                scores[target.id] = max(scores[target.id], 80 + target.importance * 10)
                reason = f"related_to:{source.id}:{relation.kind.value}"
                if reason not in reasons[target.id]:
                    reasons[target.id].append(reason)

        explicit = [element for element in unique if element.id in explicit_ids]
        always = [
            element
            for element in unique
            if element.id not in explicit_ids and element.always_include
        ]
        automatic = [
            element
            for element in unique
            if element.id in text_matched | related
            and element.id not in explicit_ids
            and not element.always_include
        ]
        order = {element.id: index for index, element in enumerate(unique)}
        automatic.sort(
            key=lambda element: (
                -scores[element.id],
                -element.importance,
                order[element.id],
            )
        )
        automatic = automatic[:max(0, max_auto_elements)]
        return [
            SelectedBibleElement(element, scores[element.id], tuple(reasons[element.id]))
            for element in [*explicit, *always, *automatic]
        ]


def _scene_text_values(scene: dict) -> list[str]:
    values: list[str] = []
    for field in _SCENE_TEXT_FIELDS:
        values.extend(_strings(scene.get(field, "")))
    return [normalized for value in values if (normalized := normalize_text(value))]


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _strings(item)]
    return []


def _text_match(element: BibleElement, scene_values: list[str]) -> tuple[int, list[str]]:
    name = normalize_text(element.name)
    aliases = [normalize_text(alias) for alias in element.aliases]
    tags = [normalize_text(tag) for tag in element.tags]
    exact_name = name in scene_values
    exact_alias = any(alias in scene_values for alias in aliases)
    name_or_alias_substring = not (exact_name or exact_alias) and any(
        value and value in scene_value
        for value in [name, *aliases]
        for scene_value in scene_values
    )
    exact_tag = any(tag in scene_values for tag in tags)
    tag_substring = not exact_tag and any(
        tag and tag in scene_value for tag in tags for scene_value in scene_values
    )
    details = [
        normalize_text(value)
        for value in _strings(element.model_dump(exclude=_NON_DETAIL_FIELDS))
        if value
    ]
    detail_substring = any(
        detail in scene_value or scene_value in detail
        for detail in details
        for scene_value in scene_values
    )

    matches = (
        (exact_name, 400, "exact_name"),
        (exact_alias, 380, "exact_alias"),
        (name_or_alias_substring, 300, "name_or_alias_substring"),
        (exact_tag, 250, "exact_tag"),
        (tag_substring, 180, "tag_substring"),
        (detail_substring, 120, "summary_or_typed_field_substring"),
    )
    return (
        max((score for matched, score, _ in matches if matched), default=0),
        [reason for matched, _, reason in matches if matched],
    )
