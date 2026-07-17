from app.pipeline.bible_suggestions import (
    AddCharacterRelationSuggestion,
    AddElementRelationSuggestion,
    CreateElementSuggestion,
    UpdateElementSuggestion,
    apply_bible_suggestions,
    find_duplicate_candidates,
)
from app.storage.bible_models import FactionElement, LocationElement
from app.storage.bible_repository import WorldBibleService
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.models import CharacterCore, Project
from app.storage.project_files import create_project
import pytest


def test_duplicate_candidates_are_type_scoped_ranked_and_deterministic():
    proposal = CreateElementSuggestion(
        proposal_id="new-sect",
        confidence=0.8,
        element_type="faction",
        name="ＣＲＩＭＳＯＮ ＣＬＯＵＤ ＳＥＣＴ",
        aliases=["Red Cloud"],
    )
    existing = [
        FactionElement(id="alias-name", name="Red Cloud"),
        LocationElement(id="wrong-type", name="Crimson Cloud Sect"),
        FactionElement(id="same-name", name="Crimson Cloud Sect"),
    ]

    candidates = find_duplicate_candidates(proposal, existing)

    assert [(item.element_id, item.reason) for item in candidates] == [
        ("same-name", "same_name"),
        ("alias-name", "proposed_alias_matches_name"),
    ]


def test_apply_assigns_final_ids_and_resolves_temporary_relation_refs(tmp_path):
    project_dir = create_project(tmp_path, Project(title="故事", genre="玄幻"))
    service = WorldBibleService(project_dir)
    service.save_element(FactionElement(id="sect-id", name="赤云宗"))

    result = apply_bible_suggestions(
        service,
        [
            CreateElementSuggestion(
                proposal_id="new-mine",
                confidence=0.9,
                element_type="location",
                name="北谷灵矿",
            ),
            AddElementRelationSuggestion(
                proposal_id="sect-controls-mine",
                confidence=0.8,
                source_ref="sect-id",
                kind="controls",
                target_ref="new-mine",
            ),
        ],
        id_factory=lambda: "final-mine-uuid",
    )

    assert result.created_element_ids == {"new-mine": "final-mine-uuid"}
    by_id = {element.id: element for element in service.load().elements}
    assert by_id["final-mine-uuid"].name == "北谷灵矿"
    assert by_id["sect-id"].relationships[0].target_element_id == "final-mine-uuid"


def test_apply_updates_an_existing_element_through_snapshot_validation(tmp_path):
    project_dir = create_project(tmp_path, Project(title="故事", genre="玄幻"))
    service = WorldBibleService(project_dir)
    original = service.save_element(
        FactionElement(id="sect-id", name="赤云宗", description="旧描述")
    )

    apply_bible_suggestions(
        service,
        [
            UpdateElementSuggestion(
                proposal_id="update-sect",
                confidence=0.85,
                target_element_id="sect-id",
                aliases=["赤云门"],
                summary="北谷宗门",
                typed_fields={"description": "控制北谷灵矿"},
            )
        ],
    )

    updated = service.load().elements[0]
    assert (updated.aliases, updated.summary, updated.description) == (
        ["赤云门"],
        "北谷宗门",
        "控制北谷灵矿",
    )
    assert updated.revision == original.revision + 1


def test_apply_resolves_new_element_ref_for_character_relation(tmp_path):
    project_dir = create_project(tmp_path, Project(title="故事", genre="玄幻"))
    bible_service = WorldBibleService(project_dir)
    bible_service.load()
    character_service = CharacterDefinitionService(project_dir)
    character_service.save(CharacterCore(id="hero-id", name="林风"))

    result = apply_bible_suggestions(
        bible_service,
        [
            CreateElementSuggestion(
                proposal_id="new-sect",
                confidence=0.9,
                element_type="faction",
                name="赤云宗",
            ),
            AddCharacterRelationSuggestion(
                proposal_id="hero-member",
                confidence=0.8,
                character_id="hero-id",
                kind="member_of",
                target_ref="new-sect",
            ),
        ],
        character_service=character_service,
        id_factory=lambda: "final-sect-uuid",
    )

    assert result.updated_character_ids == ("hero-id",)
    relation = character_service.load("hero-id").element_relations[0]
    assert (relation.kind, relation.target_element_id) == (
        "member_of",
        "final-sect-uuid",
    )


def test_invalid_typed_fields_leave_the_bible_unchanged(tmp_path):
    project_dir = create_project(tmp_path, Project(title="故事", genre="玄幻"))
    service = WorldBibleService(project_dir)
    service.load()
    before_manifest = (project_dir / "bible" / "manifest.yaml").read_bytes()

    with pytest.raises(ValueError, match="typed fields"):
        apply_bible_suggestions(
            service,
            [
                CreateElementSuggestion(
                    proposal_id="bad-faction",
                    confidence=0.9,
                    element_type="faction",
                    name="赤云宗",
                    typed_fields={"realms": []},
                )
            ],
            id_factory=lambda: "must-not-be-written",
        )

    assert (project_dir / "bible" / "manifest.yaml").read_bytes() == before_manifest
    assert not (
        project_dir / "bible" / "elements" / "must-not-be-written.yaml"
    ).exists()


def test_mixed_apply_rolls_back_bible_when_character_write_fails(
    tmp_path, monkeypatch
):
    project_dir = create_project(tmp_path, Project(title="故事", genre="玄幻"))
    bible_service = WorldBibleService(project_dir)
    bible_service.load()
    character_service = CharacterDefinitionService(project_dir)
    character_service.save(CharacterCore(id="hero-id", name="林风"))
    before = {
        path: path.read_bytes()
        for path in (
            project_dir / "bible" / "manifest.yaml",
            project_dir / "project.yaml",
            project_dir / "world.md",
            character_service.definition_path("hero-id"),
        )
    }

    def fail_save(core):
        raise OSError("character definition write failed")

    monkeypatch.setattr(character_service, "save", fail_save)

    with pytest.raises(OSError, match="character definition write failed"):
        apply_bible_suggestions(
            bible_service,
            [
                CreateElementSuggestion(
                    proposal_id="new-sect",
                    confidence=0.9,
                    element_type="faction",
                    name="赤云宗",
                ),
                AddCharacterRelationSuggestion(
                    proposal_id="hero-member",
                    confidence=0.8,
                    character_id="hero-id",
                    kind="member_of",
                    target_ref="new-sect",
                ),
            ],
            character_service=character_service,
            id_factory=lambda: "rolled-back-id",
        )

    assert all(path.read_bytes() == content for path, content in before.items())
    assert not (
        project_dir / "bible" / "elements" / "rolled-back-id.yaml"
    ).exists()


def test_invalid_relation_target_is_rejected_before_any_write(tmp_path):
    project_dir = create_project(tmp_path, Project(title="故事", genre="玄幻"))
    service = WorldBibleService(project_dir)
    service.save_element(FactionElement(id="sect-id", name="赤云宗"))
    before = {
        path: path.read_bytes()
        for path in (
            project_dir / "bible" / "manifest.yaml",
            project_dir / "bible" / "elements" / "sect-id.yaml",
            project_dir / "project.yaml",
            project_dir / "world.md",
        )
    }

    with pytest.raises(ValueError, match="missing target"):
        apply_bible_suggestions(
            service,
            [
                AddElementRelationSuggestion(
                    proposal_id="bad-relation",
                    confidence=0.8,
                    source_ref="sect-id",
                    kind="controls",
                    target_ref="missing-id",
                )
            ],
        )

    assert all(path.read_bytes() == content for path, content in before.items())
