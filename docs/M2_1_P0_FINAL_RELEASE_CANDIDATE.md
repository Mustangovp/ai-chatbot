# M2.1 + P0 final local release candidate

Base: `af8cf0b57204321e4420e791ad583f590491db6c`.
Prepared: 2026-10-25. Local review only; no release operation is authorized here.

## Exact scope

1. `.gitignore`
2. `app.py`
3. `coaching/progress_analysis.py`
4. `static/progress_analysis.js`
5. `static/progress_analysis.css`
6. `templates/apex.html`
7. `training_engine/renderer.py`
8. `tests/test_progress_analysis.py`
9. `tests/test_chat_enforcement.py`
10. `tests/test_workout_completion_contract.py`
11. `tests/playwright/progress-analysis.spec.js`
12. `tests/playwright/workout-delivery-integrity.spec.js`
13. `tests/playwright/canonical-workout-delivery.spec.js`
14. `tests/playwright/free-activation.spec.js`
15. `tests/playwright/workout-compression.spec.js`
16. `tests/playwright/workout.spec.js`
17. `docs/PROGRESS_CHAT_M2_1.md`
18. `docs/WORKOUT_DELIVERY_INTEGRITY_P0.md`
19. `docs/M2_1_RELEASE_CANDIDATE.md`
20. `docs/M2_1_P0_FINAL_RELEASE_CANDIDATE.md`

The candidate uses the exact base inline CSS, excluding the unrelated Premium UI
experiment. Core source, canvas placement, engines, physics and pointer behavior
remain unchanged. No preview scripts, synthetic-account runtime, temporary DB,
test output or secrets belong to the release. The original working tree and the
previous frozen M2.1-only patch are preserved, not reset or overwritten.

The older M2.1-only release record remains historical. Its null-metadata blocker
is addressed by this separately tested P0-inclusive candidate, not waived.

## Browser baseline reconciliation: four to two

- Malformed/null workout metadata: a real baseline fail-open defect. P0 now rejects
  it in the actual current SSE exchange before cards, Start, history, Voice reply
  or activation. New adversarial tests replace the invalid positive legacy fixture.
- CL-3 interrupted-history assertion: the old fixture could seed history before
  authenticated account hydration cleared it. The fixture now awaits the existing
  account-owned startup state. Outcome assertions remain unchanged; no sleeps.
- CL-8: still counts all fetches, including the existing AthleteModel post-turn
  refresh, as chat attempts. Expected two, observed three.
- CL-9: still expects obsolete Bulgarian quota wording. The actual terminal state
  remains failed, not a bypass.

The first two are resolved, not silently reclassified. CL-8 and CL-9 are the two
remaining browser baselines. Eight unrelated exact-base Python failures concern
legacy rep-only duration fixtures (two), old Goblet Squat selection assertions
(three), older nutrition wording (two), and the `reason`/`reason_code` substring
assertion (one). No safety or ownership expectation is relaxed.

## Release invariants

- Account-owned immutable completed evidence is the only progress-analysis input.
  Chart/table share one bounded dataset, exact recorded UTC timestamps and units.
- Null/missing/malformed/mismatched workout contracts fail closed. Only matching
  canonical first-session metadata can create an executable protocol.
- Interrupted SSE, cancellation, retry races and account rotation cannot finalize
  pending training/analysis, save unverified assistant workouts or confirm training
  activation. Verified refusal text may remain in server conversation history.
- Existing training safety validation remains authoritative. The renderer's added
  check compares transport metadata with its existing immutable completion source;
  it does not create another exercise or safety policy.
- No schema, migration, dependency, model policy, payment, quota or feature-flag
  change. No extra model call to render progress or on page load.
- All local validation uses temporary SQLite, synthetic data and mocked/denied
  providers. No production database, credentials or paid API operations.

## Final validation

Status: **READY_FOR_RELEASE**, subject to separate owner release authorization.
No commit, push, production access or deployment was performed.

- Focused Python: 645 passed, eight unchanged baseline failures. The exact eight
  were reproduced again on pristine base with identical mock keys/flags.
