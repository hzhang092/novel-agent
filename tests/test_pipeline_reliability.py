"""Tests for pipeline reliability: TokenTracker, incremental saves, error panel."""

import json
import tempfile
from pathlib import Path

import pytest

from app.pipeline.token_tracker import TokenTracker, _estimate_cost
from app.storage.models import (
    Project,
    Character,
    CharacterCore,
    CharacterState,
    CharacterTier,
    VolumeOutline,
    ChapterOutline,
    SceneOutline,
)
from app.storage.project_files import (
    create_project,
    save_character,
    save_volume_outline,
    save_scene_plan,
    load_scene_plan,
    save_scene_intents,
    load_scene_intents,
    save_scene_review,
    load_scene_review,
)


class TestTokenTracker:
    """Unit tests for TokenTracker singleton."""

    def setup_method(self) -> None:
        TokenTracker.reset()

    def test_session_total_accumulates(self, tmp_path: Path) -> None:
        tracker = TokenTracker.get()
        tracker.log_call(tmp_path, "scene-1", "Planner", "deepseek", "deepseek-chat", 1000, 500)
        assert tracker.session_total_tokens == 1500
        tracker.log_call(tmp_path, "scene-1", "Writer", "deepseek", "deepseek-chat", 2000, 800)
        assert tracker.session_total_tokens == 4300

    def test_jsonl_appends_lines(self, tmp_path: Path) -> None:
        tracker = TokenTracker.get()
        tracker.log_call(tmp_path, "scene-1", "Planner", "deepseek", "deepseek-chat", 100, 50)
        tracker.log_call(tmp_path, "scene-1", "Writer", "deepseek", "deepseek-chat", 200, 100)

        filepath = tmp_path / "token_usage.jsonl"
        assert filepath.exists()
        with open(filepath, "r", encoding="utf-8") as fh:
            lines = [line.strip() for line in fh if line.strip()]
        assert len(lines) == 2
        entry = json.loads(lines[0])
        assert entry["agent"] == "Planner"
        assert entry["total_tokens"] == 150
        assert entry["provider"] == "deepseek"
        assert entry["model"] == "deepseek-chat"

    def test_project_total_sums_jsonl(self, tmp_path: Path) -> None:
        tracker = TokenTracker.get()
        tracker.log_call(tmp_path, "scene-1", "Planner", "ollama", "qwen", 100, 50)
        tracker.log_call(tmp_path, "scene-2", "Writer", "ollama", "qwen", 300, 100)
        total = tracker.get_project_total(tmp_path)
        assert total == 550

    def test_deepseek_cost_estimation(self, tmp_path: Path) -> None:
        tracker = TokenTracker.get()
        tracker.log_call(tmp_path, "scene-1", "Planner", "deepseek", "deepseek-chat", 1_000_000, 1_000_000)
        assert abs(tracker.session_cost - 1.37) < 0.01

    def test_ollama_cost_is_zero(self, tmp_path: Path) -> None:
        tracker = TokenTracker.get()
        tracker.log_call(tmp_path, "scene-1", "Planner", "ollama", "qwen", 1_000_000, 1_000_000)
        assert tracker.session_cost == 0.0

    def test_get_project_total_returns_0_for_no_file(self, tmp_path: Path) -> None:
        tracker = TokenTracker.get()
        assert tracker.get_project_total(tmp_path) == 0

    def test_cost_estimate_direct(self) -> None:
        """Test _estimate_cost function directly."""
        # deepseek-chat: $0.27/M input, $1.10/M output
        cost = _estimate_cost("deepseek", "deepseek-chat", 500_000, 500_000)
        expected = (500_000 / 1_000_000) * 0.27 + (500_000 / 1_000_000) * 1.10
        assert abs(cost - expected) < 0.001

        # Non-deepseek provider returns 0
        assert _estimate_cost("ollama", "qwen", 1_000_000, 1_000_000) == 0.0


