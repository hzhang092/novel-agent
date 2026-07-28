"""Project-scoped scene generation lifecycle."""

from __future__ import annotations

import asyncio
import gc
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.application.errors import OperationBlockedError


class ProjectRunGuard:
    """One non-waiting generation lease for a project."""

    def __init__(self) -> None:
        self._owner: str | None = None

    @property
    def active_owner(self) -> str | None:
        return self._owner

    def acquire(self, owner: str) -> bool:
        if self._owner is not None:
            return False
        self._owner = owner
        return True

    def release(self, owner: str) -> None:
        if self._owner == owner:
            self._owner = None


@dataclass
class SceneWorkflowObserver:
    """Concrete rendering callbacks supplied by a Qt presentation."""

    trace: Callable[[list], None] = lambda _trace: None
    prose: Callable[[str], None] = lambda _text: None
    plan: Callable[[dict], None] = lambda _plan: None
    status: Callable[[str], None] = lambda _status: None
    generating: Callable[[bool], None] = lambda _value: None
    review: Callable[[bool, str], None] = lambda _passed, _summary: None
    draft: Callable[[Any], None] = lambda _record: None
    memory: Callable[[str, str, list[dict], list[dict]], None] = (
        lambda _scene, _revision, _facts, _changes: None
    )
    error: Callable[[Exception], None] = lambda _error: None


@dataclass
class SceneWorkflowState:
    scene_id: str | None = None
    chapter_id: str | None = None
    planner_decision: dict[str, Any] | None = None
    artifacts: list[Any] = field(default_factory=list)
    partial_prose: str = ""
    draft_record: Any = None
    selected_revision: str | None = None
    memory_facts: list[dict] = field(default_factory=list)
    memory_changes: list[dict] = field(default_factory=list)
    active: bool = False
    source_revisions: dict[str, Any] = field(default_factory=dict)