- Browser: 168 combined delivery/M2.1/workout/Next Move/account checks passed;
  completion suite 12/12 passed on its clean fixture; Voice/Core 33/33 passed;
  pilot/playback/streaming 32/32 passed; ChatLifecycle/Nutrition 26 passed with
  the same two CL-8/CL-9 baseline assertions. Both were reproduced again on base.
- Additional BG/EN mobile null-contract, valid-workout and interrupted-SSE cases:
  12/12 passed at 390px and 360px. M2.1 BG/EN 390px/1440px screenshots reviewed;
  table scroll is contained and the page has no horizontal overflow.
- Initial combined browser run: 179/180 passed. Its completion refresh assertion
  inherited two earlier `abandoned` history records from other execution tests
  using the same synthetic server account. No new abandonment request occurred.
  The unmodified entire completion suite passed 12/12 with a fresh temporary DB;
  the same refresh assertion passed on clean base. This is fixture contamination,
  not a newly waived product baseline. No source/expectation change was needed.
- Core/inline CSS match exact base after checkout EOL normalization. `db.py`,
  progress authority, dependencies, model policy and Voice authorities are unchanged.
  No database migration or PostgreSQL runtime test was performed in this local task;
  database compatibility relies on the unchanged schema and existing bounded reads.
- Python compilation, rendered inline JS/static JS syntax, candidate-only whitespace
  check, exact 20-file allowlist and added-secret-pattern scan passed. No new secrets,
  payment changes, model calls or billable audio tests were introduced.
- Local `/`, `/en`, `/app` and both progress assets returned 200. `/app` retains
  `Cache-Control: no-store`. These are local checks, not production health claims.

Clean review tree: `C:/tmp/apex-m21-p0-final-review-af8`.
Clean source archive: `C:/tmp/apex-m21-p0-final-review.zip`.
Test runtime tree (not the release archive): `C:/tmp/apex-m21-p0-final-af8`.
Review patch: `C:/tmp/apex-m21-p0-final.patch`.
SHA-256 sidecar: `C:/tmp/apex-m21-p0-final.patch.sha256`.
The patch is generated using a separate temporary index; the real index remains
empty. No candidate artifact includes preview scripts, DBs or test outputs.

Evidence logs: `C:/tmp/apex-m21-p0-final-python.log`,
`C:/tmp/apex-m21-p0-baseline-python.log`, `C:/tmp/apex-m21-p0-final-browser.log`,
`C:/tmp/apex-m21-p0-final-chat-browser.log`,
`C:/tmp/apex-m21-p0-baseline-chat-browser.log`,
`C:/tmp/apex-m21-p0-completion-clean-browser.log`,
`C:/tmp/apex-m21-p0-completion-base-browser.log`,
`C:/tmp/apex-m21-p0-final-voice-browser.log`,
`C:/tmp/apex-m21-p0-final-playback-browser.log`,
`C:/tmp/apex-m21-p0-final-mobile-browser.log`.

## Railway rollback procedure (prepared, not executed)

1. On a separately authorized release, read and record the actual production SHA
   and successful deployment ID immediately before pushing. If unchanged from
   this task, the rollback SHA is the exact base above. Never assume stale `main`
   is equivalent to that production baseline.
2. Verify the future pushed commit has only this reviewed scope. Do not change
   Railway source branch, variables, paid access or model configuration.
3. If deployment, ownership, canonical workout delivery, SSE, Nutrition, Voice,
   Next Move or health checks fail, roll back using Railway's existing known-good
   deployment for the recorded SHA. Do not rebuild a guessed branch tip.
4. Verify deployed SHA/status, PostgreSQL readiness and absence of startup errors;
   `/`, `/en`, `/app` must return 200 and `/app` must retain `Cache-Control: no-store`.
5. No schema rollback is needed. Do not delete or rewrite existing workout,
   completion, constraint, conversation or nutrition records. Factual text fallbacks
   already saved in conversation history remain readable.
6. Keep the reviewed candidate and test evidence for diagnosis. Do not automatically
   re-enable or retry a failed release.
