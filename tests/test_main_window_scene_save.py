import asyncio
from types import SimpleNamespace

import pytest

from app.storage.models import (
    ChapterOutline,
    Project,
    SceneGenerationRecord,
    SceneOutline,
    VolumeOutline,
)
from app.storage.project_files import (
    create_project,
    load_scene_generation_record,
    load_scene_prose,
    load_scene_writer_draft,
    save_scene_generation_record,
    save_scene_writer_draft,
    save_volume_outline,
)


def test_save_generated_scene_keeps_active_timeline_unchanged(
    qtbot, tmp_path, monkeypatch
):
    from app.ui.main_window import MainWindow

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    scenes = [
        SceneOutline(id="scene-1", title="第一场"),
        SceneOutline(id="scene-2", title="第二场"),
        SceneOutline(id="scene-3", title="第三场"),
    ]
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[ChapterOutline(id="ch-1", title="第一章", scenes=scenes)],
        ),
    )
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(scene_id="scene-3", revision_id="rev-3", status="current"),
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = proj_dir
    monkeypatch.setattr(window, "_refresh_prose_versions", lambda *args: [])
    save_scene_writer_draft(proj_dir, "scene-2", "新正文")

    window._save_generated_scene(
        SimpleNamespace(
            scene_id="scene-2",
            prose="新正文",
            plan=None,
            character_intents={},
            review=None,
            generated_with={},
            extracted_facts=[],
            state_changes=[],
        )
    )

    assert load_scene_generation_record(proj_dir, "scene-3").status == "current"
    assert load_scene_generation_record(proj_dir, "scene-2").status == "draft"
    assert load_scene_prose(proj_dir, "ch-1", "scene-2") == ""
    assert load_scene_writer_draft(proj_dir, "scene-2") == ""


def test_writer_recovery_is_promoted_and_visible_after_restart(
    qtbot, tmp_path, monkeypatch
):
    from app.ui.main_window import MainWindow

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    save_scene_writer_draft(proj_dir, "scene-1", "崩溃前完成的正文")
    notices = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda *args: notices.append(args),
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = proj_dir
    workspace = window.views["workspace"]
    workspace._current_chapter_id = "ch-1"
    workspace._current_scene_id = "scene-1"
    window._load_scene_prose_into_editor(workspace, "ch-1", "scene-1")

    recovered = load_scene_generation_record(proj_dir, "scene-1")
    assert recovered.status == "draft"
    assert recovered.draft_text == "崩溃前完成的正文"
    assert load_scene_writer_draft(proj_dir, "scene-1") == ""
    assert workspace.editor.toPlainText() == "崩溃前完成的正文"
    assert notices

    reopened = MainWindow()
    qtbot.addWidget(reopened)
    reopened._current_project_dir = proj_dir
    reopened_workspace = reopened.views["workspace"]
    reopened_workspace._current_chapter_id = "ch-1"
    reopened_workspace._current_scene_id = "scene-1"
    reopened._load_scene_prose_into_editor(
        reopened_workspace, "ch-1", "scene-1"
    )

    assert reopened_workspace.editor.toPlainText() == "崩溃前完成的正文"
    assert reopened_workspace.editor.current_version() == "v1"


def test_writer_recovery_does_not_duplicate_an_already_saved_draft(
    qtbot, tmp_path, monkeypatch
):
    from app.ui.main_window import MainWindow, _save_versioned_prose
    from app.storage.project_files import list_scene_prose_versions

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    _save_versioned_prose(proj_dir, "ch-1", "scene-1", "已接受正文", 1)
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_number=1,
            status="current",
            draft_text="已接受正文",
        ),
    )
    _save_versioned_prose(proj_dir, "ch-1", "scene-1", "已保存的恢复正文", 2)
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_number=2,
            status="draft",
            draft_text="已保存的恢复正文",
        ),
    )
    save_scene_writer_draft(proj_dir, "scene-1", "已保存的恢复正文")
    monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *args: None)

    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = proj_dir
    workspace = window.views["workspace"]
    workspace._current_chapter_id = "ch-1"
    workspace._current_scene_id = "scene-1"
    window._load_scene_prose_into_editor(workspace, "ch-1", "scene-1")

    assert list_scene_prose_versions(proj_dir, "ch-1", "scene-1") == ["v2", "v1"]
    assert workspace.editor.current_version() == "v2"
    assert workspace.editor.toPlainText() == "已保存的恢复正文"
    assert load_scene_writer_draft(proj_dir, "scene-1") == ""


