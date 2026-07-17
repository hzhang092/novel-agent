"""Validated persistence for Character Definitions and their Bible links."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from app.domain.character_element_relation_catalog import relation_definition
from app.storage.bible_repository import BibleElementRepository, rollback_files
from app.storage.models import CharacterCore, CharacterElementRelation


class CharacterDefinitionService:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self.bible_repository = BibleElementRepository(self.project_dir)

    def load(self, character_id: str) -> CharacterCore:
        definition_path = self.definition_path(character_id)
        legacy_path = self.project_dir / "characters" / f"{character_id}.yaml"
        if definition_path.exists():
            raw = self._read_yaml(definition_path)
        elif legacy_path.exists():
            raw = self._read_yaml(legacy_path).get("core", {})
        else:
            raise FileNotFoundError(definition_path)
        return CharacterCore.model_validate(raw)

    def save(self, core: CharacterCore) -> CharacterCore:
        self.validate(core)
        definition_exists = self.definition_path(core.id).exists()
        try:
            previous = self.load(core.id)
        except FileNotFoundError:
            saved = core
        else:
            if self._semantic_content(previous) == self._semantic_content(core):
                if definition_exists:
                    return previous
                saved = previous
            else:
                saved = core.model_copy(
                    update={
                        "definition_revision": previous.definition_revision + 1,
                        "definition_updated_at": datetime.now(),
                    }
                )
        self.bible_repository._write_yaml_atomic(
            self.definition_path(core.id), saved.model_dump(mode="json")
        )
        return saved

    def validate(self, core: CharacterCore) -> None:
        elements = {element.id: element for element in self.bible_repository.load_all()}
        seen = set()
        for relation in core.element_relations:
            edge = (relation.kind, relation.target_element_id)
            if edge in seen:
                raise ValueError("duplicate relationship")
            seen.add(edge)
            target = elements.get(relation.target_element_id)
            if target is None:
                raise ValueError(f"Relationship target is missing: {relation.target_element_id}")
            if target.element_type not in relation_definition(relation.kind).allowed_target_types:
                raise ValueError(
                    f"Invalid relationship target type: {target.element_type.value}"
                )

    def characters_referencing_element(
        self, element_id: str
    ) -> list[tuple[CharacterCore, CharacterElementRelation]]:
        from app.storage.project_files import list_character_ids

        return [
            (core, relation)
            for character_id in list_character_ids(self.project_dir)
            for core in [self.load(character_id)]
            for relation in core.element_relations
            if relation.target_element_id == element_id
        ]

    def unlink_element(self, element_id: str) -> list[str]:
        references = self.characters_referencing_element(element_id)
        cores = {core.id: core for core, _ in references}
        paths = [self.definition_path(character_id) for character_id in cores]
        with rollback_files(paths):
            for core in cores.values():
                self.save(
                    core.model_copy(
                        update={
                            "element_relations": [
                                relation
                                for relation in core.element_relations
                                if relation.target_element_id != element_id
                            ]
                        }
                    )
                )
        return list(cores)

    def definition_path(self, character_id: str) -> Path:
        return self.project_dir / "characters" / character_id / "definition.yaml"

    @staticmethod
    def _read_yaml(path: Path) -> dict:
        with path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid Character Definition: {path}")
        return raw

    @staticmethod
    def _semantic_content(core: CharacterCore) -> dict:
        return core.model_dump(exclude={"definition_revision", "definition_updated_at"})
