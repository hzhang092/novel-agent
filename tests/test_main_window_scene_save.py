import asyncio

import pytest
from PySide6.QtWidgets import QMessageBox, QProgressBar

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
from app.pipeline.pipeline import AgentTraceEntry
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


def test_workflow_draft_refreshes_quick_outline_status(tmp_path, qtbot):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    quick = window._quick_outline_view
    quick.select_chapter("ch-1")
    assert "待写" in quick._card_widgets["ch-1"]["status"].text()

    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        status="draft",
        review={"overall_pass": True},
        scene_summary_raw={"summary": "完成"},
        draft_text="正文",
    )
    save_scene_generation_record(project_dir, record)

    window._on_workflow_draft(record)

    assert "草稿" in quick._card_widgets["ch-1"]["status"].text()
    assert quick.selected_chapter_id == "ch-1"

    assert window._on_approval_batch_approved("scene-1", "rev-1", [], [])
    assert "已批准" in quick._card_widgets["ch-1"]["status"].text()
    assert quick.selected_chapter_id == "ch-1"


def test_entering_quick_outline_refreshes_status(tmp_path, qtbot):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    quick = window._quick_outline_view
    quick.select_chapter("ch-1")

    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="rev-1",
            revision_number=1,
            status="draft",
            draft_text="正文",
        ),
    )
    assert "待写" in quick._card_widgets["ch-1"]["status"].text()

    window._set_experience_mode("quick")
    window._select_destination("outline")

    assert "草稿" in quick._card_widgets["ch-1"]["status"].text()
    assert quick.selected_chapter_id == "ch-1"


def test_quick_outline_status_refresh_defers_for_dirty_card(tmp_path, qtbot):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    quick = window._quick_outline_view
    quick.select_chapter("ch-1")
    quick.title_edit.setText("未保存标题")

    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        status="draft",
        draft_text="正文",
    )
    save_scene_generation_record(project_dir, record)
    window._on_workflow_draft(record)

    assert quick.title_edit.text() == "未保存标题"
    assert quick.is_dirty is True
    assert "待写" in quick._card_widgets["ch-1"]["status"].text()

    assert quick.discard_edits() is True
    assert quick.title_edit.text() == ""
    assert "草稿" in quick._card_widgets["ch-1"]["status"].text()
    assert quick.selected_chapter_id == "ch-1"


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
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        review={"overall_pass": True},
        scene_summary_raw={"summary": "完成"},
        draft_text="正文",
    )
    save_scene_generation_record(project_dir, record)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    workspace = window._workspace_view
    workspace.set_scene("scene-1", "ch-1")
    window._current_prose_version = "v1"
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


def test_quick_next_scene_uses_canonical_outline_query(tmp_path, qtbot, monkeypatch):
    project_dir = _project(tmp_path)
    volumes = load_all_volumes(project_dir)
    volumes[0].chapters.append(
        ChapterOutline(id="ch-2", scenes=[SceneOutline(id="scene-2")])
    )
    save_volume_outline(project_dir, volumes[0])
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("quick")
    window._workspace_view.set_scene("scene-1", "ch-1")
    monkeypatch.setattr(
        window._outline_view,
        "select_next_scene",
        lambda *_args: pytest.fail("hidden Deep outline must not drive Quick navigation"),
    )

    window._on_next_scene()

    assert window._workspace_view.current_scene_id == "scene-2"
    assert window._workspace_view.current_chapter_id == "ch-2"


def test_deep_next_scene_updates_outline_highlight(tmp_path, qtbot, monkeypatch):
    project_dir = _project(tmp_path)
    volumes = load_all_volumes(project_dir)
    volumes[0].chapters.append(
        ChapterOutline(id="ch-2", scenes=[SceneOutline(id="scene-2")])
    )
    save_volume_outline(project_dir, volumes[0])
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("deep")
    window._previous_destination = "workspace"
    window._workspace_view.set_scene("scene-1", "ch-1")
    activated = []
    monkeypatch.setattr(
        window._outline_view,
        "activate_scene",
        lambda scene_id, *, emit: activated.append((scene_id, emit)),
    )

    window._on_next_scene()

    assert activated == [("scene-2", False)]


