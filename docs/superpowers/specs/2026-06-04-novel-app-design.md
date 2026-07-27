# NovelForge — AI-Powered Novel Writing Studio

**Date:** 2026-06-04
**Status:** Draft — captures conversations and design decisions to date
**Target app type:** Desktop (Python, local-first)

---

## 1. Product Overview

NovelForge is a **local-first desktop application** for writing Chinese web novels (网络小说/网文) with AI assistance. The user creates a structured "Novel Bible" (world setting, character cards, multi-level outline), and the app generates scenes through a multi-agent pipeline, with the user in the loop to steer, approve, or rewrite.

The app is designed for a **single user or small group of writing friends**, not as a public multi-tenant SaaS.

**Core philosophy:** The app doesn't chat with the user to produce a novel. It runs a structured production pipeline: the user is the editor-in-chief, the AI agents are specialized writers who handle sub-tasks, and the final prose belongs to the user.

---

## 2. Design Decisions (from Q&A)

| Dimension | Decision | Rationale |
|---|---|---|
| **App type** | Desktop app | Single-user / small-group; no multi-tenancy |
| **Framework** | Python (PyQt6) — confirmed after evaluating Tauri (see Appendix B) | Single-process architecture avoids IPC overhead for the multi-agent pipeline; PyInstaller for standalone `.exe` distribution |
| **LLM backend** | User picks per project: Ollama (local) or DeepSeek (API) | Not mixed per scene; clean provider abstraction |
| **LLM mode** | Single model loaded; sequential agent calls | Subagent = system prompt + schema, not a separate model instance |
| **Writing workflow** | Hybrid — mostly automatic, user can pause and steer mid-scene | Balances speed with creative control |
| **Character interaction** | Characters debate/react to each other | More dynamic, produces richer scenes |
| **World setting role** | World-as-character — actively constrains scenes | Prevents rule violations, maintains consistency |
| **Style definition** | Reference text + free-text notes | Concrete grounding with flexible adjustments |
| **Editor layout** | Split view — prose on one side, source materials on the other | Cross-reference while reading/editing |
| **Data storage** | Files only — YAML/Markdown/JSON on disk (see Appendix A for full design) | Simple, git-friendly, no rebuild step. Indexed lookups and search deferred to v2. Agent logs written as JSON lines files. |
| **Language priority** | Chinese (zh-CN) first, English extensibility later | User's primary need; architecture language-agnostic |
| **Architecture principle** | Subagents produce *intent*, not prose. One writer agent owns all final prose | Prevents incoherent multi-voice output |
| **Character agent scaling** | Only **major** characters run through intent agents; supporting/background characters are writer context | 2–4 intent agents max per scene regardless of total participant count |

---

## 3. Architecture

### 3.1 High-Level Architecture (Adapted from React+FastAPI to PyQt Desktop)

```text
┌──────────────────────────────────────────────┐
│               PyQt Desktop App                │
│                                               │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Dashboard │  │ Novel    │  │ Scene Gen  │  │
│  │ & Project │  │ Bible    │  │ Workspace  │  │
│  │ Manager   │  │ Editor   │  │ (SplitView)│  │
│  └──────────┘  └──────────┘  └──────┬─────┘  │
│                                      │        │
│  ┌───────────────────────────────────┴──────┐ │
│  │           Orchestration Engine            │ │
│  │  (asyncio event loop in worker thread)    │ │
│  │                                           │ │
│  │  Pipeline: Planner → Characters → Writer  │ │
│  │            → Reviewer → Rewriter          │ │
│  └───────────────────┬──────────────────────┘ │
│                      │                        │
│  ┌───────────────────┴──────────────────────┐ │
│  │           LLM Provider Layer              │ │
│  │  ┌──────────────┐  ┌──────────────────┐  │ │
│  │  │ OllamaProvider│  │ DeepSeekProvider │  │ │
│  │  └──────────────┘  └──────────────────┘  │ │
│  └──────────────────────────────────────────┘ │
│                      │                        │
│  ┌───────────────────┴──────────────────────┐ │
│  │           Storage Layer                   │ │
│  │  ┌────────────────────────────────────┐  │ │
│  │  │ File Storage (YAML/Markdown/JSON)  │  │ │
│  │  │ (project files, scenes, agent logs)│  │ │
│  │  └────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

### 3.2 Key Architectural Decisions

- **Single Python process.** The orchestration engine runs in an asyncio worker thread behind the PyQt GUI (using `qasync` to integrate the event loop with Qt's signal/slot system). No HTTP server, no REST API, no two-process overhead.
- **Provider abstraction.** `LLMProvider` interface with `OllamaProvider` and `DeepSeekProvider` implementations. User selects per project in settings.
- **Async pipeline.** Agents run as asyncio tasks. Scene planning and character intents can run concurrently where beneficial.
- **Pydantic schemas** for all structured agent outputs. JSON for non-prose agents; free-text for the Writer agent.

### 3.3 Pipeline Flow (per scene)

```text
User triggers "Generate Scene"

