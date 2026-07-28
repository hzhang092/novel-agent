"""Guided Story Brief and Story Proposal use cases."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from app.application.errors import ConcurrentModificationError, OperationBlockedError
from app.providers.base import LLMProvider, ProviderResponse
from app.storage.bible_repository import rollback_files
from app.storage.models import (
    ActiveProposalDraft,
    ApprovedStoryProposal,
    StoryBrief,
    StoryProposal,
)
from app.storage.project_files import (
    PLANNING_YAML,
    PROJECT_YAML,
    load_planning,
    load_project,
    save_planning,
    save_project,
)


class StoryDesignerService:
    """Invents reviewable proposals; it never writes canonical story data."""

    def __init__(
        self,
        project_dir: Path,
        *,
        provider_factory: Callable[[], LLMProvider] | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self._provider_factory = provider_factory or self._default_provider

    def save_brief(self, brief: StoryBrief) -> StoryBrief:
        planning = load_planning(self.project_dir)
        brief.revision = (planning.story_brief.revision + 1) if planning.story_brief else 1
        planning.story_brief = brief
        save_planning(self.project_dir, planning)
        return brief

    async def generate_proposal(self) -> ActiveProposalDraft:
        return await self._replace_draft(base_revision=None, instruction="")

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
            draft is None
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
        planning.active_draft = None
        paths = [self.project_dir / PLANNING_YAML]
        if accept_title:
            paths.append(self.project_dir / PROJECT_YAML)
        with rollback_files(paths):
            save_planning(self.project_dir, planning)
            if accept_title:
                project = load_project(self.project_dir)
                project.title = approved.title
                save_project(self.project_dir, project)
        return approved

    async def _replace_draft(
        self, *, base_revision: int | None, instruction: str
    ) -> ActiveProposalDraft:
        planning = load_planning(self.project_dir)
        brief = planning.story_brief
        if brief is None:
            raise OperationBlockedError("A Story Brief is required before a proposal")
        if base_revision is not None and (
            planning.active_draft is None
            or planning.active_draft.revision != base_revision
            or planning.active_draft.based_on_brief_revision != brief.revision
        ):
            raise ConcurrentModificationError("The proposal draft has changed; regenerate it")
        provider = self._provider_factory()
        response: ProviderResponse = await provider.generate_structured(
            _proposal_messages(brief, planning.active_draft, instruction), StoryProposal
        )
        proposal = (
            response.model
            if isinstance(response.model, StoryProposal)
            else StoryProposal.model_validate(response.parsed or {})
        )
        current = load_planning(self.project_dir)
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
        from app.providers.config import get_provider_for_step, load_provider_config

        return get_provider_for_step("story_designer", load_provider_config())


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


def _draft_revision(planning) -> int | None:
    return planning.active_draft.revision if planning.active_draft else None