def test_scene_selection_projects_chapter_identity_into_quick_writing(tmp_path, qtbot):
    project_dir = _project(tmp_path)
    volume = load_all_volumes(project_dir)[0]
    volume.chapters[0].title = "起点"
    volume.chapters[0].summary = "主角发现线索"
    volume.chapters.append(
        ChapterOutline(
            id="ch-2",
            title="追踪",
            scenes=[SceneOutline(id="scene-2")],
        )
    )
    save_volume_outline(project_dir, volume)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)

    window._on_scene_selected("scene-2")

    quick = window._workspace_view.findChild(QuickChapterView)
    assert "第 2 章：追踪" == quick.chapter_identity_label.text()
    assert "主角发现线索" in quick.previous_chapter_label.text()


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


def test_quick_start_approves_waiting_initial_plan(tmp_path, qtbot, monkeypatch):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("quick")
    window._select_destination("workspace")
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._workspace_view.set_generating(True)
    plan = ScenePlan(scene_id="scene-1", scene_goal="找到出口").model_dump(
        mode="json"
    )
    window._workspace_view.show_plan_checkpoint(plan)
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    workflow = window._application.scene_workflow
    workflow._plan_future = future
    workflow.state.scene_id = "scene-1"
    starts = []
    monkeypatch.setattr(window, "_on_generate_requested", starts.append)
    quick = window._workspace_view.findChild(QuickChapterView)

    quick.start_button.click()

    assert future.result() == (True, plan)
    assert starts == []
    assert not quick.start_button.isEnabled()
    loop.close()


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
    assert quick.start_button.isEnabled()

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
    window._refresh_prose_versions("ch-1", "scene-1", "v1")
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
    window._refresh_prose_versions("ch-1", "scene-1", "v1")
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
    assert quick.adjust_button.text() == "调整方案"
    assert window._pending_plan_patch is None
    assert not future.done()

    quick.adjust_button.click()
    quick.start_button.click()

    assert quick.goal_edit.isReadOnly()
    assert quick.start_button.text() == "生成写作方案"
    assert quick.start_button.isEnabled()
    assert not quick.adjust_button.isEnabled()
    assert len(warnings) == 1
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
    window._refresh_prose_versions("ch-1", "scene-1", "v1")
    quick = window._workspace_view.findChild(QuickChapterView)

    quick.adjust_button.click()
    assert window._pending_plan_patch is not None
    quick.show_review(False, "旧项目审查")
    quick.show_memory([{"description": "旧项目事实"}], [])

    window._bind_project_application(second_dir)

    assert window._pending_plan_patch is None
    assert window._workspace_view.current_scene_id is None
    assert window._workspace_view.quick_plan()["scene_goal"] == ""
    assert not quick.review_section.isVisible()
    assert not quick.memory_section.isVisible()
    assert quick.goal_edit.isReadOnly()
    assert quick.adjust_button.text() == "调整方案"
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
    window._refresh_prose_versions("ch-1", "scene-1", "v1")
    calls = []
    monkeypatch.setattr(
        window._application.scene_workflow,
        "regenerate",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    quick = window._workspace_view.findChild(QuickChapterView)

    quick.adjust_button.click()
    quick._advanced_actions["context"].trigger()
    window._on_plan_rejected()

    assert window._pending_plan_patch is None
    assert quick.goal_edit.isReadOnly()
    assert quick.adjust_button.text() == "调整方案"

    window._set_experience_mode("quick")
    window._select_destination("workspace")
    quick.adjust_button.click()
    quick._advanced_actions["context"].trigger()
    edited = record.scene_plan | {"ending_hook": "警报响起"}
    window._on_plan_approved(edited)

    assert len(calls) == 1
    assert window._pending_plan_patch is None
    assert quick.hook_edit.isReadOnly()
    assert quick.adjust_button.text() == "调整方案"
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

    window._on_prose_version_selected("v1")

    assert window._workspace_view.quick_plan()["scene_goal"] == ""


def test_late_workflow_callbacks_do_not_replace_new_scene_state(
    tmp_path, qtbot
):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    workspace = window._workspace_view
    workspace.set_scene("scene-1", "ch-1")
    observer = window._scene_workflow_observer("scene-1")

    workspace.set_scene("scene-2", "ch-2")
    workspace.set_prose_text("第二章正文")
    observer.plan({"scene_id": "scene-1", "scene_goal": "旧计划"})
    observer.prose("旧流式正文")
    observer.review(False, "旧审查")
    observer.memory("scene-1", "rev-1", [{"description": "旧事实"}], [])
    observer.draft(
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="rev-1",
            revision_number=1,
            draft_text="旧完整正文",
        )
    )

    quick = workspace.findChild(QuickChapterView)
    assert workspace.prose_text() == "第二章正文"
    assert workspace.quick_plan()["scene_goal"] == ""
    assert not quick.review_section.isVisible()
    assert not quick.memory_section.isVisible()


