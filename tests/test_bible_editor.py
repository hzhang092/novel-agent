"""Integration tests for Bible editor: load → edit → save → reload round-trip."""

import pytest
import yaml

from app.storage.models import Project
from app.storage.project_files import (
    create_project,
    load_project,
    save_style_guide,
    save_world_setting,
)


def test_bible_dirty_state_tracks_semantic_world_and_style_changes(tmp_path, qtbot):
    from app.ui.bible_editor import BibleEditorView

    proj_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)

    assert editor.is_dirty is False

    editor._geo_edit.setPlainText("新地理")
    assert editor.is_dirty is True
    editor._geo_edit.clear()
    assert editor.is_dirty is False

    editor._notes_edit.setPlainText("新风格")
    assert editor.is_dirty is True


def test_bible_save_all_persists_dirty_scopes_and_clears_state(tmp_path, qtbot):
    from app.storage.models import Character, CharacterCore, CharacterState
    from app.storage.project_files import load_character, save_character
    from app.ui.bible_editor import BibleEditorView

    proj_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-1", name="林轩"),
            state=CharacterState(character_id="char-1"),
        ),
    )
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._geo_edit.setPlainText("新地理")
    editor._notes_edit.setPlainText("新风格")
    editor._character_tab._core_name.setText("林轩改")

    assert editor.save_all() is True
    assert editor.is_dirty is False
    loaded = load_project(proj_dir)
    assert loaded.world_setting.geography == "新地理"
    assert loaded.style_guide.freeform_notes == "新风格"
    assert load_character(proj_dir, "char-1").core.name == "林轩改"


def test_bible_save_all_writes_only_dirty_sections(tmp_path, qtbot, monkeypatch):
    from app.ui.bible_editor import BibleEditorView

    proj_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._geo_edit.setPlainText("新地理")
    calls = []
    monkeypatch.setattr(
        "app.ui.bible_editor.save_world_setting",
        lambda *_args, **_kwargs: calls.append("world"),
    )
    monkeypatch.setattr(
        "app.ui.bible_editor.save_style_guide",
        lambda *_args, **_kwargs: calls.append("style"),
    )

    assert editor.save_all() is True
    assert calls == ["world"]


def test_template_fill_empty_uses_current_form_without_saving(tmp_path, qtbot):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    from app.ui.bible_editor import BibleEditorView
    from app.ui.template_apply_dialog import TemplateApplyDialog

    proj_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._geo_edit.setPlainText("我的地理")

    def accept_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, TemplateApplyDialog)
        dialog.accept()

    QTimer.singleShot(0, accept_dialog)
    editor._template_btn.click()

    assert editor._gather_world().geography == "我的地理"
    assert editor._gather_style().pacing == "很快"
    assert editor._gather_style().dialogue_density == "适中"
    assert editor.is_dirty is True
    assert load_project(proj_dir).world_setting.geography == ""


def test_cancelled_template_application_changes_nothing(tmp_path, qtbot):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    from app.ui.bible_editor import BibleEditorView
    from app.ui.template_apply_dialog import TemplateApplyDialog

    proj_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._geo_edit.setPlainText("我的地理")
    before_world = editor._gather_world()
    before_style = editor._gather_style()

    def reject_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, TemplateApplyDialog)
        dialog.reject()

    QTimer.singleShot(0, reject_dialog)
    editor._template_btn.click()

    assert editor._gather_world() == before_world
    assert editor._gather_style() == before_style


def test_replace_template_requires_explicit_confirmation(tmp_path, qtbot, monkeypatch):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from app.ui.bible_editor import BibleEditorView
    from app.ui.template_apply_dialog import TemplateApplyDialog

    proj_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)
    editor._geo_edit.setPlainText("我的地理")
    before = editor._gather_world()

    def choose_replace():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, TemplateApplyDialog)
        dialog._replace.setChecked(True)
        dialog.accept()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    QTimer.singleShot(0, choose_replace)
    editor._template_btn.click()

    assert editor._gather_world() == before


def test_character_dirty_state_propagates_to_bible(tmp_path, qtbot):
    from app.storage.models import Character, CharacterCore, CharacterState
    from app.storage.project_files import save_character
    from app.ui.bible_editor import BibleEditorView

    proj_dir = create_project(tmp_path, Project(title="测试项目", genre="玄幻"))
    save_character(
        proj_dir,
        Character(
            core=CharacterCore(id="char-1", name="林轩"),
            state=CharacterState(character_id="char-1"),
        ),
    )
    editor = BibleEditorView()
    qtbot.addWidget(editor)
    editor.load_project_dir(proj_dir)

    editor._character_tab._core_name.setText("林轩改")

    assert editor._world_dirty is False
    assert editor._style_dirty is False
    assert editor.is_dirty is True


def test_loading_empty_power_system_clears_previous_project_values(tmp_path, qtbot):
    from app.storage.models import PowerSystem, WorldSetting
    from app.ui.bible_editor import BibleEditorView

    first_dir = create_project(tmp_path / "first", Project(title="一", genre="玄幻"))
    save_world_setting(
        first_dir,
        WorldSetting(power_system=PowerSystem(realms=["炼气"])),
    )
    second_dir = create_project(tmp_path / "second", Project(title="二", genre="都市"))
    editor = BibleEditorView()
    qtbot.addWidget(editor)

    editor.load_project_dir(first_dir)
    editor.load_project_dir(second_dir)

    assert editor._gather_world().power_system is None


