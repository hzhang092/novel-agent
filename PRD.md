# PRD: NovelForge — AI-Powered Chinese Web Novel Writing Studio

**Repo:** `hzhang092/novel-agent`
**Date:** 2026-07-26
**Status:** Decision-complete — two-experience expansion ready for implementation
**Label:** `ready-for-agent`

---

## Problem Statement

Writing a Chinese web novel (网络小说), from a short work to a 200+ chapter serial, requires holding enormous story state in your head. AI chat tools help with individual scenes but have no memory of world rules, character states, or plot threads across chapters. The author must manually re-explain the world every session. Worse, asking a single chat model to "write the next chapter" produces prose that ignores character knowledge boundaries, violates world rules, and drifts in style.

The user needs a writing tool that treats novel production as a structured pipeline—not a chat—while allowing different levels of visible complexity. A new author should be able to begin with a Story Brief and approve recognizable creative outcomes. An advanced author should be able to inspect and edit every story component. Both need the same continuity guarantees and must be able to switch workflows without converting the project.

## Solution

NovelForge is a local-first desktop application (Python + PyQt6) that generates Chinese web novel prose through a multi-agent pipeline. It offers **快速创作 (Quick Creation)** for outcome-oriented guided planning and chapter writing, and **深度创作 (Deep Creation)** for full control of the Story Bible, outline, context, agent trace, review, and continuity. Both experiences use the same canonical project data, single-scene chapter pipeline, revisions, and publication path.

The user may create the structured Story Bible and outline manually or approve a Story Designer proposal and bootstrap. Sub-agents produce *intentions* (not prose), a single Writer owns the narrative voice, and a Reviewer enforces continuity. All data is stored as human-readable YAML, Markdown, and JSON. LLM backends remain locally or cloud routed in advanced Settings; Quick Creation uses configured defaults without exposing routing in its normal flow.

Key differentiators:
- **Intent over prose:** Character agents output motives/goals, not dialogue. Writer synthesizes.
- **Knowledge boundaries:** Characters only act on information they possess.
- **Living character state:** CharacterCore (stable) / CharacterState (per-scene mutable) keeps characters current across 200+ chapters.
- **Canon facts with human approval:** AI-extracted facts must be approved before entering story memory.
- **Deterministic context assembly:** No embedding-based RAG. Explicit, auditable context selection with user preview.
- **One engine, two experiences:** Quick hides complexity but never creates simplified parallel data.
- **Approval before canon:** Guided planning, prose, and memory remain drafts until their explicit approval boundary.

## User Stories

**Project setup**

1. As an author, I want to begin with visually primary Quick ideation or create a blank Deep project, so that I can choose a starting workflow without choosing a permanent project type.
2. As a Quick author, I want project setup to ask only for an optional working title and location, so that genre and provider configuration do not block ideation.
3. As a Deep author, I want to fill in world settings, character cards, and outlines in any order without being forced through guided creation, so that I control the creative order.

**Novel Bible — World & Style**

4. As an author, I want to define my world's geography, factions, history, rules, taboos, and social structure in a structured editor, so the pipeline can enforce them.
5. As an author, I want to define a cultivation/power system (realms, abilities, limitations, costs, rare resources, forbidden methods), so that power progression stays consistent.
6. As an author, I want to define writing style using structured trait pickers (pacing, dialogue density, tone, sentence length, POV) plus freeform notes, so the Writer agent produces prose that matches my voice.
7. As an author, I want to optionally paste reference prose passages into the style guide, so the Writer has concrete examples of my desired style.
8. As an author, I want to save a glossary of world-specific terminology (term → definition), so the Writer uses consistent nomenclature.

**Novel Bible — Characters**

9. As an author, I want to create character cards with stable traits (identity, personality, background, speech style, skills, weaknesses) that rarely change, so I establish characters once.
10. As an author, I want mutable per-character state (current emotion, goal, location, relationships, knowledge, power level, status) that updates after each scene, so characters evolve across 200+ chapters without manual re-reading.
11. As an author, I want to assign a tier to each character (major/supporting/background), so only major characters consume LLM calls during scene generation.
12. As an author, I want the app to propose character state updates after each scene (emotion changes, new goals, relationship shifts, knowledge gained) for my approval, so I don't manually maintain state for every character.

