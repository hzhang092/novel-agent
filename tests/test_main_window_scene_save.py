import asyncio

import pytest

from app.storage.models import (
    ChapterOutline,
    Project,
    SceneGenerationRecord,
    SceneOutline,
    ScenePlan,
    VolumeOutline,
)
from app.storage.project_files import (
    create_project,
    load_all_volumes,
    save_scene_generation_record,
    save_scene_writer_draft,
    save_volume_outline,
)
from app.application.errors import OperationBlockedError
from app.ui.quick_chapter_view import QuickChapterView
from app.ui.main_window import MainWindow


def _project(tmp_path):
    project_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        project_dir,
        VolumeOutline(
            id="vol-1",
            chapters=[
                ChapterOutline(
                    id="ch-1", scenes=[SceneOutline(id="scene-1")]
                )
            ],
        ),
    )
    return project_dir


def test_writer_recovery_delegates_to_project_workflow(tmp_path, qtbot, monkeypatch):
    project_dir = _project(tmp_path)
    save_scene_writer_draft(project_dir, "scene-1", "崩溃前完成的正文")
    notices = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information", lambda *args: notices.append(args)
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = project_dir
    window._bind_project_application(project_dir)
    workspace = window._workspace_view
    workspace.set_scene("scene-1", "ch-1")

    window._load_scene_prose_into_editor(workspace, "ch-1", "scene-1")

    record = window._application.scene_workflow.state.draft_record
    assert record.status == "draft"
    assert workspace.prose_text() == "崩溃前完成的正文"
    assert notices


