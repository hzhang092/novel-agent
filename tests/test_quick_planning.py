from __future__ import annotations

import pytest

from app.application.errors import ConcurrentModificationError, OperationBlockedError
from app.application.quick_planning import (
    ChapterCardStatus,
    QuickPlanningService,
)
from app.providers.base import MockProvider
from app.storage.models import (
    ChapterOutline,
    Character,
    CharacterCore,
    CharacterState,
    CharacterTier,
    Project,
    ReplanPreview,
    SceneGenerationRecord,
    StoryPatchPreview,
    SceneOutline,
    StoryBrief,
    VolumeOutline,
)
from app.storage.project_files import (
    create_project,
    load_all_volumes,
    load_planning,
    save_scene_generation_record,
    save_scene_prose,
    save_volume_outline,
)

def project_with_outline(tmp_path, *, published: bool = False):
    project_dir = create_project(tmp_path, Project(title="测试小说"))
    scene = SceneOutline(
        id="scene-1",
        chapter_id="chapter-1",
        title="场景",
        location="屋顶",
        pov_character_id="hero",
        participating_character_ids=["hero"],
        scene_goal="找到线索",
        conflict="追兵出现",
        ending_hook="印记发光",
    )
    chapter = ChapterOutline(
        id="chapter-1",
        volume_id="arc-1",
        title="开端",
        summary="主角寻找线索",
        scenes=[scene],
    )
    save_volume_outline(
        project_dir,
        VolumeOutline(id="arc-1", story_id="story-1", title="第一阶段", chapters=[chapter]),
    )
    from app.storage.project_files import save_character

    save_character(
        project_dir,
        Character(
            core=CharacterCore(id="hero", name="主角"),
            state=CharacterState(character_id="hero"),
        ),
    )
    save_character(
        project_dir,
        Character(
            core=CharacterCore(id="support", name="顾承渊"),
            state=CharacterState(character_id="support"),
        ),
    )
    if published:
        save_scene_generation_record(
            project_dir,
            SceneGenerationRecord(
                scene_id="scene-1",
                revision_id="published-1",
                revision_number=1,
                status="current",
                draft_text="正文",
                final_text="正文",
            ),
        )
        from app.storage.project_files import set_active_scene_prose_version

        save_scene_prose(project_dir, "chapter-1", "scene-1", "正文")
        set_active_scene_prose_version(project_dir, "chapter-1", "scene-1", "v1", "published-1")
    return project_dir


def test_story_arc_and_card_are_canonical_projections_with_derived_status(tmp_path):
    project_dir = project_with_outline(tmp_path)
    service = QuickPlanningService(project_dir)

    story = service.story_projection()

    assert story.arcs[0].id == "arc-1"
    assert story.arcs[0].chapter_cards[0].title == "开端"
    assert story.arcs[0].chapter_cards[0].ending_hook == "印记发光"
    assert story.arcs[0].chapter_cards[0].status is ChapterCardStatus.UNWRITTEN
    assert not any(project_dir.glob("**/*quick*"))


def test_card_edit_changes_only_title_summary_and_hook(tmp_path):
    project_dir = project_with_outline(tmp_path)
    service = QuickPlanningService(project_dir)

    preview = service.preview_card_edit(
        "chapter-1",
        title="屋顶追踪",
        summary="顾承渊在屋顶寻找线索。目标：逃离；冲突：追兵；节拍：夺门、坠落",
        ending_hook="印记熄灭",
    )

    assert preview.changed_fields == ["title", "summary", "ending_hook"]
    service.apply_card_edit(preview)

    chapter = load_all_volumes(project_dir)[0].chapters[0]
    assert chapter.title == "屋顶追踪"
    assert chapter.summary == "顾承渊在屋顶寻找线索。目标：逃离；冲突：追兵；节拍：夺门、坠落"
    assert chapter.scenes[0].ending_hook == "印记熄灭"
    assert chapter.scenes[0].pov_character_id == "hero"
    assert chapter.scenes[0].participating_character_ids == ["hero"]
    assert chapter.scenes[0].scene_goal == "找到线索"
    assert chapter.scenes[0].conflict == "追兵出现"
    assert chapter.scenes[0].required_plot_beats == []
    assert getattr(chapter, "generation_blocked", False) is False


