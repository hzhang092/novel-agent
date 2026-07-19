"""Dependency rules for the project-editing application boundary."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
EDITORS = (
    ROOT / "app/ui/character_editor.py",
    ROOT / "app/ui/world_bible_editor.py",
    ROOT / "app/ui/bible_editor.py",
    ROOT / "app/ui/outline_editor.py",
)
FORBIDDEN_EDITOR_IMPORTS = (
    "app.storage.project_files",
    "app.storage.repository",
    "app.storage.bible_repository",
    "app.storage.character_definition_service",
    "app.storage.story_bible_transaction",
    "app.storage.state_repository",
    "app.storage.character_events",
    "app.storage.timeline_repository",
    "app.pipeline",
    "app.providers",
)


def _imports(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _matches(module: str, forbidden: str) -> bool:
    return module == forbidden or module.startswith(f"{forbidden}.")


def test_migrated_editors_only_reach_operations_through_application_services():
    for path in EDITORS:
        imports = _imports(path)
        violations = sorted(
            module
            for module in imports
            if any(_matches(module, item) for item in FORBIDDEN_EDITOR_IMPORTS)
        )
        assert not violations, f"{path.relative_to(ROOT)}: {violations}"
        assert any(module.startswith("app.application") for module in imports)


def test_application_package_has_no_qt_or_ui_imports():
    for path in (ROOT / "app/application").glob("*.py"):
        violations = sorted(
            module
            for module in _imports(path)
            if module == "PySide6"
            or module.startswith("PySide6.")
            or module == "app.ui"
            or module.startswith("app.ui.")
        )
        assert not violations, f"{path.relative_to(ROOT)}: {violations}"
