from __future__ import annotations

import asyncio

import pytest
from PySide6.QtWidgets import QMessageBox

from app.pipeline.pipeline import ScenePipeline
from app.providers.base import MockProvider, ProviderResponse
from app.storage.bible_models import WorldOverview
from app.storage.models import (
    Character,
    CharacterCore,
    CharacterIntent,
    CharacterState,
    ChapterLength,
    ChapterOutline,
    ReviewResult,
    SceneOutline,
    ScenePlan,
    StoryBootstrap,
    StoryBrief,
    StoryProposal,
    StyleGuide,
    VolumeOutline,
)
from app.storage.project_files import (
    get_active_scene_prose_version,
    load_all_characters,
    load_all_volumes,
    load_canon_facts,
    load_planning,
    load_project,
    load_scene_generation_record,
    list_scene_prose_versions,
)
from app.ui.main_window import MainWindow


def _brief() -> StoryBrief:
    return StoryBrief(
        setting_tags=["城市"],
        protagonist_tags=["调查者"],
        premise="一名调查者追查一枚失踪的城市印记。",
        target_length="short",
        chapter_length=ChapterLength(preset="short"),
    )


def _proposal() -> StoryProposal:
    return StoryProposal(
        title="失印之城",
        logline="调查者追查一枚失踪的城市印记。",
        main_characters=["林默", "沈遥"],
        core_conflict="真相与城市安全只能保住一个。",
        story_promises=["追踪线索", "同伴试探", "公开真相"],
        ending_direction="主角选择公开真相。",
    )


def _bootstrap() -> StoryBootstrap:
    characters = [
        Character(
            core=CharacterCore(id=f"character-{index}", name=name),
            state=CharacterState(character_id=f"character-{index}"),
        )
        for index, name in enumerate(("林默", "沈遥"))
    ]
    chapters = [
        ChapterOutline(
            id="chapter-1",
            title="第一章",
            summary="主角发现失踪的城市印记。",
            scenes=[
                SceneOutline(
                    id="scene-1", title="失印", ending_hook="印记发光"
                )
            ],
        ),
        ChapterOutline(
            id="chapter-2",
            title="第二章",
            summary="主角追踪印记留下的线索。",
            scenes=[
                SceneOutline(
                    id="scene-2", title="追踪", ending_hook="线索指向旧城"
                )
            ],
        ),
    ]
    return StoryBootstrap(
        overview=WorldOverview(geography="旧城", rules=["印记记录城市记忆"]),
        characters=characters,
        style=StyleGuide(tone="克制"),
        arcs=[VolumeOutline(id="arc-1", title="第一卷", chapters=chapters)],
    )


class _MemoryProvider(MockProvider):
    async def generate_structured(self, _messages, schema, temperature=0.3):
        if schema.__name__ == "FactList":
            parsed = {
                "facts": [{"description": "印记会记录城市记忆", "category": "world"}],
                "summary": "主角找到失印线索。",
                "open_threads": [],
            }
        else:
            parsed = {"changes": []}
        return ProviderResponse(text="", parsed=parsed, usage={})


def _generation_providers() -> tuple[MockProvider, ...]:
    return (
        MockProvider(
            structured_response=ScenePlan(
                scene_id="scene-1",
                scene_goal="找到失踪印记",
                required_beats=["追踪", "发现线索"],
                conflict="线索正在消失",
                ending_hook="印记发光",
            )
        ),
        MockProvider(
            structured_response=CharacterIntent(
                character_name="林默", current_emotion="警觉", private_goal="找到印记"
            )
        ),
        MockProvider(stream_tokens=["主角走进旧城。", "印记在墙上发光。"]),
        MockProvider(
            structured_response=ReviewResult(
                scene_id="scene-1", overall_pass=True, summary="审查通过"
            )
        ),
    )


async def _wait_for_plan(workflow) -> None:
    for _ in range(2000):
        if workflow.waiting_for_plan:
            return
        await asyncio.sleep(0)
    raise AssertionError("the scene workflow did not reach its plan checkpoint")