def test_world_setting_save_load_round_trip(tmp_path):
    """Save a full WorldSetting, reload, verify all fields preserved."""
    project = Project(title="测试项目", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import PowerSystem, WorldSetting

    world = WorldSetting(
        geography="测试地理",
        power_system=PowerSystem(
            realms=["炼气", "筑基", "金丹"],
            abilities={"炼气": "灵气感知", "筑基": "御剑飞行", "金丹": "金丹领域"},
            limitations=["需要灵石"],
            costs=["消耗寿元"],
            rare_resources=["天火"],
            forbidden_methods=["血祭"],
        ),
        factions=[
            {"name": "青云宗", "description": "正道宗门", "goals": "维护和平"},
            {"name": "魔渊殿", "description": "魔道势力", "goals": "统治世界"},
        ],
        history="上古大战",
        rules=["规则一", "规则二"],
        taboos=["禁忌一"],
        technology_level="修仙文明",
        social_structure="宗门制",
        terminology={"灵石": "修炼货币", "秘境": "上古遗迹"},
    )

    save_world_setting(proj_dir, world)
    loaded = load_project(proj_dir)

    ws = loaded.world_setting
    assert ws.geography == "测试地理"
    assert ws.power_system is not None
    assert ws.power_system.realms == ["炼气", "筑基", "金丹"]
    assert ws.power_system.abilities == {"炼气": "灵气感知", "筑基": "御剑飞行", "金丹": "金丹领域"}
    assert ws.power_system.limitations == ["需要灵石"]
    assert ws.power_system.costs == ["消耗寿元"]
    assert ws.power_system.rare_resources == ["天火"]
    assert ws.power_system.forbidden_methods == ["血祭"]
    assert len(ws.factions) == 2
    assert ws.factions[0]["name"] == "青云宗"
    assert ws.factions[1]["description"] == "魔道势力"
    assert ws.history == "上古大战"
    assert ws.rules == ["规则一", "规则二"]
    assert ws.taboos == ["禁忌一"]
    assert ws.technology_level == "修仙文明"
    assert ws.social_structure == "宗门制"
    assert ws.terminology == {"灵石": "修炼货币", "秘境": "上古遗迹"}

    # Verify world.md contains key data
    md = (proj_dir / "world.md").read_text(encoding="utf-8")
    assert "测试地理" in md
    assert "青云宗" in md
    assert "炼气" in md
    assert "灵石" in md


def test_style_guide_save_load_round_trip(tmp_path):
    """Save a full StyleGuide, reload, verify all fields preserved."""
    project = Project(title="测试项目", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import StyleGuide

    style = StyleGuide(
        pacing="快节奏",
        dialogue_density="对白适中",
        description_style="简练",
        tone="热血",
        sentence_length="短句多",
        pov="第三人称",
        taboo_patterns=["禁忌一", "禁忌二"],
        preferred_patterns=["偏好一", "偏好二"],
        reference_passages=["段落一", "段落二"],
        freeform_notes="测试笔记内容",
    )

    save_style_guide(proj_dir, style)
    loaded = load_project(proj_dir)

    sg = loaded.style_guide
    assert sg.pacing == "快节奏"
    assert sg.dialogue_density == "对白适中"
    assert sg.description_style == "简练"
    assert sg.tone == "热血"
    assert sg.sentence_length == "短句多"
    assert sg.pov == "第三人称"
    assert sg.taboo_patterns == ["禁忌一", "禁忌二"]
    assert sg.preferred_patterns == ["偏好一", "偏好二"]
    assert sg.reference_passages == ["段落一", "段落二"]
    assert sg.freeform_notes == "测试笔记内容"

    # Verify style.yaml contains key data
    with open(proj_dir / "style.yaml", "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    assert raw["pacing"] == "快节奏"
    assert raw["tone"] == "热血"
    assert len(raw["reference_passages"]) == 2


def test_world_setting_empty_save_load(tmp_path):
    """Save an empty WorldSetting, verify it reloads with defaults."""
    project = Project(title="空项目", genre="科幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import WorldSetting

    world = WorldSetting()
    save_world_setting(proj_dir, world)
    loaded = load_project(proj_dir)

    assert loaded.world_setting.geography == ""
    assert loaded.world_setting.power_system is None
    assert loaded.world_setting.factions == []
    assert loaded.world_setting.rules == []


def test_style_guide_empty_save_load(tmp_path):
    """Save an empty StyleGuide, verify it reloads with defaults."""
    project = Project(title="空项目", genre="科幻")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import StyleGuide

    style = StyleGuide()
    save_style_guide(proj_dir, style)
    loaded = load_project(proj_dir)

    assert loaded.style_guide.pacing == ""
    assert loaded.style_guide.pov == ""
    assert loaded.style_guide.taboo_patterns == []


def test_world_md_without_power_system(tmp_path):
    """World markdown should not include power system section when None."""
    project = Project(title="无修炼", genre="都市")
    proj_dir = create_project(tmp_path, project)

    from app.storage.models import WorldSetting

    world = WorldSetting(geography="现代都市")
    save_world_setting(proj_dir, world)

    md = (proj_dir / "world.md").read_text(encoding="utf-8")
    assert "现代都市" in md
    assert "修炼体系" not in md  # No power system section
