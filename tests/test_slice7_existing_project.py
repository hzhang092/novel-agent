from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.project_context import build_project_application
from app.application.story_designer import StoryDesignerService
from app.providers.base import MockProvider
from app.storage.bible_models import TerminologyElement, WorldOverview
from app.storage.models import (
    ActiveBootstrapDraft,
    ApprovedStoryProposal,
    Character,
    CharacterCore,
    CharacterState,
    ChapterOutline,
    Project,
    SceneOutline,
    SceneGenerationRecord,
    StoryBootstrap,
    StoryBrief,
    StyleGuide,
    VolumeOutline,
    WorldSetting,
)
from app.storage.project_files import (
    create_project,
    load_planning,
    load_project,
    save_planning,
    save_scene_generation_record,
    save_volume_outline,
)
from PySide6.QtWidgets import QMessageBox

from app.ui.main_window import MainWindow
from app.ui.quick_story_view import QuickStoryView


def _existing_project(tmp_path):
    project_dir = create_project(
        tmp_path,
        Project(
            title="已有故事",
            world_setting=WorldSetting(geography="旧世界", rules=["旧规则"]),
        ),
    )
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="volume-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="chapter-1",
                    title="第一章",
                    summary="调查开始",
                    scenes=[SceneOutline(id="scene-1", ending_hook="新的线索")],
                )
            ],
        ),
    )
    return project_dir


def _bootstrap_planning():
    brief = StoryBrief(premise="先活下来")
    proposal = ApprovedStoryProposal(
        title="已有提案",
        logline="一个故事",
        main_characters=["甲", "乙"],
        core_conflict="冲突",
        story_promises=["看点一", "看点二", "看点三"],
        ending_direction="暂定结局",
        revision=1,
        based_on_brief_revision=brief.revision,
    )
    characters = [
        Character(
            core=CharacterCore(id=f"character-{index}", name=f"角色{index}"),
            state=CharacterState(character_id=f"character-{index}"),
        )
        for index in range(2)
    ]
    chapter = ChapterOutline(
        id="bootstrap-chapter",
        scenes=[SceneOutline(id="bootstrap-scene")],
    )
    bootstrap = StoryBootstrap(
        overview=WorldOverview(geography="城市"),
        elements=[TerminologyElement(id="term-1", name="术语", definition="定义")],
        characters=characters,
        style=StyleGuide(tone="克制"),
        arcs=[
            VolumeOutline(id="bootstrap-volume", chapters=[chapter]),
            VolumeOutline(id="later-volume"),
        ],
    )
    return brief, proposal, ActiveBootstrapDraft(
        revision=2,
        based_on_brief_revision=brief.revision,
        based_on_proposal_revision=proposal.revision,
        bootstrap=bootstrap,
    )


@pytest.mark.asyncio
async def test_existing_project_can_generate_an_editable_brief_without_saving_it(tmp_path):
    project_dir = _existing_project(tmp_path)
    generated = StoryBrief(premise="从旧世界里找出新的秘密")
    service = StoryDesignerService(
        project_dir,
        provider_factory=lambda: MockProvider(structured_response=generated),
    )

    draft = await service.generate_brief_from_existing()

    assert draft.premise == generated.premise
    planning = load_planning(project_dir)
    assert planning.story_brief is None
    assert planning.approved_proposal is None
    assert load_project(project_dir).title == "已有故事"


@pytest.mark.asyncio
async def test_quick_story_view_keeps_generated_existing_brief_editable_until_save(
    tmp_path, qtbot
):
    project_dir = _existing_project(tmp_path)
    application = build_project_application(project_dir)
    application.story_designer._provider_factory = lambda: MockProvider(
        structured_response=StoryBrief(premise="可编辑方向")
    )
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(application)

    await view._generate_brief_from_existing()

    assert view.premise_edit.toPlainText() == "可编辑方向"
    assert load_planning(project_dir).story_brief is None
    view._save_brief()
    assert load_planning(project_dir).story_brief.premise == "可编辑方向"


def test_switching_blank_project_to_quick_starts_brief_in_the_same_folder(
    tmp_path, qtbot
):
    project_dir = create_project(tmp_path, Project(title="空白故事"))
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)

    window._experience_switch.setCurrentIndex(
        window._experience_switch.findData("quick")
    )

    assert (project_dir / "planning.yaml").is_file()
    assert load_planning(project_dir).story_brief is not None
    assert load_project(project_dir).title == "空白故事"