↓ Step 1: Build Scene Context (RetrievalEngine)
  The RetrievalEngine deterministically filters what enters the prompt:
  - Collect world rules relevant to this scene's location, factions, power usage
  - Collect character cards for scene participants
    · Major characters: full Character (Core + State)
    · Supporting characters: name + relationship + one-line description → writer context
    · Background characters: name only → writer context
  - Collect chapter/scene outline
  - Collect recent continuity summary (last 3–5 scenes)
  - Collect relevant canon facts (category-filtered: world, character, plot)
  - Collect style guide
  - Assemble into a bounded context window
  - (MVP) Present the Context Preview panel to the user before generation

↓ Step 2: Scene Planner Agent
  - Input: assembled context
  - Output: structured scene plan (beats, conflict, emotional arc, ending hook)
  - Model: local via Ollama (fast, structured output with JSON schema)

↓ Step 3: Character Intent Agents (major characters only)
  - Run one agent per major-tier character (max 2–4)
  - Input: context + character card (Core + State) + scene plan
  - Output: character intent JSON (emotion, private/public goals, dialogue intentions, forbidden actions)
  - Model: local via Ollama (fast, structured output)
  - Knowledge boundaries enforced at prompt level
  - Supporting and background characters are passed directly to the Writer as context

↓ Step 4: Writer Agent
  - Input: context + scene plan + major character intents + supporting/background character context + style guide
  - Output: Chinese novel prose (free-text, no JSON)
  - Model: DeepSeek preferred for quality prose; Ollama fallback
  - The ONLY agent that writes prose

↓ Step 5: Review Agent (Continuity + Style)
  - Input: context + scene plan + draft + character intents
  - Output: review JSON (issues with severity, pass/fail)
  - Model: local via Ollama (structured output)
  - For v1: single combined reviewer
  - Post-MVP: split into Continuity Reviewer and Style Reviewer (see §5.4)

↓ Step 6 (optional): Rewrite Agent
  - Triggered if review fails or user requests changes
  - Input: draft + review + rewrite instructions
  - Output: revised prose

↓ Step 7: Update Memory
  - Step 7a: Fact Extractor — extract claimed new facts from generated prose
  - Step 7b: Present extracted facts to user for approval (Human Approval gate)
  - Step 7c: Append approved facts to Canon Database
  - Step 7d: Generate scene summary
  - Step 7e: Update CharacterState for all participating major characters
  - Step 7f: Update open plot threads

↓ Return scene draft to editor
```

### 3.4 Generation Modes

| Mode | Agents Used | Use Case |
|---|---|---|
| **Draft** | Planner → Writer | Fast exploration, early chapters |
| **Standard** | Planner → Character Agents (major only) → Writer → Reviewer | Default, balanced quality/speed |
| **High-Quality** | Planner → Character Agents (major only) → Director → Writer → Continuity Reviewer \| Style Reviewer (parallel) → Rewriter → Final Review | Climax scenes, critical chapters |
| **Rewrite** | Existing draft → Rewrite instruction → Rewriter → Reviewer | Revising generated or user-written text |

---

## 4. Data Model

### 4.1 Project

```python
class Project(BaseModel):
    id: str  # UUID
    title: str
    genre: str  # 玄幻, 都市, 科幻, 历史, 无限流, etc.
    language: str  # zh-CN
    llm_provider: str  # "ollama" | "deepseek"
    created_at: datetime
    updated_at: datetime
```

### 4.2 Style Guide

```python
class StyleGuide(BaseModel):
    """Explicit style traits, not author names."""
    pacing: str  # 节奏快/慢
    dialogue_density: str  # 对白多/适中/少
    description_style: str  # 简练/细致
    tone: str  # 严肃/轻松/热血/黑暗
    sentence_length: str  # 长句多/短句多/混合
    pov: str  # 第三人称/第一人称/多视角
    taboo_patterns: list[str]
    preferred_patterns: list[str]
    reference_passages: list[str]  # approved prose samples
    freeform_notes: str
```

### 4.3 World Setting

```python
class PowerSystem(BaseModel):
    """Structured model for cultivation/Xianxia power systems."""
    realms: list[str]  # 炼气, 筑基, 金丹...
    abilities: dict[str, str]  # realm → description of abilities
    limitations: list[str]
    costs: list[str]  # what it costs to use power
    rare_resources: list[str]
    forbidden_methods: list[str]

