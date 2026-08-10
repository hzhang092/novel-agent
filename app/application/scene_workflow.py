"""Project-scoped scene generation lifecycle."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.application.errors import OperationBlockedError
from app.storage.models import ChapterLength, ChapterOutline, Project, ScenePlan, ScenePlanPatch


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
    length_warning: Callable[[str], None] = lambda _warning: None
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
    approved_plan: ScenePlan | None = None
    active: bool = False


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
        self._acquired_task: asyncio.Task | None = None
        self._plan_future: asyncio.Future[tuple[bool, dict | None]] | None = None
        self._observer = SceneWorkflowObserver()
        self._pipeline: Any = None
        self._result: Any = None
        self._approved_plan: ScenePlan | None = None
        self._instruction = ""
        self._target_characters: int | None = None
        self._providers: list[Any] = []
        self._source_revisions: dict[str, dict] = {}
        self._source_context_fingerprint = ""
        self._provider_loader = provider_loader or _load_generation_providers
        self._pipeline_factory = pipeline_factory or _new_pipeline

    @property
    def task(self) -> asyncio.Task | None:
        return self._task

    @property
    def waiting_for_plan(self) -> bool:
        return self._plan_future is not None and not self._plan_future.done()

    def remember_active_chapter(self, chapter_id: str) -> None:
        _remember_active_chapter(self.project_dir, chapter_id)

    def start(
        self,
        scene_id: str,
        chapter_id: str,
        observer: SceneWorkflowObserver,
        *,
        approved_plan: ScenePlan | dict | None = None,
        instruction: str = "",
        plan_patch: ScenePlanPatch | dict | None = None,
        target_characters: int | None = None,
    ) -> None:
        if prose_instruction_requires_plan_patch(instruction) and plan_patch is None:
            raise OperationBlockedError("该修改会改变事件、角色或钩子，请先提交计划补丁")
        if plan_patch is not None and approved_plan is None:
            raise OperationBlockedError("计划补丁需要基于已批准的章节计划")
        if plan_patch is not None:
            approved_plan = _apply_plan_patch(approved_plan, plan_patch)
        _remember_active_chapter(self.project_dir, chapter_id)
        if not self.run_guard.acquire("scene_workflow"):
            raise OperationBlockedError("Another project generation is already active")
        self.state = SceneWorkflowState(
            scene_id=scene_id,
            chapter_id=chapter_id,
            approved_plan=ScenePlan.model_validate(approved_plan) if approved_plan is not None else None,
            active=True,
        )
        self._approved_plan = self.state.approved_plan
        self._instruction = instruction
        self._target_characters = target_characters
        self._source_revisions = {}
        self._source_context_fingerprint = ""
        self._observer = observer
        self._pipeline = self._pipeline_factory()
        self._observer.generating(True)
        self._observer.status("正在组装上下文...")
        self._acquired_task = None
        self._task = asyncio.ensure_future(self._run())
        self._task.add_done_callback(self._finish_cancelled_task)

    def approve_plan(self, plan: dict[str, Any]) -> None:
        if self._plan_future is not None and not self._plan_future.done():
            self.state.planner_decision = plan
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

    def restore_draft(self, record: Any, chapter_id: str) -> None:
        """Restore a saved draft's review/publication state without starting a run."""
        if self.state.active:
            return
        from app.pipeline.pipeline import GenerationResult
        from app.storage.models import CharacterIntent, ReviewResult

        plan = ScenePlan.model_validate(record.scene_plan) if record.scene_plan else None
        trace = [_trace_entry_from_dict(item) for item in record.generation_trace]
        self.state = SceneWorkflowState(
            scene_id=record.scene_id,
            chapter_id=chapter_id,
            artifacts=trace,
            draft_record=record,
            selected_revision=record.revision_id,
            memory_facts=list(record.extracted_facts_raw),
            memory_changes=list(record.state_changes_raw),
            approved_plan=plan,
        )
        self._approved_plan = plan
        self._pipeline = self._pipeline_factory()
        self._result = GenerationResult(
            scene_id=record.scene_id,
            plan=plan,
            character_intents={
                name: CharacterIntent.model_validate(value)
                for name, value in record.character_intents.items()
            },
            prose=record.draft_text,
            review=ReviewResult.model_validate(record.review) if record.review else None,
            trace=trace,
            generated_with=record.generated_with,
            source_context_fingerprint=record.source_context_fingerprint,
        )

    def set_memory_selections(self, facts: list[dict], changes: list[dict]) -> None:
        self.state.memory_facts = facts
        self.state.memory_changes = changes

    def cancel(self) -> None:
        for provider in self._providers:
            cancel = getattr(provider, "cancel", None)
            if cancel is None:
                continue
            try:
                result = cancel()
                if inspect.isawaitable(result):
                    asyncio.ensure_future(result)
            except Exception:
                pass
        if self._task is not None and not self._task.done():
            self._task.cancel()
        elif self._task is None:
            self._finish("已取消")

    def retry(self) -> None:
        if (
            self.state.active
            or (self._task is not None and not self._task.done())
            or not self.state.scene_id
            or not self.state.chapter_id
        ):
            raise OperationBlockedError("No finished scene run is available to retry")
        self.start(self.state.scene_id, self.state.chapter_id, self._observer)

    def regenerate(
        self,
        scene_id: str,
        source_record: Any,
        observer: SceneWorkflowObserver,
        *,
        instruction: str = "",
        plan_patch: ScenePlanPatch | dict | None = None,
        target_characters: int | None = None,
    ) -> None:
        if not source_record.scene_plan:
            raise OperationBlockedError("没有已批准的章节计划，无法安全再生成")
        if self.state.active:
            raise OperationBlockedError("Another scene generation is already active")
        plan = ScenePlan.model_validate(source_record.scene_plan)
        if plan_patch is not None:
            patch = ScenePlanPatch.model_validate(plan_patch)
            if patch.base_revision_id and patch.base_revision_id != source_record.revision_id:
                raise OperationBlockedError("计划补丁基于过期草稿")
            plan = patch.apply(plan)
        self.start(
            scene_id,
            _chapter_for_scene(self.project_dir, scene_id) or "",
            observer,
            approved_plan=plan,
            instruction=instruction,
            plan_patch=ScenePlanPatch() if plan_patch is not None else None,
            target_characters=target_characters,
        )

    async def continue_review(
        self, observer: SceneWorkflowObserver | None = None
    ) -> None:
        self._require_idle_task()
        if self._pipeline is None or self._result is None or self.state.draft_record is None:
            return
        self._acquire_run(observer, "正在继续审查...")
        try:
            self.state.draft_record.review_overridden = True
            from app.storage.project_files import save_scene_generation_record

            save_scene_generation_record(self.project_dir, self.state.draft_record)
            await self._analyze_draft()
        finally:
            self._release_run()

    async def save_edited_draft(
        self,
        prose: str,
        source_record: Any,
        observer: SceneWorkflowObserver,
        *,
        analyze: bool = True,
    ) -> Any:
        from app.pipeline.pipeline import GenerationResult
        from app.storage.models import CharacterIntent, ScenePlan
        scene_id = source_record.scene_id
        chapter_id = _chapter_for_scene(self.project_dir, scene_id)
        if not chapter_id:
            raise OperationBlockedError("The scene has no chapter")
        self._acquire_run(
            observer,
            "正在保存并重新审查修改..." if analyze else "正在保存修改...",
        )
        self.state = SceneWorkflowState(
            scene_id=scene_id,
            chapter_id=chapter_id,
            active=True,
        )
        try:
            self._observer = observer
            self._pipeline = self._pipeline_factory()
            self._result = GenerationResult(
                scene_id=scene_id, prose=prose,
                plan=ScenePlan.model_validate(source_record.scene_plan) if source_record.scene_plan else None,
                character_intents={name: CharacterIntent.model_validate(value) for name, value in source_record.character_intents.items()},
                generated_with=source_record.generated_with,
            )
            self.state.scene_id = scene_id
            self.state.chapter_id = chapter_id
            record = self._save_draft(self._result)
            record.review_overridden = analyze
            self.state.draft_record = record
            self.state.selected_revision = record.revision_id
            self._observer.draft(record)
            if analyze:
                try:
                    await self._analyze_draft()
                finally:
                    self._release_run()
            else:
                self._finish("草稿已保存")
            return record
        except BaseException:
            if self.state.active:
                self._finish("")
            raise

    def recover_writer_draft(self, scene_id: str, chapter_id: str, prose: str) -> Any:
        """Promote a crash-recovery buffer through the normal draft store."""
        from app.pipeline.pipeline import GenerationResult
        from app.storage.project_files import (
            discard_scene_writer_draft,
            list_scene_prose_versions,
            load_scene_generation_record,
            load_scene_prose_version,
        )

        if self.state.active:
            if self.state.scene_id != scene_id:
                raise OperationBlockedError("Another scene generation is already active")
            return self.state.draft_record
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
        self,
        scene_id: str,
        revision_id: str | None = None,
        facts: list[dict] | None = None,
        changes: list[dict] | None = None,
    ) -> None:
        from app.storage.timeline_repository import publish_scene_revision

        revision_id = revision_id or self.state.selected_revision
        if not revision_id:
            raise OperationBlockedError("请先选择要发布的草稿修订")
        from app.storage.project_files import load_scene_generation_record

        record = load_scene_generation_record(
            self.project_dir, scene_id, revision_id=revision_id
        )
        if (
            record is not None
            and record.stale_input
            and not record.stale_input_reviewed
        ):
            raise OperationBlockedError("该草稿基于旧设定，请先复核后继续或重新生成")
        publish_scene_revision(
            self.project_dir,
            scene_id,
            revision_id,
            facts if facts is not None else self.state.memory_facts,
            changes if changes is not None else self.state.memory_changes,
            self.event_bus,
        )
        self._finish("已发布")

    async def continue_stale(
        self,
        revision_id: str | None = None,
        observer: SceneWorkflowObserver | None = None,
    ) -> Any:
        from app.storage.project_files import load_scene_generation_record, save_scene_generation_record

        self._require_idle_task()
        revision_id = revision_id or self.state.selected_revision
        if not revision_id or not self.state.scene_id:
            raise OperationBlockedError("请先选择过期草稿")
        record = load_scene_generation_record(
            self.project_dir, self.state.scene_id, revision_id=revision_id
        )
        if record is None or not record.stale_input or record.stale_input_reviewed:
            raise OperationBlockedError("该草稿不是过期草稿")
        needs_analysis = (record.review or {}).get("overall_pass", False)
        if needs_analysis:
            self._acquire_run(observer, "正在复核旧设定...")
        elif self.state.active:
            raise OperationBlockedError("Another scene generation is already active")
        try:
            record.stale_input_reviewed = True
            save_scene_generation_record(self.project_dir, record)
            self.state.selected_revision = record.revision_id
            self.state.draft_record = record
            if needs_analysis:
                try:
                    await self._analyze_draft()
                finally:
                    self._release_run()
            return record
        except BaseException:
            if self.state.active:
                self._finish("复核失败")
            raise

    async def _run(self) -> None:
        providers: list[Any] = []
        release_after_close = False
        finish_after_close: str | None = None
        try:
            planner, characters, writer, reviewer = self._provider_loader()
            providers = [planner, characters, writer, reviewer]
            self._providers = providers
            if self._target_characters:
                from app.pipeline.agents.writer import provider_target_warning

                warning = provider_target_warning(writer, self._target_characters)
                if warning:
                    self._observer.length_warning(warning)
            async for token, result in self._pipeline.generate_stream(
                self.project_dir,
                self.state.scene_id,
                planner,
                characters,
                writer,
                reviewer,
                on_trace=self._trace,
                on_plan_ready=self._wait_for_plan,
                approved_plan=self._approved_plan,
                revision_instruction=self._instruction,
                target_characters=self._target_characters,
            ):
                if token is not None:
                    self._result = getattr(
                        self._pipeline, "partial_result", self._result
                    )
                    self._source_revisions = getattr(
                        self._pipeline, "source_revisions", self._source_revisions
                    ) or self._source_revisions
                    self._source_context_fingerprint = getattr(
                        self._pipeline,
                        "source_context_fingerprint",
                        self._source_context_fingerprint,
                    ) or self._source_context_fingerprint
                    self.state.partial_prose += token
                    self._observer.prose(token)
                if result is not None:
                    self._result = result
                    self._source_revisions = getattr(result, "generated_with", {}) or {}
                    self._source_context_fingerprint = getattr(
                        result, "source_context_fingerprint", ""
                    )
                    if not result.prose:
                        finish_after_close = "生成失败"
                        return
                    record = self._save_draft(result)
                    self.state.draft_record = record
                    self.state.selected_revision = record.revision_id
                    self._observer.draft(record)
                    if result.review is not None and not record.stale_input:
                        self._observer.review(result.review.overall_pass, result.review.summary)
                    if record.stale_input:
                        self._observer.status("基于旧设定，请复核后继续或重新生成")
                    elif result.review is not None and result.review.overall_pass:
                        await self._analyze_draft()
                    else:
                        self._observer.status("草稿已保存")
                    release_after_close = True
                    return
            finish_after_close = "生成失败"
        except asyncio.CancelledError:
            result = self._result or getattr(self._pipeline, "partial_result", None)
            completed_artifacts = bool(
                result
                and (
                    result.plan
                    or result.character_intents
                    or any(item.status == "completed" for item in result.trace)
                )
            )
            if (
                self.state.draft_record is None
                and (self.state.partial_prose or completed_artifacts)
            ):
                from app.pipeline.pipeline import GenerationResult

                result = result or GenerationResult(
                    scene_id=self.state.scene_id or "",
                    plan=self._approved_plan,
                )
                if not result.trace:
                    result.trace = [
                        item
                        for item in self.state.artifacts
                        if hasattr(item, "agent_name")
                    ]
                result.prose = self.state.partial_prose
                result.generated_with = (
                    getattr(self._pipeline, "source_revisions", {})
                    or self._source_revisions
                )
                result.source_context_fingerprint = (
                    getattr(self._pipeline, "source_context_fingerprint", "")
                    or self._source_context_fingerprint
                )
                record = self._save_draft(result, cancelled=True)
                self.state.draft_record = record
                self.state.selected_revision = record.revision_id
                self._observer.draft(record)
            raise
        except Exception as error:
            self._observer.error(error)
            finish_after_close = "生成失败"
        finally:
            self._providers = []
            for provider in providers:
                try:
                    await provider.close()
                except Exception:
                    pass
            if finish_after_close is not None:
                self._finish(finish_after_close)
            elif release_after_close:
                self._release_run()

    async def _wait_for_plan(self, plan: Any) -> bool:
        self._plan_future = asyncio.get_running_loop().create_future()
        self.state.planner_decision = plan.model_dump(mode="json")
        self._observer.plan(self.state.planner_decision)
        self._observer.status("写作方案已生成，等待确认后继续…")
        try:
            approved, edited = await self._plan_future
            if approved and edited is not None:
                validated = type(plan).model_validate(edited)
                for field, value in validated.model_dump().items():
                    setattr(plan, field, value)
            if approved:
                self._observer.status("正在继续生成…")
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
            self._providers = providers
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
            self._observer.review(False, "记忆分析失败；草稿已保存，可重试")
            self._observer.status("记忆分析失败")
        finally:
            if self._providers is providers:
                self._providers = []
            for provider in providers:
                try:
                    await provider.close()
                except Exception:
                    pass

    def _save_draft(
        self, result: Any, version: int | None = None, *, cancelled: bool = False
    ) -> Any:
        from app.pipeline.agents.writer import count_chinese_characters
        from app.storage.models import SceneGenerationRecord, parse_generation_read_points
        from app.storage.project_files import discard_scene_writer_draft, save_scene_generation_record
        from app.storage.timeline_repository import find_scene_position

        chapter_id = self.state.chapter_id
        if not chapter_id:
            raise OperationBlockedError("The scene has no chapter")
        version = version or _next_version(self.project_dir, chapter_id, result.scene_id)
        _save_versioned_prose(self.project_dir, chapter_id, result.scene_id, result.prose, version)
        source_revisions = getattr(result, "generated_with", {}) or {}
        stale_input = _run_inputs_are_stale(
            self.project_dir,
            result.scene_id,
            source_revisions,
            getattr(result, "source_context_fingerprint", ""),
            self._pipeline,
        )
        points = parse_generation_read_points(getattr(result, "generated_with", {})).characters
        checkpoint = next((point.get("checkpoint_id", "") for point in points.values() if point.get("checkpoint_id")), "")
        position = find_scene_position(self.project_dir, result.scene_id)
        record = SceneGenerationRecord(
            scene_id=result.scene_id,
            source_chapter_id=chapter_id,
            revision_number=version,
            scene_order=position.scene_order if position else 0,
            generated_from_checkpoint_id=checkpoint,
            generated_with=getattr(result, "generated_with", {}),
            source_context_fingerprint=getattr(
                result, "source_context_fingerprint", ""
            ),
            status="draft",
            generation_mode="standard",
            scene_plan=result.plan.model_dump(mode="json") if result.plan else {},
            character_intents={key: value.model_dump(mode="json") for key, value in result.character_intents.items()},
            generation_trace=[asdict(item) for item in getattr(result, "trace", [])],
            draft_text=result.prose,
            review=result.review.model_dump(mode="json") if result.review else None,
            final_text="",
            extracted_facts_raw=getattr(result, "extracted_facts", []),
            state_changes_raw=getattr(result, "state_changes", []),
            target_chinese_characters=getattr(result, "target_chinese_characters", 3000),
            prose_chinese_characters=count_chinese_characters(result.prose),
            length_warning=getattr(result, "length_warning", ""),
            stale_input=stale_input,
            stale_reason="基于旧设定" if stale_input else "",
            cancelled=cancelled,
        )
        save_scene_generation_record(self.project_dir, record)
        discard_scene_writer_draft(self.project_dir, result.scene_id)
        return record

    def _finish(self, status: str) -> None:
        self._release_run()
        self._observer.status(status)

    def _release_run(self) -> None:
        self.state.active = False
        self._observer.generating(False)
        self.run_guard.release("scene_workflow")
        if (
            self._acquired_task is not None
            and self._acquired_task is asyncio.current_task()
        ):
            self._task = None
            self._acquired_task = None

    def _require_idle_task(self) -> None:
        if self._task is not None and not self._task.done():
            raise OperationBlockedError("Another scene generation is already active")

    def _acquire_run(
        self,
        observer: SceneWorkflowObserver | None = None,
        initial_status: str = "",
    ) -> None:
        self._require_idle_task()
        if self.state.active or not self.run_guard.acquire("scene_workflow"):
            raise OperationBlockedError("Another project generation is already active")
        if observer is not None:
            self._observer = observer
        self._task = asyncio.current_task()
        self._acquired_task = self._task
        self.state.active = True
        self._observer.generating(True)
        if initial_status:
            self._observer.status(initial_status)

    def _finish_cancelled_task(self, task: asyncio.Task) -> None:
        if task.cancelled():
            self._finish("已取消")
            return
        error = task.exception()
        if error is not None:
            self._observer.error(error)
            self._finish("生成失败")


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


