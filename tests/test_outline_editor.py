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


# ── Detail form tests ──────────────────────────────────────────────────────

def test_select_volume_shows_detail(editor):
    """Selecting a volume populates the volume detail form."""
    widget, proj_dir = editor
    widget._on_add_volume()
    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))
    assert widget._detail_stack.currentWidget() is widget._volume_form


def test_select_scene_shows_detail_fields(editor):
    """Selecting a scene populates the scene detail form with all fields."""
    widget, proj_dir = editor
    widget._on_add_volume()
    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))
    widget._on_add_chapter()
    root = widget._tree.topLevelItem(0)
    chapter_item = root.child(0)
    widget._tree.setCurrentItem(chapter_item)
    widget._on_add_scene()
    root = widget._tree.topLevelItem(0)
    scene_item = root.child(0).child(0)
    widget._tree.setCurrentItem(scene_item)
    assert widget._detail_stack.currentWidget() is widget._scene_form


def test_scene_ending_hook_label(editor):
    """The ending hook field must be labeled 断章."""
    widget, proj_dir = editor
    labels = widget._scene_form.findChildren(QLabel)
    label_texts = [l.text() for l in labels]
    assert any("断章" in t for t in label_texts)


def test_gather_scene_from_form(editor):
    """After populating and editing a scene form, _gather_scene returns correct data."""
    widget, proj_dir = editor
    widget._on_add_volume()
    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))
    widget._on_add_chapter()
    root = widget._tree.topLevelItem(0)
    chapter_item = root.child(0)
    widget._tree.setCurrentItem(chapter_item)
    widget._on_add_scene()
    root = widget._tree.topLevelItem(0)
    scene_item = root.child(0).child(0)
    widget._tree.setCurrentItem(scene_item)

    # Edit form fields
    widget._scene_title.setText("测试场景")
    widget._scene_location.setText("广场")
    widget._scene_time.setText("清晨")
    widget._scene_goal.setPlainText("通过考核")
    widget._scene_conflict.setPlainText("嘲笑与反击")
    widget._scene_ending_hook.setPlainText("考核官意味深长的笑容")

    sc = widget._gather_scene(widget._selected_node_id)
    assert sc.title == "测试场景"
    assert sc.location == "广场"
    assert sc.time == "清晨"
    assert sc.scene_goal == "通过考核"
    assert sc.conflict == "嘲笑与反击"
    assert sc.ending_hook == "考核官意味深长的笑容"


# ── Save/Load tests ────────────────────────────────────────────────────────

def test_save_and_reload_preserves_data(editor, qtbot):
    """Save outline, create a new editor, load — data is preserved."""
    widget, proj_dir = editor

    # Create a volume with a chapter and scene
    widget._on_add_volume()
    widget._tree.setCurrentItem(widget._tree.topLevelItem(0))
    widget._on_add_chapter()
    root = widget._tree.topLevelItem(0)
    chapter = root.child(0)
    widget._tree.setCurrentItem(chapter)
    widget._on_add_scene()

    # Edit the scene
    root = widget._tree.topLevelItem(0)
    scene_item = root.child(0).child(0)
    widget._tree.setCurrentItem(scene_item)
    widget._scene_title.setText("考核日")
    widget._scene_ending_hook.setPlainText("悬念结尾")

    # Save
    widget._on_save()

    # Create a new editor and load the same project
    from app.ui.outline_editor import OutlineEditorView
    widget2 = OutlineEditorView()
    qtbot.addWidget(widget2)
    widget2.load_project_dir(proj_dir)

    # Verify data survived
    assert widget2._tree.topLevelItemCount() == 1
    root2 = widget2._tree.topLevelItem(0)
    assert root2.childCount() == 1
    ch2 = root2.child(0)
    assert ch2.childCount() == 1
    sc2 = ch2.child(0)

    widget2._tree.setCurrentItem(sc2)
    assert widget2._scene_title.text() == "考核日"
    assert widget2._scene_ending_hook.toPlainText() == "悬念结尾"


def test_on_save_writes_all_volumes_to_disk(editor):
    """_on_save writes volume YAML files and emits the saved signal."""
    widget, proj_dir = editor

    widget._on_add_volume()
    widget._on_add_volume()

    saved_emitted = []
    widget.saved.connect(lambda: saved_emitted.append(True))

    widget._on_save()

    assert len(saved_emitted) == 1
    # Verify files exist
    vol_files = list((proj_dir / "outline").glob("*.yaml"))
    assert len(vol_files) == 2
