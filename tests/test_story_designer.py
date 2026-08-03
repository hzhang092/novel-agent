import asyncio

import pytest

from app.application.errors import ConcurrentModificationError, OperationBlockedError
from app.application.story_designer import StoryDesignerService
from app.providers.base import MockProvider
from app.storage.bible_models import TerminologyElement, WorldOverview
from app.storage.models import (
    ActiveBootstrapDraft,
    ActiveProposalDraft,
    BootstrapPatchPreview,
    CanonFact,
    ChapterLength,
    Character,
    CharacterCore,
    CharacterState,
    ChapterOutline,
    Project,
    SceneOutline,
    StoryBootstrap,
    StoryBrief,
    StoryProposal,
    StyleGuide,
    VolumeOutline,
)
from app.storage.project_files import create_project, load_all_volumes, load_planning, load_project, save_canon_facts
from app.storage.project_files import save_planning


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


def bootstrap() -> StoryBootstrap:
    characters = [
        Character(core=CharacterCore(id=f"character-{index}", name=f"角色{index}"), state=CharacterState(character_id=f"character-{index}"))
        for index in range(2)
    ]
    chapter = ChapterOutline(
        id="chapter-1", title="开端", summary="开始", scenes=[SceneOutline(id="scene-1", ending_hook="钩子")]
    )
    return StoryBootstrap(
        overview=WorldOverview(geography="城市", rules=["规则"]),
        elements=[TerminologyElement(id="term-1", name="术语", definition="定义")],
        characters=characters,
        style=StyleGuide(tone="克制"),
        arcs=[VolumeOutline(id="arc-1", title="第一卷", summary="第一弧", chapters=[chapter]), VolumeOutline(id="arc-2", title="第二卷", summary="后续")],
    )