def resolve_chapter_target(
    project: Project,
    chapter: ChapterOutline,
    override: ChapterLength | None = None,
) -> int:
    if override is not None:
        return override.resolved_target
    if chapter.chapter_length_override is not None:
        return chapter.chapter_length_override.resolved_target
    if chapter.target_word_count != 3000:
        return chapter.target_word_count
    return project.chapter_length.resolved_target


def prose_instruction_requires_plan_patch(instruction: str) -> bool:
    lowered = instruction.casefold()
    story_terms = ("事件", "情节", "角色", "人物", "钩子", "结尾", "event", "character", "hook")
    change_terms = (
        "改",
        "换",
        "新增",
        "增加",
        "删除",
        "移除",
        "杀死",
        "复活",
        "change",
        "replace",
        "add",
        "remove",
        "kill",
    )
    return any(term in lowered for term in story_terms) and any(
        term in lowered for term in change_terms
    )


def _apply_plan_patch(
    approved_plan: ScenePlan | dict,
    plan_patch: ScenePlanPatch | dict,
) -> ScenePlan:
    plan = ScenePlan.model_validate(approved_plan)
    patch = ScenePlanPatch.model_validate(plan_patch)
    if patch.base_revision_id:
        raise OperationBlockedError("计划补丁需要在具体草稿上提交")
    return patch.apply(plan)


