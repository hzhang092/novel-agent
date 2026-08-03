from __future__ import annotations

import pytest

from app.application.quick_planning import ChapterCardStatus, QuickPlanningService
from app.storage.models import (
    ChapterOutline,
    Character,
    CharacterCore,
    CharacterState,
    Project,
    SceneGenerationRecord,
    SceneOutline,
    VolumeOutline,
)
from app.storage.project_files import (
    create_project,
    load_all_volumes,
    save_scene_generation_record,
    save_scene_prose,
    save_volume_outline,
)


def project_with_outline(tmp_path):
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
        VolumeOutline(
            id="arc-1",
            story_id="story-1",
            title="第一阶段",
            chapters=[chapter],
        ),
    )
    from app.storage.project_files import save_character

    for character_id, name in (("hero", "主角"), ("support", "顾承渊")):
        save_character(
            project_dir,
            Character(
                core=CharacterCore(id=character_id, name=name),
                state=CharacterState(character_id=character_id),
            ),
        )
    return project_dir


def project_with_later_chapters(tmp_path):
    project_dir = project_with_outline(tmp_path)
    volume = load_all_volumes(project_dir)[0]
    for number in range(2, 5):
        volume.chapters.append(
            ChapterOutline(
                id=f"chapter-{number}",
                volume_id=volume.id,
                title=f"第{number}章",
                summary=f"事件 {number}",
                scenes=[
                    SceneOutline(
                        id=f"scene-{number}",
                        chapter_id=f"chapter-{number}",
                        ending_hook=f"钩子 {number}",
                    )
                ],
            )
        )
    save_volume_outline(project_dir, volume)
    for number in range(1, 4):
        save_scene_prose(
            project_dir,
            f"chapter-{number}",
            f"scene-{number}",
            f"正文 {number}",
        )
    return project_dir


def test_story_arc_and_card_are_canonical_projections_with_derived_status(tmp_path):
    project_dir = project_with_outline(tmp_path)

    story = QuickPlanningService(project_dir).story_projection()

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


def test_title_only_card_edit_does_not_mark_prose_for_review(tmp_path):
    project_dir = project_with_later_chapters(tmp_path)
    service = QuickPlanningService(project_dir)

    service.apply_card_edit(
        service.preview_card_edit("chapter-1", title="新标题")
    )

    assert [
        service.chapter_card(f"chapter-{number}").status
        for number in range(1, 5)
    ] == [
        ChapterCardStatus.DRAFT,
        ChapterCardStatus.DRAFT,
        ChapterCardStatus.DRAFT,
        ChapterCardStatus.UNWRITTEN,
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [("summary", "新事件"), ("ending_hook", "新钩子")],
)
def test_story_affecting_card_edit_marks_current_and_later_prose_for_review(
    tmp_path, field, value
):
    project_dir = project_with_later_chapters(tmp_path)
    service = QuickPlanningService(project_dir)

    service.apply_card_edit(
        service.preview_card_edit("chapter-1", **{field: value})
    )

    assert [
        service.chapter_card(f"chapter-{number}").status
        for number in range(1, 5)
    ] == [
        ChapterCardStatus.NEEDS_REVIEW,
        ChapterCardStatus.NEEDS_REVIEW,
        ChapterCardStatus.NEEDS_REVIEW,
        ChapterCardStatus.UNWRITTEN,
    ]


def test_card_status_distinguishes_draft_and_new_draft(tmp_path):
    project_dir = project_with_outline(tmp_path)
    service = QuickPlanningService(project_dir)
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="draft-1",
            revision_number=1,
            status="draft",
        ),
    )
    assert service.chapter_card("chapter-1").status is ChapterCardStatus.DRAFT

    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="published-1",
            revision_number=2,
            status="current",
            final_text="正文",
        ),
    )
    from app.storage.project_files import set_active_scene_prose_version

    save_scene_prose(project_dir, "chapter-1", "scene-1", "正文")
    set_active_scene_prose_version(
        project_dir, "chapter-1", "scene-1", "v2", "published-1"
    )
    assert service.chapter_card("chapter-1").status is ChapterCardStatus.APPROVED

    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="draft-3",
            revision_number=3,
            status="draft",
        ),
    )
    assert service.chapter_card("chapter-1").status is ChapterCardStatus.NEW_DRAFT


def test_unpublished_prose_stays_draft(tmp_path):
    project_dir = project_with_outline(tmp_path)
    save_scene_prose(project_dir, "chapter-1", "scene-1", "未发布正文")

    assert (
        QuickPlanningService(project_dir).chapter_card("chapter-1").status
        is ChapterCardStatus.DRAFT
    )


def test_quick_projection_rejects_multi_scene_chapters(tmp_path):
    project_dir = project_with_outline(tmp_path)
    volume = load_all_volumes(project_dir)[0]
    volume.chapters[0].scenes.append(
        SceneOutline(id="scene-2", chapter_id="chapter-1")
    )
    save_volume_outline(project_dir, volume)

    with pytest.raises(ValueError, match="multi-scene"):
        QuickPlanningService(project_dir).story_projection()
