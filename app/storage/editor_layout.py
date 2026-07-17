"""Project-local Story Bible layout persistence."""

import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

import yaml
from PyQt6.QtCore import QTimer
from pydantic import BaseModel, Field, ValidationError


logger = logging.getLogger(__name__)


class CharacterEditorLayout(BaseModel):
    visible_fields: list[str] = Field(default_factory=list)
    collapsed_sections: list[str] = Field(default_factory=list)
    initialized_for_tier: str | None = None
    visibility_customized: bool = False
    custom_section_collapsed: bool = False
    hidden_custom_field_ids: list[str] = Field(default_factory=list)


class WorldEditorLayout(BaseModel):
    selected_item_id: str = "overview"
    type_filter: str = ""
    tag_filters: list[str] = Field(default_factory=list)
    overview_visible_sections: list[str] = Field(default_factory=list)
    overview_collapsed_sections: list[str] = Field(default_factory=list)
    collapsed_type_groups: list[str] = Field(default_factory=list)

    # Transitional aliases used by the Phase 2 editor until World extraction completes.
    @property
    def visible_sections(self) -> list[str]:
        return self.overview_visible_sections

    @visible_sections.setter
    def visible_sections(self, value: list[str]) -> None:
        self.overview_visible_sections = value

    @property
    def collapsed_sections(self) -> list[str]:
        return self.overview_collapsed_sections

    @collapsed_sections.setter
    def collapsed_sections(self, value: list[str]) -> None:
        self.overview_collapsed_sections = value


class StyleEditorLayout(BaseModel):
    collapsed_sections: list[str] = Field(default_factory=list)


class BibleEditorLayout(BaseModel):
    schema_version: int = 3
    selected_tab: str = "overview"
    world: WorldEditorLayout = Field(default_factory=WorldEditorLayout)
    style: StyleEditorLayout = Field(default_factory=StyleEditorLayout)
    characters: dict[str, CharacterEditorLayout] = Field(default_factory=dict)


class EditorLayoutStore:
    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir
        self._path = project_dir / ".novel-agent" / "editor-layout.yaml"
        self._save_timer: QTimer | None = None
        self._layout = BibleEditorLayout()
        self.recovered_from_error = False
        if self._path.exists():
            try:
                self._layout = self._load()
            except (yaml.YAMLError, ValidationError, OSError):
                self.recovered_from_error = True
                logger.exception("Failed to load editor layout; restoring defaults")
                broken_path = self._path.with_name(
                    f"editor-layout.broken-{datetime.now():%Y%m%d-%H%M%S}.yaml"
                )
                try:
                    self._path.replace(broken_path)
                except OSError:
                    logger.exception("Failed to back up broken editor layout")
                try:
                    self.save()
                except OSError:
                    logger.exception("Failed to persist restored editor layout")

    @property
    def layout(self) -> BibleEditorLayout:
        return self._layout

    @property
    def project_dir(self) -> Path:
        return self._project_dir

    def character_layout(self, character_id: str) -> CharacterEditorLayout:
        return self._layout.characters.setdefault(character_id, CharacterEditorLayout())

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        gitignore = self._project_dir / ".gitignore"
        content = gitignore.read_bytes() if gitignore.exists() else b""
        if b".novel-agent/" not in content.splitlines():
            with gitignore.open("ab") as handle:
                handle.write((b"" if not content or content.endswith(b"\n") else b"\n"))
                handle.write(b".novel-agent/\n")
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=".editor-layout.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                yaml.safe_dump(
                    self._layout.model_dump(mode="json"),
                    handle,
                    allow_unicode=True,
                    sort_keys=False,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def schedule_save(self) -> None:
        if self._save_timer is None:
            self._save_timer = QTimer()
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(150)
            self._save_timer.timeout.connect(self.save)
        self._save_timer.start()

    def _load(self) -> BibleEditorLayout:
        with self._path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if isinstance(raw, dict):
            if raw.get("schema_version", 1) == 1:
                raw = _migrate_v1(raw)
            if raw.get("schema_version") == 2:
                raw = _migrate_v2(raw)
        return BibleEditorLayout.model_validate(raw)


def _migrate_v1(raw: dict) -> dict:
    allowed = {"geography", "society", "rules", "taboos"}
    world_v1 = raw.get("world") if isinstance(raw.get("world"), dict) else {}
    migrated = dict(raw)
    migrated["schema_version"] = 2
    migrated["world"] = {
        "selected_item_id": "overview",
        "overview_visible_sections": [
            section
            for section in world_v1.get("visible_sections", [])
            if section in allowed
        ],
        "overview_collapsed_sections": [
            section
            for section in world_v1.get("collapsed_sections", [])
            if section in allowed
        ],
    }
    return migrated


def _migrate_v2(raw: dict) -> dict:
    migrated = dict(raw)
    migrated["schema_version"] = 3
    characters = migrated.get("characters", {})
    if isinstance(characters, dict):
        migrated["characters"] = {
            character_id: {
                **layout,
                "custom_section_collapsed": False,
                "hidden_custom_field_ids": [],
            }
            for character_id, layout in characters.items()
            if isinstance(layout, dict)
        }
    return migrated
