"""Structured, reviewable Story Bible proposals."""

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Annotated, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from app.storage.bible_models import (
    BibleElement,
    BibleElementBase,
    BibleElementType,
    BibleElementRelation,
    BibleRelationKind,
    normalize_text,
)
from app.storage.models import CharacterElementRelation, CharacterElementRelationKind


class SuggestionAction(str, Enum):
    CREATE_ELEMENT = "create_element"
    UPDATE_ELEMENT = "update_element"
    ADD_ELEMENT_RELATION = "add_element_relation"
    ADD_CHARACTER_RELATION = "add_character_relation"


class BibleSuggestionBase(BaseModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    confidence: float = Field(ge=0, le=1)
    rationale: str = ""
    source_excerpt: str = ""


class CreateElementSuggestion(BibleSuggestionBase):
    action: Literal[SuggestionAction.CREATE_ELEMENT] = SuggestionAction.CREATE_ELEMENT
    element_type: BibleElementType
    name: str
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    typed_fields: dict = Field(default_factory=dict)


class UpdateElementSuggestion(BibleSuggestionBase):
    action: Literal[SuggestionAction.UPDATE_ELEMENT] = SuggestionAction.UPDATE_ELEMENT
    target_element_id: str
    name: str | None = None
    aliases: list[str] | None = None
    summary: str | None = None
    typed_fields: dict = Field(default_factory=dict)


class AddElementRelationSuggestion(BibleSuggestionBase):
    action: Literal[SuggestionAction.ADD_ELEMENT_RELATION] = (
        SuggestionAction.ADD_ELEMENT_RELATION
    )
    source_ref: str
    kind: BibleRelationKind
    target_ref: str
    note: str = ""


class AddCharacterRelationSuggestion(BibleSuggestionBase):
    action: Literal[SuggestionAction.ADD_CHARACTER_RELATION] = (
        SuggestionAction.ADD_CHARACTER_RELATION
    )
    character_id: str
    kind: CharacterElementRelationKind
    target_ref: str
    note: str = ""


BibleSuggestion = Annotated[
    Union[
        CreateElementSuggestion,
        UpdateElementSuggestion,
        AddElementRelationSuggestion,
        AddCharacterRelationSuggestion,
    ],
    Field(discriminator="action"),
]


class BibleSuggestionResponse(BaseModel):
    proposals: list[BibleSuggestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_proposal_ids(self) -> "BibleSuggestionResponse":
        ids = [proposal.proposal_id for proposal in self.proposals]
        if len(ids) != len(set(ids)):
            raise ValueError("proposal IDs must be unique")
        return self


@dataclass(frozen=True)
class DuplicateCandidate:
    element_id: str
    reason: str
    score: int


@dataclass(frozen=True)
class AppliedBibleSuggestions:
    created_element_ids: dict[str, str]
    updated_character_ids: tuple[str, ...] = ()


def find_duplicate_candidates(
    proposal: CreateElementSuggestion,
    existing_elements: list[BibleElement],
) -> list[DuplicateCandidate]:
    """Return deterministic possible duplicates without choosing a merge."""
    proposed_name = normalize_text(proposal.name)
    proposed_aliases = {normalize_text(alias) for alias in proposal.aliases}
    candidates: list[tuple[DuplicateCandidate, str]] = []
    for element in existing_elements:
        if element.element_type != proposal.element_type:
            continue
        name = normalize_text(element.name)
        aliases = {normalize_text(alias) for alias in element.aliases}
        match: tuple[str, int] | None = None
        if proposed_name == name:
            match = ("same_name", 100)
        elif proposed_name in aliases:
            match = ("proposed_name_matches_alias", 90)
        elif name in proposed_aliases:
            match = ("proposed_alias_matches_name", 80)
        elif proposed_aliases & aliases:
            match = ("same_alias", 70)
        elif (
            proposal.summary
            and element.summary
            and SequenceMatcher(
                None,
                normalize_text(proposal.summary),
                normalize_text(element.summary),
            ).ratio()
            >= 0.75
        ):
            match = ("similar_summary", 60)
        if match is not None:
            reason, score = match
            candidates.append(
                (DuplicateCandidate(element.id, reason, score), name)
            )
    return [
        candidate
        for candidate, _ in sorted(
            candidates,
            key=lambda item: (-item[0].score, item[1], item[0].element_id),
        )
    ]


def apply_bible_suggestions(
    service,
    proposals: list[BibleSuggestion],
    *,
    character_service=None,
    id_factory=lambda: str(uuid4()),
) -> AppliedBibleSuggestions:
    """Apply already-reviewed proposals through the existing atomic Bible seam."""
    bible = service.load()
    created_ids = {
        proposal.proposal_id: id_factory()
        for proposal in proposals
        if isinstance(proposal, CreateElementSuggestion)
    }
    elements = list(bible.elements)
    adapter = TypeAdapter(BibleElement)
    for proposal in proposals:
        if isinstance(proposal, CreateElementSuggestion):
            created = adapter.validate_python(
                {
                    "id": created_ids[proposal.proposal_id],
                    "element_type": proposal.element_type,
                    "name": proposal.name,
                    "aliases": proposal.aliases,
                    "summary": proposal.summary,
                    **proposal.typed_fields,
                }
            )
            allowed = set(type(created).model_fields) - set(BibleElementBase.model_fields)
            if set(proposal.typed_fields) - allowed:
                raise ValueError("Element creation contains invalid typed fields")
            elements.append(created)

    by_id = {element.id: element for element in elements}
    for proposal in proposals:
        if not isinstance(proposal, UpdateElementSuggestion):
            continue
        if proposal.target_element_id not in by_id:
            raise ValueError(
                f"Element update proposal references a missing target: "
                f"{proposal.target_element_id}"
            )
        current = by_id[proposal.target_element_id]
        unknown = set(proposal.typed_fields) - set(type(current).model_fields)
        protected = set(proposal.typed_fields) & set(BibleElementBase.model_fields)
        if unknown or protected:
            raise ValueError("Element update contains invalid typed fields")
        changes = {
            key: value
            for key in ("name", "aliases", "summary")
            if (value := getattr(proposal, key)) is not None
        }
        updated = adapter.validate_python(
            {**current.model_dump(), **changes, **proposal.typed_fields}
        )
        elements[elements.index(current)] = updated
        by_id[current.id] = updated

    for proposal in proposals:
        if not isinstance(proposal, AddElementRelationSuggestion):
            continue
        source_id = created_ids.get(proposal.source_ref, proposal.source_ref)
        target_id = created_ids.get(proposal.target_ref, proposal.target_ref)
        if source_id not in by_id or target_id not in by_id:
            raise ValueError("Element relationship proposal references a missing target")
        source = by_id[source_id]
        updated = source.model_copy(
            update={
                "relationships": [
                    *source.relationships,
                    BibleElementRelation(
                        kind=proposal.kind,
                        target_element_id=target_id,
                        note=proposal.note,
                    ),
                ]
            }
        )
        elements[elements.index(source)] = updated
        by_id[source_id] = updated

    character_updates = {}
    for proposal in proposals:
        if not isinstance(proposal, AddCharacterRelationSuggestion):
            continue
        if character_service is None:
            raise ValueError("Character relationship proposals require a character service")
        target_id = created_ids.get(proposal.target_ref, proposal.target_ref)
        target = by_id.get(target_id)
        if target is None:
            raise ValueError("Character relationship proposal references a missing target")
        from app.domain.character_element_relation_catalog import relation_definition

        if target.element_type not in relation_definition(proposal.kind).allowed_target_types:
            raise ValueError("Character relationship proposal has an invalid target type")
        core = character_updates.get(proposal.character_id)
        if core is None:
            core = character_service.load(proposal.character_id)
        relation = CharacterElementRelation(
            kind=proposal.kind,
            target_element_id=target_id,
            note=proposal.note,
        )
        edge = (relation.kind, relation.target_element_id)
        if edge in {(item.kind, item.target_element_id) for item in core.element_relations}:
            raise ValueError("duplicate character relationship")
        character_updates[core.id] = core.model_copy(
            update={"element_relations": [*core.element_relations, relation]}
        )

    from app.storage.bible_repository import rollback_files

    touched = [path for path in service.project_dir.rglob("*") if path.is_file()]
    touched.extend(
        service.repository.elements_dir / f"{element_id}.yaml"
        for element_id in created_ids.values()
    )
    with rollback_files(touched):
        service.apply_snapshot(bible.overview, elements)
        for core in character_updates.values():
            character_service.save(core)
    return AppliedBibleSuggestions(created_ids, tuple(character_updates))