**Outline**

13. As an author, I want to build a multi-level outline (Story Arcs/Volumes → Chapters → one Scene per Chapter) in a tree editor, so my story structure is explicit before generation.
14. As an author, I want each scene outline to specify location, time, POV character, participating characters, scene goal, conflict, emotional turn, and ending hook, so the pipeline has clear creative direction.
15. As an author, I want to view a pacing heatmap across chapters (hooks present/absent, power progression cadence, action-to-downtime ratio), so I catch structural pacing issues before writing.
16. As an author, I want the app to warn when a chapter lacks an ending hook (断章), so I maintain reader engagement.

**Scene Generation Pipeline**

17. As an author, I want to trigger scene generation from the Writing Workspace and see agent progress in real time in a trace panel, so I know what the pipeline is doing.
18. As an author, I want the RetrievalEngine to deterministically assemble scene context (relevant world rules, character cards, recent scene summaries, canon facts) that I can preview in a collapsed badge before generation, so I audit the AI's inputs without friction.
19. As an author using the Context Preview, I want to see a badge summary ("12 facts, 4 character states") and hit Enter to generate immediately when I trust the context, so the preview doesn't slow me down.
20. As an author, I want the Scene Planner to output a structured plan (beats, conflict, emotional arc, hook, constraints) before prose generation begins, so I can approve or edit the plan before the Writer runs.
21. As an author at the planner checkpoint, I want to approve the plan to continue the pipeline, or reject it to regenerate with different settings, so I maintain creative control at the highest-leverage decision point.
22. As an author, I want major characters' intents (emotion, private/public goals, dialogue intentions, likely actions, forbidden actions) generated in parallel before the Writer runs, so character behavior is coherent.
23. As an author, I want only one Writer agent to produce all narrative prose, synthesizing character intents, scene plan, and context into a single Chinese chapter, so the narrative voice is unified.
24. As an author, I want the Review agent to check generated prose for continuity violations, style drift, pacing issues (missing hooks), and face-slapping (打脸) beat completeness (setup → confrontation → payoff → reaction), so quality issues are caught before I read.
25. As an author, I want face-slapping (打脸) beats tracked automatically by the Reviewer: has the setup occurred, the confrontation, the payoff, and the witness reaction, so this core 网文 structural pattern is enforced.

**Post-Generation**

26. As an author, I want the Fact Extractor to identify new claimed facts from generated prose and present them as a batch approval list (description, category, confidence), so I approve canon facts in ~20 seconds.
27. As an author, I want the State Updater to propose character state changes (emotion, goal, relationships, knowledge, location) alongside facts in the same approval panel, so I update character states in one pass.
28. As an author, I want to approve, reject, or edit each proposed fact and state change before they enter the canon database, so hallucinated facts don't pollute the story's foundation.
29. As an author, I want to manually add missed canon facts after generation, so the canon database stays complete even when the Fact Extractor misses something.
30. As an author, I want auto-versioning: every Generate or Rewrite saves a timestamped copy of the scene, and I can switch between versions from a dropdown, so I never lose a good draft.

**Editing**

31. As an author, I want a Markdown editor for generated prose with cut/copy/paste and undo/redo, so I can manually polish the output.
32. As an author, I want a Preview mode that renders the Markdown with proper Chinese typography (indentation, quotation marks, paragraph spacing), so I read my prose in a novel-like format.
33. As an author, I want a "Regenerate Scene" button that re-runs the full pipeline with the same context, so I can get a fresh take when unsatisfied.
34. As an author, I want a "Next Scene" shortcut in the workspace that jumps to the next scene in the outline sequence, so navigating between chapters is fast.

**Pipeline Reliability**

35. As an author, I want each failed agent call to show an error panel with the failed prompt, the bad output, and a Retry button, so I can recover from failures without losing context.
36. As an author, I want all completed agent outputs saved to disk as the pipeline runs, so if a later step fails I don't lose 3 minutes of completed work.
37. As an author, I want to see per-scene token usage (broken down by agent) in the Agent Trace panel, with session and project totals, so I understand costs.

**Export & Completion**

