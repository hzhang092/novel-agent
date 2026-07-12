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
def test_post_processors_preserve_both_ends_when_prose_is_too_long(prompt: str) -> None:
    assert "A" * 3000 in prompt
    assert "Z" * 3000 in prompt
    assert "MIDDLE" not in prompt
    assert "中间省略，正文共 6006 字" in prompt
