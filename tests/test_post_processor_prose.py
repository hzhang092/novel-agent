"""Tests for prose selection in post-processing prompts."""

import pytest

from app.pipeline.agents.fact_extractor import FactExtractorAgent
from app.pipeline.agents.reviewer import ReviewerAgent
from app.pipeline.agents.state_updater import StateUpdaterAgent


def _prompts(prose: str) -> list[str]:
    return [
        ReviewerAgent().build_prompt({}, {}, {}, prose),
        StateUpdaterAgent().build_prompt({}, prose, []),
        FactExtractorAgent().build_prompt({}, prose),
    ]


@pytest.mark.parametrize("prompt", _prompts("x" * 6000))
def test_post_processors_keep_complete_prose_at_limit(prompt: str) -> None:
    assert "x" * 6000 in prompt
    assert "中间省略" not in prompt


@pytest.mark.parametrize("prompt", _prompts("A" * 3000 + "MIDDLE" + "Z" * 3000))
def test_post_processors_keep_complete_long_prose(prompt: str) -> None:
    assert "A" * 3000 in prompt
    assert "MIDDLE" in prompt
    assert "Z" * 3000 in prompt
    assert "中间省略" not in prompt


def test_state_updater_sees_current_power_level() -> None:
    prompt = StateUpdaterAgent().build_prompt(
        {},
        "正文",
        [
            {
                "core": {"id": "char-1", "name": "林轩"},
                "state": {"current_power_level": "筑基初期标记"},
            }
        ],
    )

    assert "筑基初期标记" in prompt
