import asyncio
from pathlib import Path

import pytest

from app.application.errors import OperationBlockedError
from app.application.story_bible import StoryBibleApplicationService
from app.pipeline.agents.bible_assistant import BibleAssistantAgent
from app.pipeline.bible_suggestions import (
    BibleSuggestionResponse,
    CreateElementSuggestion,
)
from app.providers.base import MockProvider
from app.storage.bible_models import (
    BibleElementRelation,
    FactionElement,
    PowerSystemElement,
    WorldOverview,
)
from app.storage.bible_repository import BibleElementRepository
from app.storage.character_definition_service import CharacterDefinitionService
from app.storage.models import (
    ChapterOutline,
    CharacterCore,
    CharacterElementRelation,
    Project,
    SceneGenerationRecord,
    SceneOutline,
    StyleGuide,
    VolumeOutline,
)
from app.storage.project_files import (
    create_project,
    load_all_volumes,
    save_scene_generation_record,
    save_volume_outline,
    set_active_scene_prose_version,
)
from app.utils.template_merge import StoryTemplate, TemplateMergeMode


def _project(tmp_path: Path) -> Path:
    return create_project(tmp_path, Project(title="Story", genre="Fantasy"))


def test_load_and_save_editor_data(tmp_path):
    project_dir = _project(tmp_path)
    service = StoryBibleApplicationService(project_dir)

    service.save_overview(WorldOverview(geography="Eastern peaks"))
    created = service.save_element(FactionElement(id="sect", name="Jade Sect"))
    unchanged = service.save_element(created)
    updated = service.save_element(created.model_copy(update={"summary": "Ancient"}))
    style = service.save_style(StyleGuide(tone="Spare"))
    snapshot = service.load_editor_snapshot()

    assert created.revision == 1
    assert unchanged.revision == 1
    assert updated.revision == 2
    assert snapshot.bible.overview.geography == "Eastern peaks"
    assert snapshot.bible.elements[0].summary == "Ancient"
    assert style.tone == snapshot.style_guide.tone == "Spare"


def test_snapshot_failure_rolls_back_all_touched_files(tmp_path, monkeypatch):
    project_dir = _project(tmp_path)
    service = StoryBibleApplicationService(project_dir)
    existing = service.save_element(FactionElement(id="sect", name="Jade Sect"))
    tracked = [
        project_dir / "bible" / "elements" / "sect.yaml",
        project_dir / "bible" / "manifest.yaml",
        project_dir / "project.yaml",
        project_dir / "world.md",
    ]
    before = {path: path.read_bytes() for path in tracked}
    real_write = service._bible.repository._write_yaml_atomic
    failed = False

    def fail_manifest_once(destination, data):
        nonlocal failed
        if Path(destination).name == "manifest.yaml" and not failed:
            failed = True
            raise OSError("manifest write failed")
        return real_write(destination, data)

    monkeypatch.setattr(service._bible.repository, "_write_yaml_atomic", fail_manifest_once)

    with pytest.raises(OSError, match="manifest write failed"):
        service.save_snapshot(
            WorldOverview(geography="Changed"),
            [existing.model_copy(update={"summary": "Changed"})],
        )

    assert all(path.read_bytes() == content for path, content in before.items())


def test_deletion_impact_and_unlink_cover_all_structured_references(tmp_path):
    project_dir = _project(tmp_path)
    service = StoryBibleApplicationService(project_dir)
    target = PowerSystemElement(
        id="power",
        name="Cultivation",
        relationships=[BibleElementRelation(kind="uses", target_element_id="sect")],
    )
    source = FactionElement(
        id="source",
        name="Moon Sect",
        relationships=[BibleElementRelation(kind="uses", target_element_id="power")],
    )
    service.save_snapshot(
        WorldOverview(),
        [FactionElement(id="sect", name="Jade Sect"), target, source],
    )
    service._bible.set_primary_power_system("power")
    CharacterDefinitionService(project_dir).save(
        CharacterCore(
            id="hero",
            name="Lin",
            element_relations=[
                CharacterElementRelation(kind="uses", target_element_id="power")
            ],
        )
    )
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="volume",
            chapters=[
                ChapterOutline(
                    id="chapter",
                    scenes=[
                        SceneOutline(
                            id="scene",
                            title="Awakening",
                            world_element_ids=["power"],
                        )
                    ],
                )
            ],
        ),
    )

    impact = service.inspect_element_deletion("power")

    assert impact.inbound_element_count == 1
    assert impact.outgoing_relationship_count == 1
    assert impact.inbound_character_count == 1
    assert impact.usage_counts.explicit_outline == 1
    assert impact.is_primary_power_system is True
    with pytest.raises(OperationBlockedError):
        service.delete_element("power", unlink_references=False)

    service.delete_element("power", unlink_references=True)

    assert [item.id for item in BibleElementRepository(project_dir).load_all()] == [
        "sect",
        "source",
    ]
    assert BibleElementRepository(project_dir).load("source").relationships == []
    assert CharacterDefinitionService(project_dir).load("hero").element_relations == []
    assert load_all_volumes(project_dir)[0].chapters[0].scenes[0].world_element_ids == []
    assert BibleElementRepository(project_dir).load_manifest().primary_power_system_id is None


