"""FactExtractorAgent — extracts new canon facts from generated prose."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.providers.base import LLMProvider, ProviderResponse
from app.storage.models import ExtractedFact


class FactExtractorAgent:
    """Extracts claimed new facts from generated scene prose.

    Usage::

        agent = FactExtractorAgent()
        facts: list[ExtractedFact] = await agent.generate(provider, context, prose, scene_id)
    """

    def __init__(self) -> None:
        self.last_usage: dict | None = None

    async def generate(
        self,
        provider: LLMProvider,
        context: dict,
        prose: str,
        scene_id: str,
    ) -> list[ExtractedFact]:
        """Run the fact extractor and return validated ExtractedFact list."""
        messages = _build_fact_extractor_messages(context, prose)

        class FactList(BaseModel):
            facts: list[ExtractedFact] = Field(default_factory=list)

        resp: ProviderResponse = await provider.generate_structured(
            messages, FactList, temperature=0.2
        )
        self.last_usage = resp.usage
        if resp.model is not None and isinstance(resp.model, FactList):
            return resp.model.facts
        parsed = resp.parsed or {}
        items = parsed.get("facts", [])
        return [ExtractedFact(**item) for item in items]

    def build_prompt(self, context: dict, prose: str) -> str:
        """Return the user-facing prompt string for inspection."""
        return _build_fact_extractor_prompt(context, prose)


def _build_fact_extractor_messages(
    context: dict,
    prose: str,
) -> list[dict[str, str]]:
    system = (
        "你是一位细心的设定整理员。"
        "你的任务是从刚生成的场景正文中提取可能影响后续剧情的新设定/事实。"
        "注意：只提取新的事实，不要重复已知设定。"
        "每条事实应包括：描述、分类（world/character/plot）、可信度（0-1）、原文出处。"
        "你必须输出严格的 JSON 格式。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _build_fact_extractor_prompt(context, prose)},
    ]


def _build_fact_extractor_prompt(context: dict, prose: str) -> str:
    lines: list[str] = []

    # Known facts to avoid duplication
    facts = context.get("canon_facts", [])
    if facts:
        lines.append(f"【已知设定（共{len(facts)}条，请勿重复提取）】")
        for f in facts[:20]:
            lines.append(f"- [{f.get('category', '')}] {f.get('description', '')}")
        lines.append("")

    # Scene info for context
    scene = context.get("scene_info", {})
    if scene:
        lines.append("【场景信息】")
        lines.append(f"- 标题：{scene.get('scene_title', '')}")
        lines.append(f"- 地点：{scene.get('location', '')}")
        chars = scene.get("participating_characters", [])
        if chars:
            lines.append(f"- 角色：{'、'.join(chars)}")
        lines.append("")

    # The prose (truncated)
    prose_excerpt = prose[:6000] if len(prose) > 6000 else prose
    lines.append("【场景正文】")
    lines.append(prose_excerpt)
    if len(prose) > 6000:
        lines.append(f"\n... (正文共 {len(prose)} 字，以上为前 6000 字)")
    lines.append("")

    lines.append("【输出要求】")
    lines.append("从以上正文中提取新的事实，每条事实包含：")
    lines.append("- description: 事实描述（一句话）")
    lines.append("- category: world（世界观）/ character（角色）/ plot（剧情）")
    lines.append("- confidence: 可信度 0-1（1=明确陈述，0.5=暗示，0.3=推测）")
    lines.append("- source_excerpt: 原文中支持该事实的句子或短语")
    lines.append("")
    lines.append('输出 JSON 格式：{"facts": [...]}')
    lines.append('如果正文中没有新的事实，输出 {"facts": []}')

    return "\n".join(lines)
