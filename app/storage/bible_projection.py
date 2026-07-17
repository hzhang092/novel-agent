"""Compatibility projection from typed Bible Elements to legacy WorldSetting."""

import logging

from app.storage.bible_models import (
    BibleElement,
    BibleManifest,
    FactionElement,
    HistoricalEventElement,
    PowerSystemElement,
    TerminologyElement,
    WorldOverview,
    normalize_text,
)
from app.storage.models import PowerSystem, WorldSetting


logger = logging.getLogger(__name__)


def project_elements_to_legacy_world(
    overview: WorldOverview,
    elements: list[BibleElement],
    manifest: BibleManifest,
) -> WorldSetting:
    by_id = {element.id: element for element in elements}
    ordered = [by_id[element_id] for element_id in manifest.element_order if element_id in by_id]
    factions = [
        {
            "name": element.name,
            "description": element.description,
            "goals": "；".join(element.goals),
        }
        for element in ordered
        if isinstance(element, FactionElement)
    ]
    terminology = {}
    terminology_names: set[str] = set()
    for element in ordered:
        if not isinstance(element, TerminologyElement):
            continue
        normalized_name = normalize_text(element.name)
        if normalized_name in terminology_names:
            raise ValueError("Terminology names must be unique after normalization")
        terminology_names.add(normalized_name)
        terminology[element.name] = element.definition
    histories = [element for element in ordered if isinstance(element, HistoricalEventElement)]
    if len(histories) == 1 and manifest.migrated_from_world_setting:
        history = histories[0].description
    else:
        rendered_histories = []
        for element in histories:
            heading = " ".join(part for part in (element.time_label, element.name) if part)
            parts = [heading, element.description]
            if element.consequences:
                parts.append("Consequences: " + "；".join(element.consequences))
            rendered_histories.append("\n".join(part for part in parts if part))
        history = "\n\n".join(rendered_histories)
    power_elements = [element for element in ordered if isinstance(element, PowerSystemElement)]
    if power_elements and not any(
        element.id == manifest.primary_power_system_id for element in power_elements
    ):
        manifest.primary_power_system_id = power_elements[0].id
        logger.warning("Repaired missing primary power system: %s", power_elements[0].id)
    primary = next(
        (element for element in power_elements if element.id == manifest.primary_power_system_id),
        None,
    )
    power_system = None
    if primary is not None:
        power_system = PowerSystem(
            realms=[realm.name for realm in primary.realms],
            abilities={
                realm.name: "；".join(realm.abilities)
                for realm in primary.realms
                if realm.abilities
            },
            limitations=primary.limitations,
            costs=primary.costs,
            rare_resources=primary.rare_resources,
            forbidden_methods=primary.forbidden_methods,
        )
    return WorldSetting(
        **overview.model_dump(),
        factions=factions,
        terminology=terminology,
        history=history,
        power_system=power_system,
    )