class SceneWorkflow:
    """One project run, draft, review, and publication lifecycle."""

    def __init__(
        self,
        project_dir: Path,
        *,
        event_bus: object | None = None,
        provider_loader: Callable[[], tuple[Any, Any, Any, Any]] | None = None,
        pipeline_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.event_bus = event_bus
        self.run_guard = ProjectRunGuard()
        self.state = SceneWorkflowState()
        self._task: asyncio.Task | None = None
        self._plan_future: asyncio.Future[tuple[bool, dict | None]] | None = None
        self._observer = SceneWorkflowObserver()
        self._pipeline: Any = None
        self._result: Any = None
        self._provider_loader = provider_loader or _load_generation_providers
        self._pipeline_factory = pipeline_factory or _new_pipeline

    @property
    def task(self) -> asyncio.Task | None:
        return self._task

    def start(
        self,
        scene_id: str,
        chapter_id: str,
        observer: SceneWorkflowObserver | None = None,
    ) -> None:
        if not self.run_guard.acquire("scene_workflow"):
            raise OperationBlockedError("Another project generation is already active")
        self.state = SceneWorkflowState(scene_id=scene_id, chapter_id=chapter_id, active=True)
        if observer is None:
            return
        self._observer = observer
        self._pipeline = self._pipeline_factory()
        self._observer.generating(True)
        self._observer.status("正在组装上下文...")
        self._task = asyncio.ensure_future(self._run())

    def approve_plan(self, plan: dict[str, Any]) -> None:
        self.state.planner_decision = plan
        if self._plan_future is not None and not self._plan_future.done():
            self._plan_future.set_result((True, plan))

    def receive_plan(self, plan: dict[str, Any]) -> None:
        self.state.planner_decision = plan

    def append_prose(self, text: str) -> None:
        self.state.partial_prose += text

    def save_draft(self, record: Any) -> None:
        self.state.draft_record = record
        self.state.selected_revision = getattr(record, "revision_id", None)

    def finish(self) -> None:
        self._finish("")

    def reject_plan(self) -> None:
        if self._plan_future is not None and not self._plan_future.done():
            self._plan_future.set_result((False, None))

    def select_revision(self, revision_id: str) -> None:
        self.state.selected_revision = revision_id

    def set_memory_selections(self, facts: list[dict], changes: list[dict]) -> None:
        self.state.memory_facts = facts
        self.state.memory_changes = changes

    def cancel(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._finish("已取消")

    def retry(self) -> None:
        if self.state.active or not self.state.scene_id or not self.state.chapter_id:
            raise OperationBlockedError("No finished scene run is available to retry")
        self.start(self.state.scene_id, self.state.chapter_id, self._observer)

    async def continue_review(self) -> None:
        if self._pipeline is None or self._result is None or self.state.draft_record is None:
            return
        self.state.draft_record.review_overridden = True
        from app.storage.project_files import save_scene_generation_record

        save_scene_generation_record(self.project_dir, self.state.draft_record)
        await self._analyze_draft()

    async def save_edited_draft(self, prose: str, source_record: Any) -> Any:
        from app.pipeline.pipeline import GenerationResult
        from app.storage.models import CharacterIntent, ScenePlan
        self._pipeline = self._pipeline_factory()
        self._result = GenerationResult(
            scene_id=source_record.scene_id, prose=prose,
            plan=ScenePlan.model_validate(source_record.scene_plan) if source_record.scene_plan else None,
            character_intents={name: CharacterIntent.model_validate(value) for name, value in source_record.character_intents.items()},
            generated_with=source_record.generated_with,
        )
        self.state.scene_id = source_record.scene_id
        self.state.chapter_id = self.state.chapter_id or _chapter_for_scene(self.project_dir, source_record.scene_id)
        record = self._save_draft(self._result)
        record.review_overridden = True
        self.state.draft_record = record
        await self._analyze_draft()
        return record

    def recover_writer_draft(self, scene_id: str, chapter_id: str, prose: str) -> Any:
        """Promote a crash-recovery buffer through the normal draft store."""
        from app.pipeline.pipeline import GenerationResult
        from app.storage.project_files import (
            discard_scene_writer_draft,
            list_scene_prose_versions,
            load_scene_generation_record,
            load_scene_prose_version,
        )

        self.state.scene_id, self.state.chapter_id = scene_id, chapter_id
        for version_name in list_scene_prose_versions(self.project_dir, chapter_id, scene_id):
            if not version_name.startswith("v"):
                continue
            try:
                record = load_scene_generation_record(
                    self.project_dir, scene_id, version=version_name
                )
            except ValueError:
                record = None
            if record is not None and record.status == "draft" and record.draft_text == prose:
                discard_scene_writer_draft(self.project_dir, scene_id)
                self.save_draft(record)
                return record
            if record is None and load_scene_prose_version(
                self.project_dir, chapter_id, scene_id, version_name
            ) == prose:
                record = self._save_draft(
                    GenerationResult(scene_id=scene_id, prose=prose),
                    version=int(version_name[1:]),
                )
                self.save_draft(record)
                return record
        record = self._save_draft(GenerationResult(scene_id=scene_id, prose=prose))
        self.save_draft(record)
        return record

    def publish(
        self, scene_id: str, revision_id: str, facts: list[dict], changes: list[dict]
    ) -> None:
        from app.storage.timeline_repository import publish_scene_revision

        publish_scene_revision(
            self.project_dir, scene_id, revision_id, facts, changes, self.event_bus
        )
        self._finish("已发布")

    async def _run(self) -> None:
        providers: list[Any] = []
        try:
            planner, characters, writer, reviewer = self._provider_loader()
            providers = [planner, characters, writer, reviewer]
            async for token, result in self._pipeline.generate_stream(
                self.project_dir,
                self.state.scene_id,
                planner,
                characters,
                writer,
                reviewer,
                on_trace=self._trace,
                on_plan_ready=self._wait_for_plan,
            ):
                if token is not None:
                    self.state.partial_prose += token
                    self._observer.prose(token)
                if result is not None:
                    self._result = result
                    self.state.artifacts.append(result)
                    if not result.prose:
                        self._finish("生成失败")
                        return
                    record = self._save_draft(result)
                    self.state.draft_record = record
                    self.state.selected_revision = record.revision_id
                    self._observer.draft(record)
                    if result.review is not None:
                        self._observer.review(result.review.overall_pass, result.review.summary)
                    if result.review is not None and result.review.overall_pass:
                        await self._analyze_draft()
                    else:
                        self._observer.status("草稿已保存")
                    return
        except asyncio.CancelledError:
            self._finish("已取消")
            raise
        except Exception as error:
            self._observer.error(error)
            self._finish("生成失败")
        finally:
            for provider in providers:
                try:
                    await provider.close()
                except Exception:
                    pass
            gc.collect()

    async def _wait_for_plan(self, plan: Any) -> bool:
        self._plan_future = asyncio.get_running_loop().create_future()
        self._observer.plan(plan.model_dump(mode="json"))
        try:
            approved, edited = await self._plan_future
            if approved and edited is not None:
                validated = type(plan).model_validate(edited)
                for field, value in validated.model_dump().items():
                    setattr(plan, field, value)
            return approved
        finally:
            self._plan_future = None

    def _trace(self, trace: list) -> None:
        self.state.artifacts = list(trace)
        self._observer.trace(trace)

    async def _analyze_draft(self) -> None:
        providers: list[Any] = []
        try:
            from app.providers.config import get_provider_for_step, load_provider_config
            from app.storage.project_files import save_scene_generation_record

            config = load_provider_config()
            fact_provider = get_provider_for_step("fact_extractor", config)
            state_provider = get_provider_for_step("state_updater", config)
            providers = [fact_provider, state_provider]
            await self._pipeline.analyze_draft(
                self.project_dir,
                self._result,
                fact_provider=fact_provider,
                state_provider=state_provider,
                review_overridden=self.state.draft_record.review_overridden,
                on_trace=self._trace,
            )
            record = self.state.draft_record
            record.extracted_facts_raw = self._result.extracted_facts
            record.state_changes_raw = self._result.state_changes
            record.scene_summary_raw = self._result.scene_summary
            save_scene_generation_record(self.project_dir, record)
            self.state.memory_facts = self._result.extracted_facts
            self.state.memory_changes = self._result.state_changes
            self._observer.memory(
                self._result.scene_id,
                record.revision_id,
                self.state.memory_facts,
                self.state.memory_changes,
            )
            self._observer.status("等待发布")
        except Exception as error:
            self._observer.error(error)
            self._observer.status("记忆分析失败")
        finally:
            for provider in providers:
                try:
                    await provider.close()
                except Exception:
                    pass

    def _save_draft(self, result: Any, version: int | None = None) -> Any:
        from app.storage.models import SceneGenerationRecord, parse_generation_read_points
        from app.storage.project_files import discard_scene_writer_draft, save_scene_generation_record
        from app.storage.timeline_repository import find_scene_position

        chapter_id = self.state.chapter_id
        if not chapter_id:
            raise OperationBlockedError("The scene has no chapter")
        version = version or _next_version(self.project_dir, chapter_id, result.scene_id)
        _save_versioned_prose(self.project_dir, chapter_id, result.scene_id, result.prose, version)
        points = parse_generation_read_points(getattr(result, "generated_with", {})).characters
        checkpoint = next((point.get("checkpoint_id", "") for point in points.values() if point.get("checkpoint_id")), "")
        position = find_scene_position(self.project_dir, result.scene_id)
        record = SceneGenerationRecord(
            scene_id=result.scene_id,
            revision_number=version,
            scene_order=position.scene_order if position else 0,
            generated_from_checkpoint_id=checkpoint,
            generated_with=getattr(result, "generated_with", {}),
            status="draft",
            generation_mode="standard",
            scene_plan=result.plan.model_dump(mode="json") if result.plan else {},
            character_intents={key: value.model_dump(mode="json") for key, value in result.character_intents.items()},
            draft_text=result.prose,
            review=result.review.model_dump(mode="json") if result.review else None,
            final_text="",
            extracted_facts_raw=getattr(result, "extracted_facts", []),
            state_changes_raw=getattr(result, "state_changes", []),
        )
        save_scene_generation_record(self.project_dir, record)
        discard_scene_writer_draft(self.project_dir, result.scene_id)
        return record

    def _finish(self, status: str) -> None:
        self.state.active = False
        self._observer.generating(False)
        self._observer.status(status)
        self.run_guard.release("scene_workflow")


def _load_generation_providers() -> tuple[Any, Any, Any, Any]:
    from app.providers.config import get_provider_for_step, load_provider_config

    config = load_provider_config()
    return tuple(get_provider_for_step(step, config) for step in ("planner", "characters", "writer", "reviewer"))


def _new_pipeline() -> Any:
    from app.pipeline.pipeline import ScenePipeline

    return ScenePipeline()


def _next_version(project_dir: Path, chapter_id: str, scene_id: str) -> int:
    from app.storage.project_files import list_scene_prose_versions

    versions = list_scene_prose_versions(project_dir, chapter_id, scene_id)
    return max((int(value[1:]) for value in versions if value.startswith("v") and value[1:].isdigit()), default=0) + 1


def _chapter_for_scene(project_dir: Path, scene_id: str) -> str | None:
    from app.storage.project_files import load_all_volumes
    for volume in load_all_volumes(project_dir):
        for chapter in volume.chapters:
            if any(scene.id == scene_id for scene in chapter.scenes):
                return chapter.id
    return None


def _save_versioned_prose(project_dir: Path, chapter_id: str, scene_id: str, prose: str, version: int) -> None:
    import os
    import tempfile

    target = project_dir / "scenes" / chapter_id / f"{scene_id}.v{version}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        handle.write(prose)
        temporary = Path(handle.name)
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
