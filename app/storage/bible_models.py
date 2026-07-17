"""Typed, independently persisted World Bible elements."""

from __future__ import annotations

import unicodedata
import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


_SAFE_STORAGE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_storage_id(value: str) -> str:
    value = value.strip()
    if not _SAFE_STORAGE_ID.fullmatch(value):
        raise ValueError("ID must contain only letters, numbers, underscores, and hyphens")
    return value


class BibleElementType(str, Enum):
    FACTION = "faction"
    TERMINOLOGY = "terminology"
    HISTORICAL_EVENT = "historical_event"
    POWER_SYSTEM = "power_system"
    LOCATION = "location"


class BibleRelationKind(str, Enum):
    RELATED_TO = "related_to"
    PART_OF = "part_of"
    LOCATED_IN = "located_in"
    CONTROLS = "controls"
    USES = "uses"
    ALLIED_WITH = "allied_with"
    OPPOSED_TO = "opposed_to"
    CAUSED = "caused"
    PRECEDED_BY = "preceded_by"
    DEPENDS_ON = "depends_on"


class BibleElementRelation(BaseModel):
    kind: BibleRelationKind
    target_element_id: str
    note: str = ""

    @field_validator("target_element_id")
    @classmethod
    def validate_target_id(cls, value: str) -> str:
        return validate_storage_id(value)

    @field_validator("note")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def _normalize_display_values(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        if not value:
            continue
        if len(value) > 80:
            raise ValueError("aliases and tags must be at most 80 characters")
        key = normalize_text(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


class BibleElementBase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    element_type: BibleElementType
    name: str
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    importance: int = Field(default=3, ge=1, le=5)
    always_include: bool = False
    revision: int = Field(default=1, ge=1)
    relationships: list[BibleElementRelation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_storage_id(value)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("aliases", "tags")
    @classmethod
    def normalize_display_values(cls, values: list[str]) -> list[str]:
        return _normalize_display_values(values)


class FactionElement(BibleElementBase):
    element_type: Literal[BibleElementType.FACTION] = BibleElementType.FACTION
    description: str = ""
    goals: list[str] = Field(default_factory=list)
    ideology: str = ""


class TerminologyElement(BibleElementBase):
    element_type: Literal[BibleElementType.TERMINOLOGY] = BibleElementType.TERMINOLOGY
    definition: str = ""
    category: str = ""
    examples: list[str] = Field(default_factory=list)


class HistoricalEventElement(BibleElementBase):
    element_type: Literal[BibleElementType.HISTORICAL_EVENT] = (
        BibleElementType.HISTORICAL_EVENT
    )
    time_label: str = ""
    description: str = ""
    consequences: list[str] = Field(default_factory=list)


class PowerRealm(BaseModel):
    name: str
    abilities: list[str] = Field(default_factory=list)


class PowerSystemElement(BibleElementBase):
    element_type: Literal[BibleElementType.POWER_SYSTEM] = BibleElementType.POWER_SYSTEM
    realms: list[PowerRealm] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    costs: list[str] = Field(default_factory=list)
    rare_resources: list[str] = Field(default_factory=list)
    forbidden_methods: list[str] = Field(default_factory=list)


class LocationElement(BibleElementBase):
    element_type: Literal[BibleElementType.LOCATION] = BibleElementType.LOCATION
    description: str = ""
    atmosphere: str = ""
    notable_features: list[str] = Field(default_factory=list)


BibleElement = Annotated[
    Union[
        FactionElement,
        TerminologyElement,
        HistoricalEventElement,
        PowerSystemElement,
        LocationElement,
    ],
    Field(discriminator="element_type"),
]


class BibleManifest(BaseModel):
    schema_version: int = 1
    content_revision: int = 1
    element_order: list[str] = Field(default_factory=list)
    primary_power_system_id: str | None = None
    migrated_from_world_setting: bool = False
    migration_fingerprint: str = ""
    migrated_at: datetime | None = None
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("element_order")
    @classmethod
    def validate_element_order(cls, values: list[str]) -> list[str]:
        return [validate_storage_id(value) for value in values]

    @field_validator("primary_power_system_id")
    @classmethod
    def validate_primary_power_system_id(cls, value: str | None) -> str | None:
        return validate_storage_id(value) if value is not None else None


class WorldOverview(BaseModel):
    geography: str = ""
    rules: list[str] = Field(default_factory=list)
    taboos: list[str] = Field(default_factory=list)
    technology_level: str = ""
    social_structure: str = ""


class WorldBible(BaseModel):
    overview: WorldOverview = Field(default_factory=WorldOverview)
    elements: list[BibleElement] = Field(default_factory=list)
    manifest: BibleManifest = Field(default_factory=BibleManifest)


def semantically_equal(left: BibleElementBase, right: BibleElementBase) -> bool:
    excluded = {"revision", "created_at", "updated_at"}
    return left.model_dump(exclude=excluded) == right.model_dump(exclude=excluded)


def power_realms_from_legacy(
    realms: list[str], abilities: dict[str, str]
) -> list[PowerRealm]:
    names = list(realms) + [name for name in abilities if name not in realms]
    return [
        PowerRealm(name=name, abilities=[abilities[name]] if abilities.get(name) else [])
        for name in names
    ]
