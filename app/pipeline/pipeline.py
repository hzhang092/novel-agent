"""ScenePipeline — orchestrates the full five-agent scene generation pipeline.

Pipeline: Planner → Character Intents (parallel) → Writer → Reviewer.
User checkpoint after Planner before Character Intents + Writer run.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator, Callable, Awaitable

from app.pipeline.agents.character import CharacterIntentAgent
from app.pipeline.agents.planner import ScenePlannerAgent
from app.pipeline.agents.reviewer import ReviewerAgent
from app.pipeline.agents.fact_extractor import FactExtractorAgent
from app.pipeline.agents.state_updater import StateUpdaterAgent
from app.pipeline.agents.writer import WriterAgent
from app.pipeline.context_builder import RetrievalEngine
from app.providers.base import LLMProvider
from app.pipeline.token_tracker import TokenTracker
from app.storage.models import (
    CharacterIntent,
    ReviewResult,
    ScenePlan,
)


class PipelineStage(str, Enum):
    PLANNER = "planner"
    CHARACTERS = "characters"
    WRITER = "writer"
    REVIEWER = "reviewer"


@dataclass
class AgentTraceEntry:
    """Record of a single agent run for the trace panel."""
    agent_name: str
    stage: str = ""
    status: str = "pending"  # pending / running / completed / failed
    duration_ms: int = 0
    token_count: int = 0
    error_message: str = ""
    failed_prompt: str = ""  # prompt sent when the call failed (for debugging)
    failed_output: str = ""  # partial or raw output when the call failed
    children: list[AgentTraceEntry] = field(default_factory=list)


@dataclass
class GenerationResult:
    """Result of a full pipeline run."""
    scene_id: str
    plan: ScenePlan | None = None
    character_intents: dict[str, CharacterIntent] = field(default_factory=dict)
    prose: str = ""
    review: ReviewResult | None = None
    trace: list[AgentTraceEntry] = field(default_factory=list)
    total_duration_ms: int = 0
    total_tokens: int = 0
    extracted_facts: list[dict] = field(default_factory=list)
    state_changes: list[dict] = field(default_factory=list)
    generated_with: dict[str, dict] = field(default_factory=dict)


# Callback types for trace updates
TraceCallback = Callable[[list[AgentTraceEntry]], None]
PlanReadyCallback = Callable[[ScenePlan], Awaitable[bool]]  # returns True to proceed


class ScenePipeline:
    """Orchestrator for full scene generation.

    Usage::

        pipeline = ScenePipeline()

        async def on_trace(trace):
            update_ui_trace(trace)

        async def on_plan_ready(plan: ScenePlan) -> bool:
            # Show plan to user, return True if approved
            return await show_plan_dialog(plan)

        async for token, result in pipeline.generate_stream(
            project_dir, scene_id, planner_provider, char_provider,
            writer_provider, reviewer_provider,
            on_trace=on_trace, on_plan_ready=on_plan_ready,
        ):
            if token is not None:
                editor.append(str(token))
        # result is fully populated
    """

    def __init__(self) -> None:
        self._engine = RetrievalEngine()
        self._planner = ScenePlannerAgent()
        self._character_agent = CharacterIntentAgent()
        self._writer = WriterAgent()
        self._reviewer = ReviewerAgent()
        self._fact_extractor = FactExtractorAgent()
        self._state_updater = StateUpdaterAgent()

    def assemble_context(self, project_dir: Path, scene_id: str) -> dict:
        """Build the context dict via RetrievalEngine."""
        return self._engine.assemble(project_dir, scene_id)

    async def generate_stream(
        self,
        project_dir: Path,
        scene_id: str,
        planner_provider: LLMProvider,
        char_provider: LLMProvider,
        writer_provider: LLMProvider,
        reviewer_provider: LLMProvider,
        on_trace: TraceCallback | None = None,
        on_plan_ready: PlanReadyCallback | None = None,
        max_character_agents: int = 4,
    ) -> AsyncGenerator[tuple[str | None, GenerationResult | None], None]:
        """Run the full pipeline and stream writer tokens.

        Yields (token, None) during the writer phase,
        then a final (None, result) after completion (or early abort).
        """
        result = GenerationResult(scene_id=scene_id)
        pipeline_start = time.monotonic()
        tracker = TokenTracker.get()
        # ── Step 1: Assemble context ──
        context = self.assemble_context(project_dir, scene_id)
        result.generated_with = context.get("read_points", {})

        # ── Step 2: Planner ──
        planner_trace = AgentTraceEntry(agent_name="Scene Planner", stage="planner")
        result.trace.append(planner_trace)
        self._emit_trace(on_trace, result.trace)

        planner_trace.status = "running"
        t0 = time.monotonic()
        try:
            plan = await self._planner.generate(planner_provider, context, scene_id)
            planner_trace.status = "completed"
            planner_trace.duration_ms = int((time.monotonic() - t0) * 1000)
            if self._planner.last_usage:
                planner_trace.token_count = self._planner.last_usage.get("total_tokens", 0)
            result.plan = plan
            if self._planner.last_usage:
                tracker.log_call(
                    project_dir, scene_id, agent_name='Scene Planner',
                    provider=planner_provider.__class__.__name__.replace('Provider', '').lower(),
                    model=getattr(planner_provider, 'model', 'unknown'),
                    prompt_tokens=self._planner.last_usage.get('prompt_tokens', 0),
                    completion_tokens=self._planner.last_usage.get('completion_tokens', 0),
                    duration_ms=planner_trace.duration_ms,
                )
            self._emit_trace(on_trace, result.trace)
        except Exception as e:
            planner_trace.status = "failed"
            planner_trace.error_message = str(e)
            planner_trace.failed_prompt = self._planner.build_prompt(context)
            self._emit_trace(on_trace, result.trace)
            result.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
            yield (None, result)
            return

        # ── Step 3: User checkpoint (plan approval) ──
        if on_plan_ready is not None:
            approved = await on_plan_ready(plan)
            if not approved:
                result.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
                yield (None, result)
                return

        plan_dict = plan.model_dump(mode="json")

        # ── Step 4: Character Intent agents (parallel, major-tier only) ──
        chars = context.get("characters", {})
        major_chars = chars.get("major", [])[:max_character_agents]

        char_trace = AgentTraceEntry(
            agent_name=f"Characters ({len(major_chars)})", stage="characters"
        )
        result.trace.append(char_trace)

        if major_chars:
            char_trace.status = "running"
            self._emit_trace(on_trace, result.trace)

            async def _run_char_intent(mc: dict) -> tuple[str, CharacterIntent | None, int, str]:
                name = mc["core"]["name"]
                t0_c = time.monotonic()
                try:
                    intent = await self._character_agent.generate(
                        char_provider, context, plan_dict,
                        mc.get("core", {}), mc.get("state", {}),
                    )
                    dur = int((time.monotonic() - t0_c) * 1000)
                    tokens = self._character_agent.last_usage.get("total_tokens", 0) if self._character_agent.last_usage else 0
                    return (name, intent, tokens, f"completed:{dur}")
                except Exception as e:
                    dur = int((time.monotonic() - t0_c) * 1000)
                    return (name, None, 0, f"failed:{dur}:{e}")

            tasks = [asyncio.create_task(_run_char_intent(mc)) for mc in major_chars]
            gathered = await asyncio.gather(*tasks, return_exceptions=True)

            for item in gathered:
                if isinstance(item, Exception):
                    child = AgentTraceEntry(
                        agent_name="CharacterIntent", stage="characters",
                        status="failed", error_message=str(item),
                    )
                    char_trace.children.append(child)
                    continue
                name, intent, tokens, status_str = item
                parts = status_str.split(":", 2)
                child_status = parts[0]
                child_dur = int(parts[1]) if len(parts) > 1 else 0
                child_err = parts[2] if len(parts) > 2 and parts[0] == "failed" else ""
                child = AgentTraceEntry(
                    agent_name=name, stage="characters",
                    status=child_status, duration_ms=child_dur,
                    token_count=tokens,
                    error_message=child_err,
                )
                char_trace.children.append(child)
                if intent is not None:
                    result.character_intents[name] = intent

            char_trace.status = "completed"
            char_trace.duration_ms = sum(
                c.duration_ms for c in char_trace.children
            )
            for child in char_trace.children:
                if child.token_count > 0:
                    tracker.log_call(
                        project_dir, scene_id,
                        agent_name=f'CharIntent: {child.agent_name}',
                        provider=char_provider.__class__.__name__.replace('Provider', '').lower(),
                        model=getattr(char_provider, 'model', 'unknown'),
                        prompt_tokens=0, completion_tokens=child.token_count,
                        duration_ms=child.duration_ms,
                    )
        else:
            char_trace.status = "completed"

        self._emit_trace(on_trace, result.trace)

        # ── Step 5: Writer Agent ──
        writer_trace = AgentTraceEntry(agent_name="Writer", stage="writer")
        result.trace.append(writer_trace)

        writer_trace.status = "running"
        self._emit_trace(on_trace, result.trace)

        t_writer = time.monotonic()
        tokens_collected: list[str] = []
        try:
            enhanced_context = _enhance_context_with_plan_and_intents(
                context, plan_dict, {
                    k: v.model_dump(mode="json")
                    for k, v in result.character_intents.items()
                }
            )
            async for token in self._writer.generate_stream(writer_provider, enhanced_context):
                tokens_collected.append(token)
                yield (token, None)

            writer_trace.status = "completed"
            writer_trace.duration_ms = int((time.monotonic() - t_writer) * 1000)
            writer_trace.token_count = len(tokens_collected)
            result.prose = "".join(tokens_collected)
        except Exception as e:
            writer_trace.status = "failed"
            writer_trace.error_message = str(e)
            writer_trace.failed_prompt = self._writer.build_prompt(enhanced_context)
            writer_trace.failed_output = "".join(tokens_collected)
            self._emit_trace(on_trace, result.trace)
            result.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
            yield (None, result)
            return

        self._emit_trace(on_trace, result.trace)

        # ── Step 6: Reviewer Agent ──
        reviewer_trace = AgentTraceEntry(agent_name="Reviewer", stage="reviewer")
        result.trace.append(reviewer_trace)

        reviewer_trace.status = "running"
        self._emit_trace(on_trace, result.trace)

        t_review = time.monotonic()
        try:
            review = await self._reviewer.generate(
                reviewer_provider, context, plan_dict,
                {k: v.model_dump(mode="json") for k, v in result.character_intents.items()},
                result.prose, scene_id,
            )
            reviewer_trace.status = "completed"
            reviewer_trace.duration_ms = int((time.monotonic() - t_review) * 1000)
            if self._reviewer.last_usage:
                reviewer_trace.token_count = self._reviewer.last_usage.get("total_tokens", 0)
            result.review = review
            if self._reviewer.last_usage:
                tracker.log_call(
                    project_dir, scene_id, agent_name='Reviewer',
                    provider=reviewer_provider.__class__.__name__.replace('Provider', '').lower(),
                    model=getattr(reviewer_provider, 'model', 'unknown'),
                    prompt_tokens=self._reviewer.last_usage.get('prompt_tokens', 0),
                    completion_tokens=self._reviewer.last_usage.get('completion_tokens', 0),
                    duration_ms=reviewer_trace.duration_ms,
                )
        except Exception as e:
            reviewer_trace.status = "failed"
            reviewer_trace.error_message = str(e)
            reviewer_trace.failed_prompt = self._reviewer.build_prompt(
                context, plan_dict,
                {k: v.model_dump(mode="json") for k, v in result.character_intents.items()},
                result.prose,
            )

        self._emit_trace(on_trace, result.trace)

        # ── Compute totals ──
        result.total_tokens = _count_trace_tokens(result.trace)
        result.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)

        yield (None, result)

    async def analyze_draft(
        self,
        project_dir: Path,
        result: GenerationResult,
        on_trace: TraceCallback | None = None,
        max_character_agents: int = 4,
    ) -> GenerationResult:
        """Extract memory proposals from a reviewed or explicitly overridden draft."""
        if not result.prose:
            return result
        context = self.assemble_context(project_dir, result.scene_id)
        major_chars = context.get("characters", {}).get("major", [])[:max_character_agents]
        fact_trace = AgentTraceEntry(agent_name="Fact Extractor", stage="fact_extractor", status="running")
        state_trace = AgentTraceEntry(agent_name="State Updater", stage="state_updater", status="running")
        result.trace.extend([fact_trace, state_trace])
        self._emit_trace(on_trace, result.trace)

        from app.providers.config import get_provider_for_step, load_provider_config
        config = load_provider_config()
        fact_provider = get_provider_for_step("fact_extractor", config)
        state_provider = get_provider_for_step("state_updater", config)
        started = time.monotonic()

        async def _run_facts() -> None:
            try:
                facts = await self._fact_extractor.generate(
                    fact_provider, context, result.prose, result.scene_id
                )
                result.extracted_facts = [fact.model_dump(mode="json") for fact in facts]
                fact_trace.status = "completed"
            except Exception as exc:
                fact_trace.status = "failed"
                fact_trace.error_message = str(exc)
                fact_trace.failed_prompt = self._fact_extractor.build_prompt(context, result.prose)
            finally:
                fact_trace.duration_ms = int((time.monotonic() - started) * 1000)
                if self._fact_extractor.last_usage:
                    fact_trace.token_count = self._fact_extractor.last_usage.get("total_tokens", 0)

        async def _run_state_updates() -> None:
            try:
                changes = await self._state_updater.generate(
                    state_provider, context, result.prose, result.scene_id, major_chars
                )
                result.state_changes = [change.model_dump(mode="json") for change in changes]
                state_trace.status = "completed"
            except Exception as exc:
                state_trace.status = "failed"
                state_trace.error_message = str(exc)
                state_trace.failed_prompt = self._state_updater.build_prompt(
                    context, result.prose, major_chars
                )
            finally:
                state_trace.duration_ms = int((time.monotonic() - started) * 1000)
                if self._state_updater.last_usage:
                    state_trace.token_count = self._state_updater.last_usage.get("total_tokens", 0)

        try:
            await asyncio.gather(_run_facts(), _run_state_updates())
        finally:
            await asyncio.gather(
                fact_provider.close(), state_provider.close(), return_exceptions=True
            )
        result.total_tokens = _count_trace_tokens(result.trace)
        self._emit_trace(on_trace, result.trace)
        return result

    def _emit_trace(
        self, callback: TraceCallback | None, trace: list[AgentTraceEntry]
    ) -> None:
        if callback is not None:
            callback(trace)


def _enhance_context_with_plan_and_intents(
    context: dict,
    plan: dict,
    intents: dict[str, dict],
) -> dict:
    """Create an enhanced context dict that includes the plan and character intents."""
    enhanced = dict(context)
    enhanced["scene_plan"] = plan
    enhanced["character_intents"] = intents
    return enhanced


def _count_trace_tokens(trace: list[AgentTraceEntry]) -> int:
    return sum(
        entry.token_count + sum(child.token_count for child in entry.children)
        for entry in trace
    )
