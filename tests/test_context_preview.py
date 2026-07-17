"""Tests for the Context Preview panel widget."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from app.ui.context_preview import ContextPreviewView


@pytest.fixture(scope="module")
def qapp():
    """Module-level QApplication for UI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_context_preview_shows_badge_when_context_provided(qapp, qtbot):
    """Setting context shows the badge with summary counts."""
    widget = ContextPreviewView()
    qtbot.addWidget(widget)

    context = {
        "scene_info": {"scene_title": "测试场景"},
        "world_rules": {"rules": ["规则1"]},
        "characters": {
            "major": [{"core": {"name": "林轩"}, "state": {"current_emotion": "坚定"}}],
            "supporting": [{"name": "苏清鸾", "relationship": "同门"}],
            "background": [],
        },
        "outline_context": {},
        "recent_summaries": [{"scene_id": "s1"}, {"scene_id": "s2"}],
        "canon_facts": [
            {"description": "事实1", "importance": 4},
            {"description": "事实2", "importance": 3},
            {"description": "事实3", "importance": 5},
        ],
        "style_guide": {"pacing": "快节奏"},
    }

    widget.set_context(context)
    assert widget.isVisible()
    badge_text = widget._badge_label.text()
    assert "3" in badge_text  # 3 facts
    assert "1" in badge_text  # 1 major character state
    assert "2" in badge_text  # 2 summaries


def test_context_preview_expands_to_show_full_context(qapp, qtbot):
    """Expanding the badge reveals the full context panel with sections."""
    widget = ContextPreviewView()
    qtbot.addWidget(widget)

    context = {
        "scene_info": {"scene_title": "测试场景"},
        "world_rules": {"rules": ["规则1"]},
        "characters": {"major": [], "supporting": [], "background": []},
        "outline_context": {},
        "recent_summaries": [],
        "canon_facts": [{"description": "事实1", "importance": 4}],
        "style_guide": {},
    }

    widget.set_context(context)
    assert widget._detail_panel.isHidden()

    qtbot.mouseClick(widget._badge_button, Qt.MouseButton.LeftButton)
    assert not widget._detail_panel.isHidden()

    qtbot.mouseClick(widget._badge_button, Qt.MouseButton.LeftButton)
    assert widget._detail_panel.isHidden()


def test_context_preview_badge_includes_selected_element_count(qapp, qtbot):
    widget = ContextPreviewView()
    qtbot.addWidget(widget)

    widget.set_context({
        "world_context": {"elements": [{"id": "f1"}, {"id": "p1"}]},
        "canon_facts": [{}, {}, {}],
        "characters": {"major": [
            {"core": {"name": "甲"}, "state": {}},
            {"core": {"name": "乙"}, "state": {}},
        ]},
        "recent_summaries": [{}],
    })

    assert widget._badge_label.text() == (
        "2 elements · 3 facts · 2 character states · 1 summary"
    )


def test_context_preview_explains_element_selection_without_raw_ids(qapp, qtbot):
    widget = ContextPreviewView()
    qtbot.addWidget(widget)
    widget.set_context({
        "world_context": {"elements": [
            {"id": "faction-qingyun", "type": "faction", "name": "青云宗"},
            {"id": "faction-moyuan", "type": "faction", "name": "魔渊殿"},
            {"id": "power-main", "type": "power_system", "name": "九重天境"},
        ]},
        "world_element_read_points": {
            "faction-qingyun": {"revision": 2, "selection_reasons": ["explicit_scene_reference"]},
            "faction-moyuan": {
                "revision": 1,
                "selection_reasons": ["related_to:faction-qingyun:opposed_to"],
            },
            "power-main": {"revision": 1, "selection_reasons": ["always_include"]},
        },
    })

    detail = widget._detail_content.text()
    assert "── Story Elements ──" in detail
    assert "青云宗 [Faction]" in detail
    assert "Selected because: explicit scene reference" in detail
    assert "Selected because: related through Opposed to" in detail
    assert "Selected because: always included" in detail
    assert "faction-qingyun" not in detail