class WorldSetting(BaseModel):
    geography: str
    power_system: PowerSystem | None = None
    factions: list[dict[str, str]]  # name, description, goals
    history: str
    rules: list[str]  # immutable facts the world must obey
    taboos: list[str]
    technology_level: str
    social_structure: str
    terminology: dict[str, str]  # term → definition
```

### 4.4 Character Model (Core + State Separation)

Characters are classified into three tiers. Only **major** characters run through intent agents per scene.

```python
class CharacterTier(str, Enum):
    MAJOR = "major"            # Runs through intent agent per scene
    SUPPORTING = "supporting"  # Provided to writer as context, no intent agent
    BACKGROUND = "background"  # Named only; writer handles entirely
```

#### CharacterCore (rarely changes)

```python
class CharacterCore(BaseModel):
    """Immutable or very-slowly-changing traits."""
    id: str
    name: str
    aliases: list[str] = []
    tier: CharacterTier = CharacterTier.SUPPORTING
    identity: str
    age: str | int
    appearance: str
    personality: str           # stable personality traits
    background: str            # history before story start
    long_term_goal: str | None = None
    hidden_motive: str | None = None
    speech_style: str          # 说话风格
    core_skills: list[str]     # innate abilities that don't change much
    core_weaknesses: list[str] # permanent flaws
```

#### CharacterState (updates per scene)

```python
class CharacterState(BaseModel):
    """Mutable state that evolves across scenes."""
    character_id: str
    current_goal: str                           # what they want right now
    current_emotion: str                        # dominant emotion heading into a scene
    current_location: str                       # where they are now
    current_power_level: str | None = None      # for cultivation/progression stories
    current_relationships: dict[str, str]       # character_name → current relationship
    current_knowledge: list[str]                # facts learned since story start
    current_secrets: list[str]                  # secrets still hidden
    current_status: str                         # 状态：如 "受伤", "隐藏身份"
    last_updated_scene: str | None = None       # scene_id of last update
```

#### Full Character Record (assembled for agents)

```python
class Character(BaseModel):
    """Assembled view: core + current state."""
    core: CharacterCore
    state: CharacterState

    @property
    def knowledge_scope(self) -> list[str]:
        """Everything this character knows (core background + learned facts)."""
        return self.core.background_knowledge() + self.state.current_knowledge
```

**Why this split matters:** After 200 chapters, `current_goal`, `relationships`, `power_level`, `knowledge`, and `status` all change dramatically. A single flat card becomes outdated. Separating core from state means only `CharacterState` is updated per scene, while `CharacterCore` stays stable. This becomes important surprisingly early — within the first 20–30 chapters for most web novels.

### 4.5 Outline Hierarchy

```python
class SceneOutline(BaseModel):
    id: str
    chapter_id: str
    title: str
    location: str
    time: str
    pov_character: str
    participating_characters: list[str]
    scene_goal: str
    conflict: str
    required_plot_beats: list[str]
    emotional_turn: str
    ending_hook: str
    constraints: list[str] = []

class ChapterOutline(BaseModel):
    id: str
    volume_id: str
    title: str
    summary: str
    scenes: list[SceneOutline]
    target_word_count: int

class VolumeOutline(BaseModel):
    id: str
    story_id: str
    title: str
    summary: str
    chapters: list[ChapterOutline]

class StoryOutline(BaseModel):
    id: str
    project_id: str
    premise: str
    themes: list[str]
    ending: str
    volumes: list[VolumeOutline]
```

### 4.6 Scene (Generated)

```python
class SceneGenerationRecord(BaseModel):
    """Stored alongside the prose for traceability."""
    scene_id: str
    generation_mode: str  # draft / standard / hq / rewrite
    scene_plan: dict  # planner output
    character_intents: dict[str, dict]  # character_name → intent JSON (major only)
    draft_text: str
    review: dict | None = None
    final_text: str
    extracted_facts: list[dict]  # raw fact extractor output
    approved_fact_ids: list[str] # facts the user approved into canon
    created_at: datetime
    user_modifications: str | None = None  # user's manual edits
```

### 4.7 Memory System

```python
class CanonFact(BaseModel):
    """Immutable facts about the story world."""
    fact_id: str
    description: str
    category: str  # world / character / plot
    source_scene_id: str
    created_at: datetime

class SceneSummary(BaseModel):
    scene_id: str
    chapter_id: str
    summary: str  # 2-3 sentence summary
    new_facts: list[str]
    character_state_changes: dict[str, str]  # character → state change
    relationship_changes: list[str]
    open_threads: list[str]  # plot threads introduced but not resolved

