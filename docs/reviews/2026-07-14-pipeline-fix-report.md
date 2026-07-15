# Pipeline Fix Verification Report

Date: 2026-07-14

Scope: the eleven continuity, approval, context, editing, summary, and recovery findings reported for the scene-generation pipeline.

## Result

All eleven issues were reproduced or confirmed from the implementation, fixed, tested, reviewed on both repository-standards and specification axes, and committed separately. The final repository test run passed: **308 tests**.

## Fixes

### 1. POV character missing from character context

- **Verified:** the POV selector and participant selector were independent, while character collection read only participant IDs.
- **Before:** a POV character omitted from the participant list had no State, intent, or knowledge boundary in generation context.
- **Fix:** collect unique character IDs from the union of POV and participants.
- **After:** the POV character is always present once, even when not selected as a participant.
- **Commit:** `be3c9a8` — Enhance character context collection to include POV characters and ensure uniqueness.

### 2. Regeneration changed accepted state before approval

- **Verified:** regeneration invalidation could affect accepted prose and memory before the replacement was approved.
- **Before:** generating a candidate could hide or retire accepted state even if the author rejected the candidate.
- **Fix:** keep revisions as non-canonical drafts and move retirement/replacement into publication after approval. Keep the accepted prose visible while a draft exists.
- **After:** regeneration is read-only with respect to accepted state until publication succeeds.
- **Commits:** `f8fcad1`, `846352d`, `0038990`.

### 3. Approval was not an atomic logical transaction

- **Verified:** characters could be appended, checkpointed, published, and snapshotted one at a time under a shared transaction ID.
- **Before:** a failure partway through approval could leave a partially published batch.
- **Fix:** validate the complete batch first, stage publication, and make interrupted publication recoverable and safe to retry.
- **After:** approval either completes the approved batch or resumes the same staged transaction without duplicating or partially replacing canonical state.
- **Commits:** `a8e6edf`, `f58bbe2`, `fa9256a`.

### 4. Fifth and later major characters received no State update

- **Verified:** the four-character concurrency cap also limited the single State Updater input.
- **Before:** only the first four major participants could receive proposed State changes.
- **Fix:** retain the cap only for concurrent Character Intent calls and pass every participating major character to the State Updater.
- **After:** all participating major characters are considered for State changes.
- **Commit:** `8e66804` — fix: update state for every major character.

### 5. Long scenes lost their endings during review and memory work

- **Verified:** post-processing prompts truncated prose from the start only.
- **Before:** late revelations, final locations, injuries, power changes, and hooks could be absent from review, fact extraction, State updates, and summary generation.
- **Fix:** remove post-processing prose truncation and pass the complete scene to Reviewer, Fact Extractor, and State Updater.
- **After:** opening, middle, and ending events are all available to review, facts, State changes, and summary generation.
- **Commits:** `e50aa5f`, followed by full-coverage correction `075e7da`.

### 6. Summary and fact retrieval ignored story time

- **Verified:** retrieval could include current or future scenes when generation occurred out of order.
- **Before:** future knowledge could leak into a character's context and continuity could be ordered by file history instead of story position.
- **Fix:** resolve scene positions, sort summaries by story order, and retrieve only facts and summaries from prior story scenes.
- **After:** out-of-order generation respects the target scene's timeline and knowledge boundary.
- **Commit:** `66a8350` — fix: bound retrieval to prior story scenes.

### 7. Failed review did not block memory analysis

- **Verified:** missing, failed, or crashed review output could still be followed by fact and State analysis.
- **Before:** memory proposals could be produced after an unsuccessful review without explicit author authorization.
- **Fix:** require a passing review or a persisted explicit override before analysis begins.
- **After:** review failure gates memory work; an author can deliberately continue by overriding it.
- **Commit:** `740fbb8` — fix: gate memory analysis on review outcome.

### 8. Assembled context was discarded before writing

- **Verified:** the context builder loaded substantial world and character data that the Writer and State Updater prompts omitted.
- **Before:** the Writer lacked geography, factions, history, terminology, social structure, technology, volume summary, and detailed major-character State; the State Updater lacked current power level.
- **Fix:** include the assembled world, volume, and major-character context in the Writer prompt and current power State in State Updater input.
- **After:** both agents receive the context already gathered for their decisions.
- **Commit:** `1a58543` — fix: include assembled context in agent prompts.

### 9. Required plan and proposal editing controls were missing

- **Verified:** the plan was read-only and State proposals could not be edited change by change.
- **Before:** authors could only accept or reject the generated structures as presented.
- **Fix:** make the structured plan checkpoint editable and add selection plus per-change editors for nested State proposals.
- **After:** authors can revise the plan before writing and edit individual proposed changes before approval.
- **Commit:** `7531724` — feat: add required approval editing controls.

### 10. The normal pipeline produced no Scene Summary

- **Verified:** retrieval read scene summaries, but generation did not create or persist them.
- **Before:** recent-scene-summary context normally remained empty and continuity depended only on facts and State.
- **Fix:** require the Fact Extractor to return a narrative summary and open threads, persist the raw result with the revision, and publish the approved revision's summary with revision-aware active filtering.
- **After:** every successful memory-analysis pass produces a revision-scoped summary that becomes canonical only with its approved revision.
- **Commit:** `da9576b` — feat: generate revision-scoped scene summaries.

### 11. Completed Writer prose was not saved immediately

- **Verified:** completed prose remained only in memory while Reviewer and later agents ran.
- **Before:** a crash after Writer completion could lose the whole draft, and the app had no recovery path on restart.
- **Fix:** atomically save a Writer recovery artifact before Reviewer starts; promote it to a non-canonical versioned draft on scene load; make prose and generation-record finalization atomic and idempotent across interruption points; remove the recovery artifact only after durable finalization.
- **After:** completed prose survives downstream crashes, reappears after reopening, preserves accepted prose, and does not create duplicate recovery revisions.
- **Commit:** `30006fc` — fix: persist writer prose before review.

## Final Audit Follow-up

The repository-wide audit also found that edited-draft and explicit review-override analysis ran in detached tasks without surfacing exceptions. Commit `0652dcc` catches those task failures, keeps the draft saved, shows a visible memory-analysis failure, and restores the retry control. This follow-up was tested and reviewed separately before the final suite run.

## Verification

- Each fix received focused regression tests and a post-fix Standards review plus Spec review before commit.
- Review findings discovered during implementation were fixed and re-reviewed until both axes were clean.
- `git diff --check` was clean for each final fix; the Windows checkout reported only expected LF-to-CRLF notices.
- Final test command: `conda activate fourteen; python -m pytest -q`
- Final result: **308 passed in 6.70s**.

User-owned untracked files `environment.yml` and `notes.md` were left unchanged.
