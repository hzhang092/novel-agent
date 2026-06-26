import yaml

from app.storage.models import Project
from app.storage.project_files import create_project, load_character


def test_legacy_migration_replaces_stale_bak(qtbot, tmp_path, monkeypatch):
    from app.ui.main_window import MainWindow, QMessageBox

    proj_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    char_root = proj_dir / "characters"
    legacy_path = char_root / "legacy-1.yaml"
    legacy_path.write_text(
        yaml.safe_dump(
            {
                "core": {"id": "legacy-1", "name": "旧角色", "tier": "major"},
                "state": {"character_id": "legacy-1", "current_goal": "旧目标"},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    legacy_path.with_suffix(".yaml.bak").write_text("stale backup", encoding="utf-8")

    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args))
    window = MainWindow()
    qtbot.addWidget(window)

    window._migrate_legacy_characters(proj_dir, [legacy_path])

    assert "已迁移 1 个角色" in messages[0][2]
    assert not legacy_path.exists()
    assert (char_root / "legacy-1" / "definition.yaml").exists()
    assert load_character(proj_dir, "legacy-1").state.current_goal == "旧目标"
