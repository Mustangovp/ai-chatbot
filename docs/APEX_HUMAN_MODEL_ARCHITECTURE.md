# APEX — Human Model Architecture (redesign of M6)

**Status:** ARCHITECTURE ONLY. No implementation, no wiring, no deployment, no Brain
changes. This document freezes the target design and the path to it.

---

## 1. Why redesign

M6 shipped `recommend/` owning `preferences.py` and `diversity.py`. But preferences,
diversity history, habits, schedule, equipment, budget, compliance… are **user state**,
not recommendation logic. A recommendation engine that owns user state has two masters
and no single source of truth: every other feature (emails, dashboard, coaching memory,
future agents) would have to reach into `recommend/` for facts about the person.

**Principle:** exactly one component owns "who this person is." Everything else *reads*
it. Recommendation becomes a pure transformation of `(HumanModel, BrainDecision)`.

---

## 2. The two invariants

1. **`human_model/` is the single source of truth** for all durable user state.
2. **The Recommendation Architect is READ-ONLY** — it consumes a Human Model view; it
   never owns, writes, or mutates user state.

Plus the standing invariant: **the Brain is frozen** — the Human Model must not change
how S1–S5 / cascade / enforcement read their inputs.

---

## 3. Domains owned by the Human Model

| Domain | Nature | Source today | Target ownership |
|---|---|---|---|
| Identity | slow | profile fields | `human_profile` |
| Preferences | slow | `user_preferences` (M6) | re-homed under HM |
| Habits | slow/observed | — (new) | `human_profile` + observations |
| Lifestyle | slow | — (new) | `human_profile` |
| Schedule | slow | — (new) | `human_profile` |
| Equipment | slow | profile.equipment | `human_profile` |
| Budget | slow | prefs.budget (M6) | `human_profile` |
| Environment | slow | — (new) | `human_profile` |
| Medical history (structured) | **read-only projection** | Brain: S1 constraints + athlete model | **NOT owned** — projected read-only |
| Motivation | slow/observed | — (new) | `human_profile` + observations |
| Compliance | time-series | — (new) | `compliance_events` |
| Food history | time-series | `nutrition_history` | referenced by HM |
| Workout history | time-series | `workout_history` | referenced by HM |
| Recommendation history | time-series | `recommendation_history` (M6) | re-homed under HM |
| Behavioral observations | time-series | `coach_memory` (partly) | `behavioral_observations` |

**Medical is special:** it stays owned by the Brain (frozen clinical logic — S1
constraints, athlete-model somatic state). The Human Model exposes a **read-only
projection** of it; it never duplicates or edits clinical state.

---

## 4. Layered architecture

The Human Model is a facade with two APIs — a **read view** (immutable snapshot) and a
**write/ingest** path — over a persistence layer. Nothing writes user state except the
ingest path; nothing reads user state except through the view.

```
        ┌──────────────────────────── INGEST (writers) ────────────────────────────┐
        │  conversation signals · workout/meal completions · compliance events ·    │
        │  explicit preference statements · behavioral observations                 │
        └───────────────────────────────────┬───────────────────────────────────────┘
                                             │ human_model.observe(subject, signal)
                                             ▼
        ┌───────────────────────────── human_model/ (SoT) ──────────────────────────┐
        │  schema/        domain types (Preferences, Habits, Schedule, …)           │
        │  store/         persistence (owns: human_profile, recommendation_history, │
        │                 user_preferences, compliance_events, behavioral_obs;      │
        │                 references: workout_history, nutrition_history)            │
        │  medical/       READ-ONLY projection of the Brain's structured medical     │
        │                 state (adapter over athlete_store / Brain Decision)        │
        │  view()         → HumanModelView  (immutable read snapshot)                │
        │  observe()      → append/update (the ONLY write path)                      │
        └───────────────────────────────────┬───────────────────────────────────────┘
                                             │ view(subject) → HumanModelView  (READ-ONLY)
                                             ▼
        Brain Decision ──────────►  Recommendation Architect (READ-ONLY consumer)
        (frozen; separate input)         design(view, decision) → Blueprint
                                             ▼
                                         LLM Renderer → reply
```

---

## 5. Dependency diagram (who depends on whom)

Arrows = "depends on / reads". **No cycles. All arrows point INTO `human_model`.**

