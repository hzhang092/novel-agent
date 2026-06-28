from types import SimpleNamespace

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
    save_scene_generation_record,
    save_volume_outline,
)


def test_save_generated_scene_marks_downstream_stale_without_approval_items(
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

    assert load_scene_generation_record(proj_dir, "scene-3").status == "stale"
