"""WriterAgent — constructs prompts and calls LLM providers for prose generation.

The Writer agent is the SOLE producer of final narrative text. It receives
the assembled context dict from RetrievalEngine, builds a Chinese-language
system prompt, and fires a streaming generation call to the LLM provider.
"""

from __future__ import annotations

from typing import AsyncGenerator

from app.providers.base import LLMProvider


class WriterAgent:
    """Generates Chinese web-novel prose from assembled context.

    Usage::

        agent = WriterAgent()
        prompt = agent.build_prompt(context)  # for inspection
        async for token in agent.generate_stream(provider, context):
            editor.append(token)
    """

    def build_prompt(self, context: dict) -> str:
        """Build the full user prompt from the context dict."""
        return _build_writer_prompt(context)

    async def generate_text(self, provider: LLMProvider, context: dict) -> str:
        """Non-streaming generation: returns complete prose."""
        messages = _build_messages(context)
        resp = await provider.generate_text(messages, temperature=0.7, max_tokens=4096)
        return resp.text

    async def generate_stream(
        self, provider: LLMProvider, context: dict
    ) -> AsyncGenerator[str, None]:
        """Streaming generation: yields tokens as they arrive."""
        messages = _build_messages(context)
        async for token in provider.generate_stream(messages, temperature=0.7, max_tokens=4096):
            yield token


def _build_messages(context: dict) -> list[dict[str, str]]:
    """Build the messages list: system prompt + assembled context."""
    pov = (context.get("style_guide") or {}).get("pov") or "第三人称"
    system = (
        "你是一位专业的网文作家，精通中文网络小说的写作。"
        "你需要根据提供的场景规划、角色意图、世界观设定和风格指南，写出场景的完整小说正文。"
        "严格遵循场景规划中的情节节拍和断章要求。"
        "角色的言行必须符合其角色意图（情绪、目标、禁止行为）。"
        f"使用{pov}叙述，保持文风一致。"
        "直接输出小说正文，不要添加任何解释、标记或JSON包装。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _build_writer_prompt(context)},
    ]


