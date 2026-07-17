"""Atomic project-local persistence for typed Bible Elements."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import TypeAdapter

from app.domain.bible_relation_catalog import relation_definition
from app.storage.bible_models import (
    BibleElement,
    BibleElementBase,
    BibleElementRelation,
    BibleElementType,
    BibleManifest,
    WorldBible,
    WorldOverview,
    normalize_text,
    semantically_equal,
)


_ELEMENT_ADAPTER = TypeAdapter(BibleElement)


@contextmanager
def rollback_files(paths):
    """Restore a small set of project files if a multi-file save fails."""
    originals = {
        Path(path): Path(path).read_bytes() if Path(path).exists() else None
        for path in dict.fromkeys(paths)
    }
    try:
        yield
    except Exception:
        for path, original in originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            elif not path.exists() or path.read_bytes() != original:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=path.parent,
                        prefix=f".{path.stem}.rollback.",
                        suffix=".tmp",
                        delete=False,
                    ) as handle:
                        temporary = Path(handle.name)
                        handle.write(original)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, path)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
        raise


class BibleElementRepository:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self.bible_dir = self.project_dir / "bible"
        self.elements_dir = self.bible_dir / "elements"
        self.manifest_path = self.bible_dir / "manifest.yaml"

    def load_manifest(self) -> BibleManifest:
        if not self.manifest_path.exists():
            raise FileNotFoundError(self.manifest_path)
        return BibleManifest.model_validate(self._read_yaml(self.manifest_path))

    def load_all(self) -> list[BibleElement]:
        manifest = self.load_manifest()
        return [self.load(element_id) for element_id in manifest.element_order]

    def load(self, element_id: str) -> BibleElement:
        path = self.elements_dir / f"{element_id}.yaml"
        if not path.exists():
            raise FileNotFoundError(path)
        return _ELEMENT_ADAPTER.validate_python(self._read_yaml(path))

    def create(self, element: BibleElement) -> BibleElement:
        manifest = self.load_manifest()
        if element.id in manifest.element_order:
            raise ValueError(f"Bible Element already exists: {element.id}")
        elements = self.load_all() + [element]
        self.validate_graph(elements)
        self._validate_terminology_names(elements)
        self._write_element(element)
        manifest.element_order.append(element.id)
        self._commit_manifest(manifest)
        return element

    def save(self, element: BibleElement) -> BibleElement:
        previous = self.load(element.id)
        if semantically_equal(previous, element):
            return previous
        saved = element.model_copy(
            update={
                "revision": previous.revision + 1,
                "created_at": previous.created_at,
                "updated_at": datetime.now(),
            }
        )
        elements = [saved if item.id == saved.id else item for item in self.load_all()]
        self.validate_graph(elements)
        self._validate_terminology_names(elements)
        self._write_element(saved)
        self._commit_manifest(self.load_manifest())
        return saved

    def delete(self, element_id: str) -> None:
        manifest = self.load_manifest()
        if element_id not in manifest.element_order:
            raise FileNotFoundError(self.elements_dir / f"{element_id}.yaml")
        remaining = [item for item in self.load_all() if item.id != element_id]
        self.validate_graph(remaining)
        (self.elements_dir / f"{element_id}.yaml").unlink()
        manifest.element_order.remove(element_id)
        if manifest.primary_power_system_id == element_id:
            manifest.primary_power_system_id = None
        self._commit_manifest(manifest)

    def reorder(self, element_ids: list[str]) -> None:
        manifest = self.load_manifest()
        if len(element_ids) != len(set(element_ids)) or set(element_ids) != set(manifest.element_order):
            raise ValueError("Element order must contain each stored element exactly once")
        if element_ids == manifest.element_order:
            return
        manifest.element_order = list(element_ids)
        self._commit_manifest(manifest)

    def set_primary_power_system(self, element_id: str | None) -> None:
        manifest = self.load_manifest()
        if element_id is not None:
            element = self.load(element_id)
            if element.element_type != BibleElementType.POWER_SYSTEM:
                raise ValueError("Primary power system must reference a power-system element")
        if manifest.primary_power_system_id == element_id:
            return
        manifest.primary_power_system_id = element_id
        self._commit_manifest(manifest)

    def get_inbound_relations(
        self, element_id: str
    ) -> list[tuple[BibleElement, BibleElementRelation]]:
        return [
            (source, relation)
            for source in self.load_all()
            for relation in source.relationships
            if relation.target_element_id == element_id
        ]

    def validate_graph(self, elements: list[BibleElement]) -> None:
        ids = {element.id for element in elements}
        directed: set[tuple[str, object, str]] = set()
        for source in elements:
            local: set[tuple[object, str]] = set()
            for relation in source.relationships:
                edge = (relation.kind, relation.target_element_id)
                if relation.target_element_id == source.id:
                    raise ValueError("A Bible Element cannot relate to itself")
                if relation.target_element_id not in ids:
                    raise ValueError(f"Relationship target is missing: {relation.target_element_id}")
                if edge in local:
                    raise ValueError("duplicate relationship")
                local.add(edge)
                if relation_definition(relation.kind).symmetric and (
                    relation.target_element_id, relation.kind, source.id
                ) in directed:
                    raise ValueError("A symmetric relationship must be stored in only one direction")
                directed.add((source.id, relation.kind, relation.target_element_id))

    def _validate_terminology_names(self, elements: list[BibleElement]) -> None:
        names: set[str] = set()
        for element in elements:
            if element.element_type != BibleElementType.TERMINOLOGY:
                continue
            key = normalize_text(element.name)
            if key in names:
                raise ValueError("Terminology names must be unique after normalization")
            names.add(key)

    def _write_element(self, element: BibleElementBase) -> None:
        self.elements_dir.mkdir(parents=True, exist_ok=True)
        self._write_yaml_atomic(
            self.elements_dir / f"{element.id}.yaml",
            element.model_dump(mode="json"),
        )

    def _commit_manifest(self, manifest: BibleManifest) -> None:
        manifest.content_revision += 1
        manifest.updated_at = datetime.now()
        self._write_yaml_atomic(self.manifest_path, manifest.model_dump(mode="json"))

    @staticmethod
    def _read_yaml(path: Path):
        with path.open(encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    @staticmethod
    def _write_yaml_atomic(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.stem}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class WorldBibleService:
    """Coordinate Bible persistence with its legacy compatibility outputs."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self.repository = BibleElementRepository(self.project_dir)

    def load(self) -> WorldBible:
        from app.storage.bible_migration import ensure_bible_store

        return ensure_bible_store(self.project_dir)

    def save_overview(self, overview: WorldOverview) -> None:
        self.load()
        with rollback_files(self._transaction_paths()):
            self._synchronize(overview)

    def save_element(self, element: BibleElement) -> BibleElement:
        bible = self.load()
        with rollback_files(self._transaction_paths([
            self.repository.elements_dir / f"{element.id}.yaml"
        ])):
            if element.id in self.repository.load_manifest().element_order:
                saved = self.repository.save(element)
            else:
                saved = self.repository.create(element)
            self._synchronize(bible.overview)
        return saved

    def apply_snapshot(
        self,
        overview: WorldOverview,
        elements: list[BibleElement],
    ) -> list[BibleElement]:
        from app.domain.bible_graph import unlink_scene_references
        from app.storage.project_files import load_all_volumes, save_volume_outline

        bible = self.load()
        target_ids = [element.id for element in elements]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("A Bible snapshot cannot contain duplicate element IDs")

        current = {element.id: element for element in bible.elements}
        now = datetime.now()
        saved = []
        for element in elements:
            previous = current.get(element.id)
            if previous is None:
                saved.append(element.model_copy(update={"revision": 1}))
            elif semantically_equal(previous, element):
                saved.append(previous)
            else:
                saved.append(element.model_copy(update={
                    "revision": previous.revision + 1,
                    "created_at": previous.created_at,
                    "updated_at": now,
                }))

        self.repository.validate_graph(saved)
        self.repository._validate_terminology_names(saved)
        target_by_id = {element.id: element for element in saved}
        removed_ids = set(current) - set(target_by_id)
        changed = [
            element
            for element in saved
            if element.id not in current
            or not semantically_equal(current[element.id], element)
        ]
        manifest = bible.manifest.model_copy(deep=True)
        manifest_changed = bool(changed or removed_ids or manifest.element_order != target_ids)
        manifest.element_order = target_ids
        power_ids = [
            element.id
            for element in saved
            if element.element_type == BibleElementType.POWER_SYSTEM
        ]
        primary = (
            manifest.primary_power_system_id
            if manifest.primary_power_system_id in power_ids
            else (power_ids[0] if power_ids else None)
        )
        if primary != manifest.primary_power_system_id:
            manifest.primary_power_system_id = primary
            manifest_changed = True

        volumes = load_all_volumes(self.project_dir)
        cleaned_volumes = volumes
        for removed_id in removed_ids:
            cleaned_volumes = unlink_scene_references(cleaned_volumes, removed_id)
        changed_volumes = [
            cleaned
            for previous, cleaned in zip(volumes, cleaned_volumes, strict=True)
            if previous != cleaned
        ]

        touched = [
            self.repository.elements_dir / f"{element_id}.yaml"
            for element_id in set(target_ids) | removed_ids
        ] + [
            self.project_dir / "outline" / f"{volume.id}.yaml"
            for volume in changed_volumes
        ]
        with rollback_files(self._transaction_paths(touched)):
            for element in changed:
                self.repository._write_element(element)
            for element_id in removed_ids:
                (self.repository.elements_dir / f"{element_id}.yaml").unlink(missing_ok=True)
            for volume in changed_volumes:
                save_volume_outline(self.project_dir, volume)
            if manifest_changed:
                self.repository._commit_manifest(manifest)
            self._synchronize(overview)
        return saved

    def reorder_elements(self, element_ids: list[str]) -> None:
        bible = self.load()
        with rollback_files(self._transaction_paths()):
            self.repository.reorder(element_ids)
            self._synchronize(bible.overview)

    def set_primary_power_system(self, element_id: str | None) -> None:
        bible = self.load()
        with rollback_files(self._transaction_paths()):
            self.repository.set_primary_power_system(element_id)
            self._synchronize(bible.overview)

    def delete_element(
        self,
        element_id: str,
        *,
        unlink_references: bool = False,
    ) -> None:
        from app.domain.bible_graph import (
            unlink_element_relations,
            unlink_scene_references,
        )
        from app.storage.project_files import load_all_volumes, save_volume_outline

        bible = self.load()
        self.repository.load(element_id)
        volumes = load_all_volumes(self.project_dir)
        inbound = self.repository.get_inbound_relations(element_id)
        scene_referenced = any(
            element_id in scene.world_element_ids
            for volume in volumes
            for chapter in volume.chapters
            for scene in chapter.scenes
        )
        if (inbound or scene_referenced) and not unlink_references:
            raise ValueError("Bible Element is referenced; delete with unlink_references=True")

        remaining = unlink_element_relations(bible.elements, element_id)
        self.repository.validate_graph(remaining)
        cleaned_volumes = unlink_scene_references(volumes, element_id)
        previous_by_id = {element.id: element for element in bible.elements}
        changed_elements = [
            element
            for element in remaining
            if not semantically_equal(previous_by_id[element.id], element)
        ] if unlink_references else []
        changed_volumes = [
            cleaned
            for previous, cleaned in zip(volumes, cleaned_volumes, strict=True)
            if previous != cleaned
        ] if unlink_references else []
        changed_paths = [
            self.repository.elements_dir / f"{element.id}.yaml"
            for element in changed_elements
        ] + [
            self.project_dir / "outline" / f"{volume.id}.yaml"
            for volume in changed_volumes
        ] + [self.repository.elements_dir / f"{element_id}.yaml"]

        with rollback_files(self._transaction_paths(changed_paths)):
            for element in changed_elements:
                self.repository.save(element)
            for volume in changed_volumes:
                save_volume_outline(self.project_dir, volume)
            self.repository.delete(element_id)
            self._synchronize(bible.overview)

    def synchronize_legacy_projection(self) -> None:
        overview = self.load().overview
        with rollback_files(self._transaction_paths()):
            self._synchronize(overview)

    def _synchronize(self, overview: WorldOverview) -> None:
        from app.storage.bible_projection import project_elements_to_legacy_world
        from app.storage.bible_renderer import write_world_markdown
        from app.storage.project_files import load_project

        elements = self.repository.load_all()
        manifest = self.repository.load_manifest()
        previous_primary = manifest.primary_power_system_id
        legacy_world = project_elements_to_legacy_world(overview, elements, manifest)
        if manifest.primary_power_system_id != previous_primary:
            self.repository.set_primary_power_system(manifest.primary_power_system_id)
            manifest = self.repository.load_manifest()

        project = load_project(self.project_dir)
        project.world_setting = legacy_world
        project.updated_at = datetime.now()
        self.repository._write_yaml_atomic(
            self.project_dir / "project.yaml",
            project.model_dump(mode="json"),
        )
        write_world_markdown(self.project_dir, overview, elements, manifest)

    def _transaction_paths(self, extra=()) -> list[Path]:
        return [
            *extra,
            self.project_dir / "project.yaml",
            self.project_dir / "world.md",
            self.repository.manifest_path,
        ]
