import asyncio

import pytest

from app.application.errors import OperationBlockedError
from app.application.scene_workflow import ProjectRunGuard, SceneWorkflow, SceneWorkflowObserver
from app.pipeline.pipeline import GenerationResult
from app.storage.models import (
    ChapterOutline,
    Project,
    ReviewResult,
    SceneGenerationRecord,
    SceneOutline,
    VolumeOutline,
)
from app.storage.project_files import (
    create_project,
    load_scene_generation_record,
    list_scene_prose_versions,
    save_scene_writer_draft,
    save_volume_outline,
)


@pytest.mark.asyncio
async def test_scene_workflow_start_owns_a_real_pipeline_task(tmp_path):
    """Starting never acquires a lease without starting the requested run."""
    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))

    class Provider:
        async def close(self):
            pass

    class Pipeline:
        async def generate_stream(self, *_args, **_kwargs):
            yield None, GenerationResult(scene_id="scene-1", prose="draft")

    workflow = SceneWorkflow(
        project_dir,
        provider_loader=lambda: (Provider(), Provider(), Provider(), Provider()),
        pipeline_factory=Pipeline,
    )
    events = []
    workflow.start(
        "scene-1",
        "chapter-1",
        SceneWorkflowObserver(
            generating=lambda value: events.append(("generating", value)),
            status=lambda value: events.append(("status", value)),
        ),
    )

    assert workflow.task is not None
    await workflow.task
    assert workflow.state.draft_record.draft_text == "draft"
    assert workflow.state.selected_revision == workflow.state.draft_record.revision_id
    assert workflow.state.active is False
    assert workflow.run_guard.active_owner is None
    assert events[:2] == [
        ("generating", True),
        ("status", "正在组装上下文..."),
    ]
    assert events.count(("generating", False)) == 1

    workflow.start("scene-1", "chapter-1", SceneWorkflowObserver())
    await workflow.task
    assert workflow.state.draft_record.revision_number == 2


def test_blocked_start_does_not_emit_false_busy(tmp_path):
    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))
    workflow = SceneWorkflow(project_dir)
    workflow.run_guard.acquire("story_designer")
    events = []

    with pytest.raises(OperationBlockedError):
        workflow.start(
            "scene-1",
            "chapter-1",
            SceneWorkflowObserver(generating=events.append),
        )

    assert events == []


@pytest.mark.asyncio
async def test_run_guard_stays_owned_until_generation_providers_close(tmp_path):
    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))
    closing = asyncio.Event()
    allow_close = asyncio.Event()

    class Provider:
        async def close(self):
            closing.set()
            await allow_close.wait()

    class Pipeline:
        async def generate_stream(self, *_args, **_kwargs):
            yield None, GenerationResult(scene_id="scene-1", prose="draft")

    workflow = SceneWorkflow(
        project_dir,
        provider_loader=lambda: (Provider(), Provider(), Provider(), Provider()),
        pipeline_factory=Pipeline,
    )
    workflow.start("scene-1", "chapter-1", SceneWorkflowObserver())

    await closing.wait()
    assert workflow.state.active is True
    assert workflow.run_guard.active_owner == "scene_workflow"
    assert workflow.run_guard.acquire("story_designer") is False

    allow_close.set()
    await workflow.task
    assert workflow.run_guard.active_owner is None


@pytest.mark.asyncio
async def test_exhausted_generation_stream_releases_the_run_guard(tmp_path):
    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))

    class Provider:
        async def close(self):
            pass

    class Pipeline:
        async def generate_stream(self, *_args, **_kwargs):
            if False:
                yield None, None

    workflow = SceneWorkflow(
        project_dir,
        provider_loader=lambda: (Provider(), Provider(), Provider(), Provider()),
        pipeline_factory=Pipeline,
    )
    workflow.start("scene-1", "chapter-1", SceneWorkflowObserver())

    await workflow.task

    assert workflow.state.active is False
    assert workflow.run_guard.active_owner is None


@pytest.mark.asyncio
async def test_continuations_cannot_release_a_live_generation_run(tmp_path):
    workflow = SceneWorkflow(tmp_path)
    workflow.state.scene_id = "scene-1"
    workflow.state.active = True
    workflow.state.draft_record = SceneGenerationRecord(scene_id="scene-1")
    workflow._pipeline = object()
    workflow._result = object()
    workflow.run_guard.acquire("scene_workflow")
    workflow._task = asyncio.get_running_loop().create_future()

    with pytest.raises(OperationBlockedError):
        await workflow.continue_review()
    with pytest.raises(OperationBlockedError):
        await workflow.continue_stale()

    assert workflow.state.active is True
    assert workflow.run_guard.active_owner == "scene_workflow"
    workflow._task.cancel()


