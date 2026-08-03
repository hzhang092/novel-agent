"""Guided Story Brief and Story Proposal use cases."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from app.application.errors import (
    ConcurrentModificationError,
    OperationBlockedError,
    StoryDesignerProviderError,
)
from app.application.scene_workflow import ProjectRunGuard
from app.providers.base import LLMProvider, ProviderResponse
from app.storage.bible_repository import WorldBibleService, rollback_files
from app.storage.models import (
    ActiveProposalDraft,
    ActiveBootstrapDraft,
    ApprovedStoryProposal,
    BootstrapPatchPreview,
    Character,
    StoryBootstrap,
    StoryBrief,
    StoryProposal,
    StyleGuide,
    WorldSetting,
)
from app.storage.project_files import (
    PLANNING_YAML,
    PROJECT_YAML,
    load_planning,
    load_project,
    load_all_volumes,
    load_canon_facts,
    list_character_ids,
    save_character,
    save_planning,
    save_project,
    save_style_guide,
    save_volume_outline,
)


def require_compatible_active_draft(planning, draft_type: type) -> None:
    active = planning.active_draft
    if active is not None and not isinstance(active, draft_type):
        raise OperationBlockedError(
            f"Resolve the active {active.kind} draft before starting another planning draft"
        )


class StoryDesignerService:
    """Generates reviewable planning drafts and approves the initial canonical bundle."""

    def __init__(
        self,
        project_dir: Path,
        *,
        provider_factory: Callable[[], LLMProvider] | None = None,
        run_guard: ProjectRunGuard | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self._provider_factory = provider_factory or self._default_provider
        self.run_guard = run_guard or ProjectRunGuard()

    def save_brief(
        self, brief: StoryBrief, *, provisional_destination: str | None = None
    ) -> StoryBrief:
        planning = load_planning(self.project_dir)
        brief.revision = (planning.story_brief.revision + 1) if planning.story_brief else 1
        planning.story_brief = brief
        if provisional_destination is not None:
            planning.provisional_destination = " ".join(provisional_destination.split())
        save_planning(self.project_dir, planning)
        return brief

    def is_empty_project(self) -> bool:
        """Return whether the project has no canonical story content yet."""
        return self._is_empty_project()

    def ensure_quick_brief(self) -> StoryBrief | None:
        """Start the editable Brief in an empty project when Quick is opened."""
        planning = load_planning(self.project_dir)
        if not self.is_empty_project() or planning.story_brief is not None:
            return planning.story_brief
        return self.save_brief(StoryBrief())

    def has_unapproved_bootstrap(self) -> bool:
        return self.unapproved_bootstrap_revision() is not None

    def unapproved_bootstrap_revision(self) -> int | None:
        draft = load_planning(self.project_dir).active_draft
        return draft.revision if isinstance(draft, ActiveBootstrapDraft) else None

    def discard_unapproved_bootstrap(self, *, base_revision: int) -> None:
        """Discard only the active bootstrap draft; keep Brief and Proposal."""
        planning = load_planning(self.project_dir)
        self._bootstrap_draft(planning, base_revision)
        planning.active_draft = None
        save_planning(self.project_dir, planning)

    async def generate_proposal(self, instruction: str = "") -> ActiveProposalDraft:
        return await self._replace_draft(base_revision=None, instruction=instruction)

    async def adjust_proposal(
        self, instruction: str, *, base_revision: int
    ) -> ActiveProposalDraft:
        return await self._replace_draft(base_revision=base_revision, instruction=instruction)

    def approve_proposal(
        self, *, base_revision: int, accept_title: bool = False
    ) -> ApprovedStoryProposal:
        planning = load_planning(self.project_dir)
        draft = planning.active_draft
        if (
            not isinstance(draft, ActiveProposalDraft)
            or draft.revision != base_revision
            or planning.story_brief is None
            or draft.based_on_brief_revision != planning.story_brief.revision
        ):
            raise ConcurrentModificationError("The proposal draft has changed; regenerate it")
        revision = (planning.approved_proposal.revision + 1) if planning.approved_proposal else 1
        approved = ApprovedStoryProposal(
            **draft.proposal.model_dump(),
            revision=revision,
            based_on_brief_revision=draft.based_on_brief_revision,
        )
        planning.approved_proposal = approved
        planning.approved_brief = planning.story_brief.model_copy(deep=True)
        planning.active_draft = None
        paths = [self.project_dir / PLANNING_YAML, self.project_dir / PROJECT_YAML]
        with rollback_files(paths):
            save_planning(self.project_dir, planning)
            project = load_project(self.project_dir)
            project.chapter_length = planning.story_brief.chapter_length
            if accept_title:
                project.title = approved.title
            save_project(self.project_dir, project)
        return approved

    def can_generate_bootstrap(self) -> bool:
        """Whether this project can safely start its one bootstrap draft."""
        planning = load_planning(self.project_dir)
        return (
            planning.approved_proposal is not None
            and planning.active_draft is None
            and self._is_empty_project()
        )

    async def generate_structured(
        self, messages: list[dict[str, str]], schema: type[BaseModel]
    ) -> BaseModel:
        """Use Story Designer's configured structured-provider route for planning drafts."""
        if not self.run_guard.acquire("story_designer"):
            raise OperationBlockedError("Another project generation is already active")
        try:
            return await self._generate_with_provider(messages, schema)
        finally:
            self.run_guard.release("story_designer")

    async def _generate_with_provider(
        self, messages: list[dict[str, str]], schema: type[BaseModel]
    ) -> BaseModel:
        provider = self._provider_factory()
        try:
            response: ProviderResponse = await provider.generate_structured(
                messages, schema
            )
            return (
                response.model
                if isinstance(response.model, schema)
                else schema.model_validate(response.parsed or {})
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise StoryDesignerProviderError(str(error)) from error
        finally:
            await provider.close()

    async def generate_bootstrap(self) -> ActiveBootstrapDraft:
        """Generate one initial canonical bundle, but retain it as a draft."""
        if not self.run_guard.acquire("story_designer"):
            raise OperationBlockedError("Another project generation is already active")
        try:
            planning = load_planning(self.project_dir)
            if not self.can_generate_bootstrap():
                raise OperationBlockedError("Bootstrap requires an approved proposal and an empty project without an active draft")
            proposal = planning.approved_proposal
            brief = planning.story_brief
            if brief is None:
                raise OperationBlockedError("A Story Brief is required before bootstrap")
            bootstrap = await self._generate_with_provider(
                _bootstrap_messages(proposal, brief), StoryBootstrap
            )
            current = load_planning(self.project_dir)
            if current.approved_proposal is None or current.approved_proposal.revision != proposal.revision:
                raise ConcurrentModificationError("The approved proposal has changed; regenerate bootstrap")
            if current.story_brief is None or current.story_brief.revision != brief.revision:
                raise ConcurrentModificationError("The Story Brief has changed; regenerate bootstrap")
            if current.active_draft is not None or not self._is_empty_project():
                raise OperationBlockedError("Bootstrap requires an empty project without an active draft")
            draft = ActiveBootstrapDraft(
                revision=(current.active_draft.revision + 1 if current.active_draft else proposal.revision + 1),
                based_on_brief_revision=brief.revision,
                based_on_proposal_revision=proposal.revision,
                bootstrap=bootstrap,
            )
            current.active_draft = draft
            save_planning(self.project_dir, current)
            return draft
        finally:
            self.run_guard.release("story_designer")

    def save_bootstrap(
        self, bootstrap: StoryBootstrap, *, base_revision: int
    ) -> ActiveBootstrapDraft:
        planning = load_planning(self.project_dir)
        draft = self._bootstrap_draft(planning, base_revision)
        saved = draft.model_copy(update={"revision": draft.revision + 1, "bootstrap": bootstrap})
        planning.active_draft = saved
        save_planning(self.project_dir, planning)
        return saved

    async def adjust_bootstrap(
        self, instruction: str, *, base_revision: int
    ) -> BootstrapPatchPreview:
        if not self.run_guard.acquire("story_designer"):
            raise OperationBlockedError("Another project generation is already active")
        try:
            planning = load_planning(self.project_dir)
            draft = self._bootstrap_draft(planning, base_revision)
            preview = await self._generate_with_provider(
                _bootstrap_patch_messages(draft, instruction),
                BootstrapPatchPreview,
            )
            self._bootstrap_draft(load_planning(self.project_dir), base_revision)
            return preview.model_copy(update={"base_revision": base_revision})
        finally:
            self.run_guard.release("story_designer")

    def apply_bootstrap_patch(self, preview: BootstrapPatchPreview) -> ActiveBootstrapDraft:
        planning = load_planning(self.project_dir)
        draft = self._bootstrap_draft(planning, preview.base_revision)
        document = draft.bootstrap.model_dump(mode="json")
        for operation in preview.operations:
            _replace_bootstrap_value(document, operation.path, operation.value, operation.op)
        return self.save_bootstrap(StoryBootstrap.model_validate(document), base_revision=draft.revision)

    def approve_bootstrap(self, *, base_revision: int) -> None:
        planning = load_planning(self.project_dir)
        draft = self._bootstrap_draft(planning, base_revision)
        if not self._is_empty_project():
            raise OperationBlockedError("Bootstrap is only available for an empty project")
        bootstrap = draft.bootstrap
        bible = WorldBibleService(self.project_dir)
        paths = [
            self.project_dir / PROJECT_YAML,
            self.project_dir / "world.md",
            self.project_dir / "style.yaml",
            self.project_dir / PLANNING_YAML,
            bible.repository.manifest_path,
            *(bible.repository.element_path(item.id) for item in bootstrap.elements),
            *(self.project_dir / "outline" / f"{arc.id}.yaml" for arc in bootstrap.arcs),
            *(
                path
                for character in bootstrap.characters
                for path in (
                    self.project_dir / "characters" / character.core.id / "definition.yaml",
                    self.project_dir / "characters" / character.core.id / "events.jsonl",
                    self.project_dir / "characters" / character.core.id / "state.yaml",
                )
            ),
        ]
        with rollback_files(paths):
            bible.apply_snapshot(bootstrap.overview, bootstrap.elements)
            for character in bootstrap.characters:
                save_character(self.project_dir, character)
            save_style_guide(self.project_dir, bootstrap.style)
            for arc in bootstrap.arcs:
                save_volume_outline(self.project_dir, arc)
            planning.active_draft = None  # clear only after every canonical save succeeded
            save_planning(self.project_dir, planning)

    @staticmethod
    def _bootstrap_draft(planning, base_revision: int) -> ActiveBootstrapDraft:
        draft = planning.active_draft
        if not isinstance(draft, ActiveBootstrapDraft) or draft.revision != base_revision:
            raise ConcurrentModificationError("The bootstrap draft has changed; regenerate it")
        if planning.approved_proposal is None or (
            draft.based_on_proposal_revision != planning.approved_proposal.revision
        ):
            raise ConcurrentModificationError("The approved proposal has changed; regenerate bootstrap")
        if planning.story_brief is None or draft.based_on_brief_revision != planning.story_brief.revision:
            raise ConcurrentModificationError("The Story Brief has changed; regenerate bootstrap")
        return draft

    def _is_empty_project(self) -> bool:
        project = load_project(self.project_dir)
        bible = WorldBibleService(self.project_dir).load()
        return (
            not bible.elements
            and not list_character_ids(self.project_dir)
            and not load_all_volumes(self.project_dir)
            and not load_canon_facts(self.project_dir)
            and not any(path.is_file() for path in (self.project_dir / "scenes").rglob("*"))
            and project.world_setting == WorldSetting()
            and project.style_guide == StyleGuide()
        )

    async def _replace_draft(
        self, *, base_revision: int | None, instruction: str
    ) -> ActiveProposalDraft:
        if not self.run_guard.acquire("story_designer"):
            raise OperationBlockedError("Another project generation is already active")
        try:
            return await self._replace_draft_while_active(
                base_revision=base_revision, instruction=instruction
            )
        finally:
            self.run_guard.release("story_designer")

    async def _replace_draft_while_active(
        self, *, base_revision: int | None, instruction: str
    ) -> ActiveProposalDraft:
        planning = load_planning(self.project_dir)
        require_compatible_active_draft(planning, ActiveProposalDraft)
        brief = planning.story_brief
        if brief is None:
            raise OperationBlockedError("A Story Brief is required before a proposal")
        if base_revision is not None and (
            not isinstance(planning.active_draft, ActiveProposalDraft)
            or planning.active_draft.revision != base_revision
            or planning.active_draft.based_on_brief_revision != brief.revision
        ):
            raise ConcurrentModificationError("The proposal draft has changed; regenerate it")
        proposal = await self._generate_with_provider(
            _proposal_messages(brief, planning.active_draft, instruction),
            StoryProposal,
        )
        current = load_planning(self.project_dir)
        require_compatible_active_draft(current, ActiveProposalDraft)
        if (
            current.story_brief is None
            or current.story_brief.revision != brief.revision
            or _draft_revision(current) != _draft_revision(planning)
        ):
            raise ConcurrentModificationError("The proposal draft has changed; regenerate it")
        draft = ActiveProposalDraft(
            revision=(
                current.active_draft.revision + 1
                if current.active_draft
                else (current.approved_proposal.revision + 1 if current.approved_proposal else 1)
            ),
            based_on_brief_revision=brief.revision,
            proposal=proposal,
        )
        current.active_draft = draft
        save_planning(self.project_dir, current)
        return draft

    @staticmethod
    def _default_provider() -> LLMProvider:
        from app.providers.config import get_configured_provider_for_step, load_provider_config

        return get_configured_provider_for_step("story_designer", load_provider_config())


def _proposal_messages(
    brief: StoryBrief, draft: ActiveProposalDraft | None, instruction: str
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are Story Designer. Invent an original, compact Story Proposal. "
                "Return only title, logline, 2-4 main characters, core conflict, "
                "3-5 story promises, and ending direction."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"story_brief": brief.model_dump(), "current_draft": draft.model_dump() if draft else None,
                 "adjustment": instruction},
                ensure_ascii=False,
            ),
        },
    ]