38. As an author, I want to export my novel as a concatenated Markdown file with chapter headings, so I have a portable backup.
39. As an author, I want one-click EPUB export with chapter breaks and a title page, so I can read my novel on an e-reader.
40. As an author, I want the app to open directly to my last worked-on scene on launch, so I resume writing instantly.

**LLM Management**

41. As an author, I want to switch which LLM provider (Ollama or DeepSeek) each pipeline step uses, so I can route structured planning to local models and prose to a cloud API if I choose.
42. As an author, I want the app to work entirely offline with only Ollama installed, so I'm not dependent on cloud APIs.

**Creation experiences and guided planning**

43. As an author, I want to switch between Quick Creation and Deep Creation without converting or duplicating project data, so I can change the amount of visible control at any time.
44. As an author switching experiences, I want the same chapter, prose revision, editor buffer, outline selection, or nearest Story Bible area to remain active, so the transition feels continuous.
45. As a Quick author, I want a complete Story Brief → Story Proposal → Story Bootstrap → chapter publication flow, so I never have to enter Deep Creation to finish a chapter.
46. As a Quick author, I want categorized creative choices, custom entries, a freeform premise, target length, romance emphasis, and protagonist structure, so my direction is structured without becoming a form-filling exercise.
47. As an author, I want an existing project to work in Quick Creation from canonical data even when it has no Story Brief or Proposal, so guided planning is optional.
48. As a Quick author, I want to approve a compact Story Proposal before any Bible or outline data is created, so I can choose the story direction first.
49. As a Quick author, I want to preview and adjust a Story Bootstrap before an atomic commit creates the initial Bible, main characters, style, Story Arcs, and first-arc chapters, so partial generated planning never pollutes canon.
50. As an author, I want summary Story Arcs for the planning horizon and detailed Chapter Cards only for the first arc, so a long story is not filled with premature chapter summaries.
51. As an author nearing the end of an expanded Story Arc, I want an explicit option to plan the next arc, so later planning uses the story's current canon and never auto-commits.
52. As a Quick author, I want to edit Chapter Cards using only title, summary, and ending hook, so routine outline work stays compact without duplicating Deep fields.
53. As a Quick author, I want simple main-character and core-setting cards plus reviewable natural-language patches, so routine story changes do not require Deep editors.
54. As a Quick author, I want a compact chapter-plan checkpoint containing goal, key events, emotional turn, and hook, so I retain creative control without reading the full agent plan.
55. As an author, I want Short, Standard, Long, or custom Chinese-character targets at project and chapter level, so chapters may be longer without multi-call stitching.
56. As an author, I want regeneration to keep the approved plan fixed and create an alternate prose draft, so trying another rendition cannot silently change story events.
57. As an author, I want revision requests that change events, characters, or hooks to propose a chapter-plan patch first, so prose and planning do not drift apart.
58. As an author, I want Save to remain non-canonical and Approve Chapter to atomically publish the exact selected revision plus selected memory, so editing cannot alter the timeline accidentally.
59. As a Quick author, I want a compact checklist of facts and state changes before approval, so no continuity memory is accepted automatically.
60. As a Quick author, I want critical reviewer failures and explicit fix/detail/override actions, so hidden complexity never means hidden quality failures.
61. As a Quick author, I want Advanced Information to show read-only context, review, memory, and status with links to the matching Deep editor, so advanced controls are not duplicated.
62. As an author, I want one active Story Designer or chapter-generation run per project while I browse or edit unrelated work, so concurrent runs cannot race canonical state.
63. As an author, I want output based on changed inputs preserved as an unpublished **基于旧设定** draft and blocked from ordinary publication, so useful prose is not lost or accidentally treated as current.
64. As a Quick author, I want configured provider defaults, no silent fallback, and plain Retry/Settings recovery, so provider mechanics do not dominate the writing flow.
65. As an author, I want currency cost estimates only when trusted provider pricing is already available, so cost visibility never requires manual token-price setup.
66. As an author, I want Story Brief changes to show deterministic version drift and offer explicit replanning without rewriting canon or prose, so my original direction can evolve safely.
67. As an author, I want replanning to default to unwritten future chapters and separate any published-chapter changes for extra confirmation, so completed work is protected.
68. As an author, I want every Story Designer patch tied to the revision it read and rejected if that target changed, so the app never guesses how to merge concurrent creative edits.
69. As a returning Quick author, I want to resume the last chapter or the first chapter needing review, a draft, or writing, so unfinished work is not skipped.
70. As an author canceling generation, I want completed artifacts and partial prose preserved as unpublished work, so cancellation stops cost without discarding useful output.

