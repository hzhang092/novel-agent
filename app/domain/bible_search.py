"""Small in-memory search for author-created Bible Elements."""

from __future__ import annotations

from collections.abc import Iterable

from app.storage.bible_models import BibleElement, normalize_text


def _text_values(value) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _text_values(child)


def search_elements(
    elements: list[BibleElement],
    *,
    query: str = "",
    type_filter: str = "",
    tag_filters: list[str] | tuple[str, ...] = (),
    always_included: bool = False,
    referenced_ids: set[str] | None = None,
    target_names: dict[str, str] | None = None,
) -> list[BibleElement]:
    terms = normalize_text(query).split()
    wanted_tags = {normalize_text(tag) for tag in tag_filters}
    targets = target_names or {}
    ranked: list[tuple[int, int, int, BibleElement]] = []

    for order, element in enumerate(elements):
        if type_filter and element.element_type.value != type_filter:
            continue
        normalized_tags = {normalize_text(tag) for tag in element.tags}
        if not wanted_tags.issubset(normalized_tags):
            continue
        if always_included and not element.always_include:
            continue
        if referenced_ids is not None and element.id not in referenced_ids:
            continue

        name = normalize_text(element.name)
        aliases = [normalize_text(alias) for alias in element.aliases]
        tags = [normalize_text(tag) for tag in element.tags]
        data = element.model_dump(
            mode="json",
            exclude={
                "id", "name", "aliases", "tags", "relationships",
                "revision", "created_at", "updated_at",
            },
        )
        other_parts = [normalize_text(value) for value in _text_values(data)]
        other_parts.extend(
            normalize_text(targets.get(relation.target_element_id, ""))
            for relation in element.relationships
        )
        document = " ".join([name, *aliases, *tags, *other_parts])
        if not all(term in document for term in terms):
            continue

        whole_query = normalize_text(query)
        if not terms:
            rank = 6
        elif whole_query == name:
            rank = 0
        elif name.startswith(whole_query):
            rank = 1
        elif whole_query in aliases:
            rank = 2
        elif whole_query in tags:
            rank = 3
        elif whole_query in name:
            rank = 4
        else:
            rank = 5
        ranked.append((rank, -element.importance, order, element))

    ranked.sort(key=lambda item: item[:3])
    return [item[3] for item in ranked]
