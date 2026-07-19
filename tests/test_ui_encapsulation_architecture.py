"""Architecture rules for UI component boundaries."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
UI_ROOT = ROOT / "app/ui"

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


def test_ui_modules_do_not_access_foreign_private_members():
    actual = set()
    for path in UI_ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        for _line, member in foreign_private_accesses(path.read_text(encoding="utf-8")):
            actual.add((relative, member))

    assert not actual


def test_main_window_does_not_access_workspace_implementation_members():
    source = (UI_ROOT / "main_window.py").read_text(encoding="utf-8")
    actual = attribute_names(source) & WORKSPACE_IMPLEMENTATION_MEMBERS
    assert not actual
