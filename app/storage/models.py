"""Pydantic data models for NovelForge. All structured data is defined here."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ── Character ──────────────────────────────────────────────────────────────

class CharacterTier(str, Enum):
    MAJOR = "major"
    SUPPORTING = "supporting"
    BACKGROUND = "background"


class AgentStepId(str, Enum):
    """Pipeline steps that can be routed to different providers."""
    PLANNER = "planner"
    CHARACTERS = "characters"
    WRITER = "writer"
    REVIEWER = "reviewer"
    FACT_EXTRACTOR = "fact_extractor"


class CharacterCore(BaseModel):
    """Immutable or very-slowly-changing traits."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    aliases: list[str] = Field(default_factory=list)
    tier: CharacterTier = CharacterTier.SUPPORTING
    identity: str = ""
    age: str = ""
    appearance: str = ""
    personality: str = ""
    background: str = ""
    long_term_goal: Optional[str] = None
    hidden_motive: Optional[str] = None
    speech_style: str = ""
    core_skills: list[str] = Field(default_factory=list)
    core_weaknesses: list[str] = Field(default_factory=list)


class CharacterState(BaseModel):
    """Mutable state that evolves across scenes."""
    character_id: str
    current_goal: str = ""
    current_emotion: str = ""
    current_location: str = ""
    current_power_level: Optional[str] = None
    current_relationships: dict[str, str] = Field(default_factory=dict)
    current_knowledge: list[str] = Field(default_factory=list)
    current_secrets: list[str] = Field(default_factory=list)
    current_status: str = ""
    last_updated_scene: Optional[str] = None


class Character(BaseModel):
    """Assembled view: core + current state."""
    core: CharacterCore
    state: CharacterState


# ── World Setting ──────────────────────────────────────────────────────────

class PowerSystem(BaseModel):
    """Structured model for cultivation/Xianxia power systems."""
    realms: list[str] = Field(default_factory=list)
    abilities: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    costs: list[str] = Field(default_factory=list)
    rare_resources: list[str] = Field(default_factory=list)
    forbidden_methods: list[str] = Field(default_factory=list)


class WorldSetting(BaseModel):
    geography: str = ""
    power_system: Optional[PowerSystem] = None
    factions: list[dict[str, str]] = Field(default_factory=list)
    history: str = ""
    rules: list[str] = Field(default_factory=list)
    taboos: list[str] = Field(default_factory=list)
    technology_level: str = ""
    social_structure: str = ""
    terminology: dict[str, str] = Field(default_factory=dict)


# ── Style Guide ────────────────────────────────────────────────────────────

class StyleGuide(BaseModel):
    """Explicit style traits."""
    pacing: str = ""
    dialogue_density: str = ""
    description_style: str = ""
    tone: str = ""
    sentence_length: str = ""
    pov: str = ""
    taboo_patterns: list[str] = Field(default_factory=list)
    preferred_patterns: list[str] = Field(default_factory=list)
    reference_passages: list[str] = Field(default_factory=list)
    freeform_notes: str = ""


# ── Outline ────────────────────────────────────────────────────────────────