class TestIncrementalSaves:
    """Tests for intermediate output save/load."""

    @pytest.fixture
    def project_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Project(title="TestReliability", genre="玄幻", llm_provider="mock")
            proj_dir = create_project(Path(tmp), proj)

            scene = SceneOutline(
                id="scene-1",
                title="测试场景",
                location="测试地点",
            )
            chapter = ChapterOutline(id="ch-1", title="第一章", scenes=[scene])
            volume = VolumeOutline(id="vol-1", title="第一卷", chapters=[chapter])
            save_volume_outline(proj_dir, volume)

            yield proj_dir

    def test_save_and_load_plan(self, project_dir: Path) -> None:
        plan = {"scene_goal": "test", "required_beats": ["beat1", "beat2"]}
        save_scene_plan(project_dir, "scene-1", plan)
        loaded = load_scene_plan(project_dir, "scene-1")
        assert loaded is not None
        assert loaded["scene_goal"] == "test"
        assert loaded["required_beats"] == ["beat1", "beat2"]

    def test_save_and_load_intents(self, project_dir: Path) -> None:
        intents = {"char-a": {"current_emotion": "angry"}, "char-b": {"current_emotion": "calm"}}
        save_scene_intents(project_dir, "scene-1", intents)
        loaded = load_scene_intents(project_dir, "scene-1")
        assert loaded is not None
        assert loaded["char-a"]["current_emotion"] == "angry"

    def test_save_and_load_review(self, project_dir: Path) -> None:
        review = {"overall_pass": True, "summary": "all good", "issues": []}
        save_scene_review(project_dir, "scene-1", review)
        loaded = load_scene_review(project_dir, "scene-1")
        assert loaded is not None
        assert loaded["overall_pass"] is True
        assert loaded["summary"] == "all good"

    def test_load_nonexistent_returns_none(self, project_dir: Path) -> None:
        assert load_scene_plan(project_dir, "nonexistent") is None
        assert load_scene_intents(project_dir, "nonexistent") is None
        assert load_scene_review(project_dir, "nonexistent") is None


class TestPipelineTokenLogging:
    """Integration tests for token logging during pipeline execution."""

    @pytest.fixture
    def project_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Project(title="TestTokens", genre="玄幻", llm_provider="mock")
            proj_dir = create_project(Path(tmp), proj)

            # Create a character
            char = Character(
                core=CharacterCore(
                    name="林轩", tier=CharacterTier.MAJOR, personality="冷静果断",
                    speech_style="简洁有力",
                ),
                state=CharacterState(
                    character_id="char-1", current_emotion="平静",
                    current_goal="探索秘境",
                ),
            )
            save_character(proj_dir, char)

            # Create outline with one scene
            scene = SceneOutline(
                id="scene-1",
                title="测试场景",
                location="秘境入口",
                time="清晨",
                pov_character="林轩",
                participating_characters=["林轩"],
                scene_goal="发现秘境秘密",
                conflict="机关陷阱",
                ending_hook="秘境深处传来低语",
            )
            chapter = ChapterOutline(id="ch-1", title="第一章", scenes=[scene])
            volume = VolumeOutline(id="vol-1", title="第一卷", chapters=[chapter])
            save_volume_outline(proj_dir, volume)

            yield proj_dir

    @pytest.mark.asyncio
    async def test_token_logging_produces_jsonl(self, project_dir: Path) -> None:
        """After a pipeline run with MockProvider, token_usage.jsonl should exist."""
        from app.pipeline.pipeline import ScenePipeline
        from app.providers.base import MockProvider
        from app.storage.models import ScenePlan, CharacterIntent, ReviewResult, ReviewIssue

        TokenTracker.reset()

        plan = ScenePlan(
            scene_goal="发现秘境秘密",
            required_beats=["进入入口", "触发机关"],
            conflict="古老的机关守护着秘境",
            emotional_arc="好奇→紧张",
            ending_hook="秘境深处传来低语",
        )
        intent = CharacterIntent(
            character_name="林轩",
            current_emotion="谨慎而好奇",
            private_goal="找到宝物",
            public_goal="探索秘境",
        )
        review = ReviewResult(
            scene_id="scene-1",
            issues=[ReviewIssue(category="continuity", description="通过", passed=True)],
            overall_pass=True,
            summary="所有检查通过",
        )

        pipeline = ScenePipeline()

        async def on_plan_ready(plan):
            return True

        result = None
        async for token, gen_result in pipeline.generate_stream(
            project_dir, "scene-1",
            MockProvider(structured_response=plan),
            MockProvider(structured_response=intent),
            MockProvider(stream_tokens=["测试", "正文"]),
            MockProvider(structured_response=review),
            on_plan_ready=on_plan_ready,
        ):
            if gen_result is not None:
                result = gen_result

        assert result is not None
        assert result.prose == "测试正文"

        # Check token_usage.jsonl exists
        jsonl_path = project_dir / "token_usage.jsonl"
        assert jsonl_path.exists(), "token_usage.jsonl should exist after pipeline run"

        # Check intermediate files exist
        assert (project_dir / "scenes" / "ch-1" / "scene-1.plan.json").exists()
        assert (project_dir / "scenes" / "ch-1" / "scene-1.intents.json").exists()
        assert (project_dir / "scenes" / "ch-1" / "scene-1.review.json").exists()