def _build_writer_prompt(context: dict) -> str:
    """Assemble the Chinese writer prompt from context dict sections."""
    lines: list[str] = []

    # ── Scene Info ──
    scene = context.get("scene_info", {})
    if scene:
        lines.append("【场景信息】")
        lines.append(f"- 场景标题：{scene.get('scene_title', '')}")
        lines.append(f"- 地点：{scene.get('location', '')}")
        lines.append(f"- 时间：{scene.get('time', '')}")
        lines.append(f"- 视角角色(POV)：{scene.get('pov_character', '')}")
        participants = scene.get("participating_characters", [])
        if participants:
            lines.append(f"- 参与角色：{'、'.join(participants)}")
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

    # ── Scene Plan (from Planner) ──
    plan = context.get("scene_plan", {})
    if plan:
        lines.append("【场景规划（Planner 输出）】")
        if plan.get("scene_goal"):
            lines.append(f"- 叙事目标：{plan['scene_goal']}")
        if plan.get("conflict"):
            lines.append(f"- 核心冲突：{plan['conflict']}")
        beats = plan.get("required_beats", [])
        if beats:
            lines.append(f"- 剧情节拍：{' → '.join(beats)}")
        if plan.get("emotional_arc"):
            lines.append(f"- 情绪曲线：{plan['emotional_arc']}")
        if plan.get("ending_hook"):
            lines.append(f"- 断章钩子：{plan['ending_hook']}")
        constraints = plan.get("continuity_constraints", [])
        if constraints:
            lines.append(f"- 连续性约束：{'；'.join(constraints)}")
        lines.append("")

    # ── World Rules ──
    world = context.get("world_rules", {})
    if world:
        lines.append("【世界观设定】")
        if world.get("geography"):
            lines.append(f"- 地理：{world['geography']}")
        factions = world.get("factions", [])
        if factions:
            lines.append("- 势力：" + "；".join(
                "，".join(f"{key}：{value}" for key, value in faction.items())
                for faction in factions
            ))
        if world.get("history"):
            lines.append(f"- 历史：{world['history']}")
        rules = world.get("rules", [])
        if rules:
            lines.append(f"- 世界规则：{'；'.join(rules)}")
        taboos = world.get("taboos", [])
        if taboos:
            lines.append(f"- 禁忌：{'；'.join(taboos)}")
        if world.get("technology_level"):
            lines.append(f"- 技术水平：{world['technology_level']}")
        if world.get("social_structure"):
            lines.append(f"- 社会结构：{world['social_structure']}")
        terminology = world.get("terminology", {})
        if terminology:
            lines.append("- 术语：" + "；".join(
                f"{term}：{meaning}" for term, meaning in terminology.items()
            ))
        ps = world.get("power_system", {})
        if ps:
            realms = ps.get("realms", [])
            if realms:
                lines.append(f"- 修炼境界：{' → '.join(realms)}")
            abilities = ps.get("abilities", {})
            if abilities:
                lines.append("- 境界能力：" + "；".join(
                    f"{realm}：{ability}" for realm, ability in abilities.items()
                ))
            limitations = ps.get("limitations", [])
            if limitations:
                lines.append(f"- 修炼限制：{'；'.join(limitations)}")
            costs = ps.get("costs", [])
            if costs:
                lines.append(f"- 修炼代价：{'；'.join(costs)}")
            resources = ps.get("rare_resources", [])
            if resources:
                lines.append(f"- 稀有资源：{'；'.join(resources)}")
            forbidden = ps.get("forbidden_methods", [])
            if forbidden:
                lines.append(f"- 禁术：{'；'.join(forbidden)}")
        lines.append("")

    # ── Characters ──
    chars = context.get("characters", {})
    if chars:
        major = chars.get("major", [])
        supporting = chars.get("supporting", [])
        background = chars.get("background", [])

        if major or supporting or background:
            lines.append("【角色信息】")
            for mc in major:
                core = mc.get("core", {})
                state = mc.get("state", {})
                lines.append(f"\n★ {core.get('name', '')}（主要角色）")
                if core.get("personality"):
                    lines.append(f"  性格：{core['personality']}")
                if core.get("speech_style"):
                    lines.append(f"  说话风格：{core['speech_style']}")
                if core.get("core_skills"):
                    lines.append(f"  技能：{'、'.join(core['core_skills'])}")
                if state.get("current_emotion"):
                    lines.append(f"  当前情绪：{state['current_emotion']}")
                if state.get("current_goal"):
                    lines.append(f"  当前目标：{state['current_goal']}")
                if state.get("current_location"):
                    lines.append(f"  当前位置：{state['current_location']}")
                if state.get("current_power_level"):
                    lines.append(f"  当前实力：{state['current_power_level']}")
                relationships = state.get("current_relationships", {})
                if relationships:
                    lines.append("  当前关系：" + "；".join(
                        f"{name}：{relationship}"
                        for name, relationship in relationships.items()
                    ))
                knowledge = state.get("current_knowledge", [])
                if knowledge:
                    lines.append(f"  已知信息：{'；'.join(knowledge)}")
                secrets = state.get("current_secrets", [])
                if secrets:
                    lines.append(f"  当前秘密：{'；'.join(secrets)}")
                if state.get("current_status"):
                    lines.append(f"  当前状态：{state['current_status']}")
            for sc in supporting:
                lines.append(f"\n· {sc.get('name', '')}（配角）")
                if sc.get("relationship"):
                    lines.append(f"  关系：{sc['relationship']}")
            for bc in background:
                lines.append(f"  • {bc.get('name', '')}（背景角色）")
            lines.append("")

    # ── Character Intents (from Character Intent agents) ──
    intents = context.get("character_intents", {})
    if intents:
        lines.append("【角色意图（各角色的私下目标和对话意图）】")
        for name, intent in intents.items():
            if isinstance(intent, dict):
                lines.append(f"\n★ {name}")
                lines.append(f"  当前情绪：{intent.get('current_emotion', '')}")
                lines.append(f"  真实目标：{intent.get('private_goal', '')}")
                lines.append(f"  表面目标：{intent.get('public_goal', '')}")
                actions = intent.get('likely_actions', [])
                if actions:
                    lines.append(f"  可能行动：{'；'.join(actions)}")
                forbidden = intent.get('forbidden_actions', [])
                if forbidden:
                    lines.append(f"  禁止行为：{'；'.join(forbidden)}")
                speech = intent.get('speech_style_notes', '')
                if speech:
                    lines.append(f"  对白风格：{speech}")
        lines.append("")

    # ── Outline Context ──
    outline = context.get("outline_context", {})
    if outline:
        lines.append("【大纲背景】")
        if outline.get("volume_title"):
            lines.append(f"- 卷：{outline['volume_title']}")
        if outline.get("volume_summary"):
            lines.append(f"- 本卷概要：{outline['volume_summary']}")
        if outline.get("chapter_title"):
            lines.append(f"- 章：{outline['chapter_title']}")
        lines.append("")

    # ── Recent Summaries ──
    summaries = context.get("recent_summaries", [])
    if summaries:
        lines.append(f"【最近场景摘要】（共{len(summaries)}篇）")
        for i, s in enumerate(summaries):
            lines.append(f"{i+1}. {s.get('summary', '')}")
        lines.append("")

    # ── Canon Facts ──
    facts = context.get("canon_facts", [])
    if facts:
        lines.append(f"【已确认设定】（共{len(facts)}条）")
        for f in facts:
            lines.append(f"- [{f.get('category', '')}] {f.get('description', '')}")
        lines.append("")

    # ── Style Guide ──
    style = context.get("style_guide", {})
    if style:
        lines.append("【风格指南】")
        traits = []
        if style.get("pacing"):
            traits.append(f"节奏：{style['pacing']}")
        if style.get("tone"):
            traits.append(f"基调：{style['tone']}")
        if style.get("pov"):
            traits.append(f"视角：{style['pov']}")
        if style.get("dialogue_density"):
            traits.append(f"对话密度：{style['dialogue_density']}")
        if style.get("sentence_length"):
            traits.append(f"句式：{style['sentence_length']}")
        if traits:
            lines.append("  " + " · ".join(traits))
        taboos_p = style.get("taboo_patterns", [])
        if taboos_p:
            lines.append(f"  禁用模式：{'；'.join(taboos_p)}")
        preferred = style.get("preferred_patterns", [])
        if preferred:
            lines.append(f"  偏好模式：{'；'.join(preferred)}")
        refs = style.get("reference_passages", [])
        if refs:
            lines.append(f"  参考段落：{len(refs)} 段（请在风格上模仿）")
            for r in refs[:2]:
                lines.append(f"    > {r[:200]}")
        freeform = style.get("freeform_notes", "")
        if freeform:
            lines.append(f"  补充说明：{freeform}")
        lines.append("")

    lines.append("【写作指令】")
    lines.append("请根据以上所有信息，写出该场景的完整小说正文。")
    lines.append("要求：")
    lines.append("1. 严格遵循场景规划中的情节节拍顺序")
    lines.append("2. 结尾必须实现指定的断章钩子")
    lines.append("3. 角色的言行必须符合其性格、情绪和目标")
    lines.append("4. 不得违反世界观设定和约束条件")
    lines.append("5. 直接输出小说正文，不要添加任何解释、标记或JSON包装")

    return "\n".join(lines)
