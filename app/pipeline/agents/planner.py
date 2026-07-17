"""ScenePlannerAgent — generates a structured scene plan from assembled context."""

from __future__ import annotations

from app.providers.base import LLMProvider, ProviderResponse
from app.storage.models import ScenePlan
from app.pipeline.agents._character_context import character_prompt_lines
from app.pipeline.agents._world_context import overview_lines, planner_element_lines


class ScenePlannerAgent:
    """Generates a structured scene plan (beats, conflict, emotional arc, hook).

    Usage::

        agent = ScenePlannerAgent()
        plan: ScenePlan = await agent.generate(provider, context, scene_id)
    """

    def __init__(self) -> None:
        self.last_usage: dict | None = None

    async def generate(
        self,
        provider: LLMProvider,
        context: dict,
        scene_id: str,
    ) -> ScenePlan:
        """Run the planner and return a validated ScenePlan."""
        messages = _build_planner_messages(context)
        resp: ProviderResponse = await provider.generate_structured(
            messages, ScenePlan, temperature=0.3
        )
        self.last_usage = resp.usage
        if resp.model is not None and isinstance(resp.model, ScenePlan):
            plan = resp.model
            plan.scene_id = scene_id
            return plan
        # Fallback: parse from dict
        parsed = resp.parsed or {}
        return ScenePlan(scene_id=scene_id, **parsed)

    def build_prompt(self, context: dict) -> str:
        """Return the user-facing prompt string for inspection."""
        return _build_planner_prompt(context)


def _build_planner_messages(context: dict) -> list[dict[str, str]]:
    system = (
        "你是一位长篇小说大纲规划师。"
        "你的任务是将场景大纲转化为详细的剧情节拍规划。"
        "你必须输出严格的 JSON 格式，字段不可缺失。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _build_planner_prompt(context)},
    ]


def _build_planner_prompt(context: dict) -> str:
    lines: list[str] = []

    # Scene info
    scene = context.get("scene_info", {})
    if scene:
        lines.append("【场景大纲】")
        lines.append(f"- 场景标题：{scene.get('scene_title', '')}")
        lines.append(f"- 地点：{scene.get('location', '')}")
        lines.append(f"- 时间：{scene.get('time', '')}")
        lines.append(f"- POV：{scene.get('pov_character', '')}")
        lines.append(f"- 参与者：{'、'.join(scene.get('participating_characters', []))}")
        if scene.get("scene_goal"):
            lines.append(f"- 场景目标：{scene['scene_goal']}")
        if scene.get("conflict"):
            lines.append(f"- 核心冲突：{scene['conflict']}")
        beats = scene.get("required_plot_beats", [])
        if beats:
            lines.append(f"- 情节节拍：{' → '.join(beats)}")
        if scene.get("emotional_turn"):
            lines.append(f"- 情绪转折：{scene['emotional_turn']}")
        if scene.get("ending_hook"):
            lines.append(f"- 断章钩子（结尾必须实现）：{scene['ending_hook']}")
        constraints = scene.get("constraints", [])
        if constraints:
            lines.append(f"- 约束条件：{'；'.join(constraints)}")
        lines.append("")

    # Characters (brief)
    chars = context.get("characters", {})
    major = chars.get("major", [])
    if major:
        lines.append("【在场主要角色】")
        for mc in major:
            core = mc.get("core", {})
            state = mc.get("state", {})
            name = core.get("name", "")
            personality = core.get("personality", "")[:80]
            emotion = state.get("current_emotion", "")
            goal = state.get("current_goal", "")
            lines.append(f"- {name}：性格{personality}，当前情绪{emotion}，当前目标{goal}")
            lines.extend(character_prompt_lines(core, state))
        lines.append("")

    # World rules
    world_context = context.get("world_context", {})
    if world_context:
        lines.extend(overview_lines(world_context, "【全局世界约束】"))
        lines.extend(planner_element_lines(world_context))
    else:
        world = context.get("world_rules", {})
        if world:
            lines.append("【世界观约束】")
            rules = world.get("rules", [])
            if rules:
                lines.append(f"- 规则：{'；'.join(rules[:5])}")
            taboos = world.get("taboos", [])
            if taboos:
                lines.append(f"- 禁忌：{'；'.join(taboos[:5])}")
            lines.append("")

    # Recent summaries
    summaries = context.get("recent_summaries", [])
    if summaries:
        lines.append(f"【最近场景摘要】（共{len(summaries)}篇）")
        for i, s in enumerate(summaries):
            lines.append(f"{i+1}. {s.get('summary', '')[:150]}")
        lines.append("")

    # Canon facts
    facts = context.get("canon_facts", [])
    if facts:
        lines.append(f"【已知设定】（共{len(facts)}条，选取关键的10条）")
        for f in facts[:10]:
            lines.append(f"- [{f.get('category', '')}] {f.get('description', '')}")
        lines.append("")

    lines.append("【输出要求】")
    lines.append("请根据以上信息，输出场景规划 JSON：")
    lines.append("- scene_goal: 本场景的核心叙事目标")
    lines.append("- required_beats: 扩写后的详细剧情节拍列表（5-8个节拍）")
    lines.append("- conflict: 核心冲突的详细描述")
    lines.append("- emotional_arc: 情绪曲线（如：紧张→对峙→爆发→余波）")
    lines.append("- ending_hook: 结尾钩子的具体实现方案")
    lines.append("- continuity_constraints: 本场景不能违反的连续性约束列表")

    return "\n".join(lines)
