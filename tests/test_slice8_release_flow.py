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
    ChapterOutline,
    ChapterLength,
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
    scene = SceneOutline(id="scene-1", title="失印", ending_hook="印记发光")
    chapter = ChapterOutline(
        id="chapter-1",
        title="第一章",
        summary="主角发现失踪的城市印记。",
        scenes=[scene],
    )
    return StoryBootstrap(
        overview=WorldOverview(geography="旧城", rules=["印记记录城市记忆"]),
        characters=characters,
        style=StyleGuide(tone="克制"),
        arcs=[VolumeOutline(id="arc-1", title="第一卷", chapters=[chapter])],
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


@pytest.mark.asyncio
async def test_clean_quick_project_passes_release_gate_without_conversion(
    tmp_path, qtbot, monkeypatch
):
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: messages.append((title, message)),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)

    class QuickProjectDialog:
        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return True

        def get_result(self):
            return {
                "title": "Release folder",
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
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._on_new_project()
    project_dir = window._current_project_dir
    assert project_dir is not None
    workflow = window._application.scene_workflow

    def switch(mode: str) -> None:
        window._set_experience_mode(mode)
        assert window._application.scene_workflow is workflow

    story_view = window._quick_story_view
    story_view.premise_edit.setPlainText(_brief().premise)
    story_view._save_brief()
    switch("quick")
    switch("deep")

    window._application.story_designer._provider_factory = lambda: MockProvider(
        structured_response=_proposal()
    )
    await story_view._generate_proposal()
    switch("quick")
    await story_view._adopt_proposal()
    approved_proposal = load_planning(project_dir).approved_proposal
    switch("deep")
    assert load_planning(project_dir).approved_proposal == approved_proposal

    window._application.story_designer._provider_factory = lambda: MockProvider(
        structured_response=_bootstrap()
    )
    await story_view._generate_bootstrap()
    switch("quick")
    story_view._approve_bootstrap()
    switch("deep")
    assert load_planning(project_dir).active_draft is None
    assert len(load_all_volumes(project_dir)[0].chapters) == 1

    memory_providers = {
        "fact_extractor": _MemoryProvider(),
        "state_updater": _MemoryProvider(),
    }
    monkeypatch.setattr(
        "app.providers.config.get_provider_for_step",
        lambda step, _config: memory_providers[step],
    )
    monkeypatch.setattr("app.providers.config.load_provider_config", lambda: object())

    window._workspace_view.set_scene("scene-1", "chapter-1")
    switch("quick")
    window._on_generate_requested("scene-1")

    async def wait_for_plan() -> None:
        while not workflow.waiting_for_plan:
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_plan(), timeout=2)
    switch("deep")
    switch("quick")
    window._on_quick_start("chapter-1", "scene-1")
    await workflow.task
    switch("deep")
    switch("quick")

    record = workflow.state.draft_record
    assert record is not None
    assert record.review and record.review["overall_pass"] is True
    assert [
        (fact["description"], fact["category"])
        for fact in record.extracted_facts_raw
    ] == [("印记会记录城市记忆", "world")]
    for checkbox in window._workspace_view._quick_chapter.fact_checks:
        checkbox.setChecked(True)
    assert window._on_quick_approve()
    switch("deep")

    published = load_scene_generation_record(
        project_dir, "scene-1", revision_id=record.revision_id
    )
    assert published is not None and published.published_at is not None
    assert (
        get_active_scene_prose_version(project_dir, "chapter-1", "scene-1")
        == "v1"
    )
    assert list_scene_prose_versions(project_dir, "chapter-1", "scene-1") == ["v1"]
    assert [fact.description for fact in load_canon_facts(project_dir)] == [
        "印记会记录城市记忆"
    ]
    assert load_project(project_dir).title == approved_proposal.title
    assert not list(project_dir.glob("**/*quick*"))
    assert messages == []
