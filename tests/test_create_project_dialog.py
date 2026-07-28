from app.ui.create_project_dialog import CreateProjectDialog


def test_create_project_dialog_returns_storage_dir(qtbot, tmp_path):
    dialog = CreateProjectDialog(default_storage_dir=tmp_path)
    qtbot.addWidget(dialog)

    dialog.title_edit.setText("测试小说")
    dialog.storage_dir_edit.setText(str(tmp_path / "custom"))
    dialog._validate_and_accept()

    result = dialog.get_result()
    assert result is not None
    assert result["storage_dir"] == str(tmp_path / "custom")


def test_flagged_dialog_offers_quick_setup_without_genre_or_provider(qtbot, tmp_path):
    dialog = CreateProjectDialog(default_storage_dir=tmp_path, quick_creation_enabled=True)
    qtbot.addWidget(dialog)

    assert dialog.quick_button.text().startswith("快速构思故事")
    dialog.quick_button.click()
    dialog.storage_dir_edit.setText(str(tmp_path))
    dialog._validate_and_accept()

    result = dialog.get_result()
    assert result == {"title": "", "storage_dir": str(tmp_path), "creation_mode": "quick"}
    assert not hasattr(dialog, "genre_combo")
    assert not hasattr(dialog, "provider_combo")
