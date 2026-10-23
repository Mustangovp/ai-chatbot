# APEX Next Move M1

## Rollout and rollback

`APEX_NEXT_MOVE_ENABLED` is OFF by default. Deploy the reviewed commit with the
flag explicitly `false` first. Verify its exact SHA, application/PostgreSQL health,
anonymous denial, authenticated account reads and existing safety regressions
before an authorized production rollout sets the flag to `true`. Recheck health,
BG/EN UI and account isolation after that rollout. No preview fixture or synthetic
account belongs in the production artifact.
Rollback: remove the flag or set it to `false`, then refresh `/app`. The existing
overview and coaching actions return. No migration or new persistence is needed;
check-ins already recorded in Human State remain valid evidence, not new authority.

## Decision boundary

- GET `/api/next-move?lang=bg|en` reads only the authenticated account's profile,
  canonical active constraints, delivered first session, immutable completion,
  recent conversation and fresh Human State. Anonymous users keep onboarding.
- The existing Brain Cascade and enforcement directive retain safety authority.
  Adaptive Coach can only soften; M1 acts on its cited state only when the same
  variable has fresh, explicit account evidence. Missing recovery asks one check-in;
  profile defaults do not become today's observations. No model call runs on GET.
- Existing ContextSnapshot projects verified facts. Fresh explicit Human State
  is also passed to the existing `/chat` context builder while this flag is ON.
  Its recovery categories are translated to existing profile contract values.
- A completed session newer than the check-in requests a post-workout check-in.
  Existing completion/progression persistence is unchanged. M1 does not claim an
  adjustment has happened merely because a recommendation was displayed.
- Reading the overview never generates a plan, changes a restriction or writes
  a record. Existing canonical completion and explicit message ingestion remain
  the evidence writers; no new learning/model operation is introduced.

## Approval and privacy

POST `/api/next-move/approve` recomputes the recommendation and checks an
account-bound evidence fingerprint. Stale or cross-account fingerprints require
another approval. Approval returns an existing workflow, not a tool invocation.
The browser opens Profile, My Training, one check-in, or sends the approved seed
through ordinary `/chat`. Training still reloads constraints and validates its
canonical prescription; approval is not a safety exemption.

POST `/api/next-move/check-in` accepts only `fresh`, `ok` or `tired`, records an
explicit check-in through existing Human State, then recalculates. The UI changes
only after a successful acknowledgement. Closing the form writes nothing.

All endpoints use server-authenticated ownership, reject cross-origin POSTs and
return `Cache-Control: private, no-store`. Responses expose bounded known enums,
canonical restriction patterns and a completion timestamp, not raw profile,
health text, conversations or account identifiers. Read failures fail closed.
Owner/language generations discard late browser responses. No polling, automatic
approval, autonomous tools, added scores or model requests occur on page load.

## Local validation

Python: `tests/test_next_move.py`, existing Human State, Adaptive Coach, My Training
and selected chat/constraint regressions. Browser: `next-move.spec.js` at 390px
and 1440px, BG/EN, approval, check-in ACK/error, owner changes and text chat.
Screenshots use a clearly labelled synthetic local account; they are not evidence
of live model quality. Core engines, renderer, states and pointer code are frozen.
