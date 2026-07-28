import pytest

from app.application.errors import OperationBlockedError
from app.application.scene_workflow import ProjectRunGuard, SceneWorkflow


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