class ContinuityState(BaseModel):
    """Serialized and prepended to scene generation context."""
    recent_summaries: list[SceneSummary]  # last 3-5 scenes
    active_open_threads: list[str]
    current_character_states: dict[str, str]
    new_canon_facts_since_last_scene: list[str]
```

---

## 5. Agent Design

### 5.1 Provider Abstraction

```python
class LLMProvider(ABC):
    """Unified interface for Ollama and DeepSeek."""

    @abstractmethod
    async def generate_text(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        ...

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        temperature: float = 0.3,
    ) -> BaseModel:
        ...

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Streaming for the Writer agent's prose output."""
        ...
```

**OllamaProvider** uses the Ollama API with `format` field for JSON schema.
**DeepSeekProvider** uses OpenAI-compatible API with tool-call strict mode or JSON mode.

### 5.2 Agent Prompts

#### Scene Planner

```
你是一位长篇小说大纲规划师。
你的任务是将以下场景大纲转化为详细的剧情节拍规划。

输出 JSON 格式：
- scene_goal: str — 该场景的核心叙事目标
- required_beats: list[str] — 场景必须覆盖的剧情节拍
- conflict: str — 核心冲突描述
- emotional_arc: str — 情绪曲线（如：紧张→对峙→爆发→余波）
- ending_hook: str — 结尾钩子
- continuity_constraints: list[str] — 本场景不能违反的连续性约束

输入材料：
[context: world setting, story outline, chapter outline, scene outline,
 recent scene summaries, character cards for participants]
```

#### Character Intent Agent (per character)

```
你正在扮演小说角色「{character_name}」。
你不是作者。你不能写小说正文。

你的任务是根据角色卡、当前场景规划和你已知的信息，输出该角色在本场景中的意图。

你必须严格遵守以下规则：
- 你只能使用该角色知道的信息（见 knowledge_scope）
- 不要替其他角色做决定
- 不要推动超出大纲的剧情
- 不要输出小说正文

输出 JSON 格式：
- character_name: str
- current_emotion: str — 当前情绪（如：压抑愤怒、故作平静）
- private_goal: str — 私下真实目标
- public_goal: str — 表面目标（与其他角色互动时表现出的）
- attitude_to_others: dict — 对其他在场角色的态度
- likely_actions: list[str] — 可能采取的行动
- dialogue_intentions: list[str] — 想通过对话达成的目的
- forbidden_actions: list[str] — 该角色不会做的事
- speech_style_notes: str — 本场景中对白风格提醒

