"""Pydantic data models for NovelForge. All structured data is defined here."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.storage.bible_models import BibleElement, WorldOverview


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
    STATE_UPDATER = "state_updater"
    BIBLE_ASSISTANT = "bible_assistant"
    STORY_DESIGNER = "story_designer"


class CharacterCustomFieldType(str, Enum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    STRING_LIST = "string_list"


class CharacterCustomField(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    label: str
    value_type: CharacterCustomFieldType
    value: str | list[str] = ""
    include_in_generation: bool = True

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Custom field label cannot be empty")
        if len(value) > 60:
            raise ValueError("Custom field label cannot exceed 60 characters")
        return value

    @model_validator(mode="after")
    def validate_value(self) -> "CharacterCustomField":
        if self.value_type == CharacterCustomFieldType.STRING_LIST:
            if self.value == "":
                self.value = []
            if not isinstance(self.value, list):
                raise ValueError("String-list custom field value must be a list")
            values = [value.strip() for value in self.value]
            if any(not value for value in values):
                raise ValueError("String-list custom field items cannot be empty")
            if len(values) > 50 or any(len(value) > 500 for value in values):
                raise ValueError("String-list custom field value is too large")
            self.value = values
        elif not isinstance(self.value, str):
            raise ValueError("Text custom field value must be a string")
        elif len(self.value) > (
            2_000
            if self.value_type == CharacterCustomFieldType.TEXT
            else 10_000
        ):
            raise ValueError("Text custom field value is too large")
        return self


class CharacterElementRelationKind(str, Enum):
    MEMBER_OF = "member_of"
    LEADS = "leads"
    SERVES = "serves"
    OPPOSED_TO = "opposed_to"
    ORIGINATES_FROM = "originates_from"
    BASED_IN = "based_in"
    USES = "uses"
    ASSOCIATED_WITH = "associated_with"


class CharacterElementRelation(BaseModel):
    kind: CharacterElementRelationKind
    target_element_id: str
    note: str = ""

    @field_validator("target_element_id", "note")
    @classmethod
    def trim_relation_text(cls, value: str) -> str:
        return value.strip()


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
    custom_fields: list[CharacterCustomField] = Field(default_factory=list, max_length=30)
    element_relations: list[CharacterElementRelation] = Field(default_factory=list)
    definition_revision: int = Field(default=1, ge=1)
    definition_updated_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="after")
    def validate_custom_fields(self) -> "CharacterCore":
        ids = [field.id for field in self.custom_fields]
        if len(ids) != len(set(ids)):
            raise ValueError("Custom field IDs must be unique")
        labels = [field.label.casefold() for field in self.custom_fields]
        if len(labels) != len(set(labels)):
            raise ValueError("Custom field labels must be unique")
        return self


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
    pov_character_id: str = ""
    participating_character_ids: list[str] = Field(default_factory=list)
    world_element_ids: list[str] = Field(default_factory=list)
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
    chapter_length_override: "ChapterLength | None" = None
    needs_review: bool = False


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


class ChapterCardStatus(str, Enum):
    UNWRITTEN = "待写"
    DRAFT = "草稿"
    APPROVED = "已批准"
    NEW_DRAFT = "有新草稿"
    NEEDS_REVIEW = "需要复核"


class ChapterCardProjection(BaseModel):
    id: str
    volume_id: str
    scene_id: str = ""
    title: str
    summary: str
    ending_hook: str
    status: ChapterCardStatus


class StoryArcProjection(BaseModel):
    id: str
    story_id: str
    title: str
    summary: str
    chapter_cards: list[ChapterCardProjection] = Field(default_factory=list)


class QuickCharacterProjection(BaseModel):
    id: str
    name: str
    identity: str
    personality: str
    long_term_goal: str | None = None


class QuickStoryProjection(BaseModel):
    arcs: list[StoryArcProjection] = Field(default_factory=list)
    main_characters: list[QuickCharacterProjection] = Field(default_factory=list)
    core_setting: WorldOverview = Field(default_factory=WorldOverview)


class ChapterCardEditPreview(BaseModel):
    chapter_id: str
    changed_fields: list[str] = Field(default_factory=list)
    title: str
    summary: str
    ending_hook: str


class StoryBriefDrift(BaseModel):
    changed_fields: list[str] = Field(default_factory=list)


class StoryPatchOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["character", "overview"]
    target_id: str = ""
    field: str
    value: str | list[str] | None


class StoryPatchPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["story_patch"] = "story_patch"
    base_revision: int = Field(default=1, ge=1)
    operations: list[StoryPatchOperation] = Field(min_length=1)
    changes: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)


class ReplanPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["replan"] = "replan"
    base_revision: int = Field(default=1, ge=1)
    future_chapter_ids: list[str] = Field(default_factory=list)
    published_chapter_ids: list[str] = Field(default_factory=list)
    downstream_review_chapter_ids: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    story_affecting: bool = True
    operations: list[dict] = Field(default_factory=list)


class LaterArcPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["later_arc"] = "later_arc"
    base_revision: int = Field(default=1, ge=1)
    title: str
    summary: str
    chapters: list[ChapterOutline] = Field(default_factory=list)
    direction_conflicts: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)


class ActiveReplanDraft(ReplanPreview):
    pass


class ActiveStoryPatchDraft(StoryPatchPreview):
    pass


class ActiveLaterArcDraft(LaterArcPlan):
    pass


# ── Scene Generation ───────────────────────────────────────────────────────

class GenerationReadPoints(BaseModel):
    characters: dict[str, dict] = Field(default_factory=dict)
    bible_elements: dict[str, dict] = Field(default_factory=dict)


def parse_generation_read_points(generated_with: dict) -> GenerationReadPoints:
    if "characters" in generated_with:
        return GenerationReadPoints.model_validate(generated_with)
    return GenerationReadPoints(characters=generated_with)

class SceneGenerationRecord(BaseModel):
    """Stored alongside prose for traceability."""
    scene_id: str
    source_chapter_id: str = ""
    revision_id: str = Field(default_factory=lambda: str(uuid4()))
    revision_number: int = 1
    scene_order: int = 0
    generated_from_checkpoint_id: str = ""
    generated_with: dict[str, dict] = Field(default_factory=dict)
    source_context_fingerprint: str = ""
    status: Literal["draft", "current", "superseded", "stale"] = "current"
    generation_mode: str = "standard"
    scene_plan: dict = Field(default_factory=dict)
    character_intents: dict[str, dict] = Field(default_factory=dict)
    generation_trace: list[dict] = Field(default_factory=list)
    draft_text: str = ""
    review: Optional[dict] = None
    final_text: str = ""
    extracted_facts: list[dict] = Field(default_factory=list)
    extracted_facts_raw: list[dict] = Field(default_factory=list)  # raw ExtractedFact dicts from pipeline
    state_changes_raw: list[dict] = Field(default_factory=list)  # raw StateChangeProposal dicts from pipeline
    scene_summary_raw: Optional[dict] = None
    approved_fact_ids: list[str] = Field(default_factory=list)
    approved_state_changes: list[str] = Field(default_factory=list)  # character_ids whose changes were approved
    approved_facts: list[dict] = Field(default_factory=list)
    approved_state_change_proposals: list[dict] = Field(default_factory=list)
    review_overridden: bool = False
    published_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    user_modifications: Optional[str] = None
    target_chinese_characters: int = 3000
    prose_chinese_characters: int = 0
    length_warning: str = ""
    stale_input: bool = False
    stale_input_reviewed: bool = False
    stale_reason: str = ""
    cancelled: bool = False


# ── Memory System ──────────────────────────────────────────────────────────

class CanonFact(BaseModel):
    """Immutable facts about the story world."""
    fact_id: str = Field(default_factory=lambda: str(uuid4()))
    description: str
    category: str  # world / character / plot
    source_scene_id: str
    source_scene_revision_id: str = ""
    importance: int = Field(default=3, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class SceneSummary(BaseModel):
    scene_id: str
    chapter_id: str = ""
    source_scene_revision_id: str = ""
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
    genre: str | None = None
    language: str = "zh-CN"
    llm_provider: str = "ollama"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    world_setting: WorldSetting = Field(default_factory=WorldSetting)
    style_guide: StyleGuide = Field(default_factory=StyleGuide)
    chapter_length: "ChapterLength" = Field(default_factory=lambda: ChapterLength())
    last_active_chapter_id: str | None = None


# ── Provider Config ────────────────────────────────────────────────────────

class ProviderConfig(BaseModel):
    """App-level LLM provider settings, persisted via QSettings."""
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen:14b"
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_api_key: str = Field(default="", exclude=True)
    routing: dict[str, str] = Field(default_factory=lambda: {
        "planner": "ollama",
        "characters": "ollama",
        "writer": "ollama",
        "reviewer": "ollama",
        "fact_extractor": "ollama",
        "state_updater": "ollama",
        "bible_assistant": "ollama",
        "story_designer": "ollama",
    })

    @model_validator(mode="after")
    def fill_missing_routes(self) -> "ProviderConfig":
        self.routing.setdefault(
            "state_updater",
            self.routing.get("fact_extractor", "ollama"),
        )
        self.routing.setdefault(
            "bible_assistant",
            self.routing.get("fact_extractor", "ollama"),
        )
        self.routing.setdefault("story_designer", "ollama")
        return self


# ── Guided planning ───────────────────────────────────────────────────────

def _normalized_text(value: str) -> str:
    return " ".join(value.split())


class StoryBrief(BaseModel):
    """Author-controlled direction for guided planning."""

    model_config = ConfigDict(extra="forbid")
    revision: int = Field(default=1, ge=1)
    setting_tags: list[str] = Field(default_factory=list)
    protagonist_tags: list[str] = Field(default_factory=list)
    relationship_tags: list[str] = Field(default_factory=list)
    plot_engine_tags: list[str] = Field(default_factory=list)
    tone_tags: list[str] = Field(default_factory=list)
    premise: str = ""
    target_length: Literal["short", "around_30", "around_100", "ongoing", "custom"] = "short"
    custom_target_chapters: int | None = Field(default=None, gt=0)
    romance_emphasis: Literal["none", "secondary", "primary"] = "none"
    protagonist_structure: Literal["single", "dual", "ensemble"] = "single"
    chapter_length: "ChapterLength" = Field(default_factory=lambda: ChapterLength())

    @field_validator(
        "premise", mode="before",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _normalized_text(value)

    @field_validator(
        "setting_tags", "protagonist_tags", "relationship_tags", "plot_engine_tags",
        "tone_tags",
    )
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            value = _normalized_text(value)
            if value and value not in normalized:
                normalized.append(value)
        return normalized


class ChapterLength(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset: Literal["short", "standard", "long", "custom"] = "standard"
    target_chinese_characters: int = Field(default=3000, gt=0)

    @property
    def resolved_target(self) -> int:
        return {
            "short": 2000,
            "standard": 3000,
            "long": 5000,
            "custom": self.target_chinese_characters,
        }[self.preset]


class StoryProposal(BaseModel):
    """The bounded, reviewable output of Story Designer."""

    model_config = ConfigDict(extra="forbid")
    title: str
    logline: str
    main_characters: list[str] = Field(min_length=2, max_length=4)
    core_conflict: str
    story_promises: list[str] = Field(min_length=3, max_length=5)
    ending_direction: str


class ApprovedStoryProposal(StoryProposal):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    based_on_brief_revision: int = Field(ge=1)


class ActiveProposalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["proposal"] = "proposal"
    revision: int = Field(default=1, ge=1)
    based_on_brief_revision: int = Field(ge=1)
    proposal: StoryProposal


class StoryBootstrap(BaseModel):
    """The small, reviewable initial canonical bundle made by Story Designer."""

    model_config = ConfigDict(extra="forbid")
    overview: "WorldOverview"
    elements: list["BibleElement"] = Field(default_factory=list)
    characters: list[Character] = Field(min_length=2, max_length=4)
    style: StyleGuide
    arcs: list[VolumeOutline]

    @model_validator(mode="after")
    def validate_first_arc_only(self) -> "StoryBootstrap":
        if not self.arcs:
            raise ValueError("Bootstrap needs a first story arc")
        if not self.arcs[0].chapters:
            raise ValueError("Bootstrap first arc needs chapters")
        if any(len(chapter.scenes) != 1 for chapter in self.arcs[0].chapters):
            raise ValueError("Every bootstrap chapter needs exactly one scene")
        if any(arc.chapters for arc in self.arcs[1:]):
            raise ValueError("Only the first bootstrap arc may contain chapters")
        arc_ids = [arc.id for arc in self.arcs]
        if len(arc_ids) != len(set(arc_ids)):
            raise ValueError("Bootstrap arc IDs must be unique")
        chapter_ids = [chapter.id for arc in self.arcs for chapter in arc.chapters]
        scene_ids = [scene.id for arc in self.arcs for chapter in arc.chapters for scene in chapter.scenes]
        element_ids = [element.id for element in self.elements]
        if len(chapter_ids) != len(set(chapter_ids)):
            raise ValueError("Bootstrap chapter IDs must be unique")
        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("Bootstrap scene IDs must be unique")
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("Bootstrap Bible Element IDs must be unique")
        if any(
            chapter.volume_id and chapter.volume_id != arc.id
            for arc in self.arcs for chapter in arc.chapters
        ) or any(
            scene.chapter_id and scene.chapter_id != chapter.id
            for arc in self.arcs for chapter in arc.chapters for scene in chapter.scenes
        ):
            raise ValueError("Bootstrap outline association IDs must match their parent")
        character_ids = {character.core.id for character in self.characters}
        if len(character_ids) != len(self.characters) or any(
            character.state.character_id != character.core.id for character in self.characters
        ):
            raise ValueError("Bootstrap character states must match their character")
        return self


class ActiveBootstrapDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["bootstrap"] = "bootstrap"
    revision: int = Field(default=1, ge=1)
    based_on_brief_revision: int = Field(ge=1)
    based_on_proposal_revision: int = Field(ge=1)
    bootstrap: StoryBootstrap


class BootstrapPatchOperation(BaseModel):
    """A deliberately small RFC6902 subset for reviewable draft edits."""

    model_config = ConfigDict(extra="forbid")
    op: Literal["replace", "add", "remove"] = "replace"
    path: str
    value: object | None = None


class BootstrapPatchPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)
    operations: list[BootstrapPatchOperation] = Field(min_length=1)
    changes: list[str] = Field(min_length=1)
    consequences: list[str] = Field(min_length=1)


ActivePlanningDraft = Annotated[
    Union[
        ActiveProposalDraft,
        ActiveBootstrapDraft,
        ActiveStoryPatchDraft,
        ActiveReplanDraft,
        ActiveLaterArcDraft,
    ],
    Field(discriminator="kind"),
]


class PlanningData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    story_brief: StoryBrief | None = None
    provisional_destination: str = ""
    approved_proposal: ApprovedStoryProposal | None = None
    approved_brief: StoryBrief | None = None
    active_draft: ActivePlanningDraft | None = None


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


class ScenePlanPatch(BaseModel):
    """Explicit plan changes required before a story-affecting rewrite."""

    base_revision_id: str = ""
    scene_goal: str | None = None
    required_beats: list[str] | None = None
    conflict: str | None = None
    emotional_arc: str | None = None
    ending_hook: str | None = None
    continuity_constraints: list[str] | None = None

    def apply(self, plan: ScenePlan) -> ScenePlan:
        values = plan.model_dump()
        for field in (
            "scene_goal",
            "required_beats",
            "conflict",
            "emotional_arc",
            "ending_hook",
            "continuity_constraints",
        ):
            value = getattr(self, field)
            if value is not None:
                values[field] = value
        return ScenePlan.model_validate(values)


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
