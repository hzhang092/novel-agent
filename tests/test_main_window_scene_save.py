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
    load_scene_prose,
    load_scene_generation_record,
    save_scene_generation_record,
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