```
        app.py (future orchestrator; not wired now)
           │        │            │              │
           │        │            │              └────────────► renderer  (blueprint→text)
           │        │            └───────────────► recommend.architect (READ-ONLY)
           │        │                                   │            │
           │        │                                   │ reads      │ reads
           │        │                                   ▼            ▼
           │        └───────────────► brain.cascade ─► BrainDecision │
           │                             (FROZEN)                     │
           │                                                          ▼
           └──────────────────────────────────────────────► human_model.view()
                                                                     │
                                     ┌───────────────────────────────┤
                                     ▼                               ▼
                               human_model.store            human_model.medical
                                     │                               │  (read-only)
                                     ▼                               ▼
                                    db.py  ◄──────────────  brain.athlete_store (somatic SoT, frozen)

   Ingest writers ──► human_model.observe()  (ONLY writer of user state)

   NON-dependencies (must remain true):
     • brain/*            ─╳─►  human_model      (Brain never reads the Human Model)
     • recommend/*        ─╳─►  db / user tables (Architect touches no state directly)
     • human_model        ─╳─►  recommend        (SoT knows nothing of consumers)
```

Key edges:
- `recommend.architect` **depends on** `human_model.view()` (read) + `BrainDecision` (read). It no longer imports `preferences`/`diversity` or touches `db`.
- `human_model` **depends on** `db` (persist) and, read-only, on `brain.athlete_store` (to *project* somatic/medical state). It does **not** depend on `recommend`.
- `brain/*` depends on **nothing new** — it never imports `human_model`. (No Brain change.)
- No component other than `human_model.observe()` writes user state → single writer.

---

## 6. Contracts

**Read view (immutable):**
```
human_model.view(subject) -> HumanModelView
    .identity, .preferences, .habits, .lifestyle, .schedule, .equipment,
    .budget, .environment, .motivation, .compliance,
    .food_history(n), .workout_history(n), .recommendation_history(kind, n),
    .behavioral_observations(n),
    .medical   # READ-ONLY projection: constraints, flags, contraindications
```
The view is a snapshot; consumers cannot mutate it.

**Write path (single writer):**
```
human_model.observe(subject, signal)   # preference stmt, completion, compliance, observation
human_model.update(subject, domain, patch)
```

**Architect (read-only):**
```
recommend.architect.design(view: HumanModelView, decision: BrainDecision) -> Blueprint | None
```
No `subject`, no `preferences` arg, no DB, no writes. Diversity is *read* from
`view.recommendation_history(...)`; recording the chosen anchor happens through
`human_model.observe(...)` at the orchestration layer, **not** inside the Architect.

---

## 7. Migration plan (additive, reversible, staged — no wiring/deploy/Brain change until approved)

M6 (`recommend/`) is committed but **not deployed or wired**, so re-homing state has
**no production data to migrate** — this is a pure code reshaping.

| Phase | Action | Risk | Reversible |
|---|---|---|---|
| **P0 (this doc)** | Freeze the design. No code. | none | n/a |
| **P1** | Create `human_model/` skeleton: `schema/`, `store/`, `view()`, `observe()`, `medical/` (read-only adapter over `athlete_store`). Additive, unused. | none | delete package |
| **P2** | Re-home ownership: move `user_preferences` + `recommendation_history` under `human_model.store`; `recommend/preferences.py` + `recommend/diversity.py` become thin adapters or are removed. Tables unchanged (no data move). | low | keep adapters |
| **P3** | Refactor `architect.design(view, decision)` — read-only, consumes `HumanModelView`. Update `recommend.plan()` to build the view + record via `observe()`. Update tests. | low | revert commit |
| **P4** | Unify existing scattered state behind the view: `workout_history`, `nutrition_history`, `coach_memory` surfaced read-only through `HumanModelView` (adapters; no data move). | low | adapters are additive |
| **P5** | Add missing domains: new additive tables `human_profile` (JSON domains), `compliance_events`, `behavioral_observations` (migrations v7+, created by the resilient runner). Ingestion writers. | low | tables additive/inert |
| **P6** | (Separate, deploy-gated) wire the pipeline into `/chat` — Brain Decision → `human_model.view` → Architect → Renderer. Flag-gated, like M4. | med | flag off |

**DB migration footprint (when P5 lands):** additive only — `human_profile`,
`compliance_events`, `behavioral_observations` (v7–v9). Existing tables
(`user_preferences`, `recommendation_history`, `workout_history`, `nutrition_history`,
`coach_memory`, `athlete_models`) are **referenced, never dropped or altered**. No
destructive migration at any phase.

**Invariants enforced at every phase:** Brain untouched; Architect writes nothing; a
single writer (`observe`) for user state; all dependency arrows point into
`human_model`; no cycles.

---

## 8. Non-goals / guardrails
- Not merging the Human Model with the Brain's athlete model. The athlete model remains
  the Brain's somatic source of truth; the Human Model only *projects* it read-only.
- No behavior change and no `/chat` wiring in P0–P5 (P6 is separate and deploy-gated).
- No new clinical/medical logic — medical stays owned by the frozen Brain.
