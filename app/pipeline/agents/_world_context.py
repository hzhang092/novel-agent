"""Prompt-only rendering for selected Story Bible context."""

from __future__ import annotations


TYPE_LABELS = {
    "location": "Location",
    "faction": "Faction",
    "historical_event": "Historical event",
    "power_system": "Power system",
    "terminology": "Terminology",
}

WRITER_HEADINGS = {
    "location": "【相关地点】",
    "faction": "【相关势力】",
    "historical_event": "【相关历史事件】",
    "power_system": "【相关力量体系】",
    "terminology": "【相关术语】",
}


def overview_lines(world_context: dict, heading: str) -> list[str]:
    overview = world_context.get("overview", {})
    if not overview:
        return []
    lines = [heading]
    fields = (
        ("geography", "地理"),
        ("rules", "规则"),
        ("taboos", "禁忌"),
        ("social_structure", "社会结构"),
        ("technology_level", "技术水平"),
    )
    for key, label in fields:
        value = overview.get(key)
        if value:
            text = "；".join(value) if isinstance(value, list) else str(value)
            lines.append(f"- {label}：{text}")
    lines.append("")
    return lines


def planner_element_lines(world_context: dict) -> list[str]:
    elements = world_context.get("elements", [])
    if not elements:
        return []
    lines = ["【本场景相关故事元素】"]
    for element in elements:
        text = element.get("summary", "") or _detail_text(element.get("details", {}))
        relations = _relationship_text(element)
        suffix = "；".join(part for part in (text, relations) if part)
        lines.append(
            f"- [{TYPE_LABELS.get(element.get('type', ''), element.get('type', ''))}] "
            f"{element.get('name', '')}" + (f"：{suffix}" if suffix else "")
        )
    lines.append("")
    return lines


def writer_element_lines(world_context: dict) -> list[str]:
    elements = world_context.get("elements", [])
    lines: list[str] = []
    for element_type, heading in WRITER_HEADINGS.items():
        group = [element for element in elements if element.get("type") == element_type]
        if not group:
            continue
        lines.append(heading)
        for element in group:
            parts = [element.get("summary", ""), _detail_text(element.get("details", {})), _relationship_text(element)]
            text = "；".join(part for part in parts if part)
            lines.append(f"- {element.get('name', '')}" + (f"：{text}" if text else ""))
        lines.append("")
    return lines


def reviewer_element_lines(world_context: dict) -> list[str]:
    elements = world_context.get("elements", [])
    if not elements:
        return []
    lines = ["【相关故事元素（不可违反）】"]
    for element in elements:
        parts = [element.get("summary", ""), _detail_text(element.get("details", {})), _relationship_text(element)]
        text = "；".join(part for part in parts if part)
        lines.append(f"- [{TYPE_LABELS.get(element.get('type', ''), '')}] {element.get('name', '')}：{text}")
    lines.append("")
    return lines


def _detail_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "、".join(filter(None, (_detail_text(item) for item in value)))
    if isinstance(value, dict):
        return "；".join(
            f"{key}={text}"
            for key, item in value.items()
            if (text := _detail_text(item))
        )
    return str(value) if value not in (None, "") else ""


def _relationship_text(element: dict) -> str:
    return "；".join(
        " ".join(
            part
            for part in (
                relation.get("kind", "").replace("_", " "),
                relation.get("target_name", ""),
                relation.get("note", ""),
            )
            if part
        )
        for relation in element.get("relationships", [])
    )