## Implementation Decisions

**Architecture**

- Single Python process (PyQt6 + asyncio + qasync). No HTTP server, no REST API, no IPC. The orchestration engine runs in an asyncio worker thread behind the Qt event loop.
- `LLMProvider` abstract interface with `generate_text`, `generate_structured`, `generate_stream`. `OllamaProvider` and `DeepSeekProvider` implementations.
- Per-agent-step model routing: each pipeline step (planner, character, writer, reviewer, fact extractor) can target a different provider. UI exposes this as per-step dropdowns.
- Quick Creation and Deep Creation are separate top-level presentations sharing one `ProjectApplicationContext`, canonical repositories, Scene Workflow, generation pipeline, and publication seam. Experience preference belongs to Editor Layout.
- One project-scoped Scene Workflow owns the active run, checkpoints, artifacts, revision, memory review, cancellation, retry, and publication. Qt views own navigation and dirty editor buffers, not pipeline lifecycle.
- One Story Designer module generates Story Proposals, Story Bootstraps, and revision-checked planning patches through the existing structured-provider seam. It is separate from the extractive Story Bible Assistant and is not an agent swarm.
- Sub-agents produce *intent* (structured JSON), not prose. Only the Writer agent outputs free-text prose — single narrative voice.
- Pipeline runs sequentially with a plan checkpoint before prose and a publication checkpoint after review/memory extraction. No memory proposal becomes canonical automatically.
- On any agent failure: retry button + error panel + all completed agent outputs preserved on disk (resumable pipeline). No automatic fallback to different models in v1.
- One Story Designer or scene-generation run may be active per project. Experience switching never cancels, restarts, or duplicates it.

**Data Model**

- Characters split into `CharacterCore` (immutable/slow-changing: identity, personality, background, speech style, skills, weaknesses) and `CharacterState` (per-scene mutable: emotion, goal, location, relationships, knowledge, power level, status).
- Character tiers: major (runs through intent agent), supporting (provided to Writer as context), background (name only). Max 4 major-tier characters per scene regardless of total participant count.
- `CanonFact` gains `importance: int (1–5)` and `tags: list[str]` for RetrievalEngine filtering. Low-importance facts excluded from context by default.
- `SceneOutline.ending_hook` doubles as chapter-ending hook (断章). One scene = one chapter in v1.
- A Quick Chapter Card is a projection of `ChapterOutline.title`, `ChapterOutline.summary`, and its single `SceneOutline.ending_hook`; there is no Quick-specific stored chapter model.
- Story Brief, the approved Story Proposal, their revisions, and one active planning draft are stored in root `planning.yaml`. Approved bootstrap output writes the existing canonical models atomically.
- Planning drafts carry draft lifecycle; committed Bible, character, style, and outline models are canonical by definition and do not gain generic Generated/Edited/Approved statuses. Scene Revisions retain their distinct Draft/Published lifecycle.
- `Project.genre` is optional legacy/display metadata and is not synchronized with Story Brief or used as creative source data.
- Chapter length uses project defaults of approximately 2,000/3,000/5,000 Chinese characters or a custom target, with a per-chapter override. The Writer uses one provider call rather than stitched generations.
- `StyleGuide` uses structured trait fields (pacing, dialogue density, description style, tone, sentence length, POV, taboo/preferred patterns) plus `reference_passages` and `freeform_notes`. No AI style analyzer in v1.
- All data stored as files: YAML for structured data (characters, outline, style, canon facts), Markdown for prose and world setting, JSON for agent run artifacts (plans, intents, reviews), JSON lines for append-heavy logs (agent runs, token usage).

**Scene Generation Pipeline**