输入：
[context: character card (core + state),
 scene plan,
 this character's knowledge_scope]
```

#### Writer Agent

```
你是一位长篇小说作家，专业写作中文网络小说。

你的任务是根据提供的场景规划、角色意图、风格指南和前后文上下文，
写出完整的场景正文。

你必须严格遵守以下规则：
- 按照大纲中的剧情节拍推进叙事
- 世界观规则不能被打破
- 角色按照其意图和个性行事
- 维持指定的文风特征
- 输出纯正文，不包含 JSON 结构

风格指南：
[style guide]

世界观约束：
[world rules]

本场景规划：
[scene plan]

角色意图：
[character intents]

连续性上下文：
[recent scene summaries, open threads]

请开始写作：
```

#### Review Agent

```
你是一位严格的编辑，负责审查长篇小说场景的质量和连续性。

你的任务是检测以下类别的错误：

1. 连续性错误：
   - 角色是否使用了不该知道的信息（知识边界检查）
   - 情节是否与大纲冲突
   - 角色状态是否与前文一致
   - 已批准的正典事实是否被更改
   - 开放剧情线是否被正确推进

2. 风格合规：
   - 文风是否匹配风格指南
   - 对白风格是否匹配各角色的 speech_style
   - 文章节奏是否符合指定

3. 逻辑/质量：
   - 场景是否存在逻辑矛盾
   - 角色行为是否符合其性格设定
   - 对话和剧情是否需要更强的张力

输出 JSON 格式：
- passed: bool — 整体是否通过
- issues: list[dict] — 每个问题包含 category, severity (error|warning|suggestion), description, location
- style_score: int — 1…10
- required_rewrites: list[str] — 必须修正的问题的指令
```

#### Fact Extractor Agent

```
你是一位事实提取员。你的任务是从场景正文中提取新建立的正典事实。

规则：
- 只提取本场景独特创建的新事实
- 不要提取从大纲/角色卡/世界观中已能推断的事实
- 不要提取角色主观看法（仅为 if 其对其他角色为已知或对世界为客观事实）

输出 JSON 格式：
- facts: list[dict] — 每个 fact 包含：
  - description: str — 用一句话描述该事实
  - category: str — "world" | "character" | "plot"
  - source_excerpt: str — 正文中支持该事实的原文摘录
  - confidence: str — "certain" | "probable" | "speculative"
```

### 5.3 Pipeline Orchestrator

The pipeline orchestrator manages agent execution with streaming progress signals to the UI.

**Key behaviors:**
- Runs as an asyncio worker thread; communicates with UI via Qt signals
- Character Intent agents can run in parallel (they're independent, same model)
- Writer agent runs after Character intents complete
- Review agent (and Fact Extractor) run after Writer
- Writer streaming: tokens streamed via signal → QTextEdit incremental update

**Error handling:**
- If any Character agent fails, the Writer uses only completed intents + a warning
- If the Writer fails, the pipeline halts and the user is notified
- If the Review fails, the review JSON is still returned with partial results flagged
- All agent failures are logged per-run in `agent_runs.jsonl` in the project folder

### 5.4 Model Routing

| Task | Recommended Model | Rationale |
|---|---|---|
| Scene planning | Local Qwen via Ollama | Fast, structured output, quality sufficient for planning |
| Character simulation | Local Qwen via Ollama | Fast, structured output, quality sufficient for intent generation |
| Continuity review | Local Qwen via Ollama | Low temperature, deterministic, needs structured output |
| Style review | Local Qwen or DeepSeek | Local for speed; DeepSeek if style is subtle |
| **Final prose writing** | **DeepSeek (if quality matters) / Ollama (if privacy/cost matters)** | Prose quality is the bottleneck — DeepSeek preferred |
| Rewrite polish | DeepSeek (optional) | Only when local output needs refinement |

---

## 6. The Magic: What Makes This Possible

### 6.1 Knowledge Boundaries

Every character agent receives a `knowledge_scope` derived from `CharacterState.current_knowledge`. Characters cannot reference events they didn't witness or information they haven't learned. The Review agent checks for knowledge boundary violations.

Knowledge boundaries make multi-character scenes feel organic: supporting characters react to what they perceive, not what the reader knows.

### 6.2 Intent Over Prose

Character agents output intentions, not prose. This prevents the "stitched together" problem where each character's prose style clashes. The Writer agent is the sole owner of narrative voice.

### 6.3 CharacterState as Living Memory

Separating CharacterCore (stable) from CharacterState (mutable) means the app maintains an up-to-date picture of every character's emotional state, goals, relationships, and knowledge over hundreds of chapters — without the agent needing to re-read earlier chapters.

### 6.4 Canon Facts with Human Approval

Facts discovered during scene generation are extracted by the Fact Extractor but only enter the canon database after human approval. This prevents AI hallucination from polluting the story's factual foundation.

### 6.5 Deterministic RetrievalEngine

The RetrievalEngine deterministically collects what enters the prompt. It filters canon facts by category, collects scene summaries, assembles character cards — all based on explicit, auditable rules. No embedding-based RAG. The Context Preview panel shows the user exactly what the model will see.

---

## 7. UI Design

### 7.1 Screen Layout

The app has four main views accessible via a left sidebar:

1. **Dashboard (总览):** Project overview with writing progress, recent scenes, character counts, open plot threads.
2. **Novel Bible (设定集):** Tabbed editor for world setting, power system, factions, characters (Core + State tabs), timeline, and style guide.
3. **Outline (大纲):** Tree view of volumes → chapters → scenes. Selecting a node shows its detail card.
4. **Writing Workspace (写作台):** Three-pane split view for scene generation.

### 7.2 Writing Workspace (Three-Pane Layout)

- **Left panel (280px):** Scene context — current scene info, participating characters with current states, scene constraints, model settings.
- **Center panel (flex):** Prose editor — toolbar (generate, rewrite, cut/copy/paste, annotate), scrollable prose area.
- **Right panel (280px):** Agent trace (collapsible tree showing pipeline progress), rewrite quick-actions, keyboard shortcuts reference.

### 7.3 Context Preview Panel (Pre-Generation Audit)

Before generation, the Context Preview panel shows exactly what will enter the model's context window:

- World rules being applied
- Character cards being included (with knowledge scope indicators)
- Scene summaries being used for continuity
- Canon facts being referenced

This debuggability is more important than a frictionless one-click experience.

### 7.4 Fact Approval Panel (Post-Generation Review)

After generation, the Fact Approval panel presents extracted facts for human review:

- Each fact has a description, category, source excerpt, and confidence level
- User can approve, reject, or edit each fact
- Approved facts enter the canon database

---

## 9. MVP Scope

### 9.1 What's In

**Core pipeline:**
- Scene Planner
- Character Intent Agent (major-tier characters only, max 2–4 per scene)
- Writer Agent
- Review Agent (combined continuity + style)
- Fact Extractor Agent

**Storage:**
- Project folder: `project.yaml`, `world.md`, `characters/*.yaml`, `outline/*.yaml`, `scenes/*.md`
- `agent_runs.jsonl` and `token_usage.jsonl` for agent run logs and token usage tracking
- File system for exported Markdown

**UI:**
- Project Dashboard
- Novel Bible Editor (tabbed)
- Outline Editor (tree)
- Scene Generation Workspace (split view with agent trace)
- **Context Preview panel** (pre-generation context audit)
- **Fact Approval panel** (post-generation fact review)

### 9.2 Explicitly Out of Scope for v1

- Batch scene generation
- Full-novel autonomous generation
- Director agent (high-quality mode only)
- Split Reviewer (Continuity vs Style as separate agents)
- EPUB/DOCX export (Markdown only)
- Plugin system for custom agents
- LLM provider hot-swap mid-project
- Multiple concurrent projects open
- Vector-based semantic search (RAG)
- Real-time collaborative editing
- Cloud sync

---

## 10. Development Phases

| Phase | Focus | Deliverables |
|---|---|---|
| **1. Foundation** | Project structure, Pydantic models, file store, LLM provider abstraction | Empty PyQt app that opens, creates a project, writes to disk |
| **2. Bible Editor** | World, character, outline editors | Full CRUD on character cards, outline tree, world settings |
| **3. Single Agent** | Writer agent wired end-to-end | Generate one scene from hardcoded context → display in editor |
| **4. Full Pipeline** | Planner + Characters + Writer + Reviewer | Generate scene with full pipeline, agent trace panel live |
| **5. Memory System** | Fact Extractor, approval gate, scene summaries | Generated facts appear in approval panel, approved facts stored |
| **6. Polish & Package** | Error handling, Context Preview, PyInstaller build | Standalone `.exe`, tested end-to-end with a 10-chapter novel |

---

## 11. Risk Mitigation

| Risk | Mitigation |
|---|---|
| **Characters hallucinate facts** | Every character agent receives `knowledge_scope` derived from CharacterState; Review agent checks knowledge violations |
| **Final prose feels stitched together** | Character agents output *intentions only*; Writer agent owns all prose (single voice) |
| **Long novel loses continuity** | Maintain canon facts with Human Approval gate (not auto-append); scene summaries; CharacterState per scene; open thread tracking. Never rely only on raw previous chapters |
| **Context window explodes at 100+ chapters** | RetrievalEngine deterministically filters by category/tag/keyword; Context Preview panel lets user audit selections; bounded prompt size regardless of novel length |
| **Too slow on local hardware** | Standard mode by default; only major characters run intent agents (capped at 2–4); run reviewer after draft; use DeepSeek for prose only when needed |
| **Character cards go stale after many chapters** | CharacterCore / CharacterState separation; only State updates per scene; Core changes require explicit user action |
| **Canon fact extraction misses critical events** | Fact Extractor agent + mandatory Human Approval gate; user can add missed facts manually; reviewer checks against approved canon only |
| **Style imitation becomes vague** | Represent style as explicit traits, not author names; store approved prose samples; let user rate generated scenes |
| **LLM prompt injection / role-breaking** | Structured output schemas limit what agents can return; character prompts explicitly forbid out-of-character actions |
| **Single model bottleneck** | Provider abstraction makes model swaps trivial; user can route different pipeline steps to different models |
| **Large cast scenes (sect wars, tournaments)** | Only major-tier characters run intent agents; supporting/background characters are writer context; intent agent count capped at 4 regardless of total participants |

---

## 12. Project Structure (Planned)

```text
novel-agent/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Entry point, launches PyQt app
│   ├── config.py                  # App settings, provider config
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py         # Main window with tab navigation
│   │   ├── dashboard.py           # Project dashboard
│   │   ├── bible_editor.py        # Novel Bible tabs
│   │   ├── outline_editor.py      # Tree outline editor
│   │   ├── scene_workspace.py     # Split-view generation workspace
│   │   ├── context_preview.py     # Context Preview panel (pre-generation audit)
│   │   ├── fact_approval.py       # Fact Approval panel (post-generation review)
│   │   └── widgets/               # Reusable widgets
│   │       ├── agent_trace.py     # Collapsible agent output tree
│   │       ├── prose_editor.py    # Rich text editor for prose
│   │       └── character_card.py  # Card editor widget (Core + State tabs)
│   │
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── pipeline.py            # Scene generation pipeline orchestrator
│   │   ├── context_builder.py     # RetrievalEngine — deterministic context assembly
│   │   ├── memory.py              # Continuity state, canon facts, scene summaries
│   │   └── agents/
│   │       ├── __init__.py
│   │       ├── base.py            # Base agent class
│   │       ├── planner.py         # Scene Planner agent
│   │       ├── character.py       # Character Intent agent (major-tier only)
│   │       ├── writer.py          # Writer agent
│   │       ├── reviewer.py        # Review agent (combined for v1)
│   │       └── fact_extractor.py  # Fact Extractor agent
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                # LLMProvider abstract class
│   │   ├── ollama.py              # OllamaProvider implementation
│   │   └── deepseek.py            # DeepSeekProvider implementation
│   │
│   └── storage/
│       ├── __init__.py
│       ├── file_store.py          # JSON lines and parsed file I/O
│       ├── project_files.py       # YAML/Markdown project file I/O
│       ├── models.py              # Pydantic models (data schema)
│       └── repository.py          # CRUD operations
│
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-06-04-novel-app-design.md  # This file
│
├── pyproject.toml
├── requirements.txt
├── CLAUDE.md
└── README.md
```

---

## 13. Technology Stack

| Component | Choice | Rationale |
|---|---|---|
| **Language** | Python 3.12+ | Best ecosystem for LLM orchestration; matches simplicity goal |
| **GUI** | PyQt6 | Mature desktop framework; split pane, tabs, rich text, tree views |
| **Async** | asyncio + qasync | Async pipeline without blocking UI; single-process |
| **Data validation** | Pydantic v2 | First-class JSON schema for structured agent outputs; serialization |
| **Storage** | Files only — YAML/Markdown for source materials and generated prose; JSON lines (`.jsonl`) for agent run logs and token usage | Simplicity first; all data is human-readable and git-friendly. No database dependency. See Appendix A. |
| **LLM client (Ollama)** | httpx + Ollama API | Direct HTTP calls; lightweight, no SDK needed |
| **LLM client (DeepSeek)** | openai Python SDK | DeepSeek is OpenAI-compatible; standard SDK |
| **File export** | python-markdown, pandoc | Markdown → DOCX/EPUB via pandoc bridge |
| **Packaging** | PyInstaller | Mature, well-documented; bundles Python + Qt + all deps into single `.exe`; ~60–80 MB output for this project |

---

## 14. Design Principles

1. **Subagents produce intent, not prose.** Character agents output motives, goals, and dialogue intentions. The Writer agent is the sole producer of final narrative text.

2. **Knowledge boundaries are non-negotiable.** Characters can only act on information they possess. The Review agent validates this.

3. **The user is the editor-in-chief.** Generated text is a draft. The user can edit, rewrite, regenerate, or override at any point. All canon facts pass through Human Approval before entering the database.

4. **Start structured, stay structured.** The non-prose pipeline runs on typed JSON schemas. This makes agents deterministic, debuggable, and replaceable.

5. **Local-first, cloud-optional.** The app works entirely offline with Ollama. DeepSeek is an optional quality upgrade, not a requirement.

6. **Memory is explicit, not vector-based (v1).** Canon facts, scene summaries, and character states are structured data. Retrieval is deterministic via the RetrievalEngine. Vector search is a V2 addition if justified.

7. **One scene at a time in v1.** Batch generation, full-novel generation, and autonomous writing are post-MVP features. v1 focuses on quality and user control over each scene.

8. **Context visibility over opacity.** The Context Preview panel shows users exactly what enters the model prompt. This debuggability is more important than a frictionless one-click experience.

---

## Appendix A: Storage Strategy — File-Only Design

The project uses files as the sole storage mechanism. No SQLite, no database, no rebuild step.

### A.1 Files Are the Source of Truth

Every piece of data in a project lives on disk as a file. Human-editable content uses YAML and Markdown. Machine-generated structured data uses JSON. Append-heavy operational data uses JSON lines (`.jsonl`).

There is no secondary store, no cache layer, and no reconciliation step. What's on disk is what the app uses.

### A.2 Concrete File Layout

```
MyNovel/
├── project.yaml          # version, title, genre, llm_provider
├── world.md              # free-text world setting
├── style.yaml            # style guide
├── characters/
│   ├── lin-xuan.yaml     # core + state
│   └── su-qingluan.yaml
├── outline/
│   ├── volume-1.yaml     # nested: volume → chapters → scenes
│   └── volume-2.yaml
├── scenes/
│   ├── ch-001/
│   │   ├── scene-001.md
│   │   ├── scene-001.plan.json
│   │   ├── scene-001.intents.json
│   │   └── scene-001.review.json
│   └── ch-002/
├── canon/
│   └── facts.yaml        # approved canon facts
├── exports/              # generated exports, not source
├── agent_runs.jsonl      # agent run logs (append-only)
├── token_usage.jsonl     # token usage tracking (append-only)
└── .gitignore            # ignores exports/
```

### A.3 Rationale

- **Simplicity.** No database to install, configure, migrate, or debug. One less dependency in the stack.
- **Git-friendly.** YAML and Markdown are inherently diffable. JSON lines can be diffed with standard tools. The `.gitignore` only excludes generated exports.
- **Transparency.** Users can inspect, edit, or version-control any project file with VS Code, Notepad, or any text editor.
- **Backup.** Copy the project folder. Done.
- **Scale ceiling.** File-based storage works well for projects with <200 scenes and <50 characters. At v1 scope, loading all character YAML files and scanning scene metadata into memory takes milliseconds.

### A.4 Deferred to v2

If the project outgrows file-only storage (200+ scenes, performance issues with file scanning, need for indexed search), the migration path is clear:

1. Add SQLite as an indexed lookup layer
2. Files remain the source of truth
3. SQLite regenerates from files on startup if lost or stale

This is a one-way door: adding SQLite later is straightforward. Removing it after building around it is not. Starting file-only keeps options open.

---

## Appendix B: Frontend Evaluation — Why PyQt6 Over Tauri

### B.1 The Tauri Alternative

Tauri is a Rust-based framework that renders a web frontend (HTML/CSS/JS) in the operating system's native webview, producing a small (~5 MB) binary. It was evaluated as an alternative to PyQt6 because web-based UIs offer superior rich text editing (TipTap/ProseMirror vs QTextEdit) and more modern component libraries.

### B.2 Architecture Gap: Single-Process vs Three-Process

With PyQt6, the entire application — GUI, orchestration engine, LLM providers, storage — runs in a single Python process. The multi-agent pipeline streams progress directly to the UI via asyncio + Qt signals.

With Tauri, the architecture splits into three processes:

```
Tauri Shell (Rust) — manages window, menus, file dialogs
        │
        ├── Webview (HTML/CSS/JS) — the UI rendered in system WebView2/WebKit
        │
        └── Python Sidecar — the entire novel-agent engine, spawned as subprocess
```

This requires an IPC protocol between the webview and Python. Three patterns were considered:

| Pattern | Streaming | Complexity | Notes |
|---|---|---|---|
| **Local HTTP + SSE** | Good | Medium | Python runs uvicorn on localhost; frontend fetches; SSE for token streaming |
| **Tauri Command Proxy** | Awkward | High | JS calls Tauri commands, Rust forwards to Python via socket; 3-hop IPC with streaming relay |
| **WebSocket** | Good | Medium | Single persistent connection; bidirectional for cancel signals |

### B.3 Where the Friction Lives

| Scenario | PyQt6 | Tauri + Python |
|---|---|---|
| **Mid-generation cancel** | Cancel asyncio task in-process. Instant. | Send cancel signal over SSE/WS, Python cancels, frontend waits for ack. ~50–200ms round-trip. |
| **Python crash** | App crashes. Single process, single fate. | Tauri detects sidecar exit. Frontend shows error with "Restart Engine". Graceful but extra code. |
| **Streaming prose tokens** | AsyncGenerator yields directly to QTextEdit.append(). Zero overhead. | Each token serialized as SSE data line, parsed by JS EventSource, inserted into DOM. Overhead at high rates. |
| **Packaging** | `pyinstaller --onefile main.py`. Single .exe. Mature. | Bundle Python embeddable + all pip packages + Tauri binary. Complex CI. |
| **Debugging pipeline failures** | Single process — one debugger, one stack trace. | Two processes — correlate Python logs with JS console. Request-ID correlation adds ceremony. |
| **Rich text editing** | QTextEdit is adequate but limited. No CJK optimizations, no track-changes diff. | TipTap/ProseMirror/Monaco. Vastly superior editing with proper IME support. |

### B.4 Decision: PyQt6 for v1, Tauri Revisit for v2+

The pipeline is the hardest part of this project to get right. Single-process PyQt6 means faster iteration on the agent architecture, easier debugging, and no IPC surface to maintain. The `QTextEdit` limitations are real but acceptable for v1 — the prose editor needs to be functional, not best-in-class.

**Revisit threshold for v2:** If user feedback consistently cites editing experience as the #1 friction point, the Tauri path becomes worth the IPC cost. By then the engine's API surface will be stable, and the frontend rewrite can target a well-defined set of endpoints rather than evolving alongside the pipeline.

The engine code itself is designed to be frontend-agnostic: it exposes Python APIs, not Qt widgets. A future Tauri frontend would wrap the engine in a FastAPI layer without touching the agent logic.