def _remember_active_chapter(project_dir: Path, chapter_id: str) -> None:
    from app.storage.project_files import load_project, save_project

    if not (project_dir / "project.yaml").exists():
        return
    project = load_project(project_dir)
    if project.last_active_chapter_id == chapter_id:
        return
    project.last_active_chapter_id = chapter_id
    save_project(project_dir, project)


def _trace_entry_from_dict(data: dict) -> Any:
    from app.pipeline.pipeline import AgentTraceEntry

    values = dict(data)
    values["children"] = [
        _trace_entry_from_dict(item) for item in values.get("children", [])
    ]
    return AgentTraceEntry(**values)


def _run_inputs_are_stale(
    project_dir: Path,
    scene_id: str,
    source_revisions: dict[str, dict],
    source_context_fingerprint: str,
    pipeline: Any,
) -> bool:
    if not source_revisions and not source_context_fingerprint:
        return False
    assemble_context = getattr(pipeline, "assemble_context", None)
    if assemble_context is None:
        return True
    try:
        current = assemble_context(project_dir, scene_id)
    except Exception:
        return True
    if source_context_fingerprint:
        from app.pipeline.pipeline import generation_context_fingerprint

        return generation_context_fingerprint(current) != source_context_fingerprint
    current_revisions = {
        "characters": current.get("read_points", {}),
        "bible_elements": current.get("world_element_read_points", {}),
    }
    return any(
        current_revisions.get(kind, {}) != values
        for kind, values in source_revisions.items()
        if kind in current_revisions
    )


