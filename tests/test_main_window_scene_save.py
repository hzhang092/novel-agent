from app.storage.models import ChapterOutline, Project, SceneOutline, VolumeOutline
from app.storage.project_files import create_project, save_scene_writer_draft, save_volume_outline
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
