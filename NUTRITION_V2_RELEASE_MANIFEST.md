# Nutrition V2 Release Manifest

## Release Scope

This release contains deterministic Nutrition Conversation Orchestration,
structured `NutritionPlan` generation and persistence, deterministic rendering,
and typed nutrition-plan revisions. It does not activate Nutrition Engine V2,
change Railway configuration, or modify frontend behavior.

Changed runtime modules:

- `app.py`: routes daily-plan generation through structured JSON, renders only
  validated `NutritionPlan` objects, persists canonical plans, and applies
  typed revisions without invoking a model.
- `nutrition_conversation.py`: one nutrition conversation state machine,
  Bulgarian plan-intent vocabulary, canonical diet policy, and typed revision
  recognition.
- `nutrition_plan.py`: immutable `NutritionPlan` records, deterministic
  renderer, record hydration, and deterministic revision operations.
- `db.py`: structured-plan persistence APIs and schema migration.
- `tests/test_chat_enforcement.py` and `tests/test_nutrition_acceptance.py`:
  regression and real-user acceptance coverage.

## Database Migration

- Migration version: `10`
- New table: `nutrition_plans`
- Columns: account owner, stable plan ID, plan version, structured JSON plan,
  creation timestamp.
- Migration behavior: `db.run_migrations()` calls SQLAlchemy metadata creation
  before applying the ordered migration ledger. Existing databases receive the
  new table without rewriting existing rows.

`nutrition_history` remains a legacy display archive. It is not parsed,
upgraded, or used as an authoritative plan source. Newly generated plans are
stored in `nutrition_plans`; rendered chat text remains in conversation history
for display.

## Environment and Flags

- `DATABASE_URL`: required in production and must resolve to Railway PostgreSQL.
- `NUTRITION_ENGINE_V2_SHADOW`: must remain absent or `false` for this release.
- `RECOMMENDATION_ENGINE_ACTIVE`: unchanged by this release.
- Existing OpenAI, Stripe, authentication, and mail variables are unchanged.

No new environment variable is required.

## Startup and Deployment

- Process command from `Procfile`:
  `gunicorn app:app --workers 1 --threads 16 --timeout 180`
- Database initialization and migration execution occur at application startup.
- Expected deployment order: deploy the committed Git release, observe startup
  migration completion, verify the `nutrition_plans` table, then keep the V2
  shadow flag off.

Current Railway status: this worktree has no linked Railway project. The
project, production environment, and service must be identified and linked by
an approved operator before a deployment command can be issued safely.

## Backward Compatibility

- Existing rendered nutrition conversations remain readable.
- Existing `nutrition_history` records are unchanged.
- New plans are structured-first and never reconstructed from chat text.
- A failed structured generation remains a deterministic failure response; it
  does not expose an invalid plan or invoke a fallback generator.
- Revisions require an account-owned persisted structured plan. Anonymous
  rendered history is intentionally not parsed into one.

## Rollback

Previous committed baseline before this release: `150e2ae`.

Rollback is a Git deployment rollback to that commit or the Railway deployment
immediately preceding this release. The new `nutrition_plans` table is additive;
the previous application version ignores it. No destructive database rollback
is required. Keep `NUTRITION_ENGINE_V2_SHADOW` absent or `false` during rollback.

## Release Verification Checklist

- [x] Nutrition acceptance suite: 32 passed.
- [x] Full regression suite: 605 passed.
- [x] No expected failures or skipped acceptance scenarios.
- [x] `git diff --check` passes.
- [x] Structured-plan migration is included.
- [ ] Railway project, service, and production environment verified.
- [ ] Production deployment and migration observation completed.

## Deployment Blocker

The local Railway CLI is authenticated, but this worktree has no linked project.
Do not run a deployment command until the intended Railway project, production
environment, and service are verified explicitly.