def choose_resume_chapter(project_dir: Path) -> str | None:
    from app.storage.project_files import (
        list_scene_prose_versions,
        load_all_volumes,
        load_project,
        load_scene_generation_record,
        load_scene_writer_draft,
    )

    chapters = [chapter for volume in load_all_volumes(project_dir) for chapter in volume.chapters]
    if not chapters:
        return None
    by_id = {chapter.id: chapter for chapter in chapters}
    project = load_project(project_dir)
    if project.last_active_chapter_id in by_id:
        return project.last_active_chapter_id
    for chapter in chapters:
        if chapter.needs_review:
            return chapter.id
    unwritten: list[str] = []
    for chapter in chapters:
        has_written_scene = False
        for scene in chapter.scenes:
            prose_versions = list_scene_prose_versions(project_dir, chapter.id, scene.id)
            if prose_versions:
                has_written_scene = True
            if load_scene_writer_draft(project_dir, scene.id):
                return chapter.id
            generation_versions = {
                path.name.split(".")[-3]
                for path in (project_dir / "scenes" / chapter.id).glob(f"{scene.id}.v*.gen.json")
            }
            for version in set(prose_versions) | generation_versions:
                if version == "legacy":
                    continue
                record = load_scene_generation_record(project_dir, scene.id, version=version)
                if record is not None and record.status == "draft":
                    return chapter.id
            if prose_versions:
                from app.storage.timeline_repository import get_active_scene_revision_id

                if not get_active_scene_revision_id(project_dir, scene.id):
                    return chapter.id
        if chapter.scenes and not has_written_scene:
            unwritten.append(chapter.id)
    if unwritten:
        return unwritten[0]
    return chapters[0].id


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
