"""Safe migration from the legacy monolithic WorldSetting."""

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import yaml

from app.storage.bible_models import (
    BibleElementType,
    BibleManifest,
    FactionElement,
    HistoricalEventElement,
    PowerSystemElement,
    TerminologyElement,
    WorldBible,
    WorldOverview,
    normalize_text,
    power_realms_from_legacy,
)
from app.storage.bible_projection import project_elements_to_legacy_world
from app.storage.bible_renderer import write_world_markdown
from app.storage.bible_repository import BibleElementRepository, rollback_files
from app.storage.models import PowerSystem
from app.storage.project_files import load_project


logger = logging.getLogger(__name__)


def _overview_from_world(world) -> WorldOverview:
    return WorldOverview(
        geography=world.geography,
        rules=world.rules,
        taboos=world.taboos,
        technology_level=world.technology_level,
        social_structure=world.social_structure,
    )


def _migrated_content(world) -> dict:
    return {
        "factions": world.factions,
        "terminology": world.terminology,
        "history": world.history,
        "power_system": (
            world.power_system.model_dump(mode="json")
            if world.power_system is not None and world.power_system != PowerSystem()
            else None
        ),
    }


def _migration_id(project_id: str, element_type: BibleElementType, name: str, index: int) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"{project_id}:{element_type.value}:{normalize_text(name)}:{index}",
        )
    )


def _build_elements(project):
    world = project.world_setting
    elements = []
    for index, faction in enumerate(world.factions):
        name = faction.get("name", "")
        elements.append(
            FactionElement(
                id=_migration_id(project.id, BibleElementType.FACTION, name, index),
                name=name,
                description=faction.get("description", ""),
                goals=[faction.get("goals", "")],
            )
        )
    for index, (name, definition) in enumerate(world.terminology.items()):
        elements.append(
            TerminologyElement(
                id=_migration_id(project.id, BibleElementType.TERMINOLOGY, name, index),
                name=name,
                definition=definition,
            )
        )
    if world.history:
        elements.append(
            HistoricalEventElement(
                id=_migration_id(
                    project.id,
                    BibleElementType.HISTORICAL_EVENT,
                    "World History",
                    0,
                ),
                name="World History",
                description=world.history,
            )
        )
    if world.power_system is not None and world.power_system != PowerSystem():
        power = world.power_system
        elements.append(
            PowerSystemElement(
                id=_migration_id(
                    project.id,
                    BibleElementType.POWER_SYSTEM,
                    "Power System",
                    0,
                ),
                name="Power System",
                realms=power_realms_from_legacy(power.realms, power.abilities),
                limitations=power.limitations,
                costs=power.costs,
                rare_resources=power.rare_resources,
                forbidden_methods=power.forbidden_methods,
                always_include=True,
            )
        )
    return elements


def _backup_legacy_world(project_dir: Path) -> None:
    backup = (
        project_dir
        / ".novel-agent"
        / "backups"
        / f"world-v1-{datetime.now():%Y%m%d-%H%M%S-%f}"
    )
    backup.mkdir(parents=True)
    for name in ("project.yaml", "world.md"):
        source = project_dir / name
        if source.exists():
            shutil.copy2(source, backup / name)


def ensure_bible_store(project_dir: Path) -> WorldBible:
    project_dir = Path(project_dir)
    repository = BibleElementRepository(project_dir)
    project = load_project(project_dir)
    overview = _overview_from_world(project.world_setting)
    if repository.manifest_path.exists():
        return WorldBible(
            overview=overview,
            elements=repository.load_all(),
            manifest=repository.load_manifest(),
        )

    migrated_content = _migrated_content(project.world_setting)
    if not any(migrated_content.values()):
        repository.elements_dir.mkdir(parents=True, exist_ok=True)
        manifest = BibleManifest()
        repository._write_yaml_atomic(
            repository.manifest_path,
            manifest.model_dump(mode="json"),
        )
        return WorldBible(overview=overview, manifest=manifest)

    _backup_legacy_world(project_dir)
    elements = _build_elements(project)
    repository.validate_graph(elements)
    fingerprint = hashlib.sha256(
        json.dumps(
            migrated_content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    power = next(
        (element for element in elements if isinstance(element, PowerSystemElement)),
        None,
    )
    manifest = BibleManifest(
        element_order=[element.id for element in elements],
        primary_power_system_id=power.id if power else None,
        migrated_from_world_setting=True,
        migration_fingerprint=fingerprint,
        migrated_at=datetime.now(),
    )
    projected = project_elements_to_legacy_world(overview, elements, manifest)
    staging = repository.bible_dir / f".migration-{uuid4()}"
    destinations = [repository.element_path(element.id) for element in elements]
    try:
        staging.mkdir(parents=True)
        for element in elements:
            (staging / f"{element.id}.yaml").write_text(
                yaml.safe_dump(
                    element.model_dump(mode="json"),
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
        repository.elements_dir.mkdir(parents=True, exist_ok=True)
        with rollback_files([
            *destinations,
            project_dir / "project.yaml",
            project_dir / "world.md",
            repository.manifest_path,
        ]):
            for destination in destinations:
                os.replace(staging / destination.name, destination)
            project.world_setting = projected
            project.updated_at = datetime.now()
            repository._write_yaml_atomic(
                project_dir / "project.yaml",
                project.model_dump(mode="json"),
            )
            write_world_markdown(project_dir, overview, elements, manifest)
            repository._write_yaml_atomic(
                repository.manifest_path,
                manifest.model_dump(mode="json"),
            )
    except Exception:
        logger.exception("World Bible migration failed")
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return WorldBible(overview=overview, elements=elements, manifest=manifest)
