"""Tests for WriterAgent — prompt construction and text generation."""
import asyncio

import pytest

from app.pipeline.agents.writer import WriterAgent, _build_messages
from app.pipeline.agents._character_context import compact_character_core
from app.providers.base import MockProvider
from app.storage.bible_models import FactionElement
from app.storage.models import (
    CharacterCore,
    CharacterCustomField,
    CharacterElementRelation,
)


def _make_context() -> dict:
    """Build a minimal but realistic context dict for testing."""
    return {
        "scene_info": {
            "scene_title": "入门考核",
            "location": "落云宗广场",
            "time": "清晨",
            "pov_character": "林轩",
            "participating_characters": ["林轩", "苏清鸾", "考核长老"],
            "scene_goal": "林轩参加落云宗入门考核，展现隐藏实力",
            "conflict": "考核长老故意刁难，林轩被迫暴露部分真实修为",
            "ending_hook": "考核结束后，长老暗中吩咐弟子调查林轩来历",
            "constraints": ["林轩不能暴露全部修为", "苏清鸾旁观"],
        },
        "world_rules": {
            "geography": "东荒地理标记",
            "factions": [{"name": "青云盟标记", "goal": "守护灵脉"}],
            "history": "百年前大战标记",
            "rules": ["修真界以实力为尊", "隐藏修为是大忌"],
            "taboos": ["不得在考核中使用禁术"],
            "technology_level": "灵能机关标记",
            "social_structure": "宗门阶序标记",
            "terminology": {"灵契": "术语解释标记"},
            "power_system": {
                "realms": ["炼气", "筑基", "金丹"],
                "abilities": {"筑基": "御剑标记"},
                "limitations": ["越级挑战会损伤根基"],
                "costs": ["燃烧寿元标记"],
                "rare_resources": ["星砂标记"],
                "forbidden_methods": ["夺舍术标记"],
            },
        },
        "characters": {
            "major": [
                {
                    "core": {"name": "林轩", "tier": "major", "personality": "隐忍、果断", "speech_style": "简练", "core_skills": ["剑术", "火系法术"]},
                    "state": {
                        "current_emotion": "平静中带着警惕",
                        "current_goal": "通过考核但不暴露全部实力",
                        "current_location": "落云宗广场状态标记",
                        "current_power_level": "筑基初期标记",
                        "current_relationships": {"苏清鸾": "盟友标记"},
                        "current_knowledge": ["密道入口标记"],
                        "current_secrets": ["前世身份标记"],
                        "current_status": "轻伤标记",
                    },
                }
            ],
            "supporting": [
                {"name": "苏清鸾", "tier": "supporting", "relationship": "同门, 暗中关注林轩"},
            ],
            "background": [
                {"name": "考核长老", "tier": "background"},
            ],
        },
        "outline_context": {
            "chapter_title": "第一章",
            "volume_title": "第一卷",
            "volume_summary": "本卷追查失落灵脉标记",
        },
        "recent_summaries": [],
        "canon_facts": [],
        "style_guide": {
            "pacing": "快节奏",
            "tone": "热血",
            "pov": "第三人称",
            "dialogue_density": "适中",
            "sentence_length": "混合",
            "reference_passages": [],
            "freeform_notes": "",
            "taboo_patterns": [],
            "preferred_patterns": [],
        },
    }


