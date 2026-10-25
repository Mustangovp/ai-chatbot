# Training progress in chat (M2.1)

Local implementation; no production rollout is part of this task.

## Authority

Explicit BG/EN training-progress requests use `db.get_training_progress` for the
authenticated server account. Its existing immutable-lineage validation and
100%-completed-session boundary remain unchanged. Browser history, submitted
account IDs, legacy free-text workouts and LLM numbers are not analysis inputs.
Medical holds and existing controlled safety responses retain precedence.

The read projection contains the latest five verified completed sessions. One
exercise/version is selected deterministically, grouping by observed dose unit,
completed sets and recorded load. Missing load remains unknown. Matching these
fields does not prove equal technique, recovery or training conditions. No
fitness, strength, readiness or causal conclusion is inferred from the curve.

## Contract and presentation

`training-progress-chat-v1` has closed fields and at most five chronological
points. Each point contains an exact recorded UTC timestamp and one observed
integer value. Units are repetitions or seconds; canonical completion load is
kilograms. No prescribed dose is substituted for missing execution evidence.

The chart and table consume the same points. Two distinct observations are
required for a chart; one observation produces only a table. Empty, unavailable
or unauthenticated sources never produce a chart. Invalid observations are
excluded. No external chart package or extra model request is used.

The browser validates the payload and creates text/DOM/SVG nodes, never model
HTML. Structured evidence stays buffered until SSE `done`; interruption,
cancellation and account rotation discard it. Persisted conversation history
retains a readable text/table fallback, not a separately cached chart.

The prior legacy test expecting `show my progress` to call the LLM is intentionally
replaced by a deterministic no-provider test. Other chat intent contracts remain
unchanged. Existing Progress, Training, Nutrition and Voice surfaces are not
replaced.

## Local validation notes

The affected Python selection has 609 passing tests and eight unchanged failures
reproduced on exact base `af8cf0b57204321e4420e791ad583f590491db6c`:
seven existing chat assertions (legacy completion fixtures, old exercise choice,
old nutrition copy) and the existing Progress `reason`/`reason_code` substring
assertion. The initial focused Python selection passed 38 tests, including M1-on/off
asset loading. All 18 initial analysis browser tests passed, including the real local
persisted-data path with M1 disabled.

Four existing browser assertions also reproduce on that exact base: malformed
metadata supplied outside the current ChatLifecycle exchange, CL-3 history
hydration (flaky), CL-8 total fetch count, and CL-9 old quota copy. They are not
modified here. The new analysis tests cover the actual current exchange, SSE
interruption, cancellation, owner rotation, safe text rendering and both locales.

All previews use synthetic evidence and loopback-only temporary SQLite. There
are no billable API tests, production changes, commits, pushes or deployments.

## Release-candidate gate

Release preparation found that the malformed-workout-metadata baseline cannot
be waived as harmless: in an actual active SSE exchange, `training_completion:
null` is ignored by the existing truthiness dispatch, permitting legacy workout
cards and success prose. This reproduces on the exact base and on M2.1. It is not
caused by M2.1, but affects the canonical delivery fail-closed invariant. Release
remains BLOCKED; no unrelated delivery fix is included in M2.1. See
`docs/M2_1_RELEASE_CANDIDATE.md` for scope, evidence and rollback preparation.
