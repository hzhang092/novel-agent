"""Deterministic Markdown rendering for the typed World Bible."""

import os
import tempfile
from pathlib import Path

from app.storage.bible_models import (
    BibleElement,
    BibleManifest,
    FactionElement,
    HistoricalEventElement,
    PowerSystemElement,
    TerminologyElement,
    WorldOverview,
)


def render_world_markdown(
    overview: WorldOverview,
    elements: list[BibleElement],
    manifest: BibleManifest,
) -> str:
    by_id = {element.id: element for element in elements}
    ordered = [by_id[element_id] for element_id in manifest.element_order if element_id in by_id]
    lines = ["# 世界观", "", "## 地理", "", overview.geography, ""]
    if overview.social_structure or overview.technology_level:
        lines.extend([
            "## 社会与科技",
            "",
            overview.social_structure,
            overview.technology_level,
            "",
        ])
    if overview.rules:
        lines.extend(["## 世界规则", *[f"- {rule}" for rule in overview.rules], ""])
    if overview.taboos:
        lines.extend(["## 禁忌", *[f"- {taboo}" for taboo in overview.taboos], ""])

    if ordered:
        lines.extend(["# 故事元素", ""])
    factions = [element for element in ordered if isinstance(element, FactionElement)]
    if factions:
        lines.extend(["## 势力", ""])
        for element in factions:
            lines.extend([f"### {element.name}", "", element.description, ""])
            if element.goals:
                lines.extend(["**目标**", *[f"- {goal}" for goal in element.goals], ""])
            if element.tags:
                lines.extend(["**标签**", *[f"- {tag}" for tag in element.tags], ""])

    histories = [element for element in ordered if isinstance(element, HistoricalEventElement)]
    if histories:
        lines.extend(["## 历史事件", ""])
        for element in histories:
            lines.extend([f"### {element.name}", ""])
            if element.time_label:
                lines.extend([element.time_label, ""])
            if element.description:
                lines.extend([element.description, ""])
            if element.consequences:
                lines.extend([
                    "**后果**",
                    *[f"- {consequence}" for consequence in element.consequences],
                    "",
                ])

    powers = [element for element in ordered if isinstance(element, PowerSystemElement)]
    if powers:
        lines.extend(["## 力量体系", ""])
        for element in powers:
            lines.extend([f"### {element.name}", ""])
            if element.summary:
                lines.extend([element.summary, ""])
            if element.realms:
                lines.append("**境界**")
                for realm in element.realms:
                    abilities = "；".join(realm.abilities)
                    lines.append(f"- **{realm.name}**: {abilities}" if abilities else f"- {realm.name}")
                lines.append("")
            for label, values in (
                ("限制", element.limitations),
                ("代价", element.costs),
                ("稀有资源", element.rare_resources),
                ("禁忌之术", element.forbidden_methods),
            ):
                if values:
                    lines.extend([f"**{label}**", *[f"- {value}" for value in values], ""])
    terms = [element for element in ordered if isinstance(element, TerminologyElement)]
    if terms:
        lines.extend(["## 术语", ""])
        for element in terms:
            lines.extend([f"### {element.name}", "", element.definition, ""])
    return "\n".join(lines).rstrip() + "\n"


def write_world_markdown(
    project_dir: Path,
    overview: WorldOverview,
    elements: list[BibleElement],
    manifest: BibleManifest,
) -> Path:
    path = Path(project_dir) / "world.md"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".world.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(render_world_markdown(overview, elements, manifest))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path
