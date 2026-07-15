"""Integration tests for the full scene generation pipeline using MockProvider."""

import asyncio
import tempfile
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from app.pipeline.agents.character import CharacterIntentAgent
from app.pipeline.pipeline import ScenePipeline
from app.providers.base import MockProvider
from app.storage.models import (
    Project,
    Character,
    CharacterCore,
    CharacterState,
    CharacterTier,
    ScenePlan,
    CharacterIntent,
    ReviewResult,
    ReviewIssue,
    VolumeOutline,
    ChapterOutline,
    SceneOutline,
)
from app.storage.project_files import (
    create_project,
    save_character,
    save_volume_outline,
)


@pytest.fixture
def project_dir():
    """Create a minimal project on disk for pipeline testing."""
    with tempfile.TemporaryDirectory() as tmp:
        proj = Project(title="TestPipeline", genre="玄幻", llm_provider="mock")
        proj_dir = create_project(Path(tmp), proj)

        char = Character(
            core=CharacterCore(
                id="char-1", name="林轩", tier=CharacterTier.MAJOR, personality="冷静果断",
                speech_style="简洁有力",
            ),
            state=CharacterState(
                character_id="char-1", current_emotion="平静",
                current_goal="探索秘境",
            ),
        )
        save_character(proj_dir, char)

        scene = SceneOutline(
            id="scene-1",
            title="测试场景",
            location="秘境入口",
            time="清晨",
            pov_character_id="char-1",
            participating_character_ids=["char-1"],
            scene_goal="发现秘境秘密",
            conflict="机关陷阱",
            ending_hook="秘境深处传来低语",
        )
        chapter = ChapterOutline(id="ch-1", title="第一章", scenes=[scene])
        volume = VolumeOutline(id="vol-1", title="第一卷", chapters=[chapter])
        save_volume_outline(proj_dir, volume)

        yield proj_dir


@pytest.fixture
def mock_planner():
    plan = ScenePlan(
        scene_goal="发现秘境秘密",
        required_beats=["进入入口", "触发机关", "发现暗门", "听到低语"],
        conflict="古老的机关守护着秘境",
        emotional_arc="好奇→紧张→震惊→期待",
        ending_hook="秘境深处传来低语，林轩抬头望去",
        continuity_constraints=["秘境位于青云山脉"],
    )
    return MockProvider(structured_response=plan)


@pytest.fixture
def mock_char_agent():
    intent = CharacterIntent(
        character_name="林轩",
        current_emotion="谨慎而好奇",
        private_goal="找到秘境中的宝物",
        public_goal="探索秘境",
        likely_actions=["观察机关", "小心前进", "记录发现"],
        forbidden_actions=["鲁莽冲撞"],
        speech_style_notes="自言自语，低声",
    )
    return MockProvider(structured_response=intent)


@pytest.fixture
def mock_writer():
    return MockProvider(stream_tokens=["测试", "正文", "内容"])


@pytest.fixture
def mock_reviewer():
    review = ReviewResult(
        scene_id="scene-1",
        issues=[
            ReviewIssue(category="continuity", description="通过", passed=True),
            ReviewIssue(category="style", description="通过", passed=True),
            ReviewIssue(category="hook", description="钩子已实现", passed=True),
            ReviewIssue(category="face_slap", description="不适用", passed=True),
        ],
        overall_pass=True,
        summary="所有检查通过",
    )
    return MockProvider(structured_response=review)


@pytest.mark.asyncio
async def test_full_pipeline_generates_prose(
    project_dir, mock_planner, mock_char_agent, mock_writer, mock_reviewer
):
    """The full pipeline should produce prose and a review result."""
    pipeline = ScenePipeline()

    plan_approved = False

    async def on_plan_ready(plan):
        nonlocal plan_approved
        plan_approved = True
        return True  # approve

    trace_entries = []

    def on_trace(trace):
        trace_entries.clear()
        trace_entries.extend(trace)

    tokens = []
    result = None
    async for token, gen_result in pipeline.generate_stream(
        project_dir, "scene-1",
        mock_planner, mock_char_agent, mock_writer, mock_reviewer,
        on_trace=on_trace, on_plan_ready=on_plan_ready,
    ):
        if token is not None:
            tokens.append(token)
        if gen_result is not None:
            result = gen_result

    assert plan_approved, "Plan should have been approved"
    assert "".join(tokens) == "测试正文内容"
    assert result is not None
    assert result.prose == "测试正文内容"
    assert result.plan is not None
    assert len(result.character_intents) == 1
    assert result.review is not None
    assert result.review.overall_pass is True
    assert len(result.trace) >= 4  # Planner, Characters, Writer, Reviewer


@pytest.mark.asyncio
async def test_parallel_character_agents_keep_their_own_usage(
    project_dir, mock_planner, mock_char_agent, mock_writer, mock_reviewer, monkeypatch
):
    pipeline = ScenePipeline()
    monkeypatch.setattr(
        pipeline,
        "assemble_context",
        lambda *_: {
            "characters": {
                "major": [
                    {"core": {"name": "A"}, "state": {}},
                    {"core": {"name": "B"}, "state": {}},
                ]
            }
        },
    )

    async def generate(self, _provider, _context, _plan, core, _state):
        tokens = {"A": 11, "B": 22}[core["name"]]
        self.last_usage = {"total_tokens": tokens}
        await asyncio.sleep(0)
        return CharacterIntent(character_name=core["name"])

    monkeypatch.setattr(CharacterIntentAgent, "generate", generate)

    result = None
    async for _token, gen_result in pipeline.generate_stream(
        project_dir,
        "scene-1",
        mock_planner,
        mock_char_agent,
        mock_writer,
        mock_reviewer,
    ):
        result = gen_result or result

    character_trace = next(entry for entry in result.trace if entry.stage == "characters")
    assert {child.agent_name: child.token_count for child in character_trace.children} == {
        "A": 11,
        "B": 22,
    }


