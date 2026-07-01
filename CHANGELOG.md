# Changelog

All notable changes to APEX. Format based on [Keep a Changelog](https://keepachangelog.com/).
Newest first.

## [1.0] — 2026-07-01

### Fixed (QA hardening)
- **Chat stream timeout (M-1):** `AbortController` with a 75 s inactivity watchdog (reset per token). A stalled stream aborts, releases the UI, shows "Connection interrupted. Please try again.", and restores the message for retry — instead of blocking sends until the 180 s server timeout. `2598cf4`
- **Accessibility (M-2):** all 22 profile-wizard labels associated with their fields via `for="pf-*"`; chat input given a localized `aria-label`. `2598cf4`
- **Open redirect (L-1):** `/owner-mode?next=` restricted to internal routes via `_safe_next()`. `2598cf4`
- **Free-limit race (RV-1):** `free_usage_consume()` retries on `IntegrityError` — a first concurrent request no longer returns HTTP 500. `1a68926`
- **Subscription resilience (RV-3):** `get_subscription()` degrades to FREE if PostgreSQL is momentarily unavailable — no 500, no broken UI. `1a68926`

### Added
- **Personality Engine (1.1):** `personality.py` — a layered directive (fixed identity + banned hype, data-driven tone selector across 5 modes, true-only observation engine) that makes every reply read as the same coach. EN + BG. `009ce7b`
- **Server-side identity & persistence:** PostgreSQL via SQLAlchemy; passwordless email magic-link auth (email = canonical identity); httpOnly sessions. Tables: users, profiles, coach_memory, workout_history, nutrition_history, conversations, subscriptions, free_usage (+ auth_identities, login_tokens, sessions, payments, schema_version). UUID PKs + timestamps; idempotent migration runner. `a5668e6`, `23df238`
- **Account-owned data:** profile, workout/nutrition history, coach memory and conversations persist to the account and load on any device; one-time localStorage→DB migration on first sign-in.
- **Server-authoritative free limit** keyed to account/device (not localStorage) and **server-verified subscription** state.
- **Personalized targets:** hydration/TDEE/protein computed from profile; system rule forbidding generic figures.

### Changed
- **Chat scroll ownership:** streaming never auto-scrolls; the reader keeps their position; "Jump to latest" is the only catch-up. `dfde8e3`
- **Living organism:** uniform time-scale raised so motion is clearly, calmly alive (~10 s breath) without touching colours, composition, brightness or per-frame cost. `dfde8e3`, `b435640`

### Notes
- Not yet tagged `v1.0.0` and `main` not frozen — pending the live magic-link login and Stripe test-payment smoke tests.

## Prior milestones
- **APEX V3.x** — AI Operating System shell (`templates/apex.html`): living-organism core, hamburger menu, subscription page, 3-step biological profile, markdown/exercise/nutrition renderers, full workout protocol, complete EN/BG localization. Legacy `templates/app.html` retired.
- **APEX 1.0 landing & growth** — bilingual landing pages, OG/social assets, email sequence, Stripe plans, EU right-of-withdrawal cancellation.