@pytest.mark.asyncio
async def test_plan_decision_first_signal_wins(tmp_path):
    workflow = SceneWorkflow(tmp_path)
    decision = asyncio.get_running_loop().create_future()
    workflow._plan_future = decision

    workflow.approve_plan({"goal": "first"})
    workflow.reject_plan()
    workflow.approve_plan({"goal": "second"})

    assert decision.result() == (True, {"goal": "first"})
    assert workflow.state.planner_decision == {"goal": "first"}


def test_run_guard_rejects_without_waiting():
    guard = ProjectRunGuard()

    assert guard.acquire("story_designer") is True
    assert guard.acquire("scene_workflow") is False
    guard.release("story_designer")
    assert guard.acquire("scene_workflow") is True


def test_workflow_promotes_recovery_buffer_without_duplicate_version(tmp_path):
    project_dir = create_project(tmp_path, Project(title="Story"))
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="vol-1",
            chapters=[ChapterOutline(id="chapter-1", scenes=[SceneOutline(id="scene-1")])],
        ),
    )
    save_scene_writer_draft(project_dir, "scene-1", "recovered prose")

    record = SceneWorkflow(project_dir).recover_writer_draft(
        "scene-1", "chapter-1", "recovered prose"
    )

    assert record.status == "draft"
    assert record.draft_text == "recovered prose"
    assert load_scene_generation_record(project_dir, "scene-1").revision_number == 1


@pytest.mark.asyncio
async def test_edited_draft_uses_its_own_scene_chapter_and_current_observer(
    tmp_path, monkeypatch
):
    project_dir = _project_with_scenes(
        tmp_path, ("scene-1", "chapter-1"), ("scene-2", "chapter-2")
    )
    observer_records = []
    workflow = SceneWorkflow(project_dir, pipeline_factory=_AnalysisPipeline)
    workflow.state.scene_id = "scene-1"
    workflow.state.chapter_id = "chapter-1"
    _patch_analysis_providers(monkeypatch)

    record = await workflow.save_edited_draft(
        "edited scene two",
        SceneGenerationRecord(scene_id="scene-2"),
        SceneWorkflowObserver(draft=observer_records.append),
    )

    assert record.revision_number == 1
    assert (project_dir / "scenes" / "chapter-2" / "scene-2.v1.md").read_text(encoding="utf-8") == "edited scene two"
    assert not (project_dir / "scenes" / "chapter-1" / "scene-2.v1.md").exists()
    assert observer_records == [record]
    assert workflow.state.active is False
    assert workflow.run_guard.active_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("analyze", "initial_status"),
    [
        (False, "正在保存修改..."),
        (True, "正在保存并重新审查修改..."),
    ],
)
async def test_edited_draft_announces_busy_with_its_observer(
    tmp_path, monkeypatch, analyze, initial_status
):
    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))
    _patch_analysis_providers(monkeypatch)
    events = []
    observer = SceneWorkflowObserver(
        generating=lambda value: events.append(("generating", value)),
        status=lambda value: events.append(("status", value)),
    )
    workflow = SceneWorkflow(project_dir, pipeline_factory=_AnalysisPipeline)

    await workflow.save_edited_draft(
        "edited", SceneGenerationRecord(scene_id="scene-1"), observer, analyze=analyze
    )

    assert events[:2] == [("generating", True), ("status", initial_status)]
    assert events.count(("generating", False)) == 1


@pytest.mark.asyncio
async def test_continue_review_uses_supplied_observer_for_busy_callbacks(
    tmp_path, monkeypatch
):
    workflow = SceneWorkflow(tmp_path)
    workflow.state.scene_id = "scene-1"
    workflow.state.draft_record = SceneGenerationRecord(scene_id="scene-1")
    workflow._pipeline = object()
    workflow._result = object()
    monkeypatch.setattr(
        "app.storage.project_files.save_scene_generation_record", lambda *_args: None
    )
    async def analyze_draft():
        pass

    monkeypatch.setattr(workflow, "_analyze_draft", analyze_draft)
    events = []

    await workflow.continue_review(
        observer=SceneWorkflowObserver(
            generating=lambda value: events.append(("generating", value)),
            status=lambda value: events.append(("status", value)),
        )
    )

    assert events[:2] == [
        ("generating", True),
        ("status", "正在继续审查..."),
    ]
    assert events.count(("generating", False)) == 1


