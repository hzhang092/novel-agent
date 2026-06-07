"""Repository layer: thin CRUD wrapper over project_files for the UI to consume."""

from __future__ import annotations

from pathlib import Path

from app.storage.models import Project
from app.storage.project_files import create_project, load_project, project_exists


class Repository:
    """Manages project-level persistence. Stateless — all state is on disk."""

    def __init__(self, workspace_dir: Path) -> None:
        self._workspace = Path(workspace_dir)

    def create(self, project: Project) -> Path:
        """Create a new project on disk, return its directory path."""
        return create_project(self._workspace, project)

    def open(self, project_dir: Path) -> Project:
        """Load and validate a project from disk."""
        return load_project(Path(project_dir))

    def exists(self, project_dir: Path) -> bool:
        """Check if a path is a valid project directory."""
        return project_exists(Path(project_dir))

    def save_world_setting(self, project_dir: Path, world) -> None:
        """Update world setting on disk."""
        from app.storage.project_files import save_world_setting as _save_world
        _save_world(Path(project_dir), world)

    def save_style_guide(self, project_dir: Path, style) -> None:
        """Update style guide on disk."""
        from app.storage.project_files import save_style_guide as _save_style
        _save_style(Path(project_dir), style)