def test_writer_recovery_reuses_a_version_written_before_its_record(
    qtbot, tmp_path, monkeypatch
):
    from app.ui.main_window import MainWindow, _save_versioned_prose
    from app.storage.project_files import list_scene_prose_versions

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    _save_versioned_prose(proj_dir, "ch-1", "scene-1", "已接受正文", 1)
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_number=1,
            status="current",
            draft_text="已接受正文",
        ),
    )
    _save_versioned_prose(proj_dir, "ch-1", "scene-1", "记录前中断的正文", 2)
    save_scene_writer_draft(proj_dir, "scene-1", "记录前中断的正文")
    monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *args: None)

    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = proj_dir
    workspace = window.views["workspace"]
    workspace._current_chapter_id = "ch-1"
    workspace._current_scene_id = "scene-1"
    window._load_scene_prose_into_editor(workspace, "ch-1", "scene-1")

    recovered = load_scene_generation_record(proj_dir, "scene-1", version="v2")
    assert recovered.status == "draft"
    assert recovered.draft_text == "记录前中断的正文"
    assert list_scene_prose_versions(proj_dir, "ch-1", "scene-1") == ["v2", "v1"]
    assert workspace.editor.current_version() == "v2"
    assert workspace.editor.toPlainText() == "记录前中断的正文"
    assert load_scene_writer_draft(proj_dir, "scene-1") == ""


def test_writer_recovery_repairs_a_truncated_generation_record(
    qtbot, tmp_path, monkeypatch
):
    from app.ui.main_window import MainWindow, _save_versioned_prose
    from app.storage.project_files import list_scene_prose_versions

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    _save_versioned_prose(proj_dir, "ch-1", "scene-1", "记录写入时中断的正文", 1)
    record_path = proj_dir / "scenes" / "ch-1" / "scene-1.v1.gen.json"
    record_path.write_text('{"scene_id":', encoding="utf-8")
    save_scene_writer_draft(proj_dir, "scene-1", "记录写入时中断的正文")
    monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *args: None)

    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = proj_dir
    workspace = window.views["workspace"]
    workspace._current_chapter_id = "ch-1"
    workspace._current_scene_id = "scene-1"
    window._load_scene_prose_into_editor(workspace, "ch-1", "scene-1")

    recovered = load_scene_generation_record(proj_dir, "scene-1", version="v1")
    assert recovered.status == "draft"
    assert recovered.draft_text == "记录写入时中断的正文"
    assert list_scene_prose_versions(proj_dir, "ch-1", "scene-1") == ["v1"]
    assert workspace.editor.toPlainText() == "记录写入时中断的正文"
    assert load_scene_writer_draft(proj_dir, "scene-1") == ""


def test_writer_recovery_ignores_an_unrelated_truncated_record(
    qtbot, tmp_path, monkeypatch
):
    from app.ui.main_window import MainWindow, _save_versioned_prose
    from app.storage.project_files import list_scene_prose_versions

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    _save_versioned_prose(proj_dir, "ch-1", "scene-1", "旧正文", 1)
    corrupt_path = proj_dir / "scenes" / "ch-1" / "scene-1.v1.gen.json"
    corrupt_path.write_text('{"scene_id":', encoding="utf-8")
    _save_versioned_prose(proj_dir, "ch-1", "scene-1", "完整恢复正文", 2)
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_number=2,
            status="draft",
            draft_text="完整恢复正文",
            scene_plan={"purpose": "保留的计划"},
        ),
    )
    save_scene_writer_draft(proj_dir, "scene-1", "完整恢复正文")
    monkeypatch.setattr("app.ui.main_window.QMessageBox.information", lambda *args: None)

    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = proj_dir
    workspace = window.views["workspace"]
    workspace._current_chapter_id = "ch-1"
    workspace._current_scene_id = "scene-1"
    window._load_scene_prose_into_editor(workspace, "ch-1", "scene-1")

    recovered = load_scene_generation_record(proj_dir, "scene-1", version="v2")
    assert recovered.scene_plan == {"purpose": "保留的计划"}
    assert list_scene_prose_versions(proj_dir, "ch-1", "scene-1") == ["v2", "v1"]
    assert workspace.editor.current_version() == "v2"
    assert load_scene_writer_draft(proj_dir, "scene-1") == ""


def test_finalization_writes_replace_prose_and_record_atomically(
    tmp_path, monkeypatch
):
    from app.ui.main_window import _save_versioned_prose

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    prose_path = proj_dir / "scenes" / "ch-1" / "scene-1.v1.md"
    _save_versioned_prose(proj_dir, "ch-1", "scene-1", "完整正文", 1)
    old_record = SceneGenerationRecord(
        scene_id="scene-1", revision_number=1, draft_text="完整正文"
    )
    save_scene_generation_record(proj_dir, old_record)
    record_path = proj_dir / "scenes" / "ch-1" / "scene-1.v1.gen.json"
    old_record_json = record_path.read_text(encoding="utf-8")

    def fail_replace(*args):
        raise OSError("crash")

    monkeypatch.setattr("app.ui.main_window.os.replace", fail_replace)
    with pytest.raises(OSError, match="crash"):
        _save_versioned_prose(proj_dir, "ch-1", "scene-1", "截断正文", 1)
    assert prose_path.read_text(encoding="utf-8") == "完整正文"

    with pytest.raises(OSError, match="crash"):
        save_scene_generation_record(
            proj_dir,
            SceneGenerationRecord(
                scene_id="scene-1", revision_number=1, draft_text="截断正文"
            ),
        )
    assert record_path.read_text(encoding="utf-8") == old_record_json
    assert not list((proj_dir / "scenes" / "ch-1").glob("*.tmp"))


