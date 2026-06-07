"""Integration tests for OutlineEditorView widget."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel

from app.storage.models import Project
from app.storage.project_files import create_project

# Single QApplication for all tests
_app = QApplication.instance() or QApplication([])


@pytest.fixture
def editor(qtbot, tmp_path):
    """Create an OutlineEditorView loaded with a test project."""
    from app.ui.outline_editor import OutlineEditorView

    project = Project(title="测试", genre="玄幻")
    proj_dir = create_project(tmp_path, project)

    widget = OutlineEditorView()
    qtbot.addWidget(widget)
    widget.load_project_dir(proj_dir)
    yield widget, proj_dir


def test_initial_state_empty(editor):
    """New editor has no tree items and disabled delete button."""
    widget, _ = editor
    assert widget._tree.topLevelItemCount() == 0
    assert not widget._delete_btn.isEnabled()


def test_add_volume(editor):
    """Adding a volume creates a top-level tree item."""
    widget, proj_dir = editor
    widget._on_add_volume()
    assert widget._tree.topLevelItemCount() == 1
    root = widget._tree.topLevelItem(0)
    assert root.text(0) == "新卷"


def test_add_chapter_to_volume(editor):
    """Adding a chapter to a selected volume appends a child tree item."""
    widget, proj_dir = editor
    widget._on_add_volume()
    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))
    widget._on_add_chapter()
    root = widget._tree.topLevelItem(0)
    assert root.childCount() == 1
    assert root.child(0).text(0) == "新章"


def test_add_scene_to_chapter(editor):
    """Adding a scene to a selected chapter appends a grandchild tree item."""
    widget, proj_dir = editor
    widget._on_add_volume()
    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))
    widget._on_add_chapter()
    # Re-fetch after rebuild
    root = widget._tree.topLevelItem(0)
    chapter_item = root.child(0)
    widget._tree.setCurrentItem(chapter_item)
    widget._on_add_scene()
    # Re-fetch after rebuild again
    root = widget._tree.topLevelItem(0)
    chapter_item = root.child(0)
    assert chapter_item.childCount() == 1
    assert chapter_item.child(0).text(0) == "新场景"


def test_delete_volume(editor, qtbot):
    """Deleting a selected volume removes it from the tree and data model."""
    widget, proj_dir = editor
    widget._on_add_volume()
    widget._on_add_volume()
    assert widget._tree.topLevelItemCount() == 2

    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))
    widget._on_delete_node()
    assert widget._tree.topLevelItemCount() == 1


def test_move_up_disabled_on_first_item(editor):
    """Move up should be disabled when first item is selected."""
    widget, proj_dir = editor
    widget._on_add_volume()
    widget._on_add_volume()
    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))
    assert not widget._up_btn.isEnabled()


def test_move_down_disabled_on_last_item(editor):
    """Move down should be disabled when last item is selected."""
    widget, proj_dir = editor
    widget._on_add_volume()
    widget._on_add_volume()
    widget._tree.setCurrentItem(widget._tree.topLevelItem(1))
    assert not widget._down_btn.isEnabled()
