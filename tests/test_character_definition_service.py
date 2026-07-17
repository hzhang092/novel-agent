import os
from pathlib import Path

import pytest
import yaml

from app.storage.bible_models import FactionElement
from app.storage.bible_repository import WorldBibleService
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.models import CharacterCore, CharacterElementRelation, Project
from app.storage.project_files import create_project


def character_service(tmp_path):
    path = create_project(tmp_path, Project(title="故事", genre="玄幻"))
    WorldBibleService(path).save_element(FactionElement(id="faction", name="青云宗"))
    return path, CharacterDefinitionService(path)


def linked_character(character_id, name="林风"):
    return CharacterCore(
        id=character_id,
        name=name,
        element_relations=[
            CharacterElementRelation(kind="member_of", target_element_id="faction")
        ],
    )


def test_save_increments_revision_only_for_semantic_changes(tmp_path):
    _, service = character_service(tmp_path)
    created = service.save(CharacterCore(id="hero", name="林风"))
    definition_path = service.definition_path("hero")
    original_bytes = definition_path.read_bytes()

    unchanged = service.save(
        created.model_copy(
            update={"definition_revision": 99, "definition_updated_at": created.definition_updated_at}
        )
    )
    assert unchanged.definition_revision == 1
    assert definition_path.read_bytes() == original_bytes

    changed = service.save(created.model_copy(update={"name": "林风真人"}))

    assert original_bytes != definition_path.read_bytes()
    assert changed.definition_revision == 2
    assert changed.definition_updated_at >= created.definition_updated_at


def test_failed_atomic_save_preserves_previous_definition(tmp_path, monkeypatch):
    _, service = character_service(tmp_path)
    created = service.save(CharacterCore(id="hero", name="林风"))
    definition_path = service.definition_path("hero")
    before = definition_path.read_bytes()
    real_replace = os.replace

    def fail_definition(source, destination):
        if Path(destination) == definition_path:
            raise OSError("definition replace failed")
        real_replace(source, destination)

    monkeypatch.setattr("app.storage.bible_repository.os.replace", fail_definition)

    with pytest.raises(OSError, match="definition replace failed"):
        service.save(created.model_copy(update={"name": "新名字"}))

    assert definition_path.read_bytes() == before


def test_explicit_save_of_unchanged_legacy_definition_creates_new_layout(tmp_path):
    path, service = character_service(tmp_path)
    legacy_path = path / "characters" / "legacy.yaml"
    legacy_path.write_text(
        yaml.safe_dump(
            {"core": {"id": "legacy", "name": "旧角色"}, "state": {"character_id": "legacy"}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    saved = service.save(CharacterCore(id="legacy", name="旧角色"))

    assert service.definition_path("legacy").exists()
    assert saved.definition_revision == 1


def test_inbound_character_references_are_derived_from_definitions(tmp_path):
    _, service = character_service(tmp_path)
    service.save(linked_character("hero", "林风"))
    service.save(CharacterCore(id="other", name="路人"))

    references = service.characters_referencing_element("faction")

    assert [(core.id, relation.kind.value) for core, relation in references] == [
        ("hero", "member_of")
    ]


def test_unlink_element_removes_all_character_links_and_increments_revisions(tmp_path):
    _, service = character_service(tmp_path)
    service.save(linked_character("hero-1", "林风"))
    service.save(linked_character("hero-2", "赵云"))

    changed_ids = service.unlink_element("faction")

    assert changed_ids == ["hero-1", "hero-2"]
    assert service.load("hero-1").element_relations == []
    assert service.load("hero-2").element_relations == []
    assert service.load("hero-1").definition_revision == 2


def test_unlink_failure_rolls_back_every_character_definition(tmp_path, monkeypatch):
    _, service = character_service(tmp_path)
    service.save(linked_character("hero-1", "林风"))
    service.save(linked_character("hero-2", "赵云"))
    paths = [service.definition_path(character_id) for character_id in ("hero-1", "hero-2")]
    before = {path: path.read_bytes() for path in paths}
    real_replace = os.replace
    failed = False

    def fail_second_definition(source, destination):
        nonlocal failed
        if Path(destination) == paths[1] and not failed:
            failed = True
            raise OSError("second definition replace failed")
        real_replace(source, destination)

    monkeypatch.setattr("app.storage.bible_repository.os.replace", fail_second_definition)

    with pytest.raises(OSError, match="second definition replace failed"):
        service.unlink_element("faction")

    assert all(path.read_bytes() == before[path] for path in paths)
    assert len(service.characters_referencing_element("faction")) == 2
