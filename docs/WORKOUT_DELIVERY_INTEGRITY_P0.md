# Workout delivery integrity P0 (local only)

Base: `af8cf0b57204321e4420e791ad583f590491db6c`.
No commit, push, deployment, database migration or paid API test.

## Root cause and boundary

The SSE dispatcher tested the truthiness of `training_completion`; null was
ignored. The renderer then treated missing canonical metadata as permission to
construct a legacy actionable workout. Chat completion persisted that output
even when rendering was rejected.

All actionable workout rendering now requires a valid first-session canonical
completion contract from the current exchange. Missing/null/empty metadata,
contradictory rows/doses/units, unknown exercises and duplicate sessions are
rejected. There is no legacy workout-key creation or unverified Start fallback.
Historical text without its contract cannot recreate an actionable workout.

Server transport projection is checked against the existing immutable
`completion_projection`, after the existing training safety validator and before
lineage persistence, visible content, remembered workout or activation candidate.
No new exercise policy or constraint authority is introduced.

`X-APEX-Delivery` distinguishes server-classified conversational delivery from
training. Unclassified/training content stays buffered until `done`; ordinary
server-classified conversation retains progressive streaming. A workout table
still requires its contract regardless of that header. Progress charts keep
their independent validated M2.1 contract.

Invalid/interrupted workouts produce one existing BG/EN verification failure,
no actionable cards, no Start, no unverified workout in assistant history, no
reply-to-Voice event and no successful activation confirmation. The server may
retain its verified refusal text. Cancelled/completed exchanges ignore
late metadata; per-attempt guards prevent an old response overwriting a retry.
Failure during multi-table rendering rolls back temporary protocol registrations.

## Test fixture changes

Positive activation uses the real canonical construction fixture rather than a
partial legacy object. The overview Start test attaches metadata to its current
exchange. Protected fixtures await existing account hydration before installing
synthetic chat state. The progressive-coaching test declares its real transport
classification. Outcome assertions are retained; no arbitrary sleeps are added.

## Preservation

The original M2.1 candidate at `C:/tmp/apex-m21-rc-af8` and review patch remain
untouched. The patch SHA-256 is
`345F571DEE3D9F67226F2C764C6F1C1C123DACDCF164646B5DF173EC6624FCB0`.
It remains a historical M2.1-only candidate, not a P0-inclusive release approval.
Unrelated Premium UI experiments and local preview files are preserved locally.

Core engines/renderer/touch blocks are unchanged after Git/Windows checkout
line-ending normalization. Exercise Library,
selection, Brain policy, Nutrition generation, model routing, Voice transport,
payment limits and database schema are unchanged.

The eight previously proven Python baseline failures remain unrelated. The old
malformed-workout browser failure is repaired. CL-8's all-fetch count and CL-9's
old Bulgarian quota wording remain unchanged baseline assertions.

## Local validation (2026-10-24)

- Directly affected Python selection: 645 passed, eight unchanged exact-base
  failures as recorded in the preserved M2.1 candidate.
- Delivery integrity, canonical coverage, M2.1 and activation browser selection:
  88 passed, including stale metadata after a previously validated workout.
- Protected workout execution, overview and playback browser selection: 51 passed.
- Existing Voice suite on its intended isolated mock harness: 33 passed.
- Protected ChatLifecycle/Nutrition subset: 19 passed; only the two unchanged
  CL-8/CL-9 baseline assertions failed. The ownership hydration fixture is awaited,
  not delayed with an arbitrary sleep.
- Python compilation, inline JavaScript syntax and `git diff --check` passed.
  Core renderer/engine/pointer blocks match base after checkout EOL normalization.

These checks use loopback-only fixtures, temporary SQLite and synthetic data.
Providers are mocked or denied. No physical microphone, paid API, production,
commit, push or deployment operation was performed.
