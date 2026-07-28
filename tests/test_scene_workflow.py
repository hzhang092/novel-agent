import pytest

from app.application.errors import OperationBlockedError
from app.application.scene_workflow import ProjectRunGuard, SceneWorkflow, SceneWorkflowObserver
from app.pipeline.pipeline import GenerationResult
from app.storage.models import ChapterOutline, Project, ReviewResult, SceneOutline, VolumeOutline
from app.storage.project_files import (
    create_project,
    load_scene_generation_record,
    save_scene_writer_draft,
    save_volume_outline,
)


def test_scene_workflow_keeps_one_run_and_records_draft_lifecycle(tmp_path):
    workflow = SceneWorkflow(tmp_path)

    workflow.start("scene-1", "chapter-1")
    workflow.receive_plan({"goal": "cross the pass"})
    workflow.append_prose("first")
    workflow.append_prose(" second")
    workflow.set_memory_selections([{"fact": "snow"}], [{"state": "cold"}])

    assert workflow.state.active is True
    assert workflow.state.partial_prose == "first second"
    assert workflow.state.planner_decision == {"goal": "cross the pass"}
    assert workflow.state.memory_facts == [{"fact": "snow"}]
    with pytest.raises(OperationBlockedError):
        workflow.start("scene-2", "chapter-2")

    workflow.finish()
    workflow.start("scene-2", "chapter-2")
    assert workflow.state.scene_id == "scene-2"


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