def test_usage_counts_and_scene_sources(tmp_path):
    project_dir = _project(tmp_path)
    service = StoryBibleApplicationService(project_dir)
    service.save_element(FactionElement(id="sect", name="Jade Sect"))
    scene = SceneOutline(id="scene", title="Rumor", world_element_ids=["sect"])
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="volume",
            chapters=[ChapterOutline(id="chapter", scenes=[scene])],
        ),
    )
    prose_dir = project_dir / "scenes" / "chapter"
    prose_dir.mkdir(parents=True)
    (prose_dir / "scene.v1.md").write_text(
        "The Jade Sect controls the valley.", encoding="utf-8"
    )
    set_active_scene_prose_version(project_dir, "chapter", "scene", "v1")
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene",
            generated_with={"bible_elements": {"sect": {"revision": 1}}},
        ),
    )

    impact = service.inspect_element_deletion("sect")

    assert impact.usage_counts.explicit_outline == 1
    assert impact.usage_counts.generation_context == 1
    assert impact.usage_counts.prose_mention == 1
    assert '"id":"scene"' in service.scene_outline_source("scene")
    assert service.scene_prose_source("scene") == "The Jade Sect controls the valley."
    assert service.scene_outline_source("missing") == ""
    assert service.scene_prose_source("missing") == ""


class _ClosingProvider(MockProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.closed = False

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_suggestion_generation_closes_provider_on_success_and_failure(tmp_path):
    service = StoryBibleApplicationService(_project(tmp_path))
    response = BibleSuggestionResponse(
        proposals=[
            CreateElementSuggestion(
                proposal_id="new-sect",
                confidence=0.9,
                element_type="faction",
                name="Jade Sect",
            )
        ]
    )
    successful = _ClosingProvider(structured_response=response)
    failing = _ClosingProvider()

    proposals = await service.generate_suggestions(
        "The Jade Sect rules.", existing_elements=[], provider=successful
    )
    with pytest.raises(ValueError, match="structured_response"):
        await service.generate_suggestions(
            "The Jade Sect rules.", existing_elements=[], provider=failing
        )

    assert proposals[0].name == "Jade Sect"
    assert successful.closed is True
    assert failing.closed is True


@pytest.mark.asyncio
async def test_cancelled_suggestion_generation_closes_provider(
    tmp_path, monkeypatch
):
    service = StoryBibleApplicationService(_project(tmp_path))
    provider = _ClosingProvider()

    async def wait_forever(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(BibleAssistantAgent, "generate", wait_forever)
    task = asyncio.create_task(
        service.generate_suggestions("Jade Sect", existing_elements=[], provider=provider)
    )
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.closed is True


def test_apply_suggestions_persists_only_reviewed_proposals(tmp_path):
    project_dir = _project(tmp_path)
    service = StoryBibleApplicationService(project_dir)
    proposal = CreateElementSuggestion(
        proposal_id="new-sect",
        confidence=0.9,
        element_type="faction",
        name="Jade Sect",
    )

    service.apply_suggestions([proposal])

    assert [item.name for item in BibleElementRepository(project_dir).load_all()] == [
        "Jade Sect"
    ]


def test_template_operations_change_drafts_without_writing(tmp_path):
    project_dir = _project(tmp_path)
    service = StoryBibleApplicationService(project_dir)
    current = FactionElement(id="current", name="Old Sect")
    service.save_element(current)
    before = (project_dir / "bible" / "manifest.yaml").read_bytes()
    template = StoryTemplate(
        template_id="template",
        name="Template",
        world_overview=WorldOverview(geography="New world"),
        elements=[FactionElement(id="template-sect", name="New Sect")],
        style_guide=StyleGuide(tone="Mythic"),
    )

    preview = service.preview_template_replace([current], template)
    draft = service.apply_template_to_draft(
        WorldOverview(),
        [current],
        StyleGuide(),
        template,
        TemplateMergeMode.REPLACE,
    )
    merged_style = service.merge_template_style(
        StyleGuide(tone="Quiet"), template.style_guide, TemplateMergeMode.MERGE
    )

    assert preview.elements_replaced["faction"] == 1
    assert draft.world_overview.geography == "New world"
    assert [item.name for item in draft.elements] == ["New Sect"]
    assert merged_style.tone == "Quiet"
    assert (project_dir / "bible" / "manifest.yaml").read_bytes() == before
    assert [item.name for item in BibleElementRepository(project_dir).load_all()] == [
        "Old Sect"
    ]
