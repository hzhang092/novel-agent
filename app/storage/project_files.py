"""Filesystem I/O for project directories. Reads and writes YAML files,
creates the standard project directory layout."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import yaml

from app.storage.models import (
    Character,
    CharacterCore,
    CharacterState,
    Project,
    StyleGuide,
    VolumeOutline,
    WorldSetting,
)


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
        f.write("exports/\n.novel-agent/\n")


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


# ── Character I/O ──────────────────────────────────────────────────────────

def save_character(project_dir: Path, character: Character) -> None:
    """Write a character to characters/<id>/ in per-directory layout.

    Character State is persisted as events; state.yaml remains a derived snapshot.
    """
    from app.storage.state_repository import StateRepository, commit_character_state_edit

    char_root = project_dir / "characters"
    char_dir = char_root / character.core.id
    definition_exists = (char_dir / "definition.yaml").exists()
    legacy_exists = (char_root / f"{character.core.id}.yaml").exists()
    old_state = load_character(project_dir, character.core.id).state if definition_exists else None
    char_dir = save_character_definition(project_dir, character.core)

    if old_state is not None:
        commit_character_state_edit(char_dir, old_state, character.state)
    else:
        StateRepository().commit_initial_state(
            char_dir,
            character.state,
            source="system" if legacy_exists else "user",
        )


def save_character_definition(project_dir: Path, core: CharacterCore) -> Path:
    """Write only characters/<id>/definition.yaml and return the character directory."""
    char_root = project_dir / "characters"
    char_root.mkdir(exist_ok=True)
    char_dir = char_root / core.id
    char_dir.mkdir(exist_ok=True)

    definition_path = char_dir / "definition.yaml"
    core_data = core.model_dump(mode="json")
    with open(definition_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(core_data, f, allow_unicode=True, sort_keys=False)
    return char_dir


def load_character(project_dir: Path, character_id: str) -> Character:
    """Load a character — tries per-directory layout first, then legacy flat file.

    Raises:
        FileNotFoundError: If the character does not exist in either layout.
        ValueError: If the data is invalid or fails model validation.
    """
    from app.storage.character_state import load_or_build_snapshot, map_snapshot_to_character_state

    char_root = project_dir / "characters"
    char_dir = char_root / character_id
    flat_path = char_root / f"{character_id}.yaml"

    # ── New layout: per-directory ──
    if char_dir.is_dir():
        # Load definition.yaml
        def_path = char_dir / "definition.yaml"
        if not def_path.exists():
            raise FileNotFoundError(f"Character definition not found: {def_path}")
        with open(def_path, "r", encoding="utf-8") as f:
            try:
                raw_core = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in {def_path}: {e}") from e
        if raw_core is None:
            raise ValueError(f"Empty definition file: {def_path}")
        try:
            core = CharacterCore.model_validate(raw_core)
        except Exception as e:
            raise ValueError(f"Invalid core data in {def_path}: {e}") from e

        # Load state.yaml and map back
        snap = load_or_build_snapshot(char_dir, core.id)
        state = map_snapshot_to_character_state(snap)
        return Character(core=core, state=state)

    # ── Legacy layout: flat .yaml ──
    if flat_path.exists():
        with open(flat_path, "r", encoding="utf-8") as f:
            try:
                raw = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in {flat_path}: {e}") from e
        if raw is None:
            raise ValueError(f"Empty character file: {flat_path}")
        try:
            core = CharacterCore.model_validate(raw.get("core", {}))
            state = CharacterState.model_validate(raw.get("state", {}))
        except Exception as e:
            raise ValueError(f"Invalid character data in {flat_path}: {e}") from e
        return Character(core=core, state=state)

    raise FileNotFoundError(f"Character not found: {character_id}")


def delete_character(project_dir: Path, character_id: str) -> None:
    """Delete a character (per-directory or flat file). No-op if not found."""
    import shutil

    char_root = project_dir / "characters"
    char_dir = char_root / character_id
    flat_path = char_root / f"{character_id}.yaml"

    if char_dir.is_dir():
        shutil.rmtree(char_dir)
    if flat_path.exists():
        flat_path.unlink()


def list_character_ids(project_dir: Path) -> list[str]:
    """Return all character IDs from both per-directory and flat-file layouts."""
    char_root = project_dir / "characters"
    if not char_root.exists():
        return []
    ids: set[str] = set()

    # Per-directory layout
    for d in char_root.iterdir():
        if d.is_dir() and (d / "definition.yaml").exists():
            ids.add(d.name)

    # Legacy flat files
    for filepath in char_root.glob("*.yaml"):
        stem = filepath.stem
        if stem not in ids:
            ids.add(stem)

    return sorted(ids)


def load_all_characters(project_dir: Path) -> list[Character]:
    """Load all characters from both layouts."""
    characters = []
    failures: list[str] = []
    for cid in list_character_ids(project_dir):
        try:
            characters.append(load_character(project_dir, cid))
        except (ValueError, FileNotFoundError) as e:
            failures.append(f"{cid}: {e}")
    if failures:
        raise ValueError("Invalid character files:\n" + "\n".join(failures))
    return characters


# ── Outline I/O ────────────────────────────────────────────────────────────

def save_volume_outline(project_dir: Path, volume: VolumeOutline) -> None:
    """Write a volume with its nested chapters and scenes to outline/<id>.yaml."""
    outline_dir = project_dir / "outline"
    outline_dir.mkdir(exist_ok=True)

    data = volume.model_dump(mode="json")
    filepath = outline_dir / f"{volume.id}.yaml"
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_volume_outline(project_dir: Path, volume_id: str) -> VolumeOutline:
    """Load a single volume from outline/<id>.yaml.

    Raises:
        FileNotFoundError: If the volume file does not exist.
        ValueError: If the YAML is invalid or fails model validation.
    """
    filepath = project_dir / "outline" / f"{volume_id}.yaml"
    if not filepath.exists():
        raise FileNotFoundError(f"Volume not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {filepath}: {e}") from e

    if raw is None:
        raise ValueError(f"Empty volume file: {filepath}")

    try:
        volume = VolumeOutline.model_validate(raw)
    except Exception as e:
        raise ValueError(f"Invalid volume data in {filepath}: {e}") from e

    return volume


def delete_volume_outline(project_dir: Path, volume_id: str) -> None:
    """Delete a volume YAML file. No-op if the file does not exist."""
    filepath = project_dir / "outline" / f"{volume_id}.yaml"
    if filepath.exists():
        filepath.unlink()


def list_volume_ids(project_dir: Path) -> list[str]:
    """Return all volume IDs found in the outline/ directory."""
    outline_dir = project_dir / "outline"
    if not outline_dir.exists():
        return []
    ids = []
    for filepath in outline_dir.glob("*.yaml"):
        ids.append(filepath.stem)
    return ids


def load_all_volumes(project_dir: Path) -> list[VolumeOutline]:
    """Load all volumes from the outline/ directory, sorted by filename."""
    outline_dir = project_dir / "outline"
    if not outline_dir.exists():
        return []
    volumes = []
    failures: list[str] = []
    for filepath in sorted(outline_dir.glob("*.yaml")):
        try:
            volumes.append(load_volume_outline(project_dir, filepath.stem))
        except (ValueError, FileNotFoundError) as e:
            failures.append(f"{filepath}: {e}")
    if failures:
        raise ValueError("Invalid outline files:\n" + "\n".join(failures))
    return volumes


# ── Canon Facts I/O ────────────────────────────────────────────────────────

CANON_FACTS_YAML = "canon/facts.yaml"


def save_canon_facts(project_dir: Path, facts: list) -> None:
    """Atomically replace canon/facts.yaml with all canon facts."""
    canon_dir = project_dir / "canon"
    canon_dir.mkdir(exist_ok=True)

    data = [f.model_dump(mode="json") for f in facts]
    filepath = canon_dir / "facts.yaml"
    serialized = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=canon_dir,
            prefix=".facts.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            temp_path = Path(fh.name)
            fh.write(serialized)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, filepath)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def load_canon_facts(project_dir: Path, active_only: bool = True) -> list:
    """Load all canon facts from canon/facts.yaml.

    Returns:
        List of CanonFact models. Empty list if no facts file exists or is empty.

    Raises:
        ValueError: If the YAML is invalid or fails model validation.
    """
    from app.storage.models import CanonFact

    filepath = project_dir / CANON_FACTS_YAML
    if not filepath.exists():
        return []

    with open(filepath, "r", encoding="utf-8") as fh:
        try:
            raw = yaml.safe_load(fh)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {filepath}: {e}") from e

    if raw is None:
        return []

    try:
        facts = [CanonFact.model_validate(item) for item in raw]
    except Exception as e:
        raise ValueError(f"Invalid canon fact data in {filepath}: {e}") from e

    if not active_only:
        return facts
    active_revisions: dict[str, str] = {}
    for fact in facts:
        if fact.source_scene_revision_id and fact.source_scene_id not in active_revisions:
            active_revisions[fact.source_scene_id] = get_active_scene_revision_id(
                project_dir, fact.source_scene_id
            )
    return [
        fact
        for fact in facts
        if not fact.source_scene_revision_id
        or active_revisions.get(fact.source_scene_id) == fact.source_scene_revision_id
    ]


# ── Scene Summaries I/O ────────────────────────────────────────────────────

SCENE_SUMMARIES_YAML = "canon/summaries.yaml"


def save_scene_summaries(project_dir: Path, summaries: list) -> None:
    """Atomically replace canon/summaries.yaml with all scene summaries."""
    canon_dir = project_dir / "canon"
    canon_dir.mkdir(exist_ok=True)

    data = [s.model_dump(mode="json") for s in summaries]
    filepath = canon_dir / "summaries.yaml"
    serialized = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=canon_dir,
            prefix=".summaries.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            temp_path = Path(fh.name)
            fh.write(serialized)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, filepath)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def load_scene_summaries(project_dir: Path, active_only: bool = True) -> list:
    """Load all scene summaries from canon/summaries.yaml.

    Returns:
        List of SceneSummary models. Empty list if no file exists or is empty.

    Raises:
        ValueError: If the YAML is invalid or fails model validation.
    """
    from app.storage.models import SceneSummary

    filepath = project_dir / SCENE_SUMMARIES_YAML
    if not filepath.exists():
        return []

    with open(filepath, "r", encoding="utf-8") as fh:
        try:
            raw = yaml.safe_load(fh)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {filepath}: {e}") from e

    if raw is None:
        return []

    try:
        summaries = [SceneSummary.model_validate(item) for item in raw]
    except Exception as e:
        raise ValueError(f"Invalid scene summary data in {filepath}: {e}") from e

    if not active_only:
        return summaries
    active_revisions: dict[str, str] = {}
    for summary in summaries:
        if summary.source_scene_revision_id and summary.scene_id not in active_revisions:
            active_revisions[summary.scene_id] = get_active_scene_revision_id(
                project_dir, summary.scene_id
            )
    return [
        summary
        for summary in summaries
        if not summary.source_scene_revision_id
        or active_revisions.get(summary.scene_id) == summary.source_scene_revision_id
    ]


# ── Scene Prose I/O ───────────────────────────────────────────────────────

_SCENE_PROSE_VERSION_RE = re.compile(r"\.v(\d+)$")


def save_scene_writer_draft(project_dir: Path, scene_id: str, prose: str) -> None:
    """Atomically save completed Writer prose before post-processing starts."""
    chapter_id = _find_chapter_for_scene(project_dir, scene_id)
    if chapter_id is None:
        raise ValueError(f"Scene {scene_id} was not found in any chapter outline")
    chapter_dir = project_dir / "scenes" / chapter_id
    chapter_dir.mkdir(parents=True, exist_ok=True)
    filepath = chapter_dir / f"{scene_id}.writer-draft.md"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=chapter_dir,
            prefix=f".{scene_id}.writer-draft.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            temp_path = Path(fh.name)
            fh.write(prose)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, filepath)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def load_scene_writer_draft(project_dir: Path, scene_id: str) -> str:
    chapter_id = _find_chapter_for_scene(project_dir, scene_id)
    if chapter_id is None:
        return ""
    filepath = project_dir / "scenes" / chapter_id / f"{scene_id}.writer-draft.md"
    if not filepath.exists():
        return ""
    return filepath.read_text(encoding="utf-8")


def discard_scene_writer_draft(project_dir: Path, scene_id: str) -> None:
    chapter_id = _find_chapter_for_scene(project_dir, scene_id)
    if chapter_id is None:
        return
    (project_dir / "scenes" / chapter_id / f"{scene_id}.writer-draft.md").unlink(
        missing_ok=True
    )


def save_scene_prose(project_dir: Path, chapter_id: str, scene_id: str, prose: str) -> None:
    """Write scene prose so the next load returns this content.

    Uses legacy <scene_id>.md until versioning exists, then appends <scene_id>.vN.md.
    """
    chapter_dir = project_dir / "scenes" / chapter_id
    chapter_dir.mkdir(parents=True, exist_ok=True)
    latest_version = _latest_scene_prose_version(chapter_dir, scene_id)
    filepath = (
        chapter_dir / f"{scene_id}.v{latest_version + 1}.md"
        if latest_version is not None
        else chapter_dir / f"{scene_id}.md"
    )
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(prose)
    set_active_scene_prose_version(
        project_dir,
        chapter_id,
        scene_id,
        "legacy" if latest_version is None else f"v{latest_version + 1}",
    )


def _extract_scene_prose_version(path: Path) -> int | None:
    """Return N for a <scene_id>.vN.md path, ignoring malformed versions."""
    match = _SCENE_PROSE_VERSION_RE.search(path.stem)
    if match is None:
        return None
    return int(match.group(1))


def _latest_scene_prose_version(chapter_dir: Path, scene_id: str) -> int | None:
    versions = [
        version
        for path in chapter_dir.glob(f"{scene_id}.v*.md")
        if (version := _extract_scene_prose_version(path)) is not None
    ]
    return max(versions, default=None)


def _scene_prose_version_path(chapter_dir: Path, scene_id: str, version: str) -> Path | None:
    if version == "legacy":
        return chapter_dir / f"{scene_id}.md"
    if version.startswith("v") and version[1:].isdigit():
        return chapter_dir / f"{scene_id}.{version}.md"
    return None


def list_scene_prose_versions(project_dir: Path, chapter_id: str, scene_id: str) -> list[str]:
    """List available prose versions newest-first, plus legacy if present."""
    chapter_dir = project_dir / "scenes" / chapter_id
    if not chapter_dir.exists():
        return []

    versions = [
        version
        for path in chapter_dir.glob(f"{scene_id}.v*.md")
        if (version := _extract_scene_prose_version(path)) is not None
    ]
    result = [f"v{version}" for version in sorted(versions, reverse=True)]
    if (chapter_dir / f"{scene_id}.md").exists():
        result.append("legacy")
    return result


def load_scene_prose_version(
    project_dir: Path, chapter_id: str, scene_id: str, version: str
) -> str:
    """Load a specific scene prose version token from list_scene_prose_versions()."""
    chapter_dir = project_dir / "scenes" / chapter_id
    filepath = _scene_prose_version_path(chapter_dir, scene_id, version)
    if filepath is None:
        return ""

    if not filepath.exists():
        return ""
    with open(filepath, "r", encoding="utf-8") as fh:
        return fh.read()


def set_active_scene_prose_version(
    project_dir: Path,
    chapter_id: str,
    scene_id: str,
    version: str,
    revision_id: str = "",
) -> None:
    """Atomically persist the prose revision chosen for display/export."""
    chapter_dir = project_dir / "scenes" / chapter_id
    chapter_dir.mkdir(parents=True, exist_ok=True)
    filepath = chapter_dir / f"{scene_id}.active.yaml"
    data = {"version": version}
    if revision_id:
        data["revision_id"] = revision_id
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=chapter_dir,
            prefix=f".{scene_id}.active.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            temp_path = Path(fh.name)
            yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, filepath)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def load_scene_active_marker(
    project_dir: Path, chapter_id: str, scene_id: str
) -> dict[str, str]:
    """Return the active prose marker, tolerating legacy version-only files."""
    filepath = project_dir / "scenes" / chapter_id / f"{scene_id}.active.yaml"
    if not filepath.exists():
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key in ("version", "revision_id")
        if isinstance((value := raw.get(key)), str)
    }


def get_active_scene_prose_version(
    project_dir: Path, chapter_id: str, scene_id: str
) -> str | None:
    """Return the persisted active prose version token, if any."""
    return load_scene_active_marker(project_dir, chapter_id, scene_id).get("version")


def load_scene_prose_status(
    project_dir: Path, chapter_id: str, scene_id: str
) -> tuple[str, str | None, bool]:
    """Load active prose, falling back to latest if the active file is missing."""
    chapter_dir = project_dir / "scenes" / chapter_id
    active_marker_exists = (chapter_dir / f"{scene_id}.active.yaml").exists()
    active = get_active_scene_prose_version(project_dir, chapter_id, scene_id)
    active_path = (
        _scene_prose_version_path(chapter_dir, scene_id, active)
        if active is not None
        else None
    )
    if active_path is not None and active_path.exists():
        with open(active_path, "r", encoding="utf-8") as fh:
            return fh.read(), active, False

    for fallback_version in list_scene_prose_versions(
        project_dir, chapter_id, scene_id
    ):
        if fallback_version != "legacy":
            fallback_record = load_scene_generation_record(
                project_dir, scene_id, version=fallback_version
            )
            if fallback_record is not None and fallback_record.status == "draft":
                continue
        filepath = _scene_prose_version_path(chapter_dir, scene_id, fallback_version)
        if filepath is not None:
            with open(filepath, "r", encoding="utf-8") as fh:
                return fh.read(), fallback_version, active_marker_exists
    return "", None, active_marker_exists


def load_scene_prose(project_dir: Path, chapter_id: str, scene_id: str) -> str:
    """Load the active scene prose.

    Prefer the active version marker, then
    scenes/<chapter>/<scene_id>.vN.md using the highest numeric N, then
    fall back to legacy scenes/<chapter>/<scene_id>.md. Returns an empty string
    if no prose file exists.
    """
    prose, _, _ = load_scene_prose_status(project_dir, chapter_id, scene_id)
    return prose


# ── Scene Generation Record I/O ────────────────────────────────────────────


def save_scene_generation_record(project_dir: Path, record) -> None:
    """Atomically write one versioned SceneGenerationRecord."""
    chapter_id = _find_chapter_for_scene(project_dir, record.scene_id)
    if chapter_id is None:
        raise ValueError(
            f"Scene {record.scene_id} was not found in any chapter outline. "
            "Generation records require a valid chapter. Ensure the scene exists in the outline."
        )
    chapter_dir = project_dir / "scenes" / chapter_id
    chapter_dir.mkdir(parents=True, exist_ok=True)
    filepath = chapter_dir / f"{record.scene_id}.v{record.revision_number}.gen.json"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=chapter_dir,
            prefix=f".{record.scene_id}.v{record.revision_number}.gen.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            temp_path = Path(fh.name)
            json.dump(
                record.model_dump(mode="json"),
                fh,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, filepath)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def load_scene_generation_record(
    project_dir: Path,
    scene_id: str,
    revision_id: str = "",
    version: str = "",
):
    """Load an exact, active, or latest record, with legacy fallback."""
    from app.storage.models import SceneGenerationRecord

    scenes_dir = project_dir / "scenes"
    if not scenes_dir.exists():
        return None

    for chapter_dir in scenes_dir.iterdir():
        if not chapter_dir.is_dir():
            continue
        if version.startswith("v") and version[1:].isdigit():
            filepath = chapter_dir / f"{scene_id}.{version}.gen.json"
            if not filepath.exists():
                continue
            with open(filepath, "r", encoding="utf-8") as fh:
                return SceneGenerationRecord.model_validate(json.load(fh))
        paths = list(chapter_dir.glob(f"{scene_id}.v*.gen.json"))
        legacy = chapter_dir / f"{scene_id}.gen.json"
        if legacy.exists():
            paths.append(legacy)
        records = []
        for filepath in paths:
            with open(filepath, "r", encoding="utf-8") as fh:
                records.append(SceneGenerationRecord.model_validate(json.load(fh)))
        if not records:
            continue
        if revision_id:
            return next((record for record in records if record.revision_id == revision_id), None)
        marker = load_scene_active_marker(project_dir, chapter_dir.name, scene_id)
        active_revision = marker.get("revision_id", "")
        if active_revision:
            active = next((record for record in records if record.revision_id == active_revision), None)
            if active is not None:
                return active
        active_version = marker.get("version", "")
        if active_version.startswith("v") and active_version[1:].isdigit():
            number = int(active_version[1:])
            active = next((record for record in records if record.revision_number == number), None)
            if active is not None:
                return active
        current = [record for record in records if record.status == "current"]
        if current:
            return max(current, key=lambda record: record.revision_number)
        return max(records, key=lambda record: record.revision_number)
    return None


def get_active_scene_revision_id(project_dir: Path, scene_id: str) -> str:
    """Resolve the active revision ID without rewriting legacy project files."""
    chapter_id = _find_chapter_for_scene(project_dir, scene_id)
    if chapter_id is None:
        return ""
    marker = load_scene_active_marker(project_dir, chapter_id, scene_id)
    if marker.get("revision_id"):
        return marker["revision_id"]
    record = load_scene_generation_record(
        project_dir, scene_id, version=marker.get("version", "")
    )
    if record is None or (not marker and record.status == "draft"):
        return ""
    return record.revision_id


def _find_chapter_for_scene(project_dir: Path, scene_id: str) -> str | None:
    """Find the chapter ID that contains the given scene, by scanning all volumes."""
    volumes = load_all_volumes(project_dir)
    for vol in volumes:
        for ch in vol.chapters:
            for sc in ch.scenes:
                if sc.id == scene_id:
                    return ch.id
    return None
# ── Pipeline Intermediate Output I/O ───────────────────────────────────────


def save_scene_plan(project_dir: Path, scene_id: str, plan: dict) -> None:
    """Save planner output to scenes/<chapter>/<scene_id>.plan.json."""
    _save_intermediate(project_dir, scene_id, "plan.json", plan)


def save_scene_intents(project_dir: Path, scene_id: str, intents: dict[str, dict]) -> None:
    """Save character intent outputs to scenes/<chapter>/<scene_id>.intents.json."""
    _save_intermediate(project_dir, scene_id, "intents.json", intents)


def save_scene_review(project_dir: Path, scene_id: str, review: dict) -> None:
    """Save reviewer output to scenes/<chapter>/<scene_id>.review.json."""
    _save_intermediate(project_dir, scene_id, "review.json", review)


def load_scene_plan(project_dir: Path, scene_id: str) -> dict | None:
    """Load saved plan. Returns None if not found."""
    return _load_intermediate(project_dir, scene_id, "plan.json")


def load_scene_intents(project_dir: Path, scene_id: str) -> dict[str, dict] | None:
    """Load saved intents. Returns None if not found."""
    return _load_intermediate(project_dir, scene_id, "intents.json")


def load_scene_review(project_dir: Path, scene_id: str) -> dict | None:
    """Load saved review. Returns None if not found."""
    return _load_intermediate(project_dir, scene_id, "review.json")


def _save_intermediate(project_dir: Path, scene_id: str, suffix: str, data: dict) -> None:
    """Write intermediate output to scenes/<chapter>/<scene_id>.<suffix>."""
    chapter_id = _find_chapter_for_scene(project_dir, scene_id)
    if chapter_id is None:
        raise ValueError(f"Scene {scene_id} not found in outline")
    chapter_dir = project_dir / "scenes" / chapter_id
    chapter_dir.mkdir(parents=True, exist_ok=True)
    filepath = chapter_dir / f"{scene_id}.{suffix}"
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, default=str)


def _load_intermediate(project_dir: Path, scene_id: str, suffix: str) -> dict | None:
    """Load intermediate output. Returns None if file doesn't exist."""
    chapter_id = _find_chapter_for_scene(project_dir, scene_id)
    if chapter_id is None:
        return None
    filepath = project_dir / "scenes" / chapter_id / f"{scene_id}.{suffix}"
    if not filepath.exists():
        return None
    with open(filepath, "r", encoding="utf-8") as fh:
        return json.load(fh)
