"""Filesystem I/O for project directories. Reads and writes YAML files,
creates the standard project directory layout."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from app.storage.models import Project, StyleGuide, WorldSetting


PROJECT_YAML = "project.yaml"
WORLD_MD = "world.md"
STYLE_YAML = "style.yaml"

SUBDIRS = ["characters", "outline", "scenes", "canon", "exports"]


def create_project(project_dir: Path, project: Project) -> Path:
    """Create a new project directory with all required files and subdirectories.

    Args:
        project_dir: Parent directory that will contain the project folder.
        project: The Project model with title, genre, and provider.

    Returns:
        The path to the created project directory.

    Raises:
        FileExistsError: If the project directory already exists.
    """
    proj_path = project_dir / project.title
    if proj_path.exists():
        raise FileExistsError(f"Project already exists: {proj_path}")

    proj_path.mkdir(parents=True)

    for sub in SUBDIRS:
        (proj_path / sub).mkdir()

    _write_project_yaml(proj_path, project)
    _write_world_md(proj_path, project.world_setting)
    _write_style_yaml(proj_path, project.style_guide)
    _write_gitignore(proj_path)

    return proj_path


def _write_project_yaml(proj_path: Path, project: Project) -> None:
    data = project.model_dump(mode="json")
    with open(proj_path / PROJECT_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _write_world_md(proj_path: Path, world: WorldSetting) -> None:
    text = f"# 世界观\n\n{world.geography}\n"
    with open(proj_path / WORLD_MD, "w", encoding="utf-8") as f:
        f.write(text)


def _write_style_yaml(proj_path: Path, style: StyleGuide) -> None:
    data = style.model_dump(mode="json")
    with open(proj_path / STYLE_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _write_gitignore(proj_path: Path) -> None:
    with open(proj_path / ".gitignore", "w", encoding="utf-8") as f:
        f.write("exports/\n")


def load_project(project_dir: Path) -> Project:
    """Load and validate a project from disk.

    Args:
        project_dir: Path to an existing project directory containing project.yaml.

    Returns:
        A validated Project model.

    Raises:
        FileNotFoundError: If project.yaml does not exist.
        ValueError: If the YAML is invalid or fails model validation.
    """
    yaml_path = project_dir / PROJECT_YAML
    if not yaml_path.exists():
        raise FileNotFoundError(f"Not a project directory: {project_dir}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {yaml_path}: {e}") from e

    if raw is None:
        raise ValueError(f"Empty project file: {yaml_path}")

    try:
        project = Project.model_validate(raw)
    except Exception as e:
        raise ValueError(f"Invalid project data in {yaml_path}: {e}") from e

    return project


def project_exists(project_dir: Path) -> bool:
    """Check if a directory contains a valid project.yaml."""
    return (project_dir / PROJECT_YAML).exists()


def delete_project(project_dir: Path) -> None:
    """Remove an entire project directory."""
    if project_dir.exists():
        shutil.rmtree(project_dir)
