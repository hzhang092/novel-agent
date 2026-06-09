"""CharacterIntentAgent — generates intent JSON for one major-tier character.

Runs one instance per major-tier character per scene (max 4 in parallel).
Outputs intentions only — NEVER writes prose.
"""

from __future__ import annotations

from app.providers.base import LLMProvider, ProviderResponse
from app.storage.models import CharacterIntent


class CharacterIntentAgent:
    """Generates intent/emotion/goals for a single character in a scene.

    Usage::

        agent = CharacterIntentAgent()
        intent: CharacterIntent = await agent.generate(
            provider, context, scene_plan, char_core, char_state
        )
    """

    async def generate(
        self,
        provider: LLMProvider,
        context: dict,
        scene_plan: dict,
        char_core: dict,
        char_state: dict,
    ) -> CharacterIntent:
        """Run the character intent agent and return a validated result."""
        messages = _build_character_messages(context, scene_plan, char_core, char_state)
        resp: ProviderResponse = await provider.generate_structured(
            messages, CharacterIntent, temperature=0.5
        )
        if resp.model is not None and isinstance(resp.model, CharacterIntent):
            return resp.model
        parsed = resp.parsed or {}
        return CharacterIntent(**parsed)

    def build_prompt(
        self,
        context: dict,
        scene_plan: dict,
        char_core: dict,
        char_state: dict,
    ) -> str:
        """Return the user-facing prompt string for inspection."""
        return _build_character_prompt(context, scene_plan, char_core, char_state)


def _build_character_messages(
    context: dict,
    scene_plan: dict,
    char_core: dict,
    char_state: dict,
) -> list[dict[str, str]]:
    char_name = char_core.get("name", "未知角色")
    system = (
        f"你正在扮演小说角色「{char_name}」。"
        "你不是作者。你不能写小说正文。"
        "你的任务是根据角色卡和场景规划，输出该角色在本场景中的意图。"
        "你必须严格遵守以下规则：\n"
        "- 你只能使用该角色知道的信息\n"
        "- 不要替其他角色做决定\n"
        "- 不要推动超出大纲的剧情\n"
        "- 不要输出小说正文\n"
        "你必须输出严格的 JSON 格式。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _build_character_prompt(context, scene_plan, char_core, char_state)},
    ]


def _build_character_prompt(
    context: dict,
    scene_plan: dict,
    char_core: dict,
    char_state: dict,
) -> str:
    lines: list[str] = []
    char_name = char_core.get("name", "")
    knowledge = char_state.get("current_knowledge", [])

    lines.append(f"【角色卡：{char_name}】")
    lines.append(f"- 身份：{char_core.get('identity', '')}")
    lines.append(f"- 年龄：{char_core.get('age', '')}")
    lines.append(f"- 外貌：{char_core.get('appearance', '')}")
    lines.append(f"- 性格：{char_core.get('personality', '')}")
    lines.append(f"- 背景：{char_core.get('background', '')}")
    if char_core.get("long_term_goal"):
        lines.append(f"- 长期目标：{char_core['long_term_goal']}")
    if char_core.get("hidden_motive"):
        lines.append(f"- 隐藏动机：{char_core['hidden_motive']}")
    lines.append(f"- 说话风格：{char_core.get('speech_style', '')}")
    skills = char_core.get("core_skills", [])
    if skills:
        lines.append(f"- 技能：{'、'.join(skills)}")
    weaknesses = char_core.get("core_weaknesses", [])
    if weaknesses:
        lines.append(f"- 弱点：{'、'.join(weaknesses)}")
    lines.append("")

    lines.append("【当前状态】")
    lines.append(f"- 当前情绪：{char_state.get('current_emotion', '')}")
    lines.append(f"- 当前目标：{char_state.get('current_goal', '')}")
    lines.append(f"- 当前位置：{char_state.get('current_location', '')}")
    if char_state.get("current_power_level"):
        lines.append(f"- 当前修为：{char_state['current_power_level']}")
    if char_state.get("current_status"):
        lines.append(f"- 当前状态：{char_state['current_status']}")
    rels = char_state.get("current_relationships", {})
    if rels:
        rel_lines = [f"{k}: {v}" for k, v in rels.items()]
        lines.append(f"- 关系：{'；'.join(rel_lines)}")
    if knowledge:
        lines.append(f"- 已知信息：{'；'.join(knowledge[:10])}")
    secrets = char_state.get("current_secrets", [])
    if secrets:
        lines.append(f"- 持有秘密：{'；'.join(secrets)}")
    lines.append("")

    lines.append("【场景规划】")
    if scene_plan.get("scene_goal"):
        lines.append(f"- 场景目标：{scene_plan['scene_goal']}")
    if scene_plan.get("conflict"):
        lines.append(f"- 核心冲突：{scene_plan['conflict']}")
    beats = scene_plan.get("required_beats", [])
    if beats:
        lines.append(f"- 情节节拍：{' → '.join(beats)}")
    if scene_plan.get("emotional_arc"):
        lines.append(f"- 情绪曲线：{scene_plan['emotional_arc']}")
    lines.append("")

    # Other participants
    scene = context.get("scene_info", {})
    participants = scene.get("participating_characters", [])
    other_chars = [p for p in participants if p != char_name]
    if other_chars:
        lines.append(f"【其他在场角色】{'、'.join(other_chars)}")
        lines.append("")

    lines.append("【输出要求】")
    lines.append(f"请以{char_name}的视角，输出该角色在本场景中的意图 JSON：")
    lines.append("- character_name: 角色名")
    lines.append("- current_emotion: 当前情绪（如：压抑愤怒、故作平静）")
    lines.append("- private_goal: 私下真实目标")
    lines.append("- public_goal: 表面目标（与其他角色互动时表现出的）")
    lines.append("- attitude_to_others: 对其他在场角色的态度（dict，角色名→态度描述）")
    lines.append("- likely_actions: 可能采取的行动列表")
    lines.append("- dialogue_intentions: 想通过对话达成的目的")
    lines.append("- forbidden_actions: 该角色绝不会做的事")
    lines.append("- speech_style_notes: 本场景中对白风格提醒")

    return "\n".join(lines)