@pytest.mark.asyncio
async def test_completed_edit_and_recovery_can_move_to_another_scene(tmp_path, monkeypatch):
    project_dir = _project_with_scenes(
        tmp_path, ("scene-1", "chapter-1"), ("scene-2", "chapter-2")
    )
    workflow = SceneWorkflow(project_dir, pipeline_factory=_AnalysisPipeline)
    _patch_analysis_providers(monkeypatch)
    await workflow.save_edited_draft(
        "scene one", SceneGenerationRecord(scene_id="scene-1"), SceneWorkflowObserver()
    )

    second = await workflow.save_edited_draft(
        "scene two", SceneGenerationRecord(scene_id="scene-2"), SceneWorkflowObserver()
    )
    recovered = workflow.recover_writer_draft(
        "scene-1", "chapter-1", "recovered"
    )

    assert second.scene_id == "scene-2"
    assert recovered.scene_id == "scene-1"
    assert (workflow.state.scene_id, workflow.state.chapter_id) == (
        "scene-1",
        "chapter-1",
    )


@pytest.mark.asyncio
async def test_edit_cannot_replace_a_live_same_scene_task(tmp_path, monkeypatch):
    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))
    workflow = SceneWorkflow(project_dir, pipeline_factory=_AnalysisPipeline)
    _patch_analysis_providers(monkeypatch)
    workflow.state.scene_id = "scene-1"
    workflow.state.chapter_id = "chapter-1"
    workflow.state.active = True
    workflow._task = asyncio.get_running_loop().create_future()
    events = []

    with pytest.raises(OperationBlockedError):
        await workflow.save_edited_draft(
            "edited",
            SceneGenerationRecord(scene_id="scene-1"),
            SceneWorkflowObserver(generating=events.append),
        )

    assert events == []


@pytest.mark.asyncio
async def test_edit_cannot_join_another_edit_analysis_run(tmp_path, monkeypatch):
    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))
    analyzing = asyncio.Event()
    release = asyncio.Event()

    class BlockingPipeline:
        async def analyze_draft(self, *_args, **_kwargs):
            analyzing.set()
            await release.wait()

    _patch_analysis_providers(monkeypatch)
    workflow = SceneWorkflow(project_dir, pipeline_factory=BlockingPipeline)
    source = SceneGenerationRecord(scene_id="scene-1")
    first = asyncio.create_task(
        workflow.save_edited_draft(
            "first edit", source, SceneWorkflowObserver()
        )
    )
    await analyzing.wait()

    try:
        with pytest.raises(OperationBlockedError):
            await asyncio.wait_for(
                workflow.save_edited_draft(
                    "second edit", source, SceneWorkflowObserver()
                ),
                timeout=0.1,
            )
    finally:
        release.set()
        await first
    assert workflow.run_guard.active_owner is None


@pytest.mark.asyncio
async def test_failed_new_edit_releases_its_project_lease(tmp_path):
    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))
    workflow = SceneWorkflow(project_dir, pipeline_factory=_AnalysisPipeline)

    with pytest.raises(ValueError):
        await workflow.save_edited_draft(
            "edited",
            SceneGenerationRecord(
                scene_id="scene-1", scene_plan={"required_beats": "not a list"}
            ),
            SceneWorkflowObserver(),
        )

    assert workflow.state.active is False
    assert workflow.run_guard.active_owner is None


def test_recovery_repairs_a_truncated_record_without_duplicate_version(tmp_path):
    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))
    from app.application.scene_workflow import _save_versioned_prose

    _save_versioned_prose(project_dir, "chapter-1", "scene-1", "recovered", 1)
    (project_dir / "scenes" / "chapter-1" / "scene-1.v1.gen.json").write_text(
        '{"scene_id":', encoding="utf-8"
    )
    save_scene_writer_draft(project_dir, "scene-1", "recovered")

    record = SceneWorkflow(project_dir).recover_writer_draft(
        "scene-1", "chapter-1", "recovered"
    )

    assert record.revision_number == 1
    assert list_scene_prose_versions(project_dir, "chapter-1", "scene-1") == ["v1"]
    assert load_scene_generation_record(project_dir, "scene-1", version="v1").draft_text == "recovered"


