from PySide6.QtWidgets import QLabel, QPushButton

from app.storage.models import (
    Character,
    CharacterCore,
    CharacterState,
    CharacterTier,
    Project,
    StyleGuide,
    WorldSetting,
)
from app.storage.project_files import (
    create_project,
    save_character,
    save_style_guide,
    save_world_setting,
)


def test_empty_bible_opens_useful_overview(tmp_path, qtbot):
    from app.ui.bible_editor import BibleEditorView

    project_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)

    assert [editor._tabs.tabText(i) for i in range(editor._tabs.count())] == [
        "概览",
        "世界设定",
        "角色",
        "写作风格",
    ]
    assert editor._tabs.currentIndex() == 0
    assert any(
        "构建你的故事设定集" in label.text()
        for label in editor._tabs.currentWidget().findChildren(QLabel)
    )
    assert {
        button.text()
        for button in editor._tabs.currentWidget().findChildren(QPushButton)
    } >= {"创建角色", "添加世界设定", "设置写作风格", "应用故事模板"}


def test_overview_create_character_action_opens_editor_and_starts_draft(
    tmp_path, qtbot
):
    from app.ui.bible_editor import BibleEditorView

    project_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)

    create_button = next(
        button
        for button in editor._overview_tab.findChildren(QPushButton)
        if button.text() == "创建角色"
    )
    create_button.click()

    assert editor._tabs.currentWidget() is editor._character_tab
    assert editor._character_tab._list.count() == 1
    assert editor._overview_empty.isHidden()
    assert not editor._overview_summary.isHidden()


def test_overview_set_style_action_opens_style_and_focuses_first_control(
    tmp_path, qtbot
):
    from app.ui.bible_editor import BibleEditorView

    project_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    editor.show()

    style_button = next(
        button
        for button in editor._overview_tab.findChildren(QPushButton)
        if button.text() == "设置写作风格"
    )
    style_button.click()

    assert editor._tabs.currentWidget() is editor._style_tab
    assert editor.focusWidget() is editor._pacing_slider


def test_overview_template_action_opens_existing_template_dialog(
    tmp_path, qtbot, monkeypatch
):
    from app.ui.bible_editor import BibleEditorView
    from app.ui.template_apply_dialog import TemplateApplyDialog

    project_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    opened = []
    monkeypatch.setattr(
        TemplateApplyDialog,
        "exec",
        lambda _dialog: opened.append(True) or 0,
    )

    template_button = next(
        button
        for button in editor._overview_tab.findChildren(QPushButton)
        if button.text() == "应用故事模板"
    )
    template_button.click()

    assert opened == [True]


def test_nonempty_overview_summarizes_current_bible_values(tmp_path, qtbot):
    from app.ui.bible_editor import BibleEditorView

    project_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    save_world_setting(project_dir, WorldSetting(geography="群山"))
    save_style_guide(
        project_dir,
        StyleGuide(pacing="偏快", tone="严肃", pov="第三人称"),
    )
    save_character(
        project_dir,
        Character(
            core=CharacterCore(
                id="char-1", name="林轩", tier=CharacterTier.MAJOR
            ),
            state=CharacterState(character_id="char-1"),
        ),
    )
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)

    summaries = [label.text() for label in editor._overview_summary.findChildren(QLabel)]
    assert not editor._overview_summary.isHidden()
    assert any("4 个概览部分 · 0 个元素" in text for text in summaries)
    assert any("1 个角色" in text and "1 位主要角色" in text for text in summaries)
    assert any("偏快 · 严肃 · 第三人称" in text for text in summaries)

    editor._world_tab._overview_geography.setPlainText("群山与海洋")
    editor._pacing_slider.setValue(5)
    editor._character_tab._core_tier.setCurrentIndex(
        editor._character_tab._core_tier.findData(CharacterTier.SUPPORTING)
    )
    summaries = [label.text() for label in editor._overview_summary.findChildren(QLabel)]
    assert any("很快 · 严肃 · 第三人称" in text for text in summaries)
    assert any("0 位主要角色" in text and "1 位配角" in text for text in summaries)


def test_selected_story_bible_tab_restores_on_reopen(tmp_path, qtbot):
    from app.ui.bible_editor import BibleEditorView

    project_dir = create_project(tmp_path, Project(title="测试", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(project_dir)
    editor._tabs.setCurrentWidget(editor._style_tab)
    qtbot.wait(200)

    reopened = BibleEditorView()
    qtbot.addWidget(reopened)
    reopened.load_project_dir(project_dir)

    assert reopened._tabs.currentWidget() is reopened._style_tab
