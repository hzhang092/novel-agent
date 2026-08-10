import asyncio
from unittest.mock import AsyncMock

import pytest

from app.application.errors import OperationBlockedError
from app.application.scene_workflow import (
    SceneWorkflow,
    SceneWorkflowObserver,
    _run_inputs_are_stale,
)
from app.pipeline.pipeline import (
    AgentTraceEntry,
    GenerationResult,
    generation_context_fingerprint,
)
from app.providers.base import MockProvider
from app.storage.models import (
    ChapterOutline,
    Project,
    ReviewResult,
    SceneGenerationRecord,
    SceneOutline,
    ScenePlan,
    VolumeOutline,
)
from app.storage.project_files import (
    create_project,
    load_scene_generation_record,
    save_volume_outline,
)


def _project(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Story"))
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="volume-1",
            chapters=[
                ChapterOutline(
                    id="chapter-1", scenes=[SceneOutline(id="scene-1")]
                )
            ],
        ),
    )
    return project_dir


class _Provider(MockProvider):
    def __init__(self):
        super().__init__()
        self.cancel_called = False

    def cancel(self):
        self.cancel_called = True


@pytest.mark.asyncio
async def test_immediate_cancel_releases_the_project_run(tmp_path):
    project_dir = _project(tmp_path)

    class Pipeline:
        async def generate_stream(self, *_args, **_kwargs):
            await asyncio.Event().wait()
            yield None, None

    workflow = SceneWorkflow(
        project_dir,
        provider_loader=lambda: tuple(_Provider() for _ in range(4)),
        pipeline_factory=Pipeline,
    )
    workflow.start("scene-1", "chapter-1", SceneWorkflowObserver())
    workflow.cancel()

    with pytest.raises(asyncio.CancelledError):
        await workflow.task
    assert workflow.state.active is False
    assert workflow.run_guard.active_owner is None


