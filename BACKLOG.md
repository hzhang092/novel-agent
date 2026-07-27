# BACKLOG

> Updated 2026-07-26 from [PRD.md](PRD.md) and the [two-experience design](docs/superpowers/specs/2026-07-26-two-experience-design.md).
> The original 12-slice implementation plan is historical; its product foundation remains documented in the [June design](docs/superpowers/specs/2026-06-04-novel-app-design.md).

Eight tracer-bullet slices deliver one end-to-end path at a time. Quick Creation remains behind a development flag until slice 8.

---

## 1. Guided-planning foundation and Story Proposal

**Type:** AFK

**Blocked by:** None

### What to build

Add Story Brief, Story Proposal, revision metadata, and one active planning draft to root `planning.yaml`. Add the Story Designer proposal operation through the existing structured-provider route. Keep it separate from the extractive Story Bible Assistant.

This slice stops at proposal approval: it may persist the approved Proposal and accepted project title, but must not write Story Bible, character, style, outline, or canon data.

### Acceptance criteria

- [ ] Story Brief round-trips categorized normalized strings, premise, target length, romance emphasis, protagonist structure, and chapter-length default
- [ ] `Project.genre` is optional legacy/display metadata and is not synchronized with Story Brief
- [ ] Proposal output is limited to title, logline, 2–4 main characters, core conflict, 3–5 story promises, and ending direction
- [ ] Proposal drafts are resumable; only one active planning draft is retained
- [ ] Proposal revisions and natural-language adjustments preserve the prior approved Proposal until approval
- [ ] Proposal approval updates only planning data and an explicitly accepted `Project.title`
- [ ] A patch whose base revision changed is rejected
- [ ] Story Designer uses one dedicated provider route and never silently falls back
- [ ] Storage and Story Designer behavior are covered through temporary-project and mock-provider tests

---

## 2. Shared experience shell and Scene Workflow

**Type:** AFK

**Blocked by:** None

### What to build

Add separate Quick and Deep top-level presentations over the existing `ProjectApplicationContext`. Store the project-local experience preference in Editor Layout. Extract the existing generation/checkpoint/revision/publication lifecycle from window ownership into one project-scoped Scene Workflow used by both presentations.

Do not add a generic state framework or a second pipeline.

### Acceptance criteria

- [ ] Quick navigation is 故事 / 大纲 / 写章节; Deep navigation is 总览 / 设定集 / 大纲 / 写作台
- [ ] Existing projects with no preference open in Deep; Quick-created and blank-created projects use their defined defaults
- [ ] Writing ↔ Writing preserves chapter, scene, selected revision, and shared prose buffer
- [ ] Outline ↔ Outline preserves Story Arc and chapter selection
- [ ] Story ↔ Story Bible lands in the nearest matching area; returning to Deep restores its exact remembered page
- [ ] Switching away from a different dirty editor requires Save/Discard/Cancel; same-editor switching retains the buffer
- [ ] Switching never auto-saves, converts data, cancels a run, or creates a second run
- [ ] Scene Workflow owns the active run, checkpoint, artifacts, revision, memory review, cancel/retry, and publication state
- [ ] One project cannot start a second Story Designer or generation run while one is active
- [ ] Focused application/widget tests cover transition mapping, dirty buffers, and shared run identity

---

## 3. Quick project creation and Story Proposal experience

**Type:** AFK

**Blocked by:** 1, 2

### What to build

Make the new-project screen offer visually primary Quick ideation and secondary blank Deep creation. Quick asks only for optional working title and project location, creates the unique Project Folder immediately, then presents the Story Brief and Story Proposal review flow.

### Acceptance criteria

- [ ] Quick setup has no genre or provider field and defaults to the last project parent directory
- [ ] Project Folder is created before AI work and remains resumable after cancellation
- [ ] Accepted generated titles update project metadata without renaming the folder
- [ ] Story Brief uses categorized curated chips plus short custom entries
- [ ] Romance emphasis is the sole none/secondary/primary source and disables incompatible relationship chips
- [ ] Target length supports short, approximately 30, approximately 100, ongoing, and custom
- [ ] Ongoing work records a revisable provisional destination
- [ ] Proposal actions support adopt, natural-language adjustment, and another direction
- [ ] No-provider state gives plain Settings guidance; normal Quick flow hides provider/model routing
- [ ] Currency estimates appear only from trusted provider metadata and never require manual pricing

---

## 4. Atomic Story Bootstrap and first Story Arc

**Type:** AFK

**Blocked by:** 3

### What to build

Generate a compact, editable Story Bootstrap preview from the approved Proposal. It contains the minimal first-arc Bible, 2–4 main characters and initial states, basic Writing Style, summary Story Arcs, and detailed first-arc Chapter Cards with exactly one Scene Outline each.

Apply approval atomically through existing file rollback primitives.

### Acceptance criteria

- [ ] Bootstrap contains no Canon Facts and no lore/chapter plans beyond its defined scope
- [ ] Three to six arcs and eight to fifteen chapters are guidance, not validation limits
- [ ] For ongoing work, the planning horizon is finite rather than the entire series
- [ ] Compact cards are editable; advanced generated fields are read-only before approval
- [ ] Natural-language adjustment returns a structured patch with changes and consequences
- [ ] Accepted patches preserve unchanged values and manual edits
- [ ] A stale-base patch is rejected instead of merged heuristically
- [ ] Approval atomically commits metadata, Bible, characters/states, style, arcs, chapters, and single scenes
- [ ] Failure restores the prior canonical files and keeps the bootstrap draft
- [ ] Full bootstrap is unavailable for non-empty projects
- [ ] The existing Xianxia Story Template is never applied automatically; Generation Guides remain prompt-only

