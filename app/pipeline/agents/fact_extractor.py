"""FactExtractorAgent — extracts new canon facts from generated prose."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.pipeline.agents._prose import select_prose_excerpt
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
        self.last_summary = ""
        self.last_open_threads: list[str] = []

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
            summary: str = ""
            open_threads: list[str] = Field(default_factory=list)

        resp: ProviderResponse = await provider.generate_structured(
            messages, FactList, temperature=0.2
        )
        self.last_usage = resp.usage
        if resp.model is not None and isinstance(resp.model, FactList):
            facts = resp.model.facts
            summary = resp.model.summary
            open_threads = resp.model.open_threads
        else:
            parsed = resp.parsed or {}
            summary = parsed.get("summary", "")
            open_threads = parsed.get("open_threads", [])
            facts = [ExtractedFact(**item) for item in parsed.get("facts", [])]
        self.last_summary = summary.strip()
        if not self.last_summary:
            raise ValueError("Fact Extractor did not return a scene summary")
        self.last_open_threads = open_threads
        return facts

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

    lines.append("【场景正文】")
    lines.append(select_prose_excerpt(prose))
    lines.append("")

    lines.append("【输出要求】")
    lines.append("从以上正文中提取新的事实，每条事实包含：")
    lines.append("- description: 事实描述（一句话）")
    lines.append("- category: world（世界观）/ character（角色）/ plot（剧情）")
    lines.append("- confidence: 可信度 0-1（1=明确陈述，0.5=暗示，0.3=推测）")
    lines.append("- source_excerpt: 原文中支持该事实的句子或短语")
    lines.append("- summary: 用两到四句话概括本场景发生的事件与结尾状态")
    lines.append("- open_threads: 本场景留下的未解决悬念或后续钩子")
    lines.append("")
    lines.append('输出 JSON 格式：{"facts": [...], "summary": "...", "open_threads": [...]}')
    lines.append("即使没有新的事实，也必须输出 summary 和 open_threads")

    return "\n".join(lines)