class TestWriterPrompt:
    """Tests for the WriterAgent prompt construction."""

    def test_build_prompt_includes_scene_info(self):
        agent = WriterAgent()
        context = _make_context()
        prompt = agent.build_prompt(context)

        assert "入门考核" in prompt
        assert "落云宗广场" in prompt
        assert "林轩" in prompt

    def test_build_prompt_includes_style_guide(self):
        agent = WriterAgent()
        context = _make_context()
        prompt = agent.build_prompt(context)

        assert "快节奏" in prompt
        assert "热血" in prompt
        assert "第三人称" in prompt

    def test_system_prompt_respects_style_guide_pov(self):
        first_person = _build_messages(
            {"style_guide": {"pov": "第一人称"}}
        )[0]["content"]
        third_person = _build_messages(
            {"style_guide": {"pov": "第三人称"}}
        )[0]["content"]
        default = _build_messages({})[0]["content"]

        assert "使用第一人称叙述" in first_person
        assert "使用第三人称叙述" not in first_person
        assert "使用第三人称叙述" in third_person
        assert "使用第三人称叙述" in default

    def test_build_prompt_includes_world_rules(self):
        agent = WriterAgent()
        context = _make_context()
        prompt = agent.build_prompt(context)

        assert "修真界以实力为尊" in prompt
        assert "不得在考核中使用禁术" in prompt

    def test_build_prompt_uses_all_assembled_world_outline_and_major_state(self):
        prompt = WriterAgent().build_prompt(_make_context())

        markers = [
            "东荒地理标记", "青云盟标记", "百年前大战标记", "灵能机关标记",
            "宗门阶序标记", "术语解释标记", "御剑标记", "燃烧寿元标记",
            "星砂标记", "夺舍术标记", "落云宗广场状态标记", "筑基初期标记",
            "盟友标记", "密道入口标记", "前世身份标记", "轻伤标记",
            "本卷追查失落灵脉标记",
        ]
        for marker in markers:
            assert marker in prompt

    def test_build_prompt_includes_character_info(self):
        agent = WriterAgent()
        context = _make_context()
        prompt = agent.build_prompt(context)

        assert "隐忍" in prompt
        assert "苏清鸾" in prompt

    def test_supporting_prompt_includes_generation_fields_and_story_connections(self):
        faction = FactionElement(id="faction", name="赤霞宗")
        core = CharacterCore(
            name="苏清鸾",
            tier="supporting",
            personality="外冷内热",
            custom_fields=[
                CharacterCustomField(
                    label="秘密任务", value_type="text", value="保护林轩"
                ),
                CharacterCustomField(
                    label="编辑备注",
                    value_type="text",
                    value="不要写入提示词",
                    include_in_generation=False,
                ),
            ],
            element_relations=[
                CharacterElementRelation(
                    kind="member_of", target_element_id=faction.id
                )
            ],
        )
        context = _make_context()
        context["characters"]["supporting"] = [
            compact_character_core(core, tier=core.tier, elements=[faction])
        ]

        prompt = WriterAgent().build_prompt(context)

        assert "外冷内热" in prompt
        assert "秘密任务：保护林轩" in prompt
        assert "赤霞宗" in prompt
        assert "不要写入提示词" not in prompt

    def test_build_prompt_includes_ending_hook_instruction(self):
        agent = WriterAgent()
        context = _make_context()
        prompt = agent.build_prompt(context)

        assert "断章" in prompt or "钩子" in prompt

    def test_build_prompt_is_chinese(self):
        agent = WriterAgent()
        context = _make_context()
        prompt = agent.build_prompt(context)

        # Prompt should be predominantly Chinese
        chinese_chars = sum(1 for c in prompt if '\u4e00' <= c <= '\u9fff')
        assert chinese_chars > 100


class TestWriterAgentGeneration:
    """Tests for WriterAgent text generation with MockProvider."""

    @pytest.mark.asyncio
    async def test_generate_text_returns_provider_response(self):
        agent = WriterAgent()
        provider = MockProvider(text_response="林轩缓步走向考核台。")

        context = _make_context()
        result = await agent.generate_text(provider, context)

        assert result == "林轩缓步走向考核台。"

    @pytest.mark.asyncio
    async def test_generate_stream_yields_tokens(self):
        agent = WriterAgent()
        tokens = ["林", "轩", "缓", "步", "走", "向", "考", "核", "台", "。"]
        provider = MockProvider(stream_tokens=tokens)

        context = _make_context()
        collected = []
        async for token in agent.generate_stream(provider, context):
            collected.append(token)

        assert collected == tokens