---

## 5. Quick Story, Outline, and safe replanning

**Type:** AFK

**Blocked by:** 4

### What to build

Project existing canonical story data into Quick Story and card-based Quick Outline. Support routine main-character/core-setting patches, three-field Chapter Card edits, deterministic Story Brief drift, explicit future-only replanning, and on-demand later-arc planning.

### Acceptance criteria

- [ ] Story Arc maps one-to-one to `VolumeOutline`
- [ ] Chapter Cards derive title, summary, and ending hook from existing canonical fields; no Quick chapter model/file exists
- [ ] Card status derives as 待写 / 草稿 / 已批准 / 有新草稿 / 需要复核
- [ ] Quick manual card edits never silently change Deep-only scene fields
- [ ] A known hidden-field contradiction produces a separate advanced patch and blocks generation until resolved if rejected
- [ ] Advanced character, relationship, custom-field, and power-system editing switches to the same element in Deep
- [ ] Brief revision drift identifies concrete changed fields and never rewrites canon, outline, or prose
- [ ] Replanning defaults to future chapters without published prose
- [ ] Proposed published-chapter changes are separated for extra confirmation and show downstream review impact
- [ ] Story-affecting changes mark affected prose-bearing chapters 需要复核; display-only title fixes do not
- [ ] When two approved chapters remain, an explicit next-arc action creates a reviewable draft and never auto-commits
- [ ] Later-arc planning treats current canon as truth and reports conflicts with Brief/Proposal direction

---

## 6. Quick chapter runner end to end

**Type:** AFK

**Blocked by:** 2, 4

### What to build

Deliver the complete Quick chapter workflow over Scene Workflow: compact plan approval, one-call prose generation, simple revision selection/editing, review summary, memory checklist, atomic publication, and navigation to the next chapter.

### Acceptance criteria

- [ ] Quick plan shows goal, key events, emotional turn, and hook with Start/Adjust actions
- [ ] Deep displays the same run and full structured plan/trace
- [ ] Project defaults support approximately 2,000/3,000/5,000 Chinese characters or custom, with chapter override
- [ ] Length uses Chinese-character count and warns when the configured model cannot support the target
- [ ] Writer uses one provider call; no multi-call stitching exists
- [ ] Regenerate keeps the approved plan and creates an alternate Draft Scene Revision
- [ ] Event/character/hook-changing prose instructions require an explicit plan patch first
- [ ] Save creates only a Draft Scene Revision
- [ ] Quick shows critical reviewer failures with AI fix, details, and explicit override
- [ ] Quick memory checklist never auto-approves facts or State Change Proposals
- [ ] Approve publishes the exact selected revision and selected memory atomically through the existing publication seam
- [ ] Regeneration never replaces published prose
- [ ] 批准并进入下一章 publishes and navigates but never starts generation
- [ ] Resume chooses the last active chapter, otherwise the first needing review, then draft, then unwritten
- [ ] Advanced Information is read-only and links to the matching Deep controls

---

## 7. Existing projects, stale runs, and cancellation

**Type:** AFK

**Blocked by:** 5, 6

### What to build

Harden cross-experience behavior for existing/blank projects and generation that overlaps manual edits. Preserve useful work on stale inputs and cancellation without adding a merge engine or automatic resume.

### Acceptance criteria

- [ ] Existing projects work in Quick directly from canonical data without required planning artifacts
- [ ] Optional Brief generation for an existing project creates an editable draft only
- [ ] Switching an empty blank project to Quick starts Brief in the same folder
- [ ] Deep may inspect an unapproved bootstrap and warns before its first canonical save discards that draft
- [ ] Discarding bootstrap preserves Story Brief and approved Proposal
- [ ] Hidden Deep data remains active in retrieval, generation, review, continuity, storage, and export
- [ ] A run records the source chapter and relevant revisions it read
- [ ] Output whose relevant inputs changed is kept as a **基于旧设定** draft and blocked from ordinary one-click publication
- [ ] The author may regenerate or explicitly continue after reviewing stale inputs
- [ ] Cancel stops the provider task and preserves completed artifacts and received partial prose as unpublished work
- [ ] Retry uses the normal plan/review/publication path; no special rollback or automatic resume is introduced
- [ ] No multi-scene compatibility or migration path exists

---

## 8. End-to-end release gate

**Type:** MIXED

**Blocked by:** 7

### What to build

Verify and expose Quick Creation only after the complete path is safe. Update in-app help and package the feature with the existing application.

### Acceptance criteria

- [ ] A clean Quick project completes Brief → Proposal approval → Bootstrap approval → plan approval → prose → review/memory approval → publication
- [ ] The same project can switch to Deep and back at every major checkpoint without data conversion or run duplication
- [ ] Existing project and blank-project entry paths pass manual smoke tests
- [ ] Atomic bootstrap and publication failure tests prove canonical data is not partially applied
- [ ] Stale-output, cancel, no-provider, and provider-failure recovery pass end-to-end tests
- [ ] Quick remains hidden until all preceding acceptance criteria pass
- [ ] Chinese labels match the design spec; Simple/Professional wording does not appear
- [ ] Help text explains Story Template versus Generation Guide and Save versus Approve
- [ ] Windows packaged-app smoke test covers creation, switching, generation, publication, reopen, and export