def test_fact_approval_keeps_corrupt_canon_file_unchanged(qtbot, tmp_path, monkeypatch):
    from app.ui.main_window import MainWindow

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    save_scene_generation_record(
        proj_dir,
        SceneGenerationRecord(
            scene_id="scene-1",
            revision_id="rev-1",
            status="draft",
            review={"overall_pass": True},
        ),
    )
    facts_path = proj_dir / "canon" / "facts.yaml"
    facts_path.write_text("- description: [broken\n", encoding="utf-8")
    original = facts_path.read_bytes()

    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = proj_dir
    monkeypatch.setattr("app.ui.main_window.QMessageBox.critical", lambda *args: None)
    workspace = window.views["workspace"]
    fact = {"description": "新事实", "category": "world"}
    workspace.fact_approval.show_items("scene-1", "rev-1", [fact], [])

    window._on_approval_batch_approved(
        "scene-1",
        "rev-1",
        [fact],
        [],
    )

    assert facts_path.read_bytes() == original
    assert not workspace.fact_approval.isHidden()
    assert workspace.fact_approval._facts == [fact]


@pytest.mark.asyncio
async def test_analysis_saves_scene_summary_on_draft_record(qtbot, tmp_path, monkeypatch):
    from app.ui.main_window import MainWindow

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_volume_outline(
        proj_dir,
        VolumeOutline(
            id="vol-1",
            title="第一卷",
            chapters=[
                ChapterOutline(
                    id="ch-1",
                    title="第一章",
                    scenes=[SceneOutline(id="scene-1", title="第一场")],
                )
            ],
        ),
    )
    record = SceneGenerationRecord(
        scene_id="scene-1",
        revision_id="rev-1",
        status="draft",
        review={"overall_pass": True},
    )
    save_scene_generation_record(proj_dir, record)
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = proj_dir
    workspace = window.views["workspace"]
    result = SimpleNamespace(
        scene_id="scene-1",
        extracted_facts=[],
        state_changes=[],
        scene_summary=None,
    )

    class Pipeline:
        async def analyze_draft(self, project_dir, analyzed, **kwargs):
            analyzed.scene_summary = {
                "scene_id": "scene-1",
                "summary": "saved summary marker",
            }

    class Provider:
        async def close(self):
            pass

    monkeypatch.setattr("app.providers.config.load_provider_config", lambda: {})
    monkeypatch.setattr(
        "app.providers.config.get_provider_for_step", lambda step, config: Provider()
    )

    await window._analyze_and_offer_publication(
        Pipeline(), result, record, workspace, lambda trace: None
    )

    saved = load_scene_generation_record(proj_dir, "scene-1", revision_id="rev-1")
    assert saved.scene_summary_raw["summary"] == "saved summary marker"


@pytest.mark.asyncio
async def test_detached_analysis_failure_restores_visible_retry(qtbot, monkeypatch):
    from app.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    workspace = window.views["workspace"]
    workspace._continue_review_btn.hide()

    async def fail_analysis(*args, **kwargs):
        raise RuntimeError("summary extraction failed")

    monkeypatch.setattr(window, "_analyze_and_offer_publication", fail_analysis)
    window._schedule_analysis_with_retry(
        object(), object(), object(), workspace, lambda trace: None
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert workspace._status_label.text() == "记忆分析失败"
    assert not workspace._continue_review_btn.isHidden()
    assert "草稿已保存，可重试" in workspace._review_label.text()


def test_successful_fact_approval_clears_panel(qtbot, tmp_path, monkeypatch):
    from app.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window._current_project_dir = tmp_path
    workspace = window.views["workspace"]
    fact = {"description": "新事实", "category": "world"}
    workspace.fact_approval.show_items("scene-1", "rev-1", [fact], [])
    monkeypatch.setattr(
        "app.storage.timeline_repository.publish_scene_revision",
        lambda *args: None,
    )
    monkeypatch.setattr(window, "_find_chapter_for_scene", lambda scene_id: None)

    window._on_approval_batch_approved("scene-1", "rev-1", [fact], [])

    assert workspace.fact_approval.isHidden()
    assert workspace.fact_approval._facts == []