def test_deep_canonical_save_warns_then_discards_bootstrap_only(
    tmp_path, qtbot, monkeypatch
):
    project_dir = create_project(tmp_path, Project(title="空白故事"))
    brief, proposal, draft = _bootstrap_planning()
    save_planning(
        project_dir,
        load_planning(project_dir).model_copy(
            update={
                "story_brief": brief,
                "approved_proposal": proposal,
                "approved_brief": brief,
                "active_draft": draft,
            }
        ),
    )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    window._outline_view._save_btn.click()
    planning = load_planning(project_dir)
    assert planning.active_draft is None
    assert planning.story_brief == brief
    assert planning.approved_proposal == proposal


def test_failed_deep_save_preserves_bootstrap(tmp_path, qtbot, monkeypatch):
    project_dir = create_project(tmp_path, Project(title="空白故事"))
    brief, proposal, draft = _bootstrap_planning()
    save_planning(
        project_dir,
        load_planning(project_dir).model_copy(
            update={
                "story_brief": brief,
                "approved_proposal": proposal,
                "active_draft": draft,
            }
        ),
    )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(window._outline_view, "_save", lambda: False)

    assert window._save_deep_outline() is False
    assert isinstance(load_planning(project_dir).active_draft, ActiveBootstrapDraft)


def test_quick_existing_projection_uses_canonical_data_without_planning_artifacts(
    tmp_path, qtbot
):
    project_dir = _existing_project(tmp_path)
    view = QuickStoryView()
    qtbot.addWidget(view)
    view.bind_application(build_project_application(project_dir))

    view.refresh_quick_projection()

    assert load_planning(project_dir).story_brief is None
    assert "快速总览" in view.quick_projection_label.text()
    assert "旧世界" in view.quick_projection_label.text()
    from app.pipeline.context_builder import RetrievalEngine

    context = RetrievalEngine().assemble(project_dir, scene_id="scene-1")
    assert context["world_rules"]["geography"] == "旧世界"


def test_reopening_stale_draft_restores_warning_and_continuation_state(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _existing_project(tmp_path)
    record = SceneGenerationRecord(
        scene_id="scene-1",
        source_chapter_id="chapter-1",
        status="draft",
        draft_text="旧设定正文",
        review={"overall_pass": True, "summary": "正文审查通过"},
        generation_trace=[
            {
                "agent_name": "Scene Planner",
                "stage": "planner",
                "status": "completed",
                "duration_ms": 0,
                "token_count": 0,
                "error_message": "",
                "failed_prompt": "",
                "failed_output": "",
                "children": [],
            }
        ],
        stale_input=True,
        stale_reason="基于旧设定",
    )
    save_scene_generation_record(project_dir, record)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    trace_updates = []
    monkeypatch.setattr(
        window._workspace_view,
        "update_trace",
        lambda trace: trace_updates.append(trace),
    )

    window._show_quick_revision(record)

    state = window._application.scene_workflow.state
    assert state.draft_record.revision_id == record.revision_id
    assert state.chapter_id == "chapter-1"
    assert trace_updates[0][0].status == "completed"
    assert "基于旧设定" in window._workspace_view.review_summary

    clean = SceneGenerationRecord(
        scene_id="scene-1",
        source_chapter_id="chapter-1",
        status="draft",
        draft_text="新设定正文",
        review={"overall_pass": True, "summary": "新草稿通过"},
    )
    window._show_quick_revision(clean)
    assert window._workspace_view.continue_review_is_visible is False
    assert "新草稿通过" in window._workspace_view.review_summary


@pytest.mark.asyncio
async def test_stale_continuation_failure_restores_retry_action(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _existing_project(tmp_path)
    record = SceneGenerationRecord(
        scene_id="scene-1",
        source_chapter_id="chapter-1",
        status="draft",
        draft_text="旧设定正文",
        review={"overall_pass": True},
        stale_input=True,
    )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    monkeypatch.setattr(
        window._application.scene_workflow,
        "continue_stale",
        AsyncMock(side_effect=OSError("disk full")),
    )

    await window._continue_stale_record(record.revision_id)

    assert window._workspace_view.continue_review_is_visible is True
    assert window._workspace_view._status_label.text() == "复核失败，请重试"
