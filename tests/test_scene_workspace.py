from PySide6.QtWidgets import QTextEdit

from app.ui.scene_workspace import SceneWorkspaceView
from app.ui.widgets.agent_trace import AgentTracePanel
from app.ui.widgets.fact_approval import FactApprovalPanel
from app.ui.widgets.planner_checkpoint import PlannerCheckpointWidget
from app.ui.widgets.prose_editor import ProseEditorWidget
from app.ui.quick_chapter_view import QuickChapterView


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


def test_workspace_keeps_quick_and_deep_revision_selectors_synchronized(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    quick = workspace.findChild(QuickChapterView)
    prose = workspace.findChild(ProseEditorWidget)
    selected = []
    workspace.prose_version_selected.connect(selected.append)
    workspace.set_prose_versions(["v2", "v1"], "v2", "v1")

    assert workspace.select_prose_version("v1") is True
    assert prose.current_version() == "v1"
    assert quick.selected_revision == "v1"
    assert selected == []


def test_scene_change_clears_previous_quick_scene_state(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    quick = workspace.findChild(QuickChapterView)
    workspace.set_scene("scene-a", "chapter-a")
    workspace.show_quick_plan({"scene_id": "scene-a", "scene_goal": "旧目标"})
    workspace.show_review_result(False, "旧审查")
    workspace.show_fact_approval("scene-a", "rev-a", [{"description": "旧事实"}], [])
    workspace.set_prose_versions(["v1"], "v1")
    workspace.show_context({"old": {}})

    workspace.set_scene("scene-b", "chapter-b")

    assert quick.plan()["scene_goal"] == ""
    assert quick.review_section.isHidden()
    assert quick.memory_section.isHidden()
    assert quick.revision_section.isHidden()
    assert workspace.quick_approval_batch()[:2] == ("", "")
    assert quick.context_label.text() == ""


def test_workspace_mirrors_generation_state_into_quick_actions(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    quick = workspace.findChild(QuickChapterView)

    workspace.clear_scene()
    assert not quick.start_button.isEnabled()

    workspace.set_scene("scene-1", "chapter-1")
    assert quick.start_button.isEnabled()
    workspace.set_prose_versions(["v1"], "v1")
    workspace.set_generating(True)
    assert not quick.start_button.isEnabled()
    assert not quick.regenerate_button.isEnabled()
    assert not quick.revision_instruction_button.isEnabled()

    workspace.set_generating(False)
    assert not quick.start_button.isEnabled()
    assert quick.regenerate_button.isEnabled()
    assert quick.revision_instruction_button.isEnabled()


def test_begin_generation_preserves_explicit_waiting_status(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    workspace.set_scene("scene-1", "chapter-1")

    workspace.begin_generation("正在写作...")

    assert workspace.status_text == "正在写作..."


def test_set_scene_preserves_active_generation_status(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    workspace.set_scene("scene-a", "chapter-a")
    workspace.begin_generation("正在写作...")

    workspace.set_scene("scene-b", "chapter-b")

    assert workspace.status_text == "正在写作..."
    assert not workspace._generate_btn.isEnabled()
    assert not workspace._regenerate_btn.isEnabled()


def test_quick_can_approve_plan_while_generation_waits(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    quick = workspace.findChild(QuickChapterView)

    workspace.set_scene("scene-1", "chapter-1")
    workspace.set_generating(True)
    workspace.show_plan_checkpoint(
        {"scene_id": "scene-1", "scene_goal": "找到出口"}
    )

    assert quick.start_button.isEnabled()


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
        ("hide-plan",),
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


def test_quick_mode_is_a_compact_layer_over_the_same_workspace_state(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    quick = workspace.findChild(QuickChapterView)
    planner = workspace.findChild(PlannerCheckpointWidget)
    prose = workspace.findChild(ProseEditorWidget)

    workspace.set_scene("scene-1", "chapter-1")
    workspace.set_prose_text("shared draft")
    workspace.show_plan_checkpoint(
        {
            "scene_id": "scene-1",
            "scene_goal": "找到钥匙",
            "required_beats": ["进入档案室"],
            "emotional_arc": "笃定到不安",
            "ending_hook": "门后有脚步",
        }
    )
    workspace.set_experience_mode("quick")

    assert not quick.isHidden()
    assert quick.goal_edit.text() == "找到钥匙"
    assert planner.isHidden()
    assert prose._version_combo.isHidden()
    assert prose._set_active_btn.isHidden()
    assert workspace.prose_text() == "shared draft"

    workspace.set_experience_mode("deep")

    assert quick.isHidden()
    assert planner._plan["scene_goal"] == "找到钥匙"
    assert not prose._version_combo.isHidden()
    assert not prose._set_active_btn.isHidden()
    assert workspace.prose_text() == "shared draft"


def test_quick_mode_hides_the_deep_generation_toolbar(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    workspace.set_scene("scene-1", "chapter-1")

    workspace.set_experience_mode("quick")
    assert workspace._deep_toolbar.isHidden()
    assert workspace.prose_text() == ""

    workspace.set_experience_mode("deep")
    assert not workspace._deep_toolbar.isHidden()


def test_new_generation_clears_the_previous_quick_review(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    quick = workspace.findChild(QuickChapterView)
    workspace.set_scene("scene-1", "chapter-1")
    workspace.show_review_result(False, "旧问题")
    assert not quick.review_section.isHidden()

    workspace.begin_generation()

    assert quick.review_section.isHidden()


def test_workspace_forwards_quick_plan_apply_and_cancel(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)
    quick = workspace.findChild(QuickChapterView)
    plan = {
        "scene_id": "scene-1",
        "scene_goal": "找到钥匙",
        "required_beats": ["进入档案室"],
        "conflict": "守卫巡逻",
        "emotional_arc": "笃定到不安",
        "ending_hook": "门后有脚步",
        "continuity_constraints": ["主角仍然受伤"],
    }
    workspace.set_scene("scene-1", "chapter-1")
    workspace.show_plan_checkpoint(plan)
    starts, cancellations = [], []
    workspace.quick_start_requested.connect(
        lambda chapter, scene: starts.append((chapter, scene))
    )
    workspace.quick_adjust_cancelled.connect(lambda: cancellations.append(True))

    workspace.begin_quick_plan_adjustment()
    quick.goal_edit.setText("拿到钥匙")
    quick.start_button.click()

    assert starts == [("chapter-1", "scene-1")]
    assert quick.goal_edit.isReadOnly()
    assert workspace.quick_plan() == plan | {"scene_goal": "拿到钥匙"}

    workspace.begin_quick_plan_adjustment()
    quick.goal_edit.setText("放弃钥匙")
    quick.adjust_button.click()

    assert cancellations == [True]
    assert workspace.quick_plan() == plan | {"scene_goal": "拿到钥匙"}


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


def test_selected_quick_revision_owns_its_unchecked_memory_batch(qtbot):
    workspace = SceneWorkspaceView()
    qtbot.addWidget(workspace)

    workspace.set_quick_revision_metadata(
        "scene-1",
        "revision-2",
        True,
        "通过",
        [{"description": "事实"}],
        [{"character_id": "c1"}],
    )

    assert workspace.quick_approval_batch() == (
        "scene-1",
        "revision-2",
        [],
        [],
    )


def test_trace_reset_does_not_duplicate_internal_signal_connections(qtbot):
    trace = AgentTracePanel()
    qtbot.addWidget(trace)
    tree = trace._tree

    trace.clear()
    trace.set_waiting("waiting")
    trace.clear()

    assert tree.receivers("2itemClicked(QTreeWidgetItem*,int)") == 1
    assert tree.receivers("2customContextMenuRequested(QPoint)") == 1
