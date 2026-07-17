import pytest

from app.pipeline.agents.planner import ScenePlannerAgent
from app.pipeline.agents.reviewer import ReviewerAgent
from app.pipeline.agents.writer import WriterAgent


def world_context():
    return {
        "world_context": {
            "overview": {
                "geography": "东荒大陆",
                "rules": ["不得干涉凡人"],
                "taboos": ["不可夺舍"],
                "technology_level": "古代修真文明",
                "social_structure": "宗门治理",
            },
            "elements": [
                {
                    "id": "faction-qingyun",
                    "type": "faction",
                    "name": "青云宗",
                    "summary": "正道第一宗门",
                    "tags": ["正道"],
                    "importance": 4,
                    "details": {
                        "description": "以剑修闻名",
                        "goals": ["维护秩序"],
                        "ideology": "守正",
                    },
                    "relationships": [
                        {"kind": "opposed_to", "target_name": "魔渊殿", "note": "长期敌对"}
                    ],
                },
                {
                    "id": "faction-moyuan",
                    "type": "faction",
                    "name": "魔渊殿",
                    "summary": "隐于地下魔殿的邪道宗门",
                    "tags": ["邪道"],
                    "importance": 4,
                    "details": {
                        "description": "以禁术掠夺修为",
                        "goals": ["颠覆青云宗"],
                        "ideology": "强者为尊",
                    },
                    "relationships": [],
                },
                {
                    "id": "location-square",
                    "type": "location",
                    "name": "问剑广场",
                    "summary": "宗门试炼场",
                    "tags": [],
                    "importance": 3,
                    "details": {"description": "石台林立", "atmosphere": "肃穆"},
                    "relationships": [],
                },
                {
                    "id": "power-main",
                    "type": "power_system",
                    "name": "九重天境",
                    "summary": "九层修炼体系",
                    "tags": [],
                    "importance": 5,
                    "details": {"limitations": ["不得越级"], "costs": ["消耗灵石"]},
                    "relationships": [],
                },
                {
                    "id": "history-war",
                    "type": "historical_event",
                    "name": "正魔大战",
                    "summary": "百年前两宗决战",
                    "tags": [],
                    "importance": 4,
                    "details": {"description": "大战重塑了东荒格局"},
                    "relationships": [],
                },
                {
                    "id": "term-sword-heart",
                    "type": "terminology",
                    "name": "剑心",
                    "summary": "剑修的心境根基",
                    "tags": [],
                    "importance": 3,
                    "details": {"definition": "人剑合一前的明悟"},
                    "relationships": [],
                },
            ],
        },
        "world_rules": {
            "geography": "东荒大陆",
            "rules": ["不得干涉凡人"],
            "factions": [{"name": "UNSELECTED_SENTINEL"}],
        },
        "world_element_read_points": {
            "faction-qingyun": {"revision": 7, "selection_reasons": ["explicit_scene_reference"]},
            "faction-moyuan": {
                "revision": 2,
                "selection_reasons": ["related_to:faction-qingyun:opposed_to"],
            },
        },
    }


@pytest.mark.parametrize(
    "build_prompt",
    [
        lambda context: ScenePlannerAgent().build_prompt(context),
        lambda context: WriterAgent().build_prompt(context),
        lambda context: ReviewerAgent().build_prompt(context, {}, {}, "正文"),
    ],
)
def test_agents_use_selected_typed_elements_without_storage_metadata(build_prompt):
    prompt = build_prompt(world_context())

    assert "东荒大陆" in prompt
    assert "不得干涉凡人" in prompt
    assert "青云宗" in prompt
    assert "魔渊殿" in prompt
    assert "地下魔殿" in prompt
    assert "九重天境" in prompt
    assert "UNSELECTED_SENTINEL" not in prompt
    assert "faction-qingyun" not in prompt
    assert "selection_reasons" not in prompt
    assert "revision" not in prompt


def test_writer_uses_type_specific_element_headings():
    prompt = WriterAgent().build_prompt(world_context())

    assert "【相关地点】" in prompt
    assert "【相关势力】" in prompt
    assert "【相关力量体系】" in prompt
    assert "【相关历史事件】" in prompt
    assert "【相关术语】" in prompt