def _bootstrap_messages(
    proposal: ApprovedStoryProposal, brief: StoryBrief
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are Story Designer. Return only a StoryBootstrap using the supplied "
                "canonical shapes: Bible overview/elements, 2-4 Character core/state pairs, "
                "StyleGuide, and VolumeOutline arcs. Build a finite planning horizon (roughly "
                "the first three arcs for an ongoing story), never the entire series. Give only "
                "the first arc detailed chapters; every first-arc chapter has exactly one scene, "
                "and later arcs have summaries with no chapters. Three to six arcs and eight to "
                "fifteen first-arc chapters are guidance, not schema limits. Do not output Canon "
                "Facts. Invent original names and rules. Never apply the Xianxia Story Template. "
                "Generation Guides are prompt-only, not story content."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"approved_proposal": proposal.model_dump(), "story_brief": brief.model_dump()},
                ensure_ascii=False,
            ),
        },
    ]


def _bootstrap_patch_messages(
    draft: ActiveBootstrapDraft, instruction: str
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Return a BootstrapPatchPreview only. Use RFC6902 replace for existing scalar leaves, "
                "or add/remove one list item at explicit indices or '-'. Use paths under /overview, "
                "/elements, /characters, /style, or /arcs. Do not edit existing IDs or revisions, and do "
                "not replace whole objects or arrays. Address only the requested fields. Include short human-readable "
                "changes and consequences."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"base_revision": draft.revision, "bootstrap": draft.bootstrap.model_dump(mode="json"), "adjustment": instruction},
                ensure_ascii=False,
            ),
        },
    ]


