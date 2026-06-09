"""ReviewerAgent — checks generated prose for continuity, style, hooks, and face-slap beats."""

from __future__ import annotations

from app.providers.base import LLMProvider, ProviderResponse
from app.storage.models import ReviewResult


class ReviewerAgent:
    """Reviews generated prose against context, plan, and character intents.

    Usage::

        agent = ReviewerAgent()
        result: ReviewResult = await agent.generate(provider, context, plan, intents, prose)
    """

    async def generate(
        self,
        provider: LLMProvider,
        context: dict,
        scene_plan: dict,
        character_intents: dict[str, dict],
        prose: str,
        scene_id: str,
    ) -> ReviewResult:
        """Run the reviewer and return a validated ReviewResult."""
        messages = _build_reviewer_messages(context, scene_plan, character_intents, prose)
        resp: ProviderResponse = await provider.generate_structured(
            messages, ReviewResult, temperature=0.2
        )
        if resp.model is not None and isinstance(resp.model, ReviewResult):
            result = resp.model
            result.scene_id = scene_id
            return result
        parsed = resp.parsed or {}
        return ReviewResult(scene_id=scene_id, **parsed)

    def build_prompt(
        self,
        context: dict,
        scene_plan: dict,
        character_intents: dict[str, dict],
        prose: str,
    ) -> str:
        """Return the user-facing prompt string for inspection."""
        return _build_reviewer_prompt(context, scene_plan, character_intents, prose)


def _build_reviewer_messages(
    context: dict,
    scene_plan: dict,
    character_intents: dict[str, dict],
    prose: str,
) -> list[dict[str, str]]:
    system = (
        "你是一位严格的小说审稿编辑。"
        "你的任务是检查刚生成的场景正文是否存在问题。"
        "你必须客观、具体地指出每一个问题，不得敷衍。"
        "如果没有问题，也要明确说明。"
        "你必须输出严格的 JSON 格式。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _build_reviewer_prompt(context, scene_plan, character_intents, prose)},
    ]


def _build_reviewer_prompt(
    context: dict,
    scene_plan: dict,
    character_intents: dict[str, dict],
    prose: str,
) -> str:
    lines: list[str] = []

    lines.append("【场景规划（期望）】")
    if scene_plan.get("scene_goal"):
        lines.append(f"- 目标：{scene_plan['scene_goal']}")
    if scene_plan.get("conflict"):
        lines.append(f"- 冲突：{scene_plan['conflict']}")
    beats = scene_plan.get("required_beats", [])
    if beats:
        lines.append(f"- 节拍：{' → '.join(beats)}")
    if scene_plan.get("emotional_arc"):
        lines.append(f"- 情绪曲线：{scene_plan['emotional_arc']}")
    if scene_plan.get("ending_hook"):
        lines.append(f"- 断章钩子：{scene_plan['ending_hook']}")
    constraints = scene_plan.get("continuity_constraints", [])
    if constraints:
        lines.append(f"- 连续性约束：{'；'.join(constraints)}")
    lines.append("")

    lines.append("【角色意图（期望行为）】")
    for name, intent in character_intents.items():
        lines.append(f"\n★ {name}")
        if isinstance(intent, dict):
            lines.append(f"  情绪：{intent.get('current_emotion', '')}")
            lines.append(f"  真实目标：{intent.get('private_goal', '')}")
            lines.append(f"  表面目标：{intent.get('public_goal', '')}")
            actions = intent.get("likely_actions", [])
            if actions:
                lines.append(f"  可能行动：{'；'.join(actions)}")
            forbidden = intent.get("forbidden_actions", [])
            if forbidden:
                lines.append(f"  禁止行为：{'；'.join(forbidden)}")
    lines.append("")

    # Canon facts for continuity check
    facts = context.get("canon_facts", [])
    if facts:
        lines.append(f"【正典设定（不可违反，共{len(facts)}条）】")
        for f in facts[:15]:
            lines.append(f"- [{f.get('category', '')}] {f.get('description', '')}")
        lines.append("")

    # World rules
    world = context.get("world_rules", {})
    if world:
        lines.append("【世界观规则】")
        rules = world.get("rules", [])
        if rules:
            lines.append(f"- 规则：{'；'.join(rules)}")
        taboos = world.get("taboos", [])
        if taboos:
            lines.append(f"- 禁忌：{'；'.join(taboos)}")
        lines.append("")

    # Style guide
    style = context.get("style_guide", {})
    if style:
        lines.append("【风格指南】")
        if style.get("pacing"):
            lines.append(f"- 节奏要求：{style['pacing']}")
        if style.get("tone"):
            lines.append(f"- 基调要求：{style['tone']}")
        taboos_p = style.get("taboo_patterns", [])
        if taboos_p:
            lines.append(f"- 禁用模式：{'；'.join(taboos_p)}")
        lines.append("")

    # The prose to review (truncated)
    prose_excerpt = prose[:4000] if len(prose) > 4000 else prose
    lines.append("【待审正文】")
    lines.append(prose_excerpt)
    if len(prose) > 4000:
        lines.append(f"\n... (正文共 {len(prose)} 字，以上为前 4000 字)")
    lines.append("")

    lines.append("【审查要求】")
    lines.append("请逐一检查以下四个维度，每个维度输出一个 ReviewIssue：")
    lines.append("")
    lines.append("1. continuity（连续性）：正文是否与正典设定、连续性约束、角色当前状态一致？")
    lines.append("   - 是否有角色知道了他不该知道的信息？")
    lines.append("   - 是否有矛盾的正典设定？")
    lines.append("")
    lines.append("2. style（风格）：正文是否符合风格指南？")
    lines.append("   - 节奏、基调是否符合要求？")
    lines.append("   - 是否有禁用模式出现？")
    lines.append("")
    lines.append("3. hook（断章钩子）：结尾是否实现了指定的断章钩子？")
    lines.append("   - 钩子是否在场景结尾明确出现？")
    lines.append("   - 钩子是否有足够的悬念/冲击力？")
    lines.append("")
    lines.append("4. face_slap（打脸节拍）：如果场景涉及打脸情节，是否包含完整的 setup→confrontation→payoff→reaction 循环？")
    lines.append("   - 如果没有打脸情节，此项 passed=true，description=\"不适用\"")
    lines.append("")
    lines.append("每个 ReviewIssue 格式：")
    lines.append("- severity: \"critical\" / \"major\" / \"minor\"")
    lines.append("- description: 具体问题描述（如果没问题则写\"通过\"）")
    lines.append("- category: \"continuity\" / \"style\" / \"hook\" / \"face_slap\"")
    lines.append("- passed: true/false")
    lines.append("")
    lines.append("overall_pass 为 true 当且仅当所有 issue 的 passed 均为 true。")
    lines.append("summary: 一句话总结审查结果。")

    return "\n".join(lines)