@pytest.mark.asyncio
async def test_quick_creation_journey_from_brief_to_next_chapter(
    tmp_path, qtbot, monkeypatch
):
    information_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, message: information_calls.append((title, message)),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: None)

    class QuickProjectDialog:
        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return True

        def get_result(self):
            return {
                "title": "失印之城草稿",
                "storage_dir": str(tmp_path),
                "creation_mode": "quick",
            }

    monkeypatch.setattr("app.ui.main_window.CreateProjectDialog", QuickProjectDialog)
    monkeypatch.setattr(
        "app.application.scene_workflow._load_generation_providers",
        _generation_providers,
    )
    monkeypatch.setattr(
        "app.application.scene_workflow._new_pipeline",
        ScenePipeline,
    )
    memory_providers = {
        "fact_extractor": _MemoryProvider(),
        "state_updater": _MemoryProvider(),
    }
    monkeypatch.setattr(
        "app.providers.config.get_provider_for_step",
        lambda step, _config: memory_providers[step],
    )
    monkeypatch.setattr("app.providers.config.load_provider_config", lambda: object())

    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._on_new_project()

    project_dir = window._current_project_dir
    assert project_dir is not None and project_dir.is_dir()
    assert window._experience_mode == "quick"
    assert window._previous_destination == "story"
    assert window.stack.currentWidget() is window._quick_story_view
    assert information_calls == []

    story_view = window._quick_story_view
    application = window._application
    assert application is not None
    story_view.premise_edit.setPlainText(_brief().premise)
    application.story_designer._provider_factory = lambda: MockProvider(
        structured_response=_proposal()
    )
    story_view.generate_button.click()
    await story_view._proposal_task

    saved_brief = load_planning(project_dir).story_brief
    assert saved_brief is not None and saved_brief.premise == _brief().premise
    assert load_planning(project_dir).active_draft is not None
    assert _proposal().title in story_view.proposal_label.text()

    story_view.adopt_button.click()
    await story_view._proposal_task
    planning = load_planning(project_dir)
    assert planning.approved_proposal is not None
    assert planning.approved_proposal.title == _proposal().title
    assert planning.active_draft is None
    assert load_project(project_dir).title == _proposal().title
    assert project_dir.name == "失印之城草稿"

    application.story_designer._provider_factory = lambda: MockProvider(
        structured_response=_bootstrap()
    )
    story_view.bootstrap_button.click()
    await story_view._proposal_task
    assert load_planning(project_dir).active_draft is not None

    story_view.approve_bootstrap_button.click()
    assert load_planning(project_dir).active_draft is None
    assert len(load_all_volumes(project_dir)[0].chapters) == 2
    assert len(load_all_characters(project_dir)) == 2
    assert (project_dir / "style.yaml").is_file()
    assert (project_dir / "world.md").is_file()
    assert not story_view.continue_outline_button.isHidden()
    assert story_view.continue_outline_button.isEnabled()

    story_view.continue_outline_button.click()
    assert window._experience_mode == "quick"
    assert window._previous_destination == "outline"
    assert window.stack.currentWidget() is window._quick_outline_view
    assert set(window._quick_outline_view._card_widgets) == {"chapter-1", "chapter-2"}

    window._quick_outline_view._card_widgets["chapter-1"]["write"].click()
    assert window._previous_destination == "workspace"
    assert window._workspace_view.current_chapter_id == "chapter-1"
    assert window._workspace_view.current_scene_id == "scene-1"
    quick_chapter = window._workspace_view._quick_chapter
    assert quick_chapter.start_button.text() == "生成写作方案"
    assert quick_chapter.start_button.isEnabled()
    assert not quick_chapter.adjust_button.isEnabled()

    workflow = application.scene_workflow
    quick_chapter.start_button.click()
    await _wait_for_plan(workflow)
    assert workflow.state.active is True
    assert quick_chapter.start_button.text() == "开始写作"
    assert quick_chapter.adjust_button.text() == "调整方案"
    assert quick_chapter.start_button.isEnabled()
    assert quick_chapter.adjust_button.isEnabled()

    quick_chapter.start_button.click()
    await workflow.task
    record = workflow.state.draft_record
    assert record is not None
    assert "主角走进旧城。" in record.draft_text
    assert record.review and record.review["overall_pass"] is True
    assert not quick_chapter.review_section.isHidden()
    assert not quick_chapter.memory_section.isHidden()
    assert quick_chapter.fact_checks
    assert quick_chapter.fact_checks[0].text() == "事实：印记会记录城市记忆"
    for checkbox in quick_chapter.fact_checks:
        checkbox.setChecked(True)
    assert quick_chapter.approve_next_button.isEnabled()

    quick_chapter.approve_next_button.click()
    published = load_scene_generation_record(
        project_dir, "scene-1", revision_id=record.revision_id
    )
    assert published is not None and published.published_at is not None
    assert get_active_scene_prose_version(project_dir, "chapter-1", "scene-1") == "v1"
    assert list_scene_prose_versions(project_dir, "chapter-1", "scene-1") == ["v1"]
    assert [fact.description for fact in load_canon_facts(project_dir)] == [
        "印记会记录城市记忆"
    ]
    card = application.quick_planning.chapter_card("chapter-1")
    assert card.status.value == "已批准"
    assert window._workspace_view.current_chapter_id == "chapter-2"
    assert window._workspace_view.current_scene_id == "scene-2"
    assert workflow.state.active is False
    assert load_scene_generation_record(project_dir, "scene-2") is None
    assert quick_chapter.start_button.text() == "生成写作方案"
    assert quick_chapter.start_button.isEnabled()