@pytest.mark.asyncio
async def test_analyze_draft_uses_injected_fact_and_state_providers(
    project_dir, mock_planner, mock_char_agent, mock_writer, mock_reviewer, monkeypatch
):
    class EmptyFacts(BaseModel):
        facts: list[dict] = Field(default_factory=list)

    class EmptyChanges(BaseModel):
        changes: list[dict] = Field(default_factory=list)

    class RecordingProvider(MockProvider):
        def __init__(self, response):
            super().__init__(structured_response=response)
            self.structured_calls = 0
            self.closed = False

        async def generate_structured(self, *args, **kwargs):
            self.structured_calls += 1
            return await super().generate_structured(*args, **kwargs)

        async def close(self):
            self.closed = True
            await super().close()

    fact_provider = RecordingProvider(
        EmptyFacts(
            facts=[
                {
                    "description": "fact provider marker",
                    "category": "world",
                    "confidence": 0.9,
                    "source_excerpt": "marker",
                }
            ]
        )
    )
    state_provider = RecordingProvider(
        EmptyChanges(
            changes=[
                {
                    "character_id": "char-1",
                    "character_name": "林轩",
                    "changes": [
                        {
                            "type": "set_field",
                            "field": "emotion",
                            "value": "state provider marker",
                        }
                    ],
                }
            ]
        )
    )

    from app.providers import config as provider_config

    def fail_if_config_loaded():
        raise AssertionError("analyze_draft must not load UI provider settings")

    monkeypatch.setattr(provider_config, "load_provider_config", fail_if_config_loaded)

    pipeline = ScenePipeline()
    result = None

    async for _token, gen_result in pipeline.generate_stream(
        project_dir, "scene-1",
        mock_planner, mock_char_agent, mock_writer, mock_reviewer,
    ):
        if gen_result is not None:
            result = gen_result

    await pipeline.analyze_draft(
        project_dir,
        result,
        fact_provider=fact_provider,
        state_provider=state_provider,
    )

    assert fact_provider.structured_calls == 1
    assert state_provider.structured_calls == 1
    assert result.extracted_facts[0]["description"] == "fact provider marker"
    assert result.state_changes[0]["changes"][0]["value"] == "state provider marker"
    assert fact_provider.closed is False
    assert state_provider.closed is False


@pytest.mark.asyncio
async def test_analyze_draft_updates_all_major_characters(monkeypatch):
    from app.pipeline.pipeline import GenerationResult

    pipeline = ScenePipeline()
    major_characters = [
        {"core": {"id": f"char-{number}", "name": f"角色{number}"}, "state": {}}
        for number in range(5)
    ]
    monkeypatch.setattr(
        pipeline,
        "assemble_context",
        lambda *args: {"characters": {"major": major_characters}},
    )

    async def generate_facts(*args):
        return []

    seen_character_ids = []

    async def generate_state_changes(provider, context, prose, scene_id, characters):
        seen_character_ids.extend(character["core"]["id"] for character in characters)
        return []

    monkeypatch.setattr(pipeline._fact_extractor, "generate", generate_facts)
    monkeypatch.setattr(pipeline._state_updater, "generate", generate_state_changes)

    await pipeline.analyze_draft(
        Path("."),
        GenerationResult(scene_id="scene-1", prose="正文"),
        fact_provider=object(),
        state_provider=object(),
    )

    assert seen_character_ids == [f"char-{number}" for number in range(5)]


@pytest.mark.asyncio
async def test_failed_review_does_not_analyze_memory(
    project_dir, mock_planner, mock_char_agent, mock_writer, monkeypatch
):
    from app.providers import config as provider_config

    requested_steps = []
    monkeypatch.setattr(
        provider_config,
        "get_provider_for_step",
        lambda step_id, config: requested_steps.append(step_id),
    )
    failed_review = ReviewResult(scene_id="scene-1", overall_pass=False, summary="bad")
    pipeline = ScenePipeline()

    async for _token, _result in pipeline.generate_stream(
        project_dir,
        "scene-1",
        mock_planner,
        mock_char_agent,
        mock_writer,
        MockProvider(structured_response=failed_review),
    ):
        pass

    assert requested_steps == []


@pytest.mark.asyncio
async def test_pipeline_aborts_on_plan_rejection(
    project_dir, mock_planner, mock_char_agent, mock_writer, mock_reviewer
):
    """Pipeline should abort after planner if user rejects the plan."""
    pipeline = ScenePipeline()

    async def on_plan_ready(plan):
        return False  # reject

    result = None
    async for token, gen_result in pipeline.generate_stream(
        project_dir, "scene-1",
        mock_planner, mock_char_agent, mock_writer, mock_reviewer,
        on_plan_ready=on_plan_ready,
    ):
        if gen_result is not None:
            result = gen_result

    assert result is not None
    assert result.prose == ""
    assert result.plan is not None
    assert len(result.character_intents) == 0
    assert result.review is None


@pytest.mark.asyncio
async def test_pipeline_handles_planner_failure(
    project_dir, mock_char_agent, mock_writer, mock_reviewer
):
    """Pipeline should stop and report error if planner fails."""
    failing_provider = MockProvider()

    pipeline = ScenePipeline()

    result = None
    async for token, gen_result in pipeline.generate_stream(
        project_dir, "scene-1",
        failing_provider, mock_char_agent, mock_writer, mock_reviewer,
    ):
        if gen_result is not None:
            result = gen_result

    assert result is not None
    assert result.prose == ""
    assert result.plan is None
    assert len(result.trace) == 1
    assert result.trace[0].status == "failed"
