from PySide6.QtWidgets import QTextEdit

from app.ui.scene_workspace import SceneWorkspaceView
from app.ui.widgets.agent_trace import AgentTracePanel
from app.ui.widgets.fact_approval import FactApprovalPanel
from app.ui.widgets.planner_checkpoint import PlannerCheckpointWidget
from app.ui.widgets.prose_editor import ProseEditorWidget


def test_scene_state_and_prose_facade(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)

    workspace.set_scene("scene-1", "chapter-1")
    assert workspace.current_scene_id == "scene-1"
    assert workspace.current_chapter_id == "chapter-1"
    assert workspace.is_showing_scene("scene-1", "chapter-1") is True

    workspace.set_prose_text("first")
    workspace.append_prose(" second")
    assert workspace.prose_text() == "first second"
    workspace.findChild(QTextEdit).document().setModified(True)
    assert workspace.prose_is_modified() is True

    workspace.set_prose_versions(["v1", "v2"], "v2")
    assert workspace.current_prose_version() == "v2"

    workspace.clear_scene()
    assert workspace.current_scene_id is None
    assert workspace.current_chapter_id is None


def test_workspace_forwards_embedded_user_actions_once(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    prose = workspace.findChild(ProseEditorWidget)
    planner = workspace.findChild(PlannerCheckpointWidget)
    approval = workspace.findChild(FactApprovalPanel)
    trace = workspace.findChild(AgentTracePanel)
    events = []
    workspace.prose_version_selected.connect(lambda value: events.append(("version", value)))
    workspace.publish_version_requested.connect(lambda value: events.append(("publish", value)))
    workspace.plan_approved.connect(lambda value: events.append(("approved", value)))
    workspace.plan_rejected.connect(lambda: events.append(("rejected",)))
    workspace.approval_batch_approved.connect(
        lambda scene, revision, facts, changes: events.append(
            ("batch", scene, revision, facts, changes)
        )
    )
    workspace.retry_requested.connect(lambda agent: events.append(("retry", agent)))

    prose.version_selected.emit("v2")
    prose.set_active_requested.emit("v2")
    planner.approved.emit({"scene_id": "scene-1"})
    planner.rejected.emit()
    approval.approval_batch_approved.emit("scene-1", "rev-1", [], [])
    trace.retry_requested.emit("writer")

    assert events == [
        ("version", "v2"),
        ("publish", "v2"),
        ("approved", {"scene_id": "scene-1"}),
        ("rejected",),
        ("batch", "scene-1", "rev-1", [], []),
        ("retry", "writer"),
    ]


def test_workspace_trace_planner_status_and_generation_facades(qtbot, monkeypatch):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    trace = workspace.findChild(AgentTracePanel)
    planner = workspace.findChild(PlannerCheckpointWidget)
    calls = []
    monkeypatch.setattr(trace, "clear", lambda: calls.append(("clear",)))
    monkeypatch.setattr(trace, "set_waiting", lambda text: calls.append(("waiting", text)))
    monkeypatch.setattr(trace, "update_trace", lambda value: calls.append(("trace", value)))
    monkeypatch.setattr(planner, "show_plan", lambda plan: calls.append(("plan", plan)))
    monkeypatch.setattr(planner, "hide_plan", lambda: calls.append(("hide-plan",)))
    monkeypatch.setattr(planner, "set_waiting", lambda: calls.append(("plan-wait",)))

    workspace.set_scene("scene-1", "chapter-1")
    workspace.set_prose_text("old prose")
    workspace.update_trace(["entry"])
    workspace.show_plan_checkpoint({"scene_id": "scene-1"})
    workspace.set_plan_checkpoint_waiting()
    workspace.hide_plan_checkpoint()
    workspace.begin_generation("waiting")
    workspace.set_status("done")

    assert calls == [
        ("trace", ["entry"]),
        ("plan", {"scene_id": "scene-1"}),
        ("plan-wait",),
        ("hide-plan",),
        ("clear",),
        ("waiting", "waiting"),
    ]
    assert workspace.prose_text() == ""
    assert workspace._status_label.text() == "done"
    assert workspace._next_scene_btn.isEnabled() is False

    workspace.set_generating(False)
    workspace.set_next_scene_available(True)
    assert workspace._next_scene_btn.isEnabled() is True
    workspace.mark_last_scene()
    assert workspace._next_scene_btn.isEnabled() is False
    assert workspace._status_label.text() == "已是最后一场景"


def test_workspace_does_not_expose_raw_embedded_widgets(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)

    for name in (
        "editor",
        "trace_panel",
        "planner_checkpoint",
        "fact_approval",
        "context_preview",
    ):
        assert not hasattr(workspace, name)