_PATCH_ROOTS = {"overview", "elements", "characters", "style", "arcs"}
_IMMUTABLE_PATH_PARTS = {
    "id", "revision", "created_at", "updated_at", "definition_revision",
    "definition_updated_at", "character_id", "chapter_id", "volume_id", "story_id", "project_id",
}


def _replace_bootstrap_value(document: dict, path: str, value: object | None, op: str = "replace") -> None:
    """Apply the small RFC6902 subset accepted for bootstrap drafts."""
    if not path.startswith("/"):
        raise ValueError("Bootstrap patch path must be a JSON Pointer")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]
    if (
        len(parts) < 2
        or parts[0] not in _PATCH_ROOTS
        or (op == "replace" and parts[0] in {"elements", "characters", "arcs"} and len(parts) < 3)
    ):
        raise ValueError("Bootstrap patch must target a nested field or list item")
    if any(part in _IMMUTABLE_PATH_PARTS for part in parts):
        raise ValueError("Bootstrap patch may not change identity or revision fields")
    target: object = document
    for part in parts[:-1]:
        if isinstance(target, dict):
            if part not in target:
                raise ValueError("Bootstrap patch path does not exist")
            target = target[part]
        elif isinstance(target, list) and part.isdigit() and int(part) < len(target):
            target = target[int(part)]
        else:
            raise ValueError("Bootstrap patch path does not exist")
    final = parts[-1]
    if op == "add":
        if not isinstance(target, list) or (final != "-" and (not final.isdigit() or int(final) > len(target))):
            raise ValueError("Bootstrap patch add must target a list index")
        target.insert(len(target) if final == "-" else int(final), value)
        return
    if op == "remove":
        if not isinstance(target, list) or not final.isdigit() or int(final) >= len(target):
            raise ValueError("Bootstrap patch remove must target an existing list item")
        target.pop(int(final))
        return
    if isinstance(target, dict):
        if final not in target:
            raise ValueError("Bootstrap patch path does not exist")
        if isinstance(target[final], (dict, list)):
            raise ValueError("Bootstrap patch may only replace scalar fields")
        target[final] = value
    elif isinstance(target, list) and final.isdigit() and int(final) < len(target):
        if isinstance(target[int(final)], (dict, list)):
            raise ValueError("Bootstrap patch may only replace scalar fields")
        target[int(final)] = value
    else:
        raise ValueError("Bootstrap patch path does not exist")


def _draft_revision(planning) -> int | None:
    return getattr(planning.active_draft, "revision", None)
