import os
from pathlib import Path

import pytest

from app.domain.character_element_relation_catalog import relation_definition
from app.storage.bible_models import FactionElement, LocationElement, TerminologyElement
from app.storage.bible_repository import WorldBibleService
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.models import CharacterCore, CharacterElementRelation, Project
from app.storage.project_files import create_project


def project_with_elements(tmp_path):
    path = create_project(tmp_path, Project(title="故事", genre="玄幻"))
    bible = WorldBibleService(path)
    bible.save_element(FactionElement(id="faction", name="青云宗"))
    bible.save_element(LocationElement(id="location", name="青云山"))
    bible.save_element(TerminologyElement(id="term", name="灵石"))
    return path


@pytest.mark.parametrize(
    ("kind", "target"),
    [
        ("member_of", "faction"),
        ("originates_from", "location"),
        ("associated_with", "term"),
    ],
)
def test_valid_character_element_relations_are_saved(tmp_path, kind, target):
    service = CharacterDefinitionService(project_with_elements(tmp_path))
    saved = service.save(
        CharacterCore(
            id="hero",
            name="林风",
            element_relations=[
                CharacterElementRelation(kind=kind, target_element_id=target)
            ],
        )
    )

    assert service.load(saved.id).element_relations == saved.element_relations


def test_relation_catalog_exposes_target_types_and_inverse_labels():
    member = relation_definition("member_of")
    origin = relation_definition("originates_from")

    assert {target.value for target in member.allowed_target_types} == {"faction"}
    assert member.inverse_label == "Has member"
    assert {target.value for target in origin.allowed_target_types} == {"location"}


def test_relation_target_must_exist_and_have_an_allowed_type(tmp_path):
    service = CharacterDefinitionService(project_with_elements(tmp_path))

    with pytest.raises(ValueError, match="missing"):
        service.save(
            CharacterCore(
                id="missing-target",
                name="林风",
                element_relations=[
                    CharacterElementRelation(kind="member_of", target_element_id="missing")
                ],
            )
        )
    with pytest.raises(ValueError, match="target type"):
        service.save(
            CharacterCore(
                id="wrong-type",
                name="林风",
                element_relations=[
                    CharacterElementRelation(kind="member_of", target_element_id="location")
                ],
            )
        )


def test_duplicate_character_element_relations_are_rejected(tmp_path):
    service = CharacterDefinitionService(project_with_elements(tmp_path))
    relation = CharacterElementRelation(kind="member_of", target_element_id="faction")

    with pytest.raises(ValueError, match="duplicate relationship"):
        service.save(
            CharacterCore(
                id="hero",
                name="林风",
                element_relations=[relation, relation.model_copy()],
            )
        )


def test_element_deletion_blocks_character_references_without_unlink(tmp_path):
    path = project_with_elements(tmp_path)
    characters = CharacterDefinitionService(path)
    characters.save(
        CharacterCore(
            id="hero",
            name="林风",
            element_relations=[
                CharacterElementRelation(kind="member_of", target_element_id="faction")
            ],
        )
    )

    with pytest.raises(ValueError, match="referenced"):
        WorldBibleService(path).delete_element("faction")

    assert characters.load("hero").element_relations[0].target_element_id == "faction"


def test_element_deletion_with_unlink_removes_character_references(tmp_path):
    path = project_with_elements(tmp_path)
    characters = CharacterDefinitionService(path)
    characters.save(
        CharacterCore(
            id="hero",
            name="林风",
            element_relations=[
                CharacterElementRelation(kind="member_of", target_element_id="faction")
            ],
        )
    )

    WorldBibleService(path).delete_element("faction", unlink_references=True)

    assert characters.load("hero").element_relations == []
    with pytest.raises(FileNotFoundError):
        WorldBibleService(path).repository.load("faction")


def test_element_unlink_rolls_back_character_definitions_when_delete_fails(
    tmp_path, monkeypatch
):
    path = project_with_elements(tmp_path)
    characters = CharacterDefinitionService(path)
    characters.save(
        CharacterCore(
            id="hero",
            name="林风",
            element_relations=[
                CharacterElementRelation(kind="member_of", target_element_id="faction")
            ],
        )
    )
    definition_path = characters.definition_path("hero")
    before_definition = definition_path.read_bytes()
    real_replace = os.replace
    failed = False

    def fail_world_once(source, destination):
        nonlocal failed
        if Path(destination).name == "world.md" and not failed:
            failed = True
            raise OSError("world markdown replace failed")
        real_replace(source, destination)

    monkeypatch.setattr("app.storage.bible_repository.os.replace", fail_world_once)

    with pytest.raises(OSError, match="world markdown replace failed"):
        WorldBibleService(path).delete_element("faction", unlink_references=True)

    assert definition_path.read_bytes() == before_definition
    assert WorldBibleService(path).repository.load("faction").name == "青云宗"
