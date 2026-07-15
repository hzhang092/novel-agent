"""StateUpdaterAgent — proposes CharacterState changes after a scene.

Now outputs the new discriminated union format: a list of typed StateChange items
in the "changes" field instead of flat scalar fields.
"""

from __future__ import annotations

from app.providers.base import LLMProvider, ProviderResponse
from app.pipeline.agents._prose import select_prose_excerpt
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
        from pydantic import BaseModel, Field
        from app.storage.models import StateChange

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
        return [StateChangeProposal.model_validate(item) for item in items]

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
        "只有发生了变化的字段才需要报告，未变化的字段不要输出。"
        "每个变化必须使用 type 字段标注类型："
        "set_field（修改标量字段）、relationship_change（关系变化）、"
        "knowledge_add（获得新知识）、knowledge_remove（遗忘知识）、"
        "secret_add（发现新秘密）、secret_remove（秘密不再有效）。"
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
        lines.append(f"  实力：{state.get('current_power_level', '')}")
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

    lines.append("【场景正文】")
    lines.append(select_prose_excerpt(prose))
    lines.append("")

    lines.append("【输出要求】")
    lines.append("为每个主要角色输出一条 StateChangeProposal，在 changes 数组中列出所有状态变化：")
    lines.append("")
    lines.append("变化类型（type 字段）：")
    lines.append("- set_field: 修改标量状态字段。field 可选值: emotion, goal, location, status, power_level")
    lines.append("  例: {\"type\": \"set_field\", \"field\": \"emotion\", \"value\": \"愤怒\"}")
    lines.append("- relationship_change: 与其他角色的关系发生变化")
    lines.append("  例: {\"type\": \"relationship_change\", \"target_character_id\": \"char-bob\", \"relationship\": \"死敌\"}")
    lines.append("- knowledge_add: 角色新得知了某个信息")
    lines.append("  例: {\"type\": \"knowledge_add\", \"fact\": \"知道了宝藏的秘密\"}")
    lines.append("- knowledge_remove: 角色遗忘/不再关心某个信息")
    lines.append("  例: {\"type\": \"knowledge_remove\", \"fact\": \"旧信息\"}")
    lines.append("- secret_add: 角色发现了新秘密")
    lines.append("  例: {\"type\": \"secret_add\", \"fact\": \"师父的真实身份\"}")
    lines.append("- secret_remove: 某个秘密已不再有效")
    lines.append("  例: {\"type\": \"secret_remove\", \"fact\": \"已揭露的秘密\"}")
    lines.append("")
    lines.append("每条 Proposal 格式：")
    lines.append("{")
    lines.append('  "character_id": "角色ID",')
    lines.append('  "character_name": "角色名",')
    lines.append('  "changes": [')
    lines.append('    {\"type\": \"...\", ...},')
    lines.append('    ...')
    lines.append('  ]')
    lines.append("}")
    lines.append("")
    lines.append('整个输出为 JSON 格式：{"changes": [...]}')
    lines.append('如果所有角色都没有状态变化，输出 {"changes": []}')

    return "\n".join(lines)