def test_quick_scene_activity_keeps_origin_identity_while_scene_guard_holds(
    tmp_path, qtbot
):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("quick")
    workspace = window._workspace_view
    workspace.set_scene("scene-1", "ch-1")
    observer = window._scene_workflow_observer("scene-1")

    observer.generating(True)
    observer.trace(
        [AgentTraceEntry(agent_name="Writer", stage="writer", status="running")]
    )

    assert window.statusBar().currentMessage() == "快速创作 · 第 1 章：正在写作…"

    workspace.set_scene("scene-2", "ch-2")
    observer.prose("origin prose")
    observer.trace(
        [
            AgentTraceEntry(
                agent_name="Reviewer", stage="reviewer", status="running"
            )
        ]
    )

    assert workspace.prose_text() == ""
    assert window.statusBar().currentMessage() == "快速创作 · 第 1 章：正在审查…"

    observer.generating(False)

    assert window.findChild(QProgressBar, "quick_activity_progress").isHidden()
    assert "第 1 章" in window.statusBar().currentMessage()


def test_quick_scene_activity_reports_failure_after_finishing_while_away(
    tmp_path, qtbot
):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("quick")
    workspace = window._workspace_view
    workspace.set_scene("scene-1", "ch-1")
    observer = window._scene_workflow_observer("scene-1")

    observer.generating(True)
    workspace.set_scene("scene-2", "ch-2")
    observer.generating(False)
    observer.status("生成失败")

    assert window.statusBar().currentMessage() == "第 1 章处理失败，可返回查看"


def test_quick_scene_activity_reports_cancellation_after_finishing_while_away(
    tmp_path, qtbot
):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._set_experience_mode("quick")
    workspace = window._workspace_view
    workspace.set_scene("scene-1", "ch-1")
    observer = window._scene_workflow_observer("scene-1")

    observer.generating(True)
    workspace.set_scene("scene-2", "ch-2")
    observer.generating(False)
    observer.status("已取消")

    assert window.statusBar().currentMessage() == "第 1 章处理已取消，可返回查看"


@pytest.mark.asyncio
async def test_stale_continuation_does_not_render_origin_after_scene_navigation(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    workspace = window._workspace_view
    workspace.set_scene("scene-1", "ch-1")
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        status="draft",
        review={"overall_pass": False, "summary": "origin review"},
        stale_input=True,
        draft_text="origin prose",
    )
    workflow = window._application.scene_workflow
    workflow.state.scene_id = "scene-1"

    async def continue_stale(_revision_id, observer=None):
        workspace.set_scene("scene-2", "ch-2")
        return record

    monkeypatch.setattr(workflow, "continue_stale", continue_stale)

    await window._continue_stale_record(record.revision_id)

    assert "origin review" not in workspace.review_summary
    assert workspace._status_label.text() != "已复核旧设定，可继续发布或重新生成"


def _revision_window(tmp_path, qtbot, *, review, stale_input=False):
    project_dir = _project(tmp_path)
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        status="draft",
        review=review,
        stale_input=stale_input,
        draft_text="origin prose",
    )
    save_scene_generation_record(project_dir, record)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._current_prose_version = "v1"
    window._show_quick_revision(record)
    return window, record


async def _flush_scheduled_task():
    await asyncio.sleep(0)
    await asyncio.sleep(0)


def _capture_blocked_warning(monkeypatch):
    warnings = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.warning",
        lambda *args: warnings.append(args),
    )
    return warnings


@pytest.mark.asyncio
async def test_quick_save_reports_a_blocked_operation(
    tmp_path, qtbot, monkeypatch
):
    window, _record = _revision_window(
        tmp_path, qtbot, review={"overall_pass": True, "summary": "通过"}
    )
    warnings = _capture_blocked_warning(monkeypatch)

    async def blocked(*_args, **_kwargs):
        raise OperationBlockedError("already running")

    monkeypatch.setattr(
        window._application.scene_workflow, "save_edited_draft", blocked
    )

    window._on_quick_save()
    await _flush_scheduled_task()

    assert "已有任务正在运行" in window._workspace_view._status_label.text()
    assert any("已有任务正在运行" in call[2] for call in warnings)


