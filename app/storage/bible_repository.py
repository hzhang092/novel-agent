"""Atomic project-local persistence for typed Bible Elements."""

from __future__ import annotations

import os
import tempfile
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
    normalize_text,
    semantically_equal,
)


_ELEMENT_ADAPTER = TypeAdapter(BibleElement)


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
        if element.id in manifest.element_order or (self.elements_dir / f"{element.id}.yaml").exists():
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