def test_brief_drift_is_deterministic_and_does_not_write_canon(tmp_path):
    project_dir = project_with_outline(tmp_path)
    service = QuickPlanningService(project_dir)
    service.save_brief(StoryBrief(premise="旧方向", setting_tags=["城市"]))
    service.record_brief_baseline()
    service.save_brief(StoryBrief(premise="新方向", setting_tags=["城市", "秘术"]))

    drift = service.brief_drift()

    assert drift.changed_fields == ["setting_tags", "premise"]
    assert load_all_volumes(project_dir)[0].chapters[0].summary == "主角寻找线索"
    assert load_planning(project_dir).approved_proposal is None


def test_card_status_distinguishes_draft_and_new_draft(tmp_path):
    project_dir = project_with_outline(tmp_path)
    service = QuickPlanningService(project_dir)
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(scene_id="scene-1", revision_id="draft-1", revision_number=1, status="draft"),
    )
    assert service.chapter_card("chapter-1").status is ChapterCardStatus.DRAFT

    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1", revision_id="published-1", revision_number=2,
            status="current", final_text="正文",
        ),
    )
    from app.storage.project_files import save_scene_prose, set_active_scene_prose_version

    save_scene_prose(project_dir, "chapter-1", "scene-1", "正文")
    set_active_scene_prose_version(project_dir, "chapter-1", "scene-1", "v2", "published-1")
    assert service.chapter_card("chapter-1").status is ChapterCardStatus.APPROVED

    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1", revision_id="draft-3", revision_number=3, status="draft"
        ),
    )
    assert service.chapter_card("chapter-1").status is ChapterCardStatus.NEW_DRAFT


def test_unpublished_prose_stays_draft_and_future_replan_target(tmp_path):
    project_dir = project_with_outline(tmp_path)
    from app.storage.project_files import save_scene_prose

    save_scene_prose(project_dir, "chapter-1", "scene-1", "未发布正文")
    service = QuickPlanningService(project_dir)

    assert service.chapter_card("chapter-1").status is ChapterCardStatus.DRAFT
    assert service.preview_replan().future_chapter_ids == ["chapter-1"]


def test_quick_projection_rejects_multi_scene_chapters(tmp_path):
    project_dir = project_with_outline(tmp_path)
    volume = load_all_volumes(project_dir)[0]
    volume.chapters[0].scenes.append(
        SceneOutline(id="scene-2", chapter_id="chapter-1")
    )
    save_volume_outline(project_dir, volume)

    with pytest.raises(ValueError, match="multi-scene"):
        QuickPlanningService(project_dir).story_projection()