@pytest.mark.asyncio
async def test_quick_save_reports_an_unexpected_workflow_error(
    tmp_path, qtbot, monkeypatch
):
    window, _record = _revision_window(
        tmp_path, qtbot, review={"overall_pass": True, "summary": "通过"}
    )
    window._set_experience_mode("quick")
    warnings = _capture_blocked_warning(monkeypatch)

    async def failing(*_args, **_kwargs):
        raise RuntimeError("storage failed")

    monkeypatch.setattr(
        window._application.scene_workflow, "save_edited_draft", failing
    )

    window._on_quick_save()
    await _flush_scheduled_task()

    assert any("storage failed" in call[2] for call in warnings)
    assert "处理失败" in window.statusBar().currentMessage()


@pytest.mark.asyncio
async def test_project_rebind_cancels_a_workflow_operation_before_it_starts(
    tmp_path, qtbot
):
    first_dir = _project(tmp_path / "first")
    second_dir = _project(tmp_path / "second")
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(first_dir)
    old_application = window._application
    ran = []

    async def queued_operation():
        ran.append(True)

    task = window._schedule_workflow_task(
        queued_operation,
        application=old_application,
        scene_id="scene-1",
    )
    window._bind_project_application(second_dir)
    await asyncio.sleep(0)

    assert task.cancelled()
    assert ran == []


@pytest.mark.asyncio
async def test_modified_draft_analysis_reports_a_blocked_operation(
    tmp_path, qtbot, monkeypatch
):
    window, record = _revision_window(
        tmp_path, qtbot, review={"overall_pass": False, "summary": "需要修改"}
    )
    workspace = window._workspace_view
    workspace.set_prose_text("edited prose")
    warnings = _capture_blocked_warning(monkeypatch)
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )

    async def blocked(*_args, **_kwargs):
        raise OperationBlockedError("already running")

    monkeypatch.setattr(
        window._application.scene_workflow, "save_edited_draft", blocked
    )

    window._continue_with_edited_draft(workspace, record)
    await _flush_scheduled_task()

    assert "已有任务正在运行" in workspace._status_label.text()
    assert any("已有任务正在运行" in call[2] for call in warnings)


@pytest.mark.asyncio
async def test_continue_review_rejection_reports_and_restores_control(
    tmp_path, qtbot, monkeypatch
):
    window, record = _revision_window(
        tmp_path, qtbot, review={"overall_pass": False, "summary": "需要修改"}
    )
    workflow = window._application.scene_workflow
    warnings = _capture_blocked_warning(monkeypatch)

    async def blocked(*_args, **_kwargs):
        raise OperationBlockedError("already running")

    monkeypatch.setattr(workflow, "continue_review", blocked)
    assert window._workspace_view.continue_review_is_visible is True

    window._on_continue_review_requested()
    await _flush_scheduled_task()

    assert "已有任务正在运行" in window._workspace_view._status_label.text()
    assert window._workspace_view.continue_review_is_visible is True
    assert any("已有任务正在运行" in call[2] for call in warnings)


@pytest.mark.asyncio
async def test_stale_continuation_rejection_reports_and_restores_control(
    tmp_path, qtbot, monkeypatch
):
    window, _record = _revision_window(
        tmp_path,
        qtbot,
        review={"overall_pass": True, "summary": "通过"},
        stale_input=True,
    )
    workflow = window._application.scene_workflow
    warnings = _capture_blocked_warning(monkeypatch)

    async def blocked(*_args, **_kwargs):
        raise OperationBlockedError("already running")

    monkeypatch.setattr(workflow, "continue_stale", blocked)
    assert window._workspace_view.continue_review_is_visible is True

    window._on_continue_review_requested()
    await _flush_scheduled_task()

    assert "已有任务正在运行" in window._workspace_view._status_label.text()
    assert window._workspace_view.continue_review_is_visible is True
    assert any("已有任务正在运行" in call[2] for call in warnings)


