# APEX PULSE PRO - Project State

Verified against the current repository on 2026-10-04. This document describes
implemented architecture and current product availability, not a roadmap.

## Runtime and UI

- Flask serves `/` from `templates/landing.html`, `/en` from
  `templates/landing_en.html`, and `/app` from `templates/apex.html`.
- `templates/apex.html` is the canonical application UI, with BG/EN support.
- PostgreSQL is the production source of truth for account data. `db.py` provides
  persistence and versioned migrations; SQLite remains a local/test fallback.
- Chat uses the existing `/chat` SSE delivery path.

## Identity and persistence

- Passwordless email magic-link authentication and server-side account sessions
  exist (`/auth/request`, `/auth/verify`, `/auth/me`, `/auth/logout`).
- Account profiles persist server-side through `/api/profile` and `db.py`.
- Authenticated users have account-owned conversation and workout history that
  synchronizes across sessions/devices through the account APIs and app bootstrap.
- Explicit training constraints persist server-side and are reapplied to training
  recommendations. An unavailable constraint store is not treated as empty.
- Before sign-in, browser storage may hold local profile/history and workout
  state. Browser caches do not replace authenticated account persistence.

## Coaching and Core

- `training_engine/` owns deterministic exercise selection, prescriptions,
  mixed-modal/CrossFit structure, follow-ups, and delivery validation.
- Training plan lineage, observed execution/completion, progression events/state,
  and trajectory infrastructure exist. A completion ID alone is not proof of a
  completed session; these records do not establish readiness or adherence.
- Authoritative nutrition plans and nutrition history persist server-side for
  authenticated users. Nutrition targets and restrictions retain their existing
  deterministic authority.
- Profile/history context supports personalized coaching. Medical Boundary,
  Brain safety, active constraints, and authoritative plans outrank model prose.
- APEX Core in `templates/apex.html` uses `AthleteModel`, `PresenceEngine`,
  `BreathEngine`, and `AttentionEngine`, with `LivingCore` owning rendering and
  interaction. It is not a separate dashboard or a medical measurement.

## Access

- FREE access is live.
- CORE and PRO paid access remain disabled / coming soon. Existing payment code
  does not mean paid checkout is enabled; the backend gates it with
  `PAID_ACCESS_ENABLED`, which defaults to false.
