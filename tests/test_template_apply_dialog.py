from app.utils.template_merge import TemplateMergeMode


def test_template_dialog_defaults_to_safe_fill_empty(qtbot):
    from app.ui.template_apply_dialog import TemplateApplyDialog

    dialog = TemplateApplyDialog()
    qtbot.addWidget(dialog)

    assert dialog.apply_world is True
    assert dialog.apply_style is True
    assert dialog.merge_mode == TemplateMergeMode.FILL_EMPTY