async def approved_service(tmp_path, provider):
    project_dir = create_project(tmp_path, Project(title="Folder title"))
    service = StoryDesignerService(project_dir, provider_factory=lambda: provider)
    service.save_brief(brief())
    draft = await service.generate_proposal()
    service.approve_proposal(base_revision=draft.revision)
    return project_dir, service


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
async def test_proposal_does_not_replace_a_different_active_draft(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Folder title"))
    provider = MockProvider(structured_response=proposal())
    service = StoryDesignerService(project_dir, provider_factory=lambda: provider)
    service.save_brief(brief())
    planning = load_planning(project_dir)
    foreign_draft = ActiveBootstrapDraft(
        based_on_brief_revision=1,
        based_on_proposal_revision=1,
        bootstrap=bootstrap(),
    )
    planning.active_draft = foreign_draft
    save_planning(project_dir, planning)

    with pytest.raises(OperationBlockedError, match="bootstrap"):
        await service.generate_proposal()

    assert load_planning(project_dir).active_draft == foreign_draft


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
async def test_proposal_approval_sets_the_project_chapter_length_default(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Folder title"))
    service = StoryDesignerService(
        project_dir,
        provider_factory=lambda: MockProvider(structured_response=proposal()),
    )
    story_brief = brief()
    story_brief.chapter_length.preset = "custom"
    story_brief.chapter_length.target_chinese_characters = 4200
    service.save_brief(story_brief)
    draft = await service.generate_proposal()

    service.approve_proposal(base_revision=draft.revision)

    assert load_project(project_dir).chapter_length.resolved_target == 4200


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


@pytest.mark.asyncio
async def test_bootstrap_uses_the_existing_story_designer_route_and_keeps_only_one_active_draft(tmp_path):
    class CapturingProvider(MockProvider):
        async def generate_structured(self, messages, *args, **kwargs):
            self.messages = messages
            return await super().generate_structured(messages, *args, **kwargs)

    provider = CapturingProvider(structured_response=proposal())
    project_dir, service = await approved_service(tmp_path, provider)
    provider.structured_response = bootstrap()

    draft = await service.generate_bootstrap()

    assert draft.bootstrap.arcs[0].title == "第一卷"
    assert load_planning(project_dir).active_draft == draft
    prompt = provider.messages[0]["content"]
    assert "finite planning horizon" in prompt
    assert "Canon Facts" in prompt
    assert "Xianxia Story Template" in prompt


def test_bootstrap_schema_is_scoped_to_first_arc_and_rejects_extra_fields():
    data = bootstrap().model_dump(mode="json")
    data["canon_facts"] = []
    with pytest.raises(ValueError):
        StoryBootstrap.model_validate(data)
    data = bootstrap().model_dump(mode="json")
    data["arcs"][1]["chapters"] = data["arcs"][0]["chapters"]
    with pytest.raises(ValueError, match="first bootstrap arc"):
        StoryBootstrap.model_validate(data)
    data = bootstrap().model_dump(mode="json")
    data["arcs"][1]["id"] = data["arcs"][0]["id"]
    with pytest.raises(ValueError, match="arc IDs"):
        StoryBootstrap.model_validate(data)
    for path, message in (("elements.0.id", "Bible Element"), ("arcs.0.chapters.0.id", "chapter"), ("arcs.0.chapters.0.scenes.0.id", "scene")):
        data = bootstrap().model_dump(mode="json")
        if path.startswith("elements"):
            data["elements"].append(data["elements"][0].copy())
        elif path.endswith("scenes.0.id"):
            data["arcs"][0]["chapters"][0]["scenes"].append(data["arcs"][0]["chapters"][0]["scenes"][0].copy())
        else:
            data["arcs"][0]["chapters"].append(data["arcs"][0]["chapters"][0].copy())
        with pytest.raises(ValueError, match=message):
            StoryBootstrap.model_validate(data)
    data = bootstrap().model_dump(mode="json")
    data["arcs"][0]["chapters"][0]["volume_id"] = "other-arc"
    with pytest.raises(ValueError, match="association IDs"):
        StoryBootstrap.model_validate(data)
    data = bootstrap().model_dump(mode="json")
    data["arcs"][0]["chapters"][0]["scenes"][0]["chapter_id"] = "other-chapter"
    with pytest.raises(ValueError, match="association IDs"):
        StoryBootstrap.model_validate(data)


def test_bootstrap_arc_and_chapter_counts_are_guidance_not_schema_limits():
    data = bootstrap().model_dump(mode="json")
    data["arcs"] = [data["arcs"][0]] + [
        {**data["arcs"][1], "id": f"arc-{index}"} for index in range(2, 8)
    ]
    data["arcs"][0]["chapters"] = [
        {
            **data["arcs"][0]["chapters"][0],
            "id": f"chapter-{index}",
            "scenes": [{**data["arcs"][0]["chapters"][0]["scenes"][0], "id": f"scene-{index}"}],
        }
        for index in range(16)
    ]
    assert len(StoryBootstrap.model_validate(data).arcs) == 7


@pytest.mark.asyncio
async def test_bootstrap_patch_preview_does_not_mutate_and_preserves_manual_values(tmp_path):
    provider = MockProvider(structured_response=proposal())
    project_dir, service = await approved_service(tmp_path, provider)
    provider.structured_response = bootstrap()
    draft = await service.generate_bootstrap()
    manual = draft.bootstrap.model_copy(deep=True)
    manual.style.pov = "第一人称"
    draft = service.save_bootstrap(manual, base_revision=draft.revision)
    provider.structured_response = BootstrapPatchPreview(
        base_revision=draft.revision,
        operations=[{"path": "/arcs/0/chapters/0/title", "value": "新开端"}],
        changes=["改章名"], consequences=["钩子不变"],
    )

    preview = await service.adjust_bootstrap("改章名", base_revision=draft.revision)
    assert load_planning(project_dir).active_draft == draft
    patched = service.apply_bootstrap_patch(preview)

    assert patched.bootstrap.arcs[0].chapters[0].title == "新开端"
    assert patched.bootstrap.style.pov == "第一人称"
    with pytest.raises(ConcurrentModificationError):
        service.apply_bootstrap_patch(preview)


@pytest.mark.asyncio
async def test_bootstrap_operations_reject_a_draft_based_on_an_old_brief(tmp_path):
    provider = MockProvider(structured_response=proposal())
    _project_dir, service = await approved_service(tmp_path, provider)
    provider.structured_response = bootstrap()
    draft = await service.generate_bootstrap()
    service.save_brief(brief())
    preview = BootstrapPatchPreview(
        base_revision=draft.revision,
        operations=[{"path": "/style/tone", "value": "新语气"}],
        changes=["改语气"], consequences=["风格变化"],
    )

    assert draft.based_on_brief_revision == 1
    with pytest.raises(ConcurrentModificationError, match="Story Brief"):
        service.save_bootstrap(draft.bootstrap, base_revision=draft.revision)
    with pytest.raises(ConcurrentModificationError, match="Story Brief"):
        await service.adjust_bootstrap("改语气", base_revision=draft.revision)
    with pytest.raises(ConcurrentModificationError, match="Story Brief"):
        service.apply_bootstrap_patch(preview)
    with pytest.raises(ConcurrentModificationError, match="Story Brief"):
        service.approve_bootstrap(base_revision=draft.revision)


@pytest.mark.asyncio
async def test_bootstrap_generation_rechecks_the_brief_after_provider_waits(tmp_path):
    started, release = asyncio.Event(), asyncio.Event()

    class WaitingProvider(MockProvider):
        async def generate_structured(self, *args, **kwargs):
            started.set()
            await release.wait()
            return await super().generate_structured(*args, **kwargs)

    project_dir, initial = await approved_service(tmp_path, MockProvider(structured_response=proposal()))
    service = StoryDesignerService(
        project_dir, provider_factory=lambda: WaitingProvider(structured_response=bootstrap())
    )
    generation = asyncio.create_task(service.generate_bootstrap())
    await started.wait()
    initial.save_brief(brief())
    release.set()

    with pytest.raises(ConcurrentModificationError, match="Story Brief"):
        await generation


@pytest.mark.asyncio
async def test_bootstrap_patch_adds_and_removes_list_items_without_losing_manual_fields(tmp_path):
    provider = MockProvider(structured_response=proposal())
    _project_dir, service = await approved_service(tmp_path, provider)
    provider.structured_response = bootstrap()
    draft = await service.generate_bootstrap()
    manual = draft.bootstrap.model_copy(deep=True)
    manual.style.pov = "第一人称"
    draft = service.save_bootstrap(manual, base_revision=draft.revision)
    added = service.apply_bootstrap_patch(BootstrapPatchPreview(
        base_revision=draft.revision,
        operations=[{"op": "add", "path": "/style/taboo_patterns/-", "value": "禁忌"}],
        changes=["加入禁忌"], consequences=["写作时避开它"],
    ))
    removed = service.apply_bootstrap_patch(BootstrapPatchPreview(
        base_revision=added.revision,
        operations=[{"op": "remove", "path": "/style/taboo_patterns/0"}],
        changes=["移除禁忌"], consequences=["不再限制"],
    ))

    assert added.bootstrap.style.taboo_patterns == ["禁忌"]
    assert removed.bootstrap.style.taboo_patterns == []
    assert removed.bootstrap.style.pov == "第一人称"
    with pytest.raises(ValueError, match="identity"):
        service.apply_bootstrap_patch(BootstrapPatchPreview(
            base_revision=removed.revision,
            operations=[{"path": "/arcs/0/id", "value": "new"}],
            changes=["改 ID"], consequences=["错误"],
        ))


@pytest.mark.asyncio
async def test_bootstrap_patch_adds_and_removes_a_chapter_and_rejects_invalid_final_shapes(tmp_path):
    provider = MockProvider(structured_response=proposal())
    project_dir, service = await approved_service(tmp_path, provider)
    provider.structured_response = bootstrap()
    draft = await service.generate_bootstrap()
    manual = draft.bootstrap.model_copy(deep=True)
    manual.style.pov = "第一人称"
    draft = service.save_bootstrap(manual, base_revision=draft.revision)
    chapter = draft.bootstrap.arcs[0].chapters[0].model_dump(mode="json")
    chapter["id"] = "added-chapter"
    chapter["volume_id"] = draft.bootstrap.arcs[0].id
    chapter["scenes"][0]["id"] = "added-scene"
    chapter["scenes"][0]["chapter_id"] = "added-chapter"

    added = service.apply_bootstrap_patch(BootstrapPatchPreview(
        base_revision=draft.revision,
        operations=[{"op": "add", "path": "/arcs/0/chapters/-", "value": chapter}],
        changes=["加入章节"], consequences=["增加一个起始场景"],
    ))
    removed = service.apply_bootstrap_patch(BootstrapPatchPreview(
        base_revision=added.revision,
        operations=[{"op": "remove", "path": "/arcs/0/chapters/1"}],
        changes=["移除章节"], consequences=["恢复原章数"],
    ))
    arc = removed.bootstrap.arcs[0].model_dump(mode="json")
    arc.update({"id": "later-arc", "title": "后续故事弧", "chapters": []})
    added_arc = service.apply_bootstrap_patch(BootstrapPatchPreview(
        base_revision=removed.revision,
        operations=[{"op": "add", "path": "/arcs/-", "value": arc}],
        changes=["加入故事弧"], consequences=["保留给后续展开"],
    ))
    removed_arc = service.apply_bootstrap_patch(BootstrapPatchPreview(
        base_revision=added_arc.revision,
        operations=[{"op": "remove", "path": "/arcs/2"}],
        changes=["移除故事弧"], consequences=["恢复原故事弧"],
    ))

    assert len(added.bootstrap.arcs[0].chapters) == 2
    assert len(added_arc.bootstrap.arcs) == 3
    assert removed_arc.bootstrap.style.pov == "第一人称"
    with pytest.raises(ValueError, match="exactly one scene"):
        service.apply_bootstrap_patch(BootstrapPatchPreview(
            base_revision=removed_arc.revision,
            operations=[{"op": "add", "path": "/arcs/0/chapters/-", "value": {"id": "invalid"}}],
            changes=["加入坏章节"], consequences=["必须拒绝"],
        ))
    assert load_planning(project_dir).active_draft == removed_arc


@pytest.mark.asyncio
async def test_bootstrap_blocks_proposal_replacement_and_whole_object_patches(tmp_path):
    provider = MockProvider(structured_response=proposal())
    _project_dir, service = await approved_service(tmp_path, provider)
    provider.structured_response = bootstrap()
    draft = await service.generate_bootstrap()

    with pytest.raises(OperationBlockedError, match="bootstrap draft"):
        await service.generate_proposal()
    with pytest.raises(ValueError, match="nested"):
        service.apply_bootstrap_patch(BootstrapPatchPreview(
            base_revision=draft.revision,
            operations=[{"path": "/arcs/0", "value": {}}],
            changes=["坏变更"], consequences=["坏影响"],
        ))


@pytest.mark.asyncio
async def test_bootstrap_discard_rejects_a_stale_or_mismatched_draft(tmp_path):
    provider = MockProvider(structured_response=proposal())
    project_dir, service = await approved_service(tmp_path, provider)
    provider.structured_response = bootstrap()
    draft = await service.generate_bootstrap()

    with pytest.raises(ConcurrentModificationError, match="bootstrap draft"):
        service.discard_unapproved_bootstrap(base_revision=draft.revision + 1)

    assert load_planning(project_dir).active_draft == draft
    planning = load_planning(project_dir)
    foreign_draft = ActiveProposalDraft(
        based_on_brief_revision=1,
        proposal=proposal(),
    )
    planning.active_draft = foreign_draft
    save_planning(project_dir, planning)

    with pytest.raises(ConcurrentModificationError, match="bootstrap draft"):
        service.discard_unapproved_bootstrap(base_revision=draft.revision)

    assert load_planning(project_dir).active_draft == foreign_draft


@pytest.mark.asyncio
async def test_bootstrap_approval_writes_canonical_models_and_rejects_nonempty_projects(tmp_path):
    provider = MockProvider(structured_response=proposal())
    project_dir, service = await approved_service(tmp_path, provider)
    provider.structured_response = bootstrap()
    draft = await service.generate_bootstrap()

    service.approve_bootstrap(base_revision=draft.revision)

    assert load_planning(project_dir).active_draft is None
    assert len(load_all_volumes(project_dir)[0].chapters[0].scenes) == 1
    assert (project_dir / "characters" / "character-0" / "state.yaml").exists()
    assert not (project_dir / "canon" / "facts.yaml").exists()
    with pytest.raises(OperationBlockedError):
        await service.generate_bootstrap()


@pytest.mark.asyncio
async def test_bootstrap_rejects_a_project_with_existing_canon_facts(tmp_path):
    provider = MockProvider(structured_response=proposal())
    project_dir, service = await approved_service(tmp_path, provider)
    save_canon_facts(project_dir, [CanonFact(description="已有事实", category="world", source_scene_id="old")])
    provider.structured_response = bootstrap()

    with pytest.raises(OperationBlockedError, match="empty project"):
        await service.generate_bootstrap()


@pytest.mark.asyncio
async def test_bootstrap_query_and_generation_reject_any_active_draft_or_scene_file(tmp_path):
    provider = MockProvider(structured_response=proposal())
    project_dir, service = await approved_service(tmp_path, provider)
    assert service.can_generate_bootstrap()
    await service.generate_proposal()
    assert not service.can_generate_bootstrap()
    with pytest.raises(OperationBlockedError, match="active draft"):
        await service.generate_bootstrap()

    project_dir, service = await approved_service(tmp_path / "scenes", MockProvider(structured_response=proposal()))
    (project_dir / "scenes" / "leftover.txt").write_text("draft", encoding="utf-8")
    assert not service.can_generate_bootstrap()
    with pytest.raises(OperationBlockedError, match="empty project"):
        await service.generate_bootstrap()


@pytest.mark.asyncio
async def test_approve_proposal_rejects_bootstrap_draft_without_attribute_error(tmp_path):
    provider = MockProvider(structured_response=proposal())
    _project_dir, service = await approved_service(tmp_path, provider)
    provider.structured_response = bootstrap()
    draft = await service.generate_bootstrap()

    with pytest.raises(ConcurrentModificationError):
        service.approve_proposal(base_revision=draft.revision)


@pytest.mark.asyncio
async def test_bootstrap_approval_rolls_back_and_retains_draft_on_failure(tmp_path, monkeypatch):
    provider = MockProvider(structured_response=proposal())
    project_dir, service = await approved_service(tmp_path, provider)
    provider.structured_response = bootstrap()
    draft = await service.generate_bootstrap()
    before = (project_dir / "project.yaml").read_bytes()

    monkeypatch.setattr(
        "app.application.story_designer.save_volume_outline",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("write failed")),
    )
    with pytest.raises(RuntimeError, match="write failed"):
        service.approve_bootstrap(base_revision=draft.revision)

    assert (project_dir / "project.yaml").read_bytes() == before
    assert load_planning(project_dir).active_draft == draft
    assert not (project_dir / "characters" / "character-0" / "definition.yaml").exists()
