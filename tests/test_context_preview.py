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