class SceneOutline(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    chapter_id: str = ""
    title: str = ""
    location: str = ""
    time: str = ""
    pov_character: str = ""
    participating_characters: list[str] = Field(default_factory=list)
    scene_goal: str = ""
    conflict: str = ""
    required_plot_beats: list[str] = Field(default_factory=list)
    emotional_turn: str = ""
    ending_hook: str = ""
    constraints: list[str] = Field(default_factory=list)


class ChapterOutline(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    volume_id: str = ""
    title: str = ""
    summary: str = ""
    scenes: list[SceneOutline] = Field(default_factory=list)
    target_word_count: int = 3000


class VolumeOutline(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    story_id: str = ""
    title: str = ""
    summary: str = ""
    chapters: list[ChapterOutline] = Field(default_factory=list)


class StoryOutline(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    premise: str = ""
    themes: list[str] = Field(default_factory=list)
    ending: str = ""
    volumes: list[VolumeOutline] = Field(default_factory=list)


# ── Scene Generation ───────────────────────────────────────────────────────

class SceneGenerationRecord(BaseModel):
    """Stored alongside prose for traceability."""
    scene_id: str
    revision_id: str = Field(default_factory=lambda: str(uuid4()))
    revision_number: int = 1
    scene_order: int = 0
    generated_from_checkpoint_id: str = ""
    generated_with: dict[str, dict] = Field(default_factory=dict)
    status: Literal["current", "superseded", "stale"] = "current"
    generation_mode: str = "standard"
    scene_plan: dict = Field(default_factory=dict)
    character_intents: dict[str, dict] = Field(default_factory=dict)
    draft_text: str = ""
    review: Optional[dict] = None
    final_text: str = ""
    extracted_facts: list[dict] = Field(default_factory=list)
    extracted_facts_raw: list[dict] = Field(default_factory=list)  # raw ExtractedFact dicts from pipeline
    state_changes_raw: list[dict] = Field(default_factory=list)  # raw StateChangeProposal dicts from pipeline
    approved_fact_ids: list[str] = Field(default_factory=list)
    approved_state_changes: list[str] = Field(default_factory=list)  # character_ids whose changes were approved
    created_at: datetime = Field(default_factory=datetime.now)
    user_modifications: Optional[str] = None


# ── Memory System ──────────────────────────────────────────────────────────

class CanonFact(BaseModel):
    """Immutable facts about the story world."""
    fact_id: str = Field(default_factory=lambda: str(uuid4()))
    description: str
    category: str  # world / character / plot
    source_scene_id: str
    importance: int = Field(default=3, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class SceneSummary(BaseModel):
    scene_id: str
    chapter_id: str = ""
    summary: str = ""
    new_facts: list[str] = Field(default_factory=list)
    character_state_changes: dict[str, str] = Field(default_factory=dict)
    relationship_changes: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)


class ContinuityState(BaseModel):
    """Serialized and prepended to scene generation context."""
    recent_summaries: list[SceneSummary] = Field(default_factory=list)
    active_open_threads: list[str] = Field(default_factory=list)
    current_character_states: dict[str, str] = Field(default_factory=dict)
    new_canon_facts_since_last_scene: list[str] = Field(default_factory=list)


# ── Project ────────────────────────────────────────────────────────────────

class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    genre: str
    language: str = "zh-CN"
    llm_provider: str = "ollama"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    world_setting: WorldSetting = Field(default_factory=WorldSetting)
    style_guide: StyleGuide = Field(default_factory=StyleGuide)


# ── Provider Config ────────────────────────────────────────────────────────

class ProviderConfig(BaseModel):
    """App-level LLM provider settings, persisted via QSettings."""
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen:14b"
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_api_key: str = ""
    routing: dict[str, str] = Field(default_factory=lambda: {
        "planner": "ollama",
        "characters": "ollama",
        "writer": "ollama",
        "reviewer": "ollama",
        "fact_extractor": "ollama",
    })


# ── Agent Output Schemas ───────────────────────────────────────────────────

class ScenePlan(BaseModel):
    """Scene Planner agent output."""
    scene_id: str = ""
    scene_goal: str = ""
    required_beats: list[str] = Field(default_factory=list)
    conflict: str = ""
    emotional_arc: str = ""
    ending_hook: str = ""
    continuity_constraints: list[str] = Field(default_factory=list)


class CharacterIntent(BaseModel):
    """Character Intent agent output for one major-tier character."""
    character_name: str = ""
    current_emotion: str = ""
    private_goal: str = ""
    public_goal: str = ""
    attitude_to_others: dict[str, str] = Field(default_factory=dict)
    likely_actions: list[str] = Field(default_factory=list)
    dialogue_intentions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    speech_style_notes: str = ""


class ReviewIssue(BaseModel):
    """A single issue found by the Reviewer agent."""
    severity: str = "minor"  # critical / major / minor
    description: str = ""
    category: str = ""  # continuity / style / hook / face_slap
    passed: bool = True


class ReviewResult(BaseModel):
    """Reviewer agent output."""
    scene_id: str = ""
    issues: list[ReviewIssue] = Field(default_factory=list)
    overall_pass: bool = True
    summary: str = ""


# ── Memory Pipeline Agent Outputs ─────────────────────────────────────────

class ExtractedFact(BaseModel):
    """A single fact extracted by the Fact Extractor from generated prose."""
    description: str
    category: str  # world / character / plot
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_excerpt: str = ""


# ── State Change discriminated union (LLM-facing) ─────────────────────────

CHARACTER_SCALAR_FIELDS = Literal[
    "emotion", "goal", "location", "status", "power_level"
]


class SetFieldChange(BaseModel):
    """Set a scalar state field to a new value."""
    type: Literal["set_field"]
    field: CHARACTER_SCALAR_FIELDS
    value: str


class RelationshipChange(BaseModel):
    """Add or update a relationship with another character."""
    type: Literal["relationship_change"]
    target_character_id: str
    relationship: str


class KnowledgeAddChange(BaseModel):
    """Add a fact to the character's knowledge."""
    type: Literal["knowledge_add"]
    fact: str


class KnowledgeRemoveChange(BaseModel):
    """Remove a fact from the character's knowledge."""
    type: Literal["knowledge_remove"]
    fact: str


class SecretAddChange(BaseModel):
    """Add a secret the character knows."""
    type: Literal["secret_add"]
    fact: str


class SecretRemoveChange(BaseModel):
    """Remove a secret from the character's knowledge."""
    type: Literal["secret_remove"]
    fact: str


StateChange = Annotated[
    Union[
        SetFieldChange,
        RelationshipChange,
        KnowledgeAddChange,
        KnowledgeRemoveChange,
        SecretAddChange,
        SecretRemoveChange,
    ],
    Field(discriminator="type"),
]


class StateChangeProposal(BaseModel):
    """LLM output: proposed state changes for one character after a scene.
    Contains only new values — code fills old values from the snapshot."""
    character_id: str = ""
    character_name: str = ""
    changes: list[StateChange] = Field(default_factory=list)


# ── Stored event record (events.jsonl line) ───────────────────────────────

class CharacterStoredChange(BaseModel):
    """A single change within a stored event, with old value filled by code."""
    type: str  # same discriminator as StateChange
    field: str = ""             # for set_field
    value: str = ""             # new value (for set_field)
    old: str = ""               # previous value (filled by code)
    fact: str = ""              # for knowledge_add/remove, secret_add/remove
    target_character_id: str = ""  # for relationship_change
    relationship: str = ""      # for relationship_change


class CharacterStateEvent(BaseModel):
    """One JSONL line in events.jsonl — a single StateUpdater run."""
    event_id: int = 0
    transaction_id: str = ""    # groups events from same pipeline run
    scene_id: str = ""
    scene_revision_id: str = ""
    scene_order: int = 0
    event_seq: int = 0
    character_id: str = ""
    source: str = "ai"          # ai | user | manual_event | system
    request_id: str = ""        # UUID for observability
    schema_version: int = 1
    invalidated: bool = False
    created_at: str = ""        # ISO timestamp
    changes: list[CharacterStoredChange] = Field(default_factory=list)


# ── State snapshot (state.yaml) ───────────────────────────────────────────

class CharacterStateSnapshot(BaseModel):
    """Materialized character state at a specific event_id.
    Written to state.yaml — the cached current-state view."""
    character_id: str = ""
    last_scene_id: str = ""
    last_event_id: int = 0
    snapshot_version: int = 1
    generated_at: str = ""
    emotion: str = ""
    goal: str = ""
    location: str = ""
    status: str = ""
    power_level: str = ""
    relationships: dict[str, str] = Field(default_factory=dict)
    knowledge: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)


# ── Scene-level state checkpoint (checkpoint.yaml per scene) ──────────────

class SceneStateCheckpoint(BaseModel):
    """Snapshot of all character states at a point in the scene.
    Written to characters/<name>/checkpoints/<scene_id>.yaml."""
    scene_id: str = ""
    scene_revision_id: str = ""
    scene_order: int = 0
    checkpoint_id: str = ""
    parent_checkpoint_id: str = ""
    event_id: int = 0
    character_id: str = ""
    invalidated: bool = False
    created_at: str = ""
    snapshot: CharacterStateSnapshot = Field(default_factory=CharacterStateSnapshot)


# ── Rebuild models that reference StateChange ─────────────────────────────

ContextStateChanges = list[StateChangeProposal]
