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
    lines = ["# 世界观", ""]
    lines.append(f"## 地理\n\n{world.geography}\n")

    if world.power_system:
        lines.append("## 修炼体系\n")
        ps = world.power_system
        if ps.realms:
            lines.append("### 境界")
            for r in ps.realms:
                lines.append(f"- {r}")
            lines.append("")
        if ps.abilities:
            lines.append("### 能力")
            for realm, desc in ps.abilities.items():
                lines.append(f"- **{realm}**: {desc}")
            lines.append("")
        if ps.limitations:
            lines.append(f"### 限制\n" + "\n".join(f"- {x}" for x in ps.limitations) + "\n")
        if ps.costs:
            lines.append(f"### 代价\n" + "\n".join(f"- {x}" for x in ps.costs) + "\n")
        if ps.rare_resources:
            lines.append(f"### 稀有资源\n" + "\n".join(f"- {x}" for x in ps.rare_resources) + "\n")
        if ps.forbidden_methods:
            lines.append(f"### 禁忌之术\n" + "\n".join(f"- {x}" for x in ps.forbidden_methods) + "\n")

    if world.factions:
        lines.append("## 势力\n")
        for f in world.factions:
            name = f.get("name", "")
            desc = f.get("description", "")
            goals = f.get("goals", "")
            lines.append(f"### {name}\n{desc}\n\n**目标**: {goals}\n")

    if world.history:
        lines.append(f"## 历史\n\n{world.history}\n")

    if world.rules:
        lines.append(f"## 规则\n" + "\n".join(f"- {x}" for x in world.rules) + "\n")

    if world.taboos:
        lines.append(f"## 禁忌\n" + "\n".join(f"- {x}" for x in world.taboos) + "\n")

    if world.technology_level:
        lines.append(f"## 科技水平\n\n{world.technology_level}\n")

    if world.social_structure:
        lines.append(f"## 社会结构\n\n{world.social_structure}\n")

    if world.terminology:
        lines.append("## 术语表\n")
        for term, defn in world.terminology.items():
            lines.append(f"- **{term}**: {defn}")
        lines.append("")

    with open(proj_path / WORLD_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


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


def save_world_setting(project_dir: Path, world: WorldSetting) -> None:
    """Update the world setting in project.yaml and rewrite world.md.

    Args:
        project_dir: Path to an existing project directory.
        world: The updated WorldSetting model.

    Raises:
        FileNotFoundError: If project_dir is not a valid project.
        ValueError: If the project YAML is corrupt.
    """
    from datetime import datetime, timezone

    project = load_project(project_dir)
    project.world_setting = world
    project.updated_at = datetime.now(timezone.utc)
    _write_project_yaml(project_dir, project)
    _write_world_md(project_dir, world)


def save_style_guide(project_dir: Path, style: StyleGuide) -> None:
    """Update the style guide in project.yaml and rewrite style.yaml.

    Args:
        project_dir: Path to an existing project directory.
        style: The updated StyleGuide model.

    Raises:
        FileNotFoundError: If project_dir is not a valid project.
        ValueError: If the project YAML is corrupt.
    """
    from datetime import datetime, timezone

    project = load_project(project_dir)
    project.style_guide = style
    project.updated_at = datetime.now(timezone.utc)
    _write_project_yaml(project_dir, project)
    _write_style_yaml(project_dir, style)
