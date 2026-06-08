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

    def save_character(self, project_dir: Path, character) -> None:
        """Write a character to characters/<id>.yaml."""
        from app.storage.project_files import save_character as _save_char
        _save_char(Path(project_dir), character)

    def load_character(self, project_dir: Path, character_id: str):
        """Load a single character from disk."""
        from app.storage.project_files import load_character as _load_char
        return _load_char(Path(project_dir), character_id)

    def delete_character(self, project_dir: Path, character_id: str) -> None:
        """Delete a character YAML file."""
        from app.storage.project_files import delete_character as _del_char
        _del_char(Path(project_dir), character_id)

    def list_character_ids(self, project_dir: Path) -> list[str]:
        """List all character IDs in the project."""
        from app.storage.project_files import list_character_ids as _list_ids
        return _list_ids(Path(project_dir))

    def load_all_characters(self, project_dir: Path) -> list:
        """Load all characters from the project."""
        from app.storage.project_files import load_all_characters as _load_all
        return _load_all(Path(project_dir))

    def save_volume(self, project_dir: Path, volume) -> None:
        """Write a volume to outline/<id>.yaml."""
        from app.storage.project_files import save_volume_outline as _save_vol
        _save_vol(Path(project_dir), volume)

    def load_volume(self, project_dir: Path, volume_id: str):
        """Load a single volume from disk."""
        from app.storage.project_files import load_volume_outline as _load_vol
        return _load_vol(Path(project_dir), volume_id)

    def delete_volume(self, project_dir: Path, volume_id: str) -> None:
        """Delete a volume YAML file."""
        from app.storage.project_files import delete_volume_outline as _del_vol
        _del_vol(Path(project_dir), volume_id)

    def list_volume_ids(self, project_dir: Path) -> list[str]:
        """List all volume IDs in the project."""
        from app.storage.project_files import list_volume_ids as _list_ids
        return _list_ids(Path(project_dir))

    def load_all_volumes(self, project_dir: Path) -> list:
        """Load all volumes from the project."""
        from app.storage.project_files import load_all_volumes as _load_all
        return _load_all(Path(project_dir))

    def save_canon_facts(self, project_dir: Path, facts: list) -> None:
        """Write all canon facts to canon/facts.yaml."""
        from app.storage.project_files import save_canon_facts as _save
        _save(Path(project_dir), facts)

    def load_canon_facts(self, project_dir: Path) -> list:
        """Load all canon facts from canon/facts.yaml."""
        from app.storage.project_files import load_canon_facts as _load
        return _load(Path(project_dir))

    def save_scene_summaries(self, project_dir: Path, summaries: list) -> None:
        """Write all scene summaries to canon/summaries.yaml."""
        from app.storage.project_files import save_scene_summaries as _save
        _save(Path(project_dir), summaries)

    def load_scene_summaries(self, project_dir: Path) -> list:
        """Load all scene summaries from canon/summaries.yaml."""
        from app.storage.project_files import load_scene_summaries as _load
        return _load(Path(project_dir))