@pytest.mark.asyncio
async def test_stale_run_records_source_and_blocks_publication_until_explicit_continue(
    tmp_path, monkeypatch
):
    project_dir = _project(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()
    initial_read_points = {
        "characters": {"hero": {"definition_revision": 1}},
        "bible_elements": {"tower": {"revision": 1}},
    }
    initial_context = {
        "read_points": initial_read_points["characters"],
        "world_element_read_points": initial_read_points["bible_elements"],
        "style_guide": {"tone": "克制"},
    }

    class Pipeline:
        def __init__(self):
            self.current_context = initial_context

        def assemble_context(self, *_args):
            return self.current_context

        async def generate_stream(self, *_args, **_kwargs):
            started.set()
            await release.wait()
            yield None, GenerationResult(
                scene_id="scene-1",
                prose="基于旧设定的正文",
                review=ReviewResult(overall_pass=True),
                generated_with=initial_read_points,
                source_context_fingerprint=generation_context_fingerprint(
                    initial_context
                ),
            )

    pipeline = Pipeline()
    providers = [_Provider() for _ in range(4)]
    workflow = SceneWorkflow(
        project_dir,
        provider_loader=lambda: tuple(providers),
        pipeline_factory=lambda: pipeline,
    )
    workflow.start("scene-1", "chapter-1", SceneWorkflowObserver())
    await started.wait()
    pipeline.current_context = {
        **initial_context,
        "style_guide": {"tone": "激烈"},
    }
    release.set()
    await workflow.task

    record = load_scene_generation_record(
        project_dir, "scene-1", revision_id=workflow.state.selected_revision
    )
    assert record.source_chapter_id == "chapter-1"
    assert record.generated_with == initial_read_points
    assert record.stale_input is True
    assert record.stale_reason == "基于旧设定"
    with pytest.raises(OperationBlockedError, match="旧设定"):
        workflow.publish("scene-1", record.revision_id)

    reopened = SceneWorkflow(project_dir)
    reopened.restore_draft(record, "chapter-1")
    monkeypatch.setattr(reopened, "_analyze_draft", AsyncMock())
    await reopened.continue_stale(record.revision_id)
    assert reopened.state.active is False
    assert reopened.run_guard.active_owner is None
    continued = load_scene_generation_record(
        project_dir, "scene-1", revision_id=record.revision_id
    )
    assert continued.stale_input is True
    assert continued.stale_input_reviewed is True
    assert continued.stale_reason == "基于旧设定"
    published = []
    monkeypatch.setattr(
        "app.storage.timeline_repository.publish_scene_revision",
        lambda *args: published.append(args),
    )
    reopened.publish("scene-1", record.revision_id)
    assert published[0][2] == record.revision_id


@pytest.mark.asyncio
async def test_continue_stale_uses_supplied_observer_for_busy_callbacks(
    tmp_path, monkeypatch
):
    project_dir = _project(tmp_path)
    record = SceneGenerationRecord(
        scene_id="scene-1",
        source_chapter_id="chapter-1",
        status="draft",
        draft_text="旧设定正文",
        review={"overall_pass": True},
        stale_input=True,
    )
    from app.storage.project_files import save_scene_generation_record

    save_scene_generation_record(project_dir, record)
    workflow = SceneWorkflow(project_dir)
    workflow.restore_draft(record, "chapter-1")
    monkeypatch.setattr(workflow, "_analyze_draft", AsyncMock())
    events = []

    await workflow.continue_stale(
        record.revision_id,
        observer=SceneWorkflowObserver(
            generating=lambda value: events.append(("generating", value)),
            status=lambda value: events.append(("status", value)),
        ),
    )

    assert events[:2] == [
        ("generating", True),
        ("status", "正在复核旧设定..."),
    ]
    assert events.count(("generating", False)) == 1


@pytest.mark.asyncio
async def test_cancel_stops_external_secondary_analysis_without_late_write(
    tmp_path, monkeypatch
):
    project_dir = _project(tmp_path)
    started = asyncio.Event()
    analysis_providers = [_Provider(), _Provider()]
    provider_iter = iter(analysis_providers)
    writes = []
    from app.storage import project_files

    original_save = project_files.save_scene_generation_record

    def save_record(*args, **kwargs):
        writes.append(args[1])
        return original_save(*args, **kwargs)

    monkeypatch.setattr(project_files, "save_scene_generation_record", save_record)
    monkeypatch.setattr("app.providers.config.load_provider_config", lambda: {})
    monkeypatch.setattr(
        "app.providers.config.get_provider_for_step",
        lambda *_args: next(provider_iter),
    )

    class Pipeline:
        async def analyze_draft(self, *_args, **_kwargs):
            started.set()
            await asyncio.Event().wait()

    events = []
    workflow = SceneWorkflow(project_dir, pipeline_factory=Pipeline)
    task = asyncio.create_task(
        workflow.save_edited_draft(
            "edited", SceneGenerationRecord(scene_id="scene-1"),
            SceneWorkflowObserver(generating=lambda value: events.append(value)),
        )
    )

    await started.wait()
    workflow.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert task.cancelled()
    assert all(provider.cancel_called for provider in analysis_providers)
    assert workflow._providers == []
    assert workflow.state.active is False
    assert workflow.run_guard.active_owner is None
    assert events.count(False) == 1
    assert len(writes) == 1


@pytest.mark.asyncio
async def test_cancel_stops_provider_and_saves_partial_prose_as_unpublished_draft(
    tmp_path,
):
    project_dir = _project(tmp_path)
    received = asyncio.Event()
    providers = [_Provider() for _ in range(4)]

    class Pipeline:
        source_revisions = {"characters": {"hero": {"definition_revision": 1}}}
        source_context_fingerprint = ""
        partial_result = None

        async def generate_stream(self, *_args, **_kwargs):
            self.partial_result = GenerationResult(
                scene_id="scene-1",
                plan=ScenePlan(scene_goal="已完成的规划"),
                trace=[
                    AgentTraceEntry(
                        agent_name="Scene Planner",
                        stage="planner",
                        status="completed",
                    )
                ],
            )
            yield "收到的部分正文", None
            received.set()
            await asyncio.Event().wait()

    workflow = SceneWorkflow(
        project_dir,
        provider_loader=lambda: tuple(providers),
        pipeline_factory=Pipeline,
    )
    workflow.start("scene-1", "chapter-1", SceneWorkflowObserver())
    await received.wait()
    workflow.cancel()
    with pytest.raises(asyncio.CancelledError):
        await workflow.task

    record = load_scene_generation_record(
        project_dir, "scene-1", revision_id=workflow.state.selected_revision
    )
    assert providers[2].cancel_called is True
    assert record.cancelled is True
    assert record.status == "draft"
    assert record.draft_text == "收到的部分正文"
    assert record.generated_with == Pipeline.source_revisions
    assert record.scene_plan["scene_goal"] == "已完成的规划"
    assert record.generation_trace[0]["status"] == "completed"
    assert record.published_at is None
    assert workflow.state.active is False


@pytest.mark.asyncio
async def test_cancel_after_planning_saves_completed_artifacts_without_prose(
    tmp_path,
):
    project_dir = _project(tmp_path)
    planned = asyncio.Event()

    class Pipeline:
        source_revisions = {"characters": {"hero": {"definition_revision": 1}}}
        source_context_fingerprint = ""
        partial_result = None

        async def generate_stream(self, *_args, **_kwargs):
            self.partial_result = GenerationResult(
                scene_id="scene-1",
                plan=ScenePlan(scene_goal="已完成的规划"),
                trace=[
                    AgentTraceEntry(
                        agent_name="Scene Planner",
                        stage="planner",
                        status="completed",
                    )
                ],
            )
            planned.set()
            await asyncio.Event().wait()
            yield None, None

    workflow = SceneWorkflow(
        project_dir,
        provider_loader=lambda: tuple(_Provider() for _ in range(4)),
        pipeline_factory=Pipeline,
    )
    workflow.start("scene-1", "chapter-1", SceneWorkflowObserver())
    await planned.wait()
    workflow.cancel()
    with pytest.raises(asyncio.CancelledError):
        await workflow.task

    record = load_scene_generation_record(
        project_dir, "scene-1", revision_id=workflow.state.selected_revision
    )
    assert record.cancelled is True
    assert record.draft_text == ""
    assert record.scene_plan["scene_goal"] == "已完成的规划"
    assert record.generation_trace[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_cancel_save_failure_still_releases_the_project_run(
    tmp_path, monkeypatch
):
    project_dir = _project(tmp_path)
    planned = asyncio.Event()

    class Pipeline:
        partial_result = None

        async def generate_stream(self, *_args, **_kwargs):
            self.partial_result = GenerationResult(
                scene_id="scene-1",
                plan=ScenePlan(scene_goal="已完成的规划"),
            )
            planned.set()
            await asyncio.Event().wait()
            yield None, None

    workflow = SceneWorkflow(
        project_dir,
        provider_loader=lambda: tuple(_Provider() for _ in range(4)),
        pipeline_factory=Pipeline,
    )
    workflow.start("scene-1", "chapter-1", SceneWorkflowObserver())
    await planned.wait()
    monkeypatch.setattr(
        "app.storage.project_files.save_scene_generation_record",
        lambda *_args: (_ for _ in ()).throw(OSError("disk full")),
    )
    workflow.cancel()
    with pytest.raises(OSError, match="disk full"):
        await workflow.task
    await asyncio.sleep(0)

    assert workflow.state.active is False
    assert workflow.run_guard.active_owner is None


@pytest.mark.asyncio
async def test_retry_starts_a_normal_new_run_without_automatic_resume(tmp_path):
    project_dir = _project(tmp_path)
    received = asyncio.Event()
    calls = []

    class Pipeline:
        def __init__(self):
            self.run_number = len(calls) + 1

        async def generate_stream(self, *_args, **kwargs):
            calls.append(kwargs)
            if self.run_number == 1:
                yield "partial", None
                received.set()
                await asyncio.Event().wait()
            else:
                yield None, GenerationResult(
                    scene_id="scene-1",
                    prose="retry draft",
                    review=ReviewResult(overall_pass=True),
                )

    workflow = SceneWorkflow(
        project_dir,
        provider_loader=lambda: tuple(_Provider() for _ in range(4)),
        pipeline_factory=Pipeline,
    )
    workflow.start("scene-1", "chapter-1", SceneWorkflowObserver())
    await received.wait()
    workflow.cancel()
    with pytest.raises(asyncio.CancelledError):
        await workflow.task
    assert len(calls) == 1

    workflow.retry()
    await workflow.task
    assert len(calls) == 2
    assert calls[1]["approved_plan"] is None
    assert workflow.state.draft_record.draft_text == "retry draft"
    assert workflow.state.draft_record.review["overall_pass"] is True


def test_context_reload_failure_marks_output_stale(tmp_path):
    project_dir = _project(tmp_path)

    class BrokenPipeline:
        def assemble_context(self, *_args):
            raise ValueError("unreadable context")

    assert _run_inputs_are_stale(
        project_dir,
        "scene-1",
        {"characters": {"hero": {"definition_revision": 1}}},
        "",
        BrokenPipeline(),
    )
    assert _run_inputs_are_stale(
        project_dir,
        "scene-1",
        {"characters": {"hero": {"definition_revision": 1}}},
        "",
        object(),
    )


@pytest.mark.asyncio
async def test_failed_stale_continuation_releases_the_project_run(
    tmp_path, monkeypatch
):
    project_dir = _project(tmp_path)
    record = SceneGenerationRecord(
        scene_id="scene-1",
        source_chapter_id="chapter-1",
        status="draft",
        draft_text="旧设定正文",
        review={"overall_pass": True},
        stale_input=True,
    )
    from app.storage.project_files import save_scene_generation_record

    save_scene_generation_record(project_dir, record)
    workflow = SceneWorkflow(project_dir)
    workflow.restore_draft(record, "chapter-1")
    monkeypatch.setattr(
        "app.storage.project_files.save_scene_generation_record",
        lambda *_args: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        await workflow.continue_stale(record.revision_id)

    assert workflow.state.active is False
    assert workflow.run_guard.active_owner is None


@pytest.mark.asyncio
async def test_blocked_continuations_do_not_emit_false_busy(tmp_path):
    workflow = SceneWorkflow(tmp_path)
    workflow.state.scene_id = "scene-1"
    workflow.state.active = True
    workflow.state.draft_record = SceneGenerationRecord(scene_id="scene-1")
    workflow._pipeline = object()
    workflow._result = object()
    workflow.run_guard.acquire("scene_workflow")
    workflow._task = asyncio.get_running_loop().create_future()
    review_events = []
    stale_events = []

    with pytest.raises(OperationBlockedError):
        await workflow.continue_review(
            SceneWorkflowObserver(generating=review_events.append)
        )
    with pytest.raises(OperationBlockedError):
        await workflow.continue_stale(
            observer=SceneWorkflowObserver(generating=stale_events.append)
        )

    assert review_events == []
    assert stale_events == []
    workflow._task.cancel()


@pytest.mark.asyncio
async def test_completed_stale_run_can_start_normal_regeneration(tmp_path):
    project_dir = _project(tmp_path)
    workflow = SceneWorkflow(project_dir)
    workflow.state.scene_id = "scene-1"
    workflow.state.chapter_id = "chapter-1"
    workflow.state.active = False
    completed = asyncio.get_running_loop().create_future()
    completed.set_result(None)
    workflow._task = completed
    record = SceneGenerationRecord(
        scene_id="scene-1",
        source_chapter_id="chapter-1",
        status="draft",
        scene_plan=ScenePlan(scene_goal="重写").model_dump(mode="json"),
        stale_input=True,
    )

    workflow.regenerate("scene-1", record, SceneWorkflowObserver())

    assert workflow.state.active is True
    assert workflow.run_guard.active_owner == "scene_workflow"
    workflow.cancel()
    with pytest.raises(asyncio.CancelledError):
        await workflow.task
