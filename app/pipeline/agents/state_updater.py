"""StateUpdaterAgent — proposes CharacterState changes after a scene."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.providers.base import LLMProvider, ProviderResponse
from app.storage.models import StateChangeProposal


class StateUpdaterAgent:
    """Proposes CharacterState changes for all major characters after a scene.

    Usage::

        agent = StateUpdaterAgent()
        changes: list[StateChangeProposal] = await agent.generate(
            provider, context, prose, scene_id, major_characters
        )
    """

    def __init__(self) -> None:
        self.last_usage: dict | None = None

    async def generate(
        self,
        provider: LLMProvider,
        context: dict,
        prose: str,
        scene_id: str,
        major_characters: list[dict],
    ) -> list[StateChangeProposal]:
        """Run the state updater and return validated proposals."""
        class ChangeList(BaseModel):
            changes: list[StateChangeProposal] = Field(default_factory=list)

        messages = _build_state_updater_messages(context, prose, major_characters)
        resp: ProviderResponse = await provider.generate_structured(
            messages, ChangeList, temperature=0.2
        )
        self.last_usage = resp.usage
        if resp.model is not None and isinstance(resp.model, ChangeList):
            return resp.model.changes
        parsed = resp.parsed or {}
        items = parsed.get("changes", [])
        return [StateChangeProposal(**item) for item in items]

    def build_prompt(
        self, context: dict, prose: str, major_characters: list[dict]
    ) -> str:
        """Return the user-facing prompt string for inspection."""
        return _build_state_updater_prompt(context, prose, major_characters)


def _build_state_updater_messages(
    context: dict,
    prose: str,
    major_characters: list[dict],
) -> list[dict[str, str]]:
    system = (
        "你是一位角色状态追踪员。"
        "你的任务是根据场景正文，推理每个主要角色在本场景结束后的状态变化。"
        "只报告发生了变化的字段；没有变化的字段留空。"
        "你必须输出严格的 JSON 格式。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _build_state_updater_prompt(context, prose, major_characters)},
    ]


def _build_state_updater_prompt(
    context: dict,
    prose: str,
    major_characters: list[dict],
) -> str:
    lines: list[str] = []

    # Current character states (pre-scene)
    lines.append("【角色当前状态（场景前）】")
    for mc in major_characters:
        core = mc.get("core", {})
        state = mc.get("state", {})
        name = core.get("name", "")
        cid = core.get("id", "")
        lines.append(f"\n★ {name} (id={cid})")
        lines.append(f"  情绪：{state.get('current_emotion', '')}")
        lines.append(f"  目标：{state.get('current_goal', '')}")
        lines.append(f"  位置：{state.get('current_location', '')}")
        rels = state.get("current_relationships", {})
        if rels:
            lines.append(f"  关系：{'；'.join(f'{k}:{v}' for k, v in rels.items())}")
        knowledge = state.get("current_knowledge", [])
        if knowledge:
            lines.append(f"  已知：{'；'.join(knowledge[:10])}")
        secrets = state.get("current_secrets", [])
        if secrets:
            lines.append(f"  秘密：{'；'.join(secrets)}")
        lines.append(f"  状态：{state.get('current_status', '')}")
    lines.append("")

    # Scene plan for context
    scene = context.get("scene_info", {})
    if scene:
        lines.append("【场景信息】")
        lines.append(f"- 标题：{scene.get('scene_title', '')}")
        if scene.get("scene_goal"):
            lines.append(f"- 目标：{scene['scene_goal']}")
        if scene.get("conflict"):
            lines.append(f"- 冲突：{scene['conflict']}")
        lines.append("")

    # Prose
    prose_excerpt = prose[:5000] if len(prose) > 5000 else prose
    lines.append("【场景正文】")
    lines.append(prose_excerpt)
    if len(prose) > 5000:
        lines.append(f"\n... (正文共 {len(prose)} 字，以上为前 5000 字)")
    lines.append("")

    lines.append("【输出要求】")
    lines.append("为每个主要角色输出一条 StateChangeProposal，只填写实际发生变化的字段：")
    lines.append("- character_id: 角色的 id")
    lines.append("- character_name: 角色名")
    lines.append("- emotion: 场景结束后的新情绪（没变化则留空）")
    lines.append("- goal: 场景结束后的新目标（没变化则留空）")
    lines.append("- location: 场景结束后的新位置（没变化则留空）")
    lines.append("- relationships_add: 新增或变化的关系（dict，角色名→关系描述）")
    lines.append("- relationships_remove: 不再有效的关系角色名列表")
    lines.append("- knowledge_add: 本场景中该角色新获得的信息")
    lines.append("- secrets_add: 本场景中该角色新发现的秘密")
    lines.append("- status: 新状态描述（如受伤/突破/昏迷等，没变化则留空）")
    lines.append("")
    lines.append('输出 JSON 格式：{"changes": [...]}')
    lines.append('如果所有角色都没有状态变化，输出 {"changes": []}')

    return "\n".join(lines)