1. RetrievalEngine (deterministic context assembly)
2. Context Preview (collapsed badge, Enter to skip)
3. Scene Planner (structured plan output — **USER CHECKPOINT**)
4. Character Intent Agents (major characters only, max 4, parallel)
5. Writer Agent (sole prose producer)
6. Review Agent (continuity + style + pacing hooks + 打脸 beats)
7. Rewriter Agent (optional, manual trigger)
8. Fact Extractor + State Updater
9. Fact Approval Panel (batch approve facts + character state changes)
10. Draft Scene Revision saved with auto-versioning
11. Scene Publication (selected revision + selected memory committed atomically)

**RetrievalEngine**

- Deterministic filtering: category tags, recency (last N), keyword match against scene outline, importance threshold. No embedding-based retrieval.
- Context Preview panel shows a collapsed badge ("12 facts, 4 character states, 3 scene summaries"). Enter key generates immediately. Panel expandable for audit.

**Reviewer**

- Combined continuity + style + pacing reviewer in v1 (not split).
- Pacing checks: chapter-ending hook present, power progression cadence (warn if 8+ chapters without power-up), action-to-downtime ratio.
- Face-slapping (打脸) beat tracking: verifies setup → confrontation → payoff → reaction cycle completeness per beat.

**Character State Updates**

- A lightweight State Updater agent (or Fact Extractor in dual role) proposes changes to participating major characters' `CharacterState` after each scene. Proposals appear in the Fact Approval panel alongside canon facts — user approves, rejects, or edits.

**UI**

- Chinese interface throughout. English code (variable names, comments).
- Quick navigation: 故事 / 大纲 / 写章节. Deep navigation: 总览 / 设定集 / 大纲 / 写作台.
- Experience switch sits near the project title. Same-editor switches retain the unsaved buffer; leaving a different dirty editor requires Save/Discard/Cancel.
- Deep Creation keeps Dashboard, Novel Bible, Outline, and Writing Workspace behavior. Quick Creation uses separate task-oriented top-level views and reuses identical editors/widgets where appropriate.
- Writing Workspace: left (scene context + Context Preview badge), center (Markdown editor + Preview toggle), right (Agent Trace with token breakdown + retry buttons).
- Quick Writing shows the compact plan, prose editor, version marker, review/memory summaries, and a read-only Advanced Information drawer with links into Deep controls.
- App resumes the project's last experience and active chapter. A project with no stored preference defaults to Deep.
- Auto-versioning: each Generate/Rewrite saves `scene-NNN.v{N}.md` with timestamp. Version dropdown in editor.
- "Next Scene" shortcut in workspace toolbar.

**Export**

- Markdown concatenation of all approved scenes in chapter order.
- Basic EPUB generation via `ebooklib` (chapter breaks, title page, minimal CSS).
- `.txt` export for Chinese web novel platforms (起点/番茄) as near-future feature.

**Style Definition**

- Trait pickers (dropdowns/sliders) for pacing, tone, dialogue density, etc. Freeform notes textarea. Optional reference passage paste area. No LLM-powered style analysis.

**Story Templates and Generation Guides**

- The existing Xianxia content is an explicit Story Template that previews canonical content before application. Quick never applies it automatically.
- A Generation Guide supplies prompt-only genre requirements and requires original names/rules. It never becomes canonical content.
- Story Packs are deferred.

**Outline Authorship**

- Authors may write outlines manually in Deep Creation or approve Story Designer output in Quick Creation.
- Story Bootstrap creates summary Story Arcs and expands only the first arc. Later arcs are planned through explicit reviewable patches.
- Quick card edits expose title, summary, and ending hook. Known contradictions with hidden scene fields require a separate advanced patch before generation.

**Onboarding**

- The first screen offers Quick ideation as the primary route and blank Deep project as the secondary route.
- Quick setup asks only for optional working title and location. It creates the Project Folder before AI work and preserves it if onboarding is canceled.
- Story Proposal approval changes only the proposal baseline and an accepted title. Story Bootstrap approval is a separate atomic canonical commit.
- Existing projects do not require guided-planning artifacts to use Quick Creation.

**Storage**

- File-only: no SQLite, no database, no cache layer. Guided planning adds root `planning.yaml`; canonical project, Bible, character, outline, scene, canon, event, and artifact files retain their existing roles.
- Git-friendly, human-readable, copy-to-backup.

## Testing Decisions

**What makes a good test:** Test external behavior (inputs → outputs) not implementation details. Mock the LLM provider seam — agents should be testable without a running LLM. Use temp directories for storage tests. No UI-level automated tests in v1.

