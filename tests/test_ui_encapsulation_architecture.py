"""Architecture rules for UI component boundaries."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
UI_ROOT = ROOT / "app/ui"

# Temporary migration baseline. Each entry names its removal checkpoint and contract.
PRIVATE_BASELINE = {
    ("app/ui/bible_editor.py", "_on_add_character"): (2, "create_character"),
    ("app/ui/bible_editor.py", "_element_list"): (2, "show_overview"),
    ("app/ui/bible_editor.py", "_characters"): (2, "character_cores_in_memory"),
    ("app/ui/bible_editor.py", "_current_id"): (2, "selected_character_id"),
    ("app/ui/bible_editor.py", "_gather_core"): (2, "character_cores_in_memory"),
    ("app/ui/bible_editor.py", "_resolve_dirty_before_switch"): (2, "prepare_for_navigation"),
    ("app/ui/bible_element_editor.py", "_table"): (1, "KeyValueTable.rows"),
    ("app/ui/character_editor.py", "_table"): (1, "KeyValueTable.rows"),
    ("app/ui/character_state_edit_dialog.py", "_table"): (1, "KeyValueTable.rows"),
    ("app/ui/main_window.py", "_select_by_id"): (5, "OutlineEditorView.activate_scene"),
    ("app/ui/main_window.py", "_refresh_world_elements"): (5, "OutlineEditorView.refresh_world_elements"),
    ("app/ui/main_window.py", "_project_dir"): (5, "view is_loaded and MainWindow project state"),
    ("app/ui/main_window.py", "_on_save"): (5, "OutlineEditorView.save"),
    ("app/ui/main_window.py", "_character_tab"): (5, "BibleEditorView facade"),
    ("app/ui/main_window.py", "_world_tab"): (5, "BibleEditorView facade"),
    ("app/ui/main_window.py", "_current_scene_id"): (5, "SceneWorkspaceView.current_scene_id"),
    ("app/ui/main_window.py", "_current_chapter_id"): (5, "SceneWorkspaceView.current_chapter_id"),
    ("app/ui/main_window.py", "_status_label"): (5, "SceneWorkspaceView.set_status"),
    ("app/ui/main_window.py", "_next_scene_btn"): (5, "SceneWorkspaceView.mark_last_scene"),
    ("app/ui/main_window.py", "_continue_review_btn"): (5, "SceneWorkspaceView facade"),
    ("app/ui/world_bible_editor.py", "_find_item"): (1, "BibleElementList.restore_selection"),
    ("app/ui/world_bible_editor.py", "_tree"): (1, "BibleElementList.restore_selection"),
}

WORKSPACE_RAW_CHILD_BASELINE = {
    "editor": 4,
    "trace_panel": 4,
    "planner_checkpoint": 4,
    "fact_approval": 4,
}
WORKSPACE_IMPLEMENTATION_MEMBERS = {
    "editor",
    "trace_panel",
    "planner_checkpoint",
    "fact_approval",
    "context_preview",
    "_status_label",
    "_next_scene_btn",
    "_continue_review_btn",
    "_current_scene_id",
    "_current_chapter_id",
}


def foreign_private_accesses(source: str) -> list[tuple[int, str]]:
    """Return private attributes not accessed directly through self or cls."""
    violations = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Attribute):
            continue
        if not node.attr.startswith("_") or node.attr.startswith("__"):
            continue
        if isinstance(node.value, ast.Name) and node.value.id in {"self", "cls"}:
            continue
        violations.append((node.lineno, node.attr))
    return violations


def attribute_names(source: str) -> set[str]:
    """Return attribute names used by a module."""
    return {
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute)
    }


def test_foreign_private_detector_catches_nested_and_local_alias_access():
    source = """
def example(self, child):
    self._private
    self._child.public_method()
    self._child._private
    child._private
"""
    assert foreign_private_accesses(source) == [(5, "_private"), (6, "_private")]


def test_ui_modules_add_no_foreign_private_accesses_beyond_migration_baseline():
    actual = set()
    for path in UI_ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        for _line, member in foreign_private_accesses(path.read_text(encoding="utf-8")):
            actual.add((relative, member))

    assert not actual - PRIVATE_BASELINE.keys()
    assert not PRIVATE_BASELINE.keys() - actual


def test_main_window_adds_no_workspace_implementation_accesses():
    source = (UI_ROOT / "main_window.py").read_text(encoding="utf-8")
    actual = attribute_names(source) & WORKSPACE_IMPLEMENTATION_MEMBERS
    allowed = set(WORKSPACE_RAW_CHILD_BASELINE) | {
        member
        for path, member in PRIVATE_BASELINE
        if path == "app/ui/main_window.py"
        and member in WORKSPACE_IMPLEMENTATION_MEMBERS
    }
    assert not actual - allowed
    assert not allowed - actual
