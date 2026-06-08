"""ScenePipeline — orchestrates scene generation for v1 (Writer agent only).

In later issues this will grow to Planner → Characters → Writer → Reviewer.
For Issue #7, it runs only the Writer agent as the first end-to-end test.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator

from app.pipeline.agents.writer import WriterAgent
from app.pipeline.context_builder import RetrievalEngine
from app.providers.base import LLMProvider


@dataclass
class AgentTraceEntry:
    """Record of a single agent run for the trace panel."""
    agent_name: str
    status: str = "pending"  # pending / running / completed / failed
    duration_ms: int = 0
    token_count: int = 0
    error_message: str = ""


@dataclass
class GenerationResult:
    """Result of a full pipeline run."""
    scene_id: str
    prose: str = ""
    trace: list[AgentTraceEntry] = field(default_factory=list)
    total_duration_ms: int = 0
    total_tokens: int = 0


class ScenePipeline:
    """Orchestrator for scene generation.

    Usage::

        pipeline = ScenePipeline()
        async for token, result in pipeline.generate_stream(
            project_dir, scene_id, provider
        ):
            if token:
                editor.append(token)
        # result is populated after stream completes
    """

    def __init__(self) -> None:
        self._engine = RetrievalEngine()
        self._writer = WriterAgent()

    def assemble_context(self, project_dir: Path, scene_id: str) -> dict:
        """Build the context dict via RetrievalEngine."""
        return self._engine.assemble(project_dir, scene_id)

    async def generate_stream(
        self,
        project_dir: Path,
        scene_id: str,
        provider: LLMProvider,
    ) -> AsyncGenerator[tuple[str | None, GenerationResult | None], None]:
        """Run the Writer agent and stream tokens.

        Yields tuples of (token, None) during generation,
        then a final (None, result) after completion.
        """
        result = GenerationResult(scene_id=scene_id)
        trace = AgentTraceEntry(agent_name="Writer")
        result.trace.append(trace)

        context = self.assemble_context(project_dir, scene_id)

        trace.status = "running"
        start = time.monotonic()
        tokens_collected: list[str] = []

        try:
            async for token in self._writer.generate_stream(provider, context):
                tokens_collected.append(token)
                yield (token, None)

            trace.status = "completed"
        except Exception as e:
            trace.status = "failed"
            trace.error_message = str(e)
            yield (None, result)
            return

        trace.duration_ms = int((time.monotonic() - start) * 1000)
        result.prose = "".join(tokens_collected)
        result.total_duration_ms = trace.duration_ms
        result.total_tokens = trace.token_count

        yield (None, result)