def test_story_change_marks_published_downstream_chapters_but_title_fix_does_not(tmp_path):
    project_dir = project_with_outline(tmp_path, published=True)
    volume = load_all_volumes(project_dir)[0]
    volume.chapters.append(
        ChapterOutline(
            id="chapter-2", volume_id="arc-1", title="二", summary="二", scenes=[SceneOutline(id="scene-2", chapter_id="chapter-2")]
        )
    )
    save_volume_outline(project_dir, volume)
    from app.storage.project_files import save_scene_prose, set_active_scene_prose_version

    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(scene_id="scene-2", revision_id="published-2", revision_number=1, status="current", final_text="二"),
    )
    save_scene_prose(project_dir, "chapter-2", "scene-2", "二")
    set_active_scene_prose_version(project_dir, "chapter-2", "scene-2", "v1", "published-2")
    service = QuickPlanningService(project_dir)

    story_change = service.preview_replan()
    story_change.published_chapter_ids = ["chapter-1"]
    story_change.operations = [{"chapter_id": "chapter-1", "field": "summary", "value": "新事件"}]
    with pytest.raises(OperationBlockedError):
        service.apply_replan(story_change)
    service.apply_replan(story_change, confirm_published=True)
    assert service.chapter_card("chapter-1").status is ChapterCardStatus.NEEDS_REVIEW
    assert service.chapter_card("chapter-2").status is ChapterCardStatus.NEEDS_REVIEW

    title_fix = service.preview_replan()
    title_fix.published_chapter_ids = []
    title_fix.operations = [{"chapter_id": "chapter-1", "field": "title", "value": "新标题"}]
    title_fix.story_affecting = False
    service.apply_replan(title_fix)
    assert service.chapter_card("chapter-1").status is ChapterCardStatus.NEEDS_REVIEW

    clean_project = project_with_outline(tmp_path / "title-only", published=True)
    clean_service = QuickPlanningService(clean_project)
    clean_title = clean_service.preview_replan()
    clean_title.operations = [{"chapter_id": "chapter-1", "field": "title", "value": "仅改标题"}]
    clean_service.apply_replan(clean_title)
    assert clean_service.chapter_card("chapter-1").status is ChapterCardStatus.APPROVED


def test_replan_defaults_to_unpublished_chapters(tmp_path):
    project_dir = project_with_outline(tmp_path, published=True)
    service = QuickPlanningService(project_dir)

    replan = service.preview_replan()
    assert replan.future_chapter_ids == []
    assert replan.published_chapter_ids == []

@pytest.mark.asyncio
async def test_generated_replan_separates_published_changes_and_rejects_stale_base(tmp_path):
    project_dir = project_with_outline(tmp_path, published=True)
    provider = MockProvider(
        structured_response=ReplanPreview(
            published_chapter_ids=["chapter-1"],
            operations=[
                {"chapter_id": "chapter-1", "field": "summary", "value": "改写已发布事件"}
            ],
            changes=["修改第一章事件"],
            consequences=["后续正文需要复核"],
        )
    )
    service = QuickPlanningService(project_dir, provider_factory=lambda: provider)

    draft = await service.generate_replan("调整第一章")

    assert draft.published_chapter_ids == ["chapter-1"]
    assert draft.downstream_review_chapter_ids == ["chapter-1"]
    with pytest.raises(OperationBlockedError):
        service.apply_replan(draft)

    tampered = draft.model_copy(deep=True)
    tampered.operations[0]["value"] = "偷偷改写"
    with pytest.raises(ConcurrentModificationError):
        service.apply_replan(tampered, confirm_published=True)

    save_scene_prose(project_dir, "chapter-1", "scene-1", "并发正文修改")
    with pytest.raises(ConcurrentModificationError):
        service.apply_replan(draft, confirm_published=True)


@pytest.mark.asyncio
async def test_story_patch_updates_only_routine_fields(tmp_path):
    project_dir = project_with_outline(tmp_path)
    from app.storage.project_files import load_character, save_character

    hero = load_character(project_dir, "hero")
    hero.core.tier = CharacterTier.MAJOR
    save_character(project_dir, hero)
    provider = MockProvider(
        structured_response=StoryPatchPreview(
            operations=[
                {
                    "target": "character",
                    "target_id": "hero",
                    "field": "personality",
                    "value": "更谨慎",
                },
                {
                    "target": "overview",
                    "field": "geography",
                    "value": "浮空城",
                },
            ],
            changes=["主角更谨慎", "核心舞台改为浮空城"],
            consequences=["后续规划采用新设定"],
        )
    )
    service = QuickPlanningService(project_dir, provider_factory=lambda: provider)

    draft = await service.generate_story_patch("让主角更谨慎，舞台改为浮空城")
    service.apply_story_patch(draft)

    projection = service.story_projection()
    assert projection.main_characters[0].personality == "更谨慎"
    assert projection.core_setting.geography == "浮空城"
    assert load_character(project_dir, "hero").core.element_relations == []
