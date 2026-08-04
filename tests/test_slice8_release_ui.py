from PySide6.QtWidgets import QMessageBox, QWidget

from app.providers.config import ProviderConfigurationError
from app.ui.create_project_dialog import CreateProjectDialog
from app.ui.main_window import MainWindow


def _visible_text(widget):
    texts = []
    for child in widget.findChildren(QWidget):
        text = getattr(child, "text", None)
        if callable(text):
            texts.append(text())
    return texts


def test_release_ui_uses_creation_names_and_has_concise_help(
    qtbot, tmp_path, monkeypatch
):
    monkeypatch.delenv("NOVELFORGE_QUICK_CREATION", raising=False)
    window = MainWindow()
    dialog = CreateProjectDialog(
        default_storage_dir=tmp_path,
        quick_creation_enabled=True,
    )
    qtbot.addWidget(window)
    qtbot.addWidget(dialog)

    assert not window._experience_switch.isHidden()
    assert not dialog.quick_button.isHidden()
    all_text = " ".join(_visible_text(window) + _visible_text(dialog))
    assert "快速创作" in all_text
    assert "深度创作" in all_text
    assert "Simple" not in all_text
    assert "Professional" not in all_text

    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, message: messages.append((title, message)),
    )
    window._help_action.trigger()

    assert messages
    help_text = messages[0][1]
    assert "故事模板" in help_text and "生成指南" in help_text
    assert "保存修改" in help_text and "批准本章" in help_text


def test_no_provider_error_points_to_llm_settings_and_retry(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window._scene_workflow_observer().error(
        ProviderConfigurationError("尚未配置可用模型。")
    )

    assert messages
    assert "LLM 设置" in messages[0][1]
    assert "重试" in messages[0][1]
