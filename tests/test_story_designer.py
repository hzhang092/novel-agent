import asyncio

import pytest

from app.application.errors import ConcurrentModificationError
from app.application.story_designer import StoryDesignerService
from app.providers.base import MockProvider
from app.storage.models import ChapterLength, Project, StoryBrief, StoryProposal
from app.storage.project_files import create_project, load_planning, load_project


def brief() -> StoryBrief:
    return StoryBrief(
        setting_tags=["  urban fantasy", "urban fantasy", "", " mystery  "],
        protagonist_tags=[" detective "],
        relationship_tags=[" reluctant allies "],
        plot_engine_tags=[" case of the week "],
        tone_tags=[" hopeful noir "],
        premise="  A  detective   finds  magic. ",
        target_length="around_30",
        romance_emphasis="secondary",
        protagonist_structure="dual",
        chapter_length=ChapterLength(preset="standard", target_chinese_characters=3000),
    )


def proposal(title="Working title") -> StoryProposal:
    return StoryProposal(
        title=title,
        logline="A detective finds magic.",
        main_characters=["Li: detective", "Qin: magician"],
        core_conflict="Truth versus safety.",
        story_promises=["A clue", "A betrayal", "A final choice"],
        ending_direction="They expose the truth.",
    )


def test_story_brief_round_trips_its_normalized_schema_without_touching_legacy_genre(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Folder title", genre="legacy"))
    service = StoryDesignerService(project_dir)

    saved = service.save_brief(brief())

    assert saved.setting_tags == ["urban fantasy", "mystery"]
    assert saved.protagonist_tags == ["detective"]
    assert saved.relationship_tags == ["reluctant allies"]
    assert saved.plot_engine_tags == ["case of the week"]
    assert saved.tone_tags == ["hopeful noir"]
    assert saved.premise == "A detective finds magic."
    assert saved.target_length == "around_30"
    assert saved.custom_target_chapters is None
    assert saved.romance_emphasis == "secondary"
    assert saved.protagonist_structure == "dual"
    assert saved.chapter_length == ChapterLength()
    assert load_planning(project_dir).story_brief == saved
    assert load_project(project_dir).genre == "legacy"


def test_proposal_rejects_fields_outside_its_reviewable_shape():
    with pytest.raises(ValueError):
        StoryProposal.model_validate({**proposal().model_dump(), "lore": "not here"})


@pytest.mark.parametrize(
    "field, value",
    [
        ("target_length", "30 chapters"),
        ("romance_emphasis", "important"),
        ("protagonist_structure", "pair"),
        ("custom_target_chapters", 0),
        ("chapter_length", {"preset": "medium", "target_chinese_characters": 3000}),
        ("chapter_length", {"preset": "standard", "target_chinese_characters": 0}),
    ],
)
def test_story_brief_rejects_invalid_enums_and_cardinality(field, value):
    with pytest.raises(ValueError):
        StoryBrief.model_validate({field: value})


def test_story_brief_rejects_extra_fields():
    with pytest.raises(ValueError):
        StoryBrief.model_validate({"genre": "not a brief field"})
    with pytest.raises(ValueError):
        ChapterLength.model_validate({"preset": "standard", "unexpected": 1})


@pytest.mark.asyncio
async def test_proposal_draft_uses_dedicated_provider_and_replaces_only_active_draft(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Folder title"))
    provider = MockProvider(structured_response=proposal())
    service = StoryDesignerService(project_dir, provider_factory=lambda: provider)
    service.save_brief(brief())

    first = await service.generate_proposal()
    second = await service.adjust_proposal("Make it darker", base_revision=first.revision)

    assert second.revision == 2
    assert load_planning(project_dir).active_draft == second
    assert provider.structured_response is not None


@pytest.mark.asyncio
async def test_adjustment_rejects_stale_draft_and_approval_keeps_canonical_files_untouched(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Folder title"))
    service = StoryDesignerService(
        project_dir, provider_factory=lambda: MockProvider(structured_response=proposal())
    )
    service.save_brief(brief())
    draft = await service.generate_proposal()
    approved = service.approve_proposal(base_revision=draft.revision, accept_title=True)
    await service.generate_proposal()

    with pytest.raises(ConcurrentModificationError):
        await service.adjust_proposal("stale", base_revision=draft.revision)

    planning = load_planning(project_dir)
    assert planning.approved_proposal == approved
    assert planning.active_draft is not None
    assert load_project(project_dir).title == "Working title"
    assert project_dir.name == "Folder title"
    assert list((project_dir / "outline").glob("*.yaml")) == []


@pytest.mark.asyncio
async def test_adjustment_rejects_a_draft_based_on_an_old_brief(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Folder title"))
    service = StoryDesignerService(
        project_dir, provider_factory=lambda: MockProvider(structured_response=proposal())
    )
    service.save_brief(brief())
    draft = await service.generate_proposal()
    service.save_brief(brief())

    with pytest.raises(ConcurrentModificationError):
        await service.adjust_proposal("stale brief", base_revision=draft.revision)


@pytest.mark.asyncio
async def test_adjustment_rechecks_the_brief_after_provider_waits(tmp_path):
    started, release = asyncio.Event(), asyncio.Event()

    class WaitingProvider(MockProvider):
        async def generate_structured(self, *args, **kwargs):
            started.set()
            await release.wait()
            return await super().generate_structured(*args, **kwargs)

    project_dir = create_project(tmp_path, Project(title="Folder title"))
    initial = StoryDesignerService(
        project_dir, provider_factory=lambda: MockProvider(structured_response=proposal())
    )
    initial.save_brief(brief())
    draft = await initial.generate_proposal()
    service = StoryDesignerService(
        project_dir, provider_factory=lambda: WaitingProvider(structured_response=proposal())
    )
    adjustment = asyncio.create_task(
        service.adjust_proposal("wait", base_revision=draft.revision)
    )
    await started.wait()
    service.save_brief(brief())
    release.set()

    with pytest.raises(ConcurrentModificationError):
        await adjustment


@pytest.mark.asyncio
async def test_provider_error_propagates_without_fallback(tmp_path):
    class FailingProvider(MockProvider):
        def __init__(self):
            super().__init__()
            self.closed = False

        async def generate_structured(self, *args, **kwargs):
            raise RuntimeError("provider failed")

        async def close(self):
            self.closed = True

    project_dir = create_project(tmp_path, Project(title="Folder title"))
    provider = FailingProvider()
    service = StoryDesignerService(project_dir, provider_factory=lambda: provider)
    service.save_brief(brief())

    with pytest.raises(RuntimeError, match="provider failed"):
        await service.generate_proposal()
    assert provider.closed