def test_publish_action_delegates_to_project_workflow(tmp_path, qtbot, monkeypatch):
    project_dir = _project(tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = project_dir
    window._bind_project_application(project_dir)
    calls = []
    monkeypatch.setattr(
        window._application.scene_workflow,
        "publish",
        lambda *args: calls.append(args),
    )
    workspace = window._workspace_view
    workspace.show_fact_approval("scene-1", "rev-1", [{"description": "事实"}], [])

    window._on_approval_batch_approved("scene-1", "rev-1", [{"description": "事实"}], [])

    assert calls == [("scene-1", "rev-1", [{"description": "事实"}], [])]
    assert not workspace.fact_approval_is_visible


def test_rejected_generation_does_not_clear_workspace_buffer(tmp_path, qtbot, monkeypatch):
    project_dir = _project(tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = project_dir
    window._bind_project_application(project_dir)
    workspace = window._workspace_view
    workspace.set_scene("scene-1", "ch-1")
    workspace.set_prose_text("keep this draft")
    monkeypatch.setattr(
        window._application.scene_workflow,
        "start",
        lambda *_args: (_ for _ in ()).throw(OperationBlockedError("already running")),
    )
    monkeypatch.setattr("app.ui.main_window.QMessageBox.warning", lambda *_args: None)

    window._on_generate_requested("scene-1")

    assert workspace.prose_text() == "keep this draft"


def test_quick_approve_next_publishes_then_only_navigates(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    workspace = window._workspace_view
    workspace.set_scene("scene-1", "ch-1")
    workspace.show_fact_approval(
        "scene-1", "rev-1", [{"description": "事实"}], []
    )
    workspace.findChild(QuickChapterView).fact_checks[0].setChecked(True)
    published, next_calls = [], []
    monkeypatch.setattr(
        window._application.scene_workflow,
        "publish",
        lambda *args: published.append(args),
    )
    monkeypatch.setattr(window, "_on_next_scene", lambda: next_calls.append(True))
    monkeypatch.setattr(
        window._application.scene_workflow,
        "start",
        lambda *_args, **_kwargs: pytest.fail("approval must not generate prose"),
    )

    window._on_quick_approve_next()

    assert published == [("scene-1", "rev-1", [{"description": "事实"}], [])]
    assert next_calls == [True]


def test_quick_length_change_is_a_chapter_override(tmp_path, qtbot):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._workspace_view.set_scene("scene-1", "ch-1")

    window._on_quick_length_changed("custom", 4200)

    chapter = load_all_volumes(project_dir)[0].chapters[0]
    assert chapter.chapter_length_override.preset == "custom"
    assert chapter.chapter_length_override.resolved_target == 4200


def test_initial_quick_plan_adjustment_approves_the_merged_full_plan(
    tmp_path, qtbot
):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("quick")
    window._select_destination("workspace")
    window._workspace_view.set_scene("scene-1", "ch-1")
    plan = {
        "scene_id": "scene-1",
        "scene_goal": "找到出口",
        "required_beats": ["穿过大厅"],
        "conflict": "出口被封锁",
        "emotional_arc": "希望转为恐惧",
        "ending_hook": "门外传来脚步",
        "continuity_constraints": ["主角仍然受伤"],
        "participants": ["主角", "守卫"],
    }
    window._workspace_view.show_plan_checkpoint(plan)
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    workflow = window._application.scene_workflow
    workflow._plan_future = future
    workflow.state.scene_id = "scene-1"
    quick = window._workspace_view.findChild(QuickChapterView)

    quick.adjust_button.click()
    assert window._experience_mode == "quick"
    assert window._previous_destination == "workspace"
    assert not quick.goal_edit.isReadOnly()

    quick.goal_edit.setText("逃出大厅")
    quick.start_button.click()

    assert future.result() == (True, plan | {"scene_goal": "逃出大厅"})
    loop.close()


def test_existing_plan_adjustment_cancels_or_applies_in_quick(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _project(tmp_path)
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        scene_plan=ScenePlan(
            scene_id="scene-1",
            scene_goal="找到出口",
            conflict="出口被封锁",
            emotional_arc="希望转为恐惧",
            ending_hook="门后有脚步",
            continuity_constraints=["主角仍然受伤"],
        ).model_dump(mode="json"),
        draft_text="正文",
    )
    save_scene_generation_record(project_dir, record)
    (project_dir / "scenes" / "ch-1" / "scene-1.v1.md").write_text(
        "正文", encoding="utf-8"
    )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("quick")
    window._select_destination("workspace")
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._current_prose_version = "v1"
    calls = []
    monkeypatch.setattr(
        window._application.scene_workflow,
        "regenerate",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    quick = window._workspace_view.findChild(QuickChapterView)

    quick.adjust_button.click()
    assert window._pending_plan_patch is not None
    assert window._experience_mode == "quick"
    assert window._previous_destination == "workspace"
    assert calls == []

    quick.goal_edit.setText("放弃出口")
    quick.adjust_button.click()

    assert window._pending_plan_patch is None
    assert quick.plan() == record.scene_plan
    assert calls == []

    quick.adjust_button.click()
    quick.hook_edit.setText("警报响起")
    quick.start_button.click()

    assert len(calls) == 1
    patch = calls[0][1]["plan_patch"]
    assert patch.base_revision_id == "rev-1"
    assert patch.ending_hook == "警报响起"
    assert patch.conflict == "出口被封锁"
    assert patch.continuity_constraints == ["主角仍然受伤"]


def test_scene_and_revision_changes_cancel_the_pending_quick_plan_patch(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _project(tmp_path)
    volume = load_all_volumes(project_dir)[0]
    volume.chapters.append(
        ChapterOutline(id="ch-2", scenes=[SceneOutline(id="scene-2")])
    )
    save_volume_outline(project_dir, volume)
    records = [
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id=f"rev-{number}",
            revision_number=number,
            scene_plan=ScenePlan(
                scene_id="scene-1",
                scene_goal=f"计划 {number}",
            ).model_dump(mode="json"),
            draft_text=f"正文 {number}",
        )
        for number in (1, 2)
    ]
    for record in records:
        save_scene_generation_record(project_dir, record)
        (project_dir / "scenes" / "ch-1" / f"scene-1.v{record.revision_number}.md").write_text(
            record.draft_text, encoding="utf-8"
        )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("quick")
    window._select_destination("workspace")
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._current_prose_version = "v1"
    calls = []
    monkeypatch.setattr(
        window._application.scene_workflow,
        "regenerate",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    quick = window._workspace_view.findChild(QuickChapterView)

    quick.adjust_button.click()
    window._on_prose_version_selected("v2")

    assert window._pending_plan_patch is None
    assert quick.goal_edit.isReadOnly()

    quick.adjust_button.click()
    window._on_scene_selected("scene-2")

    assert window._pending_plan_patch is None
    assert quick.goal_edit.isReadOnly()
    assert calls == []


def test_scene_change_exits_initial_quick_plan_adjustment(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _project(tmp_path)
    volume = load_all_volumes(project_dir)[0]
    volume.chapters.append(
        ChapterOutline(id="ch-2", scenes=[SceneOutline(id="scene-2")])
    )
    save_volume_outline(project_dir, volume)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("quick")
    window._select_destination("workspace")
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._workspace_view.show_plan_checkpoint(
        ScenePlan(scene_id="scene-1", scene_goal="找到出口").model_dump(mode="json")
    )
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    workflow = window._application.scene_workflow
    workflow._plan_future = future
    workflow.state.scene_id = "scene-1"
    quick = window._workspace_view.findChild(QuickChapterView)
    warnings = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.warning",
        lambda *args: warnings.append(args),
    )

    quick.adjust_button.click()
    window._on_scene_selected("scene-2")

    assert quick.goal_edit.isReadOnly()
    assert quick.adjust_button.text() == "调整"
    assert window._pending_plan_patch is None
    assert not future.done()

    quick.adjust_button.click()
    quick.start_button.click()

    assert quick.goal_edit.isReadOnly()
    assert len(warnings) == 2
    assert not future.done()
    loop.close()


def test_project_switch_clears_pending_quick_plan_adjustment(tmp_path, qtbot):
    first_dir = _project(tmp_path / "first")
    second_dir = _project(tmp_path / "second")
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        scene_plan=ScenePlan(
            scene_id="scene-1",
            scene_goal="找到出口",
        ).model_dump(mode="json"),
        draft_text="正文",
    )
    save_scene_generation_record(first_dir, record)
    (first_dir / "scenes" / "ch-1" / "scene-1.v1.md").write_text(
        "正文", encoding="utf-8"
    )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(first_dir)
    window._set_experience_mode("quick")
    window._select_destination("workspace")
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._current_prose_version = "v1"
    quick = window._workspace_view.findChild(QuickChapterView)

    quick.adjust_button.click()
    assert window._pending_plan_patch is not None

    window._bind_project_application(second_dir)

    assert window._pending_plan_patch is None
    assert quick.goal_edit.isReadOnly()
    assert quick.adjust_button.text() == "调整"
    assert window._application.scene_workflow.project_dir == second_dir


def test_deep_plan_resolution_exits_quick_adjustment(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _project(tmp_path)
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        scene_plan=ScenePlan(
            scene_id="scene-1",
            scene_goal="找到出口",
            ending_hook="门后有脚步",
        ).model_dump(mode="json"),
        draft_text="正文",
    )
    save_scene_generation_record(project_dir, record)
    (project_dir / "scenes" / "ch-1" / "scene-1.v1.md").write_text(
        "正文", encoding="utf-8"
    )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("quick")
    window._select_destination("workspace")
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._current_prose_version = "v1"
    calls = []
    monkeypatch.setattr(
        window._application.scene_workflow,
        "regenerate",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    quick = window._workspace_view.findChild(QuickChapterView)

    quick.adjust_button.click()
    quick.context_button.click()
    window._on_plan_rejected()

    assert window._pending_plan_patch is None
    assert quick.goal_edit.isReadOnly()
    assert quick.adjust_button.text() == "调整"

    window._set_experience_mode("quick")
    window._select_destination("workspace")
    quick.adjust_button.click()
    quick.context_button.click()
    edited = record.scene_plan | {"ending_hook": "警报响起"}
    window._on_plan_approved(edited)

    assert len(calls) == 1
    assert window._pending_plan_patch is None
    assert quick.hook_edit.isReadOnly()
    assert quick.adjust_button.text() == "调整"
    assert quick.plan() == edited


def test_story_changing_ai_fix_waits_for_quick_plan_adjustment(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _project(tmp_path)
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        scene_plan=ScenePlan(
            scene_id="scene-1",
            scene_goal="找到出口",
            ending_hook="门后有脚步",
        ).model_dump(mode="json"),
        draft_text="正文",
    )
    save_scene_generation_record(project_dir, record)
    (project_dir / "scenes" / "ch-1" / "scene-1.v1.md").write_text(
        "正文", encoding="utf-8"
    )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("quick")
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._current_prose_version = "v1"
    calls = []
    monkeypatch.setattr(
        window._application.scene_workflow,
        "regenerate",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    window._workspace_view.show_review_result(False, "结尾缺少钩子")
    window._on_quick_ai_fix()
    assert window._pending_plan_patch is not None
    assert window._experience_mode == "quick"
    assert calls == []

    quick = window._workspace_view.findChild(QuickChapterView)
    assert not quick.hook_edit.isReadOnly()
    quick.hook_edit.setText("警报响起")
    quick.start_button.click()

    assert len(calls) == 1
    assert calls[0][1]["plan_patch"].base_revision_id == "rev-1"
    assert calls[0][1]["plan_patch"].ending_hook == "警报响起"


def test_selecting_revision_replaces_quick_memory_source(tmp_path, qtbot):
    project_dir = _project(tmp_path)
    first = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        extracted_facts_raw=[{"description": "旧事实"}],
        draft_text="旧正文",
    )
    second = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-2",
        revision_number=2,
        scene_plan=ScenePlan(
            scene_id="scene-1",
            scene_goal="新目标",
            ending_hook="新钩子",
        ).model_dump(mode="json"),
        extracted_facts_raw=[{"description": "新事实"}],
        draft_text="新正文",
    )
    for record in (first, second):
        save_scene_generation_record(project_dir, record)
        (project_dir / "scenes" / "ch-1" / f"scene-1.v{record.revision_number}.md").write_text(
            record.draft_text, encoding="utf-8"
        )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._workspace_view.set_prose_versions(["v2", "v1"], "v1")
    window._current_prose_version = "v1"
    window._show_quick_revision(first)

    window._on_prose_version_selected("v2")

    scene_id, revision_id, facts, changes = (
        window._workspace_view.quick_approval_batch()
    )
    assert (scene_id, revision_id, facts, changes) == (
        "scene-1",
        "rev-2",
        [],
        [],
    )
    assert window._current_prose_version == "v2"
    assert window._workspace_view.prose_text() == "新正文"
    assert window._workspace_view._editor.current_version() == "v2"
    assert window._workspace_view._quick_chapter.selected_revision == "v2"
    assert window._workspace_view.quick_plan()["scene_goal"] == "新目标"
