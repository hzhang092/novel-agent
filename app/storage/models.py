"""Pydantic data models for NovelForge. All structured data is defined here."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
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
    generation_mode: str = "standard"
    scene_plan: dict = Field(default_factory=dict)
    character_intents: dict[str, dict] = Field(default_factory=dict)
    draft_text: str = ""
    review: Optional[dict] = None
    final_text: str = ""
    extracted_facts: list[dict] = Field(default_factory=list)
    approved_fact_ids: list[str] = Field(default_factory=list)
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
