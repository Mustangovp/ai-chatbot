# APEX PULSE PRO

## What this repository is

APEX PULSE PRO is a premium AI human-performance system, not a generic chatbot.
It is a Flask production application backed by domain engines for deterministic
training, structured nutrition, safety, persistence, and coaching presentation.
The Living APEX Core is a first-class product subsystem in the browser.

This README is the repository navigation entry point. Runtime source code is the
current implementation authority. Architecture, roadmap, and research documents
provide context, but do not change runtime behavior by themselves.

## Current Production Architecture

`app.py` owns Flask routes and request-level orchestration. A `/chat` request
constructs the authoritative route, applies safety and restrictions, and then
delivers a structured result through the existing persistence and SSE paths.

| Area | Request-level path |
| --- | --- |
| Training | `app.py` -> decision/recommendation orchestration -> `training_engine/` -> `training_engine/renderer.py` -> persistence and `training_engine/followups.py` |
| Nutrition | `app.py` -> `nutrition_conversation.py` -> `nutrition_plan.py` -> `nutrition_followups.py` / `recipe_engine/` -> persistence and delivery rendering |
| Brain and safety | `app.py` -> `brain/cascade.py` / `brain/enforcement.py` -> deterministic restrictions and controlled replies. `brain/shoulder_validator.py` validates shoulder claims against the final workout. |
| Human State and coaching | `app.py` -> `human_state/` and `coaching/` behind explicit flags. Presentation projection is typed and bounded; it cannot replace training or nutrition authority. |
| APEX Core | `templates/apex.html` -> browser `AthleteModel`, `BreathEngine`, `AttentionEngine`, `PresenceEngine`, and `LivingCore`. |

### APEX Core

The current Core implementation is in `templates/apex.html`. It has seven base
states: `waiting`, `listening`, `thinking`, `answering`, `resting`, `recovering`,
and `goodbye`. Pointer/touch physics, transient gestures, reduced-motion handling,
and breath-gated state transitions remain browser-owned. The server can supply only
a validated bounded projection that biases continuous expression; it cannot select
a Core state or bypass a breath gate.

`docs/APEX_CORE.md` is useful visual reference, but it describes an earlier
five-state V1 specification. When it conflicts with `templates/apex.html`, the
runtime implementation is authoritative.

## Production, Flag-Gated, and Reference Areas

| Area | Status | Canonical paths | Notes |
| --- | --- | --- | --- |
| Flask application, auth, persistence, chat, SSE | PRODUCTION | `app.py`, `db.py`, `templates/apex.html` | Runtime behavior lives in source and tests. |
| Deterministic training | PRODUCTION | `training_engine/`, `training_engine/health_restrictions.py` | `TRAINING_ENGINE_ACTIVE` defaults to enabled. |
| Structured nutrition delivery | PRODUCTION | `nutrition_conversation.py`, `nutrition_plan.py`, `nutrition_followups.py`, `recipe_engine/` | Persisted structured plans, not rendered chat text, own follow-ups. |
| Brain safety | FLAG-GATED | `brain/`, `brain/config.py`, `brain/health_scope.py` | `BRAIN_SHADOW` observes; `BRAIN_ENFORCE` changes delivery only when deliberately enabled. |
| Persona/Expert advisory | FLAG-GATED / SHADOW | `brain/runtime_assets/`, `training_engine/advisory.py` | Shadow flags are observational; active advisory requires its separate production flag. |
| Nutrition Engine V2 | FLAG-GATED / SHADOW | `nutrition_engine/`, `nutrition_engine/canonical_delivery.py` | V2 shadow is observational. Canonical V2 delivery requires `NUTRITION_ENGINE_V2_ACTIVE` and a production-ready catalog; it is not default authority. |
| Human State and adaptive presentation | FLAG-GATED / SHADOW | `human_state/`, `coaching/` | Ingestion, audit, trajectory, shadow, and consumer behavior are independently gated. |
| Architecture, governance, milestones, research | DOCUMENTATION / CONCEPT | `docs/` | Reference material; verify every operational claim against runtime code. |
| Tests and fixtures | TEST / FIXTURE | `tests/` | Test contracts, not production runtime. |

## Canonical Source-of-Truth Map

| Concern | Canonical source |
| --- | --- |
| Application routes and request orchestration | `app.py` |
| Persistence schema and migrations | `db.py` |
| Browser APEX Core | `templates/apex.html` and `docs/APEX_CORE.md` (reference only where it differs from runtime) |
| Training runtime and plan contract | `training_engine/` |
| Training health restrictions | `training_engine/health_restrictions.py` |
| Nutrition plan contract and delivery | `nutrition_plan.py`, `nutrition_conversation.py`, `nutrition_followups.py`, `recipe_engine/` |
| Nutrition V2 gated delivery | `nutrition_engine/canonical_delivery.py` and `nutrition_engine/` |
| Brain configuration and safety boundary | `brain/config.py`, `brain/health_scope.py`, `brain/` |
| Human State and coaching presentation | `human_state/`, `coaching/` |
| Product guardrails | `APEX_GUARDRAILS.md` |
| CI | `.github/workflows/playwright.yml` |
| Dependency contracts | `.python-version`, `requirements.txt`, `requirements-dev.txt`, `package.json`, `package-lock.json` |

## Document Hierarchy

1. **Tier 1: current runtime truth.** Source code, migrations, tests, and locked
   dependencies determine current behavior.
2. **Tier 2: current architecture and governance reference.** Start with
   `docs/architecture/`, `docs/governance/`, and `docs/milestones/`; confirm any
   activation or implementation statement against Tier 1.
3. **Tier 3: roadmap, research, vision, and historical material.**
   `docs/research/`, `docs/vision/`, `docs/archive/`, `APEX_VISION.md`,
   `PROJECT_STATE.md`, `IMPLEMENTATION_PLAN.md`, and `IMPLEMENTATION_ROADMAP.md`
   are context, not runtime authority. In particular, `PROJECT_STATE.md` describes
   an earlier localStorage-only/application layout and must not be used as the
   current architecture map.

See [docs/README.md](docs/README.md) for a compact documentation index.

## Local Development

The repository selects Python `3.13.13` in `.python-version` and Node `24.x` in
`package.json`.

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
npm ci
```

For a local Flask server, use the repository entry point:

```powershell
python app.py
```

The runtime reads configuration from environment variables. The CI boot contract
sets `APEX_SECRET`, `OPENAI_API_KEY`, and `STRIPE_SECRET_KEY`; production database
selection uses `DATABASE_URL` when present and SQLite otherwise. Do not commit or
print secret values. See `app.py` and `.github/workflows/playwright.yml` before
adding configuration.

## Official Test Gate

Run the tracked Python tests, compile check, Playwright suite, and whitespace
check before a release:

```powershell
python -m pytest @(git ls-files tests | Where-Object { $_ -match '(^|/)test_.*\.py$' }) -q
python -m py_compile @(git ls-files '*.py')
npx playwright test --config=tests/playwright/playwright.config.js
git diff --check
```

GitHub Actions runs the tracked Python suite, compile validation, and the
Playwright gate in `.github/workflows/playwright.yml`. It does not deploy the
application.

## Production Discipline

- Read-only audits do not modify code, environment variables, or deployments.
- Do not deploy or change production flags without explicit authorization.
- Do not replace the APEX Core with generic animation or expose fabricated metrics.
- Do not let generic LLM output bypass safety, deterministic training, or structured
  nutrition authority.
- Structured persisted plans and workout blueprints are authoritative where their
  flows apply; do not reconstruct them from rendered chat text.