**Seams for testing (highest to lowest):**

1. **LLM Provider seam** — `LLMProvider` abstract interface. Test with `MockProvider` returning canned text/structured/streaming responses. Every agent test depends on this.
2. **Storage seam** — File I/O layer. Test CRUD operations against temp directories with known YAML/Markdown/JSON fixtures. Verify round-trip: write → read → same data.
3. **RetrievalEngine seam** — Context assembly. Given project state + scene ID, verify deterministic output: same inputs → same context dict. No LLM involved.
4. **Scene Workflow seam** — Agent sequencing, checkpoint gating, single-run ownership, cancel/retry, stale-input handling, draft creation, and publication. Test with mock agents/providers.
5. **Story Designer seam** — Proposal/bootstrap/patch generation, base-revision rejection, preview persistence, and all-or-nothing canonical application.
6. **Individual agent seams** — Planner, Character, Writer, Reviewer, FactExtractor. Each takes context dict → returns Pydantic model (or str for Writer). Test prompt construction and output parsing against `MockProvider`. Writer agent tested for streaming output assembly.
7. **Data model seam** — Pydantic models. Test schema validation: valid data parses, invalid data raises appropriate errors. Test Core/State assembly into full Character record.
8. **Presentation seam** — Verify Quick/Deep context mapping, shared active run, and dirty-editor prompts with focused widget/application tests. Full visual UI testing remains manual.

**Test priorities by risk:**

- Scene Workflow, Story Designer atomic application, and RetrievalEngine: highest risk (central coordination, canonical writes, context correctness).
- Data models: high risk (schema drift breaks all agent outputs).
- Storage: medium risk (straightforward I/O, well-understood patterns).
- Individual agents: medium risk (prompt construction is the main variable; mock provider makes these cheap).
- UI: deferred.

## Out of Scope

- Batch scene generation / full-novel autonomous generation
- Multi-scene chapters and migration from multi-scene project files
- Director agent (High-Quality mode)
- Split Reviewer (Continuity vs Style as separate agents)
- AI style analysis from reference passages (Style Analyzer agent)
- Conflict Resolver agent for character intent reconciliation
- Multiple concurrent projects open (tabbed projects)
- Concurrent planning and scene-generation runs within one project
- Vector-based semantic search (RAG) for context retrieval
- Automatic LLM fallback on failure
- Continuous AI drift monitoring
- Automatic downstream prose rewriting
- Bootstrap merging into non-empty projects
- Multi-call stitching for long chapters
- Story Packs
- Real-time collaborative editing
- Cloud sync
- EPUB/DOCX export beyond basic EPUB (Markdown concatenation + ebooklib)
- `.txt` export for Chinese platforms (near-future, not v1)
- Targeted paragraph-level rewrite (first post-MVP feature, not v1)
- WYSIWYG rich text editor
- Plugin system for custom agents

## Further Notes

**The current implementation reference for the two-experience expansion is `docs/superpowers/specs/2026-07-26-two-experience-design.md`.** The June 4 spec remains historical and continues to describe the existing pipeline, prompts, data model, and storage only where the July spec and this PRD do not override it.

**Implementation proceeds through the tracer slices in `BACKLOG.md`.** Quick Creation stays hidden from normal users until Story Brief → Proposal → Bootstrap → generation → review/memory approval → publication works end to end.

**Hardware target:** RTX 5090 32GB VRAM, Qwen 3 35B via Ollama. Pipeline target: 3–5 minutes per standard-mode scene generation end-to-end on local hardware.

**Design principles (from spec, reaffirmed):**
1. Sub-agents produce intent, not prose. Writer owns all narrative voice.
2. Knowledge boundaries are non-negotiable.
3. User is editor-in-chief — generated text is a draft.
4. Start structured, stay structured — typed JSON schemas for all non-prose agents.
5. Local-first, cloud-optional — DeepSeek API is a quality upgrade, not a requirement.
6. Memory is explicit, not vector-based (v1).
7. One scene at a time.
8. Context visibility over opacity — users see what the model sees.
9. Quick hides complexity; it never discards structure.
10. Experience switching changes presentation, not the project or engine.