def test_run_completion_restores_controls_after_browsing_away(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    workspace = window._workspace_view
    workspace.set_scene("scene-1", "ch-1")
    observer = window._scene_workflow_observer("scene-1")
    observer.generating(True)

    workspace.set_scene("scene-2", "ch-2")
    selected = SceneGenerationRecord(
        scene_id="scene-2",
        revision_id="rev-2",
        revision_number=1,
        draft_text="第二章正文",
    )
    monkeypatch.setattr(window, "_selected_generation_record", lambda: selected)
    window._application.scene_workflow.state.active = False
    observer.generating(False)

    assert workspace._generating is False
    assert window._application.scene_workflow.state.draft_record is selected


def test_returning_to_scene_restores_pending_plan(tmp_path, qtbot):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    workflow = window._application.scene_workflow
    workflow.state.scene_id = "scene-1"
    workflow.state.planner_decision = {
        "scene_id": "scene-1",
        "scene_goal": "等待确认",
    }
    loop = asyncio.new_event_loop()
    workflow._plan_future = loop.create_future()

    window._workspace_view.set_scene("scene-2", "ch-2")
    window._on_scene_selected("scene-1")

    assert window._workspace_view.quick_plan()["scene_goal"] == "等待确认"
    workflow._plan_future.cancel()
    loop.close()


def test_unwritten_quick_start_starts_initial_generation(tmp_path, qtbot, monkeypatch):
    project_dir = _project(tmp_path)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._workspace_view.set_scene("scene-1", "ch-1")
    starts = []
    monkeypatch.setattr(
        window,
        "_on_generate_requested",
        lambda scene_id: starts.append(scene_id),
    )

    quick = window._workspace_view.findChild(QuickChapterView)
    assert quick.start_button.isEnabled()

    window._on_quick_start("ch-1", "scene-1")

    assert starts == ["scene-1"]


def test_existing_quick_revision_cannot_start_fresh_generation(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _project(tmp_path)
    for revision_number in (1, 2):
        save_scene_generation_record(
            project_dir,
            SceneGenerationRecord(
                scene_id="scene-1",
                revision_id=f"rev-{revision_number}",
                revision_number=revision_number,
                status="draft",
                draft_text=f"正文 {revision_number}",
            ),
        )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._workspace_view.set_prose_versions(["v2", "v1"], "v2")
    window._current_prose_version = "v2"
    starts = []
    monkeypatch.setattr(
        window,
        "_on_generate_requested",
        lambda scene_id: starts.append(scene_id),
    )

    quick = window._workspace_view.findChild(QuickChapterView)
    assert not quick.start_button.isEnabled()
    assert quick.regenerate_button.isEnabled()

    window._on_quick_start("ch-1", "scene-1")

    assert starts == []


def test_existing_canonical_revision_blocks_start_with_stale_ui(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _project(tmp_path)
    save_scene_generation_record(
        project_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="rev-1",
            revision_number=1,
            status="draft",
            draft_text="正文",
        ),
    )
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._workspace_view.set_prose_versions([], "")
    window._current_prose_version = ""
    starts = []
    monkeypatch.setattr(
        window,
        "_on_generate_requested",
        lambda scene_id: starts.append(scene_id),
    )

    window._on_quick_start("ch-1", "scene-1")

    assert starts == []


def test_legacy_prose_selection_cannot_reuse_latest_generation_record(
    tmp_path, qtbot, monkeypatch
):
    project_dir = _project(tmp_path)
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        review={"overall_pass": True},
        scene_summary_raw={"summary": "完成"},
        draft_text="版本正文",
    )
    save_scene_generation_record(project_dir, record)
    chapter_dir = project_dir / "scenes" / "ch-1"
    (chapter_dir / "scene-1.v1.md").write_text("版本正文", encoding="utf-8")
    (chapter_dir / "scene-1.md").write_text("旧正文", encoding="utf-8")
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._current_prose_version = "v1"
    warnings = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.warning",
        lambda *args: warnings.append(args),
    )

    window._on_prose_version_selected("legacy")
    window._on_set_active_prose_version("legacy")

    assert window._workspace_view.prose_text() == "旧正文"
    assert window._selected_generation_record() is None
    assert warnings


def test_quick_approval_rejects_failed_review(tmp_path, qtbot, monkeypatch):
    project_dir = _project(tmp_path)
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        revision_number=1,
        review={"overall_pass": False, "summary": "需要修改"},
        scene_summary_raw={"summary": "完成"},
        draft_text="正文",
    )
    save_scene_generation_record(project_dir, record)
    window = MainWindow(quick_creation_enabled=True)
    qtbot.addWidget(window)
    window._bind_project_application(project_dir)
    window._workspace_view.set_scene("scene-1", "ch-1")
    window._current_prose_version = "v1"
    window._show_quick_revision(record)
    published, warnings = [], []
    monkeypatch.setattr(
        window._application.scene_workflow,
        "publish",
        lambda *args: published.append(args),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.warning",
        lambda *args: warnings.append(args),
    )

    assert window._on_quick_approve() is False
    assert published == []
    assert warnings
