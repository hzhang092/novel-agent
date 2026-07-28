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
    workflow.start("scene-1", "chapter-1", SceneWorkflowObserver())

    assert workflow.task is not None
    await workflow.task
    assert workflow.state.draft_record.draft_text == "draft"


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
    assert workflow.state.active is True
    assert workflow.run_guard.active_owner == "scene_workflow"


@pytest.mark.asyncio
async def test_edit_and_recovery_cannot_redirect_another_active_scene(tmp_path, monkeypatch):
    project_dir = _project_with_scenes(
        tmp_path, ("scene-1", "chapter-1"), ("scene-2", "chapter-2")
    )
    workflow = SceneWorkflow(project_dir, pipeline_factory=_AnalysisPipeline)
    _patch_analysis_providers(monkeypatch)
    await workflow.save_edited_draft(
        "scene one", SceneGenerationRecord(scene_id="scene-1"), SceneWorkflowObserver()
    )

    with pytest.raises(OperationBlockedError):
        await workflow.save_edited_draft(
            "scene two", SceneGenerationRecord(scene_id="scene-2"), SceneWorkflowObserver()
        )
    with pytest.raises(OperationBlockedError):
        workflow.recover_writer_draft("scene-2", "chapter-2", "recovered")
    assert (workflow.state.scene_id, workflow.state.chapter_id) == ("scene-1", "chapter-1")


@pytest.mark.asyncio
async def test_edit_cannot_replace_a_live_same_scene_task(tmp_path, monkeypatch):
    project_dir = _project_with_scenes(tmp_path, ("scene-1", "chapter-1"))
    workflow = SceneWorkflow(project_dir, pipeline_factory=_AnalysisPipeline)
    _patch_analysis_providers(monkeypatch)
    workflow.state.scene_id = "scene-1"
    workflow.state.chapter_id = "chapter-1"
    workflow.state.active = True
    workflow._task = asyncio.get_running_loop().create_future()

    with pytest.raises(OperationBlockedError):
        await workflow.save_edited_draft(
            "edited", SceneGenerationRecord(scene_id="scene-1"), SceneWorkflowObserver()
        )


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
    assert workflow.state.active is True
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
    assert workflow.state.active
    assert workflow.state.partial_prose == "first "
    assert record.status == "draft"
    assert record.generated_from_checkpoint_id == "cp-1"
    assert record.scene_summary_raw == {"summary": "crossed the pass"}
    assert memory == [("scene-1", record.revision_id, [{"description": "snow", "category": "world"}], [])]
    assert len(closed) == 6
