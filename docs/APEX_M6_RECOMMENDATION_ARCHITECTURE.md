# APEX M6 — Recommendation Architecture Engine

**Status:** Implemented (library + persistence + tests). Not yet wired into `/chat`
generation — wiring is a separate, deploy-gated step (see §7).
**Invariant:** the Brain is FROZEN. This layer sits entirely downstream and modifies
no organ (S1–S5), the cascade, or enforcement.

---

## 1. The shift

APEX stops generating recommendations directly. It **designs** them first, then the
LLM only phrases the design. The LLM never decides a macro target, a session length,
a contraindication, or a food — those are decided by deterministic Python.

```
Brain Decision ──► Recommendation Architect ──► Blueprint ──► LLM Renderer ──► reply
                        (decides every value)     (fixed)      (phrases only)
```

## 2. Components (`recommend/` package)

| Module | Responsibility |
|---|---|
| `blueprint.py` | Typed blueprints: `NutritionBlueprint`, `WorkoutBlueprint`, `RecoveryBlueprint`, each carrying `explanations` (why). `to_dict()` serializes for the renderer. |
| `architect.py` | The **Architect** — `design(kind, decision, profile, preferences, subject)` decides every value from the Brain Decision + profile + prefs, deterministically, with explanations. Reads the Decision; never mutates it. |
| `preferences.py` | The **Preference Engine** — `parse_updates()` (deterministic NL parse) + persistent `load`/`update_from_message` per subject. Never fed to the Brain. |
| `diversity.py` | **Rotation** — anchors each blueprint to a fresh choice, avoiding the last N used (`recommendation_history`). |
| `renderer.py` | The **LLM Renderer** — `render_prompt(blueprint)` returns a system instruction that constrains the LLM to *phrase, not decide*. Does not call any LLM. |
| `__init__.py` | `plan(decision, kind, profile, subject, message)` runs the whole pipeline. |

## 3. Blueprints (every field is machine-decided)

- **Nutrition** — protein/carbs/fat/fiber targets, max prep minutes, budget, preferred &
  avoided foods, rotation anchor + recent (diversity), difficulty, required equipment,
  seasonality, medical constraints.
- **Workout** — goal, difficulty, mobility requirement, joint impact, balance demand,
  equipment, session minutes, exercise families, **contraindications (from the Brain's S1
  constraints)**.
- **Recovery** — sleep, hydration, walking, mobility, stress reduction, breathing.

The Architect maps the Brain Decision faithfully: `envelope.intensity_ceiling` →
difficulty; `envelope.supported` → balance demand; `constraints[].movement` →
contraindications; `halt` → medical constraint / "route to care"; a routing decision
(medical_followup / crisis_support / conversation) → **no blueprint** (nothing to design).

## 4. Preference Engine

Deterministic parse (EN + a little BG), persisted per subject (`user:<id>` or
`device:<id>`), updated every message:

| Utterance | Update |
|---|---|
| "I hate oats" | `avoid: oats` |
| "I love eggs" | `prefer: eggs` |
| "I only have 10 minutes" | `breakfast_time: 10` |
| "I don't cook" | `cooking: minimal` |

Conflict-resolving (a new dislike removes an old like). Preferences shape the blueprint;
they are **never** given to the Brain (kept out of the athlete model).

## 5. Diversity

`recommendation_history` records the anchor used for each (subject, kind). The Architect
picks the next anchor **not used recently** (rotation pools per kind), so the same
breakfast / session emphasis isn't repeated. Recent anchors are also passed into the
blueprint (`meal_diversity`) so the renderer keeps it fresh.

## 6. Explainability

Every blueprint carries `explanations` — `(claim, because)` pairs, e.g.
`("High protein","muscle gain")`, `("Joint-friendly","<constraint reason>")`,
`("Quick breakfast","user has 10 minutes")`, `("No oats","preference")`. The renderer
weaves these into the reply so the person understands *why*.

## 7. Persistence & wiring

- **DB (additive, migrations v5/v6):** `user_preferences`, `recommendation_history`.
  Created by the resilient `run_migrations` shipped in M5.
- **Not yet wired into `/chat`.** The engine is a tested library. Turning production
  generation into "render a blueprint" is a behavior change on the generation path
  (like M4 enforcement) and should be a separate, flag-gated, approved+deployed step.
  When wired: `plan()` runs after the Brain Decision; if it returns a blueprint, its
  `prompt` replaces the free-form generation instruction; otherwise the existing
  enforcement path (route/ask/cold-start) is unchanged.

## 8. Guarantees
- No Brain modification — S1–S5, cascade, enforcement byte-identical (verified).
- The LLM never decides a blueprint value (renderer is phrase-only, enforced by prompt).
- Deterministic Architect (same inputs → same blueprint, modulo diversity rotation).
- Tests: `tests/test_recommend.py` (10) — parsing, persistence + conflict resolution,
  workout/nutrition design + explainability, route→no-blueprint, diversity rotation,
  render-only prompt with values preserved, end-to-end pipeline over a real cascade
  Decision. Full suite 142/142.
