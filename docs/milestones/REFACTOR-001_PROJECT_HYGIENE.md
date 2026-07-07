# REFACTOR-001 — Project Hygiene & Architecture Cleanup

**Type:** engineering / maintainability only. **No** new functionality; **no** Brain,
Human State, Coaching, Recommendation, DB-schema, API, or deployment behavior change.
Runtime behavior preserved 100% (proven: full suite green, corpus acceptance numbers
byte-identical, corpus fixtures byte-identical, app boots with all routes registered).

---

## PART 1 — Structure audit (findings)

| Area | Finding | Action |
|---|---|---|
| `app.py` | 2412 lines — orchestration bottleneck | Extracted internal admin/debug routes (PART 3) |
| `docs/` | 26 tracked docs flat in one folder | Reorganized into 6 categories (PART 2) |
| Dead imports | `brain.replay`(app), `secrets`(app), `sqlalchemy.delete`(db), `CONF_INFERRED`(extractor), `math`(script) | Removed (PART 5) |
| Superseded doc | `APEX_HUMAN_MODEL_ARCHITECTURE.md` superseded by the HSE doc | **Kept** — design history, not a byte duplicate |
| Coupling | Layering already clean (no cycles, no Brain bypass) | Codified as a permanent test (PART 4/6) |
| Untracked docs | 13 pre-existing untracked docs + 1 PDF at `docs/` root | **Left as-is** — out of this milestone's scope |

No dead code modules, no obsolete source files, no true duplicate docs were found.

## PART 2 — Documentation reorg

`docs/` → `architecture/` (13), `research/` (4), `milestones/` (3+this), `adr/` (1),
`vision/` (3), `product/` (3). All via `git mv` (rename-tracked). No content rewritten.
The one doc consumed by code (`APEX_VALIDATION_CORPUS.md`, read by the corpus-fixture
builder) moved to `research/`; the builder's path + the 2 docstring pointers were updated
and the builder re-run — **fixtures byte-identical**, proving the move is behavior-neutral.

## PART 3 — `app.py` extraction

Extracted the 7 internal admin/Brain-debug route handlers + `_brain_debug_on()` into
`admin_routes.py` (a Flask **Blueprint**). Chosen because they are self-contained,
internal-only (every one 404s unless its `ADMIN_TOKEN`/`BRAIN_DEBUG` gate is set → tiny
blast radius), and already covered by `test_debug_endpoint`. **URL paths and gating are
identical**; endpoints are referenced only by hardcoded paths (no `url_for`), so the
blueprint's `admin.*` endpoint renaming breaks nothing. `app.py`: 2412 → 2317 lines.

**Deliberately NOT extracted:** the `/chat` streaming pipeline (SSE closures + HSE /
enforcement / adaptation hooks). It is the real behavior-risk surface; a safe extraction
warrants its own milestone with a request/response diff harness. See Future risks.

## PART 4 / 6 — Dependency & architecture validation

Verified by scanning the real import graph and locked in as `tests/test_architecture_invariants.py`:

- Brain imports **no** downstream layer (human_state / coaching / recommend). ✓
- Human State imports **no** Brain. ✓
- Adaptive Coach imports **no** Brain organ (read-only, downstream). ✓
- Recommendation imports **no** Brain. ✓
- `brain.cascade` (the one entrypoint) has exactly **one** non-test consumer: `app.py`. ✓
- **No import cycles** among the four layers. ✓

Feature flags remain the only activation mechanism (`BRAIN_*`, `HSE_INGEST`, `HSE_AUDIT`,
`HSE_CONSUMER`, `HSE_TRAJECTORY`) — unchanged and all default OFF.

## PART 5 — Code hygiene

Removed 5 unused imports (confirmed dead by `pyflakes` + grep). No logic touched.
Post-cleanup `pyflakes` on all source: **zero** unused imports.

## PART 7 — Testing

`pytest tests/` → **195 passed** (189 prior + 6 new invariant tests). Brain Acceptance
corpus coverage identical to baseline (safe=True; 20/140 verdict; 63/63 refusal; 17/36
red-flag). App boots; all 35 routes register; extracted routes verified live (200 with
key, 404 without, 404 on unknown decision).

---

## Final report

**Files changed (10):** `app.py`, `db.py`, `human_state/extractor.py`,
`scripts/gen_pushup_surrogate.py`, `brain/corpus/build_fixtures.py`,
`brain/corpus/__init__.py`, `tests/test_corpus_acceptance.py`, `.gitignore` (+2 new below).

**Files added (2):** `admin_routes.py`, `tests/test_architecture_invariants.py`.

**Files removed:** none (no true duplicates / obsolete source found).

**Files moved (26):** all tracked `docs/*.md` into the 6-folder structure.

**Technical debt reduced:** app.py −95 lines and no longer owns internal admin/debug
routing; docs discoverable by category; architecture invariants now machine-enforced
(can't silently regress); 5 dead imports gone; corpus doc lives with its consumer.

**Future risks / follow-ups (not done here):**
1. `app.py` is still ~2.3k lines. The `/chat` streaming pipeline is the next extraction
   target but needs its own milestone with a behavior-diff harness before touching it.
2. Repo `autocrlf` inflates diffs (line-ending normalization) — cosmetic, not behavioral;
   a `.gitattributes` normalization pass would quiet it.
3. The 13 untracked pre-existing docs at `docs/` root remain unorganized/uncommitted —
   decide whether to track or discard them in a separate pass.