@pytest.mark.asyncio
async def test_analysis_failure_keeps_saved_draft_and_retry_path(tmp_path, monkeypatch):
    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))
    statuses, reviews = [], []

    class FailingPipeline:
        async def analyze_draft(self, *_args, **_kwargs):
            raise RuntimeError("summary extraction failed")

    _patch_analysis_providers(monkeypatch)
    workflow = SceneWorkflow(project_dir, pipeline_factory=FailingPipeline)
    record = await workflow.save_edited_draft(
        "saved before analysis",
        SceneGenerationRecord(scene_id="scene-1"),
        SceneWorkflowObserver(status=statuses.append, review=lambda *args: reviews.append(args)),
    )

    assert load_scene_generation_record(project_dir, "scene-1", version="v1").draft_text == "saved before analysis"
    assert workflow.state.draft_record is record
    assert workflow.state.active is False
    assert workflow.run_guard.active_owner is None
    assert statuses[-1] == "记忆分析失败"
    assert reviews[-1] == (False, "记忆分析失败；草稿已保存，可重试")


def test_version_replacement_writes_complete_prose_without_temp_files(tmp_path):
    from app.application.scene_workflow import _save_versioned_prose

    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))
    target = project_dir / "scenes" / "chapter-1" / "scene-1.v1.md"
    _save_versioned_prose(project_dir, "chapter-1", "scene-1", "complete", 1)
    _save_versioned_prose(project_dir, "chapter-1", "scene-1", "replacement", 1)

    assert target.read_text(encoding="utf-8") == "replacement"
    assert not list(target.parent.glob("*.tmp"))


def _project_with_scenes(tmp_path, *scenes):
    project_dir = create_project(tmp_path, Project(title="Story"))
    chapters = [
        ChapterOutline(id=chapter_id, scenes=[SceneOutline(id=scene_id)])
        for scene_id, chapter_id in scenes
    ]
    save_volume_outline(project_dir, VolumeOutline(id="vol-1", chapters=chapters))
    return project_dir


class _AnalysisPipeline:
    async def analyze_draft(self, _project_dir, result, **_kwargs):
        result.extracted_facts = []
        result.state_changes = []
        result.scene_summary = {"summary": "edited"}


def _patch_analysis_providers(monkeypatch):
    class Provider:
        async def close(self):
            pass

    monkeypatch.setattr("app.providers.config.load_provider_config", lambda: {})
    monkeypatch.setattr(
        "app.providers.config.get_provider_for_step", lambda *_args: Provider()
    )


@pytest.mark.asyncio
async def test_workflow_owns_pipeline_draft_and_memory_review(tmp_path, monkeypatch):
    project_dir = create_project(tmp_path, Project(title="Story"))
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="vol-1",
            chapters=[ChapterOutline(id="chapter-1", scenes=[SceneOutline(id="scene-1")])],
        ),
    )
    closed = []

    class Provider:
        async def close(self):
            closed.append(self)

    class Pipeline:
        def assemble_context(self, *_args):
            return {
                "read_points": {"hero": {"checkpoint_id": "cp-1"}},
                "world_element_read_points": {},
            }

        async def generate_stream(self, *_args, **_kwargs):
            yield "first ", None
            yield None, GenerationResult(
                scene_id="scene-1",
                prose="first draft",
                review=ReviewResult(overall_pass=True, summary="pass"),
                generated_with={"characters": {"hero": {"checkpoint_id": "cp-1"}}},
            )

        async def analyze_draft(self, _project_dir, result, **_kwargs):
            result.extracted_facts = [{"description": "snow", "category": "world"}]
            result.state_changes = []
            result.scene_summary = {"summary": "crossed the pass"}

    monkeypatch.setattr("app.providers.config.load_provider_config", lambda: {})
    monkeypatch.setattr(
        "app.providers.config.get_provider_for_step", lambda *_args: Provider()
    )
    memory = []
    workflow = SceneWorkflow(
        project_dir,
        provider_loader=lambda: (Provider(), Provider(), Provider(), Provider()),
        pipeline_factory=Pipeline,
    )

    workflow.start(
        "scene-1",
        "chapter-1",
        SceneWorkflowObserver(memory=lambda *args: memory.append(args)),
    )
    await workflow.task

    record = load_scene_generation_record(project_dir, "scene-1")
    assert workflow.state.active is False
    assert workflow.run_guard.active_owner is None
    assert workflow.state.partial_prose == "first "
    assert record.status == "draft"
    assert record.generated_from_checkpoint_id == "cp-1"
    assert record.scene_summary_raw == {"summary": "crossed the pass"}
    assert memory == [("scene-1", record.revision_id, [{"description": "snow", "category": "world"}], [])]
    assert len(closed) == 6
