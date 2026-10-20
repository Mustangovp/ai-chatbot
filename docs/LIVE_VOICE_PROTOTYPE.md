# APEX Live Voice restricted tester pilot

Status: local prototype. Mock lifecycle/security coverage is separate from bounded
live API checks using synthetic audio and isolated SQLite/PostgreSQL. Neither proves
physical-microphone recognition, echo handling, audible quality, or production
readiness. No paid minutes, pricing or entitlement changes.

## Restricted release policy: owner-approved limited-test risk

The owner explicitly approved the four-request gpt-4o-mini-tts pilot exception.
It is OFF until trusted server provisioning/enablement for ONE verified account.
Provider post-crash closure/final billing remain UNCONFIRMED, documented accepted
limited-test risk. There is still no supported TTS output-token/audio-duration
cap and no guaranteed invoice ceiling. All controllable security gates must pass
before push; production activation is separately verified after auto-deploy.

## Shared safety controls

`voice/safety.py` stores one private `voice-test:global-safety:v1` JSON record in
the existing `user_preferences` table. There are no new tables, columns, schema
versions, services or production migrations. Missing state is OFF/denied. Real
transport requires PostgreSQL; SQLite is permitted only by explicit constructor
injection in deterministic unit tests. The loopback mock never calls OpenAI.

Trusted server code must provision ONE verified account UUID, explicit global
and per-account micro-USD limits, an operation limit and an expiry. Provisioning
inserts once, initially OFF; it cannot reset/reassign/refill an existing ledger.
Limits are independent, each at most 5,000,000 internal micro-USD ($5), at most
128 operations, and at most 24 hours. There is no automatic refill or quota reset.
The earlier per-account audio allocation still applies as an additional limit.
These are internal authorized reservations, NOT guaranteed provider invoices.

PostgreSQL SELECT FOR UPDATE atomically checks/increments BOTH counters and
records a unique operation before chargeable work. Unknown/failing calls retain
their full reservation. Only complete, validated numeric provider usage may
settle unused reservation once. Operation count never decreases. Counter or
usage-bound corruption fails closed; a usage-bound violation disables the test.
No prompt, audio, transcript, health data or secret is stored in this ledger.

`voice/charging.py` guards the existing client boundary for the provisioned
account, including direct /chat and /speak requests with voice=false. It captures
only verified server identity. A revoked cookie is never authentication; it may
only locate a private budget subject so that the revoked session is rejected
rather than downgraded to an unmetered anonymous call. Auth lookup failure blocks
billable endpoints. No client account-ID/header controls budget selection.

GPT-6 requests reserve bounded text-input bytes plus protocol allowance and the
existing max_completion_tokens (including reasoning), at conservative internal
rates. Unknown models, tools, images, unbounded output or parameter overrides are
denied. SDK automatic retries are disabled only in this restricted scope; each
application retry reserves separately. Streaming stops on OFF and only reconciles
terminal usage. Background learning captures the same principal explicitly,
without retaining Flask context; its existing persistence/authority is unchanged.

Transcription reserves `(session_seconds + 256) * 1000` internal micro-USD before
opening the provider socket. This deliberately exceeds the published duration
rate and budgets per-turn accounting overhead; it is not an invoice promise.
Actual duration settlement requires provider Close plus complete committed-turn
usage. Pending/failed/crashed sessions keep their full reservation. Audio remains
sample-capped and paced, with a hard deadline and one durable account lease.

TTS has the same reservation boundary. Existing character-billed tts-1/tts-1-hd
can be bounded by input length (conservative 60 micro-USD/UTF-8 byte, which
overbounds the character count); the model is
NEVER changed by this guard. Mini-TTS remains denied without the exact durable
pilot approval; an account cannot select the exception in a browser request. Ordinary
non-test users retain the same voice/model path. Successful TTS without
trustworthy usage retains its conservative reservation.

### TTS compatibility hardening

`/speak` and the adapter reject non-string/empty input and more than 1600
characters; they no longer silently truncate or stringify arbitrary JSON. The
adapter makes exactly ONE provider request, with SDK retries disabled and a
20-second network timeout. Classic model arguments are chosen before submission;
there is no retry without instructions after an exception and no model change.
`ProtectedClient.with_options()` retains the budget wrapper rather than exposing
the unguarded SDK client. Error logs contain the exception class only.

Within the restricted tester ledger, PostgreSQL serializes all TTS reservations
against the same account/global pool used by GPT-6 and transcription. Exactly one
TTS operation may be open. The durable TTS attempt limit defaults to four, may be
explicitly provisioned from one to eight, and never refills. Missing TTS limit
state fails closed. Failed requests still count toward the attempt limit.

Submission uncertainty is recorded BEFORE provider I/O. A setup failure proven
to precede submission returns its unused reservation once but never returns an
attempt. A submission/read failure or crashed worker retains BOTH the full cost
reservation and the active slot; no TTL/restart assumes the provider stopped.
A successful full binary read releases only the concurrency slot. Binary audio
contains no trustworthy numerical usage, so it does not release cost. The generic
reconciliation path can settle verified usage once, but current mini-TTS binary
success does not fabricate such usage. These are internal allocation returns,
not refunds of provider charges. The network timeout is NOT a provider runtime
or output-duration cap.

Strict invoice-bound result: gpt-4o-mini-tts CANNOT satisfy that requirement using
the documented Speech API. This has not changed. The owner-approved release is
a limited-risk pilot, not a claim that a hard provider cost bound was established.
No unsupported max_tokens parameter or automatic model substitution is introduced.

Approved pilot policy (activation requires trusted server provisioning): retain the exact model,
one tester, one concurrent TTS call, at most four attempts, and <=400 input
characters. Reserve an operational $0.10 per attempt in the existing global
ledger, with no automatic retries/refill; hold unknown costs. This is $0.40 of
internal TTS authorization, NOT a $0.40 invoice ceiling. Its planning allowance of 8000 audio
output tokens costs $0.096, plus $0.0012 for 2000 text input tokens. The 8000-token
allowance is NOT an API cap or an empirically established maximum. Published
rates are $0.60/M text input and $12/M audio output. An anomalously long output, pending
processing after timeout/crash, and final provider accounting can exceed the
estimate. The owner has accepted that residual financial risk. The chat contract
delta is resolved as recorded below.

Trusted `control.approve_tts_pilot(account_uuid)` records this exception only for
the existing global tester, while OFF and before any TTS use. It is idempotent and
cannot refill counters, extend expiry, reassign ownership or enable the switch.
Reservation rechecks approval, the exact $0.10 quote, four-attempt count and
$0.40 sum of original reservations under the PostgreSQL row lock. Even refunds
of provably unused reservations cannot permit a fifth attempt. Successful binary
audio holds its cost allocation; unknown outcomes also keep the active slot.
The pilot accepts only <=400 characters, supported fixed voices/formats and
bounded instructions; parameter overrides and alternate models fail closed.

Activation procedure after the exact branch commit auto-deploys: resolve the
existing controlled account on the server and verify completed real login
evidence; provision the global/account ledger initially OFF (one-off $5 internal
global AND account maximum, 32 aggregate operations, one-hour expiry); approve
the TTS exception; configure one 120-second media allocation with 120 seconds
total (no second full session). Verify OFF and all counters before setting the
server feature flag. Recheck health/non-tester 403s, then enable the durable
switch. Do not create users, sessions, subscriptions, products or API credentials.
The operator never prints IDs, session cookies, secrets, profile or audio data.
Only `APEX_LIVE_VOICE_ENABLED` may change for this activation; no other Railway
configuration is part of the release. Server-owned relay/PG controls remain
mandatory, with no browser-to-provider fallback. Trusted OFF is the immediate
kill command; no admin HTTP endpoint exists.

The durable global switch is server-only `control.set_enabled(False)`. No HTTP
administration endpoint exists. OFF commits a new epoch: new sessions/operations
are denied and connected relay workers poll at most every 250 ms during normal
operation, then close upstream and downstream. A shared outage has the same stop
behavior; the independent deadline timer remains a final safeguard. Stop is sent
as session.ended, never a retryable transport error, so browser fallback/reconnect
does not reopen voice. Re-enabling cannot revive an old epoch or refill a ledger.
In-flight GPT work is already reserved/bounded; its output is discarded after OFF.

Before any future restricted activation, resolve the mini-TTS bound/model decision
explicitly, provision the actual authorized non-owner UUID and approved one-off
budget, and preserve the exact-base chat parity checks below. Do not enable the
feature for any other account. Rollback for
a future release starts by committing shared OFF, verifying media stop, then
restoring the prior successful Railway deployment; no DB rollback is required.
Rollback has been documented, not executed.

Verification: the expanded focused Python set covers PostgreSQL races for both
binding account/global caps, three operation kinds, retained/reconciled usage,
repeated sessions, separate-process OFF, active mock-media termination on OFF
and exhaustion, restart, database outage, request overrides, revoked cookies and
background learning. The local browser regression rerun passed 55/55 (BG/EN,
Core, relay cleanup, language continuity and typed workouts). An initial existing
workout startup race passed three isolated repeats and the complete rerun, with
no workout test/UI edits. Earlier guard-on/off results were NOT exact-base
evidence and are superseded by the comparison below. No provider crash
experiments were repeated. Pilot release focused result: 291 Python tests passed,
including nine PostgreSQL runtime tests and all new TTS controls. TTS lifecycle
fixtures use a legacy model only to exercise reservation mechanics; the default
model remains unchanged and mini-TTS denial is separately asserted.
Compile/diff checks passed and the protected Core engine block is unchanged.
The temporary PostgreSQL cluster is stopped after verification. Commit/push and
auto-deployment are authorized only for this tested pilot release. Local preview
runtime files and temporary databases are not part of the release commit. No paid
access, pricing, billing or unrelated configuration change is authorized.

### Exact-base chat comparison before prompt isolation

Exact base: `dd9e3af644505325e059763d4f3691f77594ff49`, exported with git archive;
the dirty worktree was not reset. Same Python environment, synthetic secrets,
feature settings and isolated SQLite bootstrap in both runs; no live API calls.
Raw JUnit/tracebacks: `C:/tmp/apex-tts-chat-base.xml` / `.log` and
`C:/tmp/apex-tts-chat-local-final.xml` / `.log`.

- Base: 462 passed, 7 failed. Two completion fixture/lineage failures, three
  stale exercise-selection expectations, two old nutrition copy expectations.
- Local, after test-only SSE cleanup: 436 passed, 33 failed. The same seven
  base failures plus 26 LOCAL prompt-contract failures caused by the previously
  added RESPONSE LANGUAGE addendum. One baseline-failing test also encounters
  this new prompt mismatch before its old exercise-selection assertion.
- The prior 37 shared guard-on/off failures therefore classify as: seven base,
  26 local prompt-contract deltas, four intermittent cases not reproduced after
  cleanup. They are NOT all baseline failures and are NOT waived for release.
  The four were non-recommend `hello`, modified-blueprint rejection, emergency
  halt `EMERGENCY_now`, and WNK-011 off-path communication.
- The memory-write flake came from a failed preceding prompt assertion leaving
  a Flask stream_with_context generator suspended. Later finalization could pop
  another test's live context. The new autouse fixture closes outstanding
  responses in reverse order before learning/patch teardown; no assertion or
  production delivery semantics changed. The complete rerun has zero context
  warnings/errors. Ten fresh-process repeats with guards ON and ten bypassed,
  with forced GC after the known preceding prompt failure, pass the memory-write
  assertion in all 20 runs. The expected prompt failure is retained every time.

No attempt was made to weaken golden prompt assertions or remove the language
work in the TTS task. Its 26 prompt failures were resolved by the subsequent
local-only isolation below. A hard invoice-bound claim remains unsupported;
the separate limited-risk pilot exception is explicitly approved above.

### GPT-6 chat regression repair (2026-10-18, local only)

Root cause: a RESPONSE LANGUAGE addendum was unconditionally appended after
shared GPT-6 prompt assembly. Live Voice also changed locale interpretation,
language-turn routing and training-explanation filtering outside voice requests.

`app.py` now resolves one `_live_voice_request` boolean: the existing voice request
AND the server's authenticated account/feature authorization. Only that scope
uses spoken language-choice parsing, speech/language instructions, controlled
language-complaint replies, BG explanation filtering and Content-Language ACK.
Shared workout-intent helpers are restored to the exact base behavior. Voice
language complaints bypass workout mutation at the request boundary, not by
changing shared training helpers. Existing medical and prescription validators
are unchanged. The shared account budget boundary remains enforced even for
voice=false; this repair does NOT create a cost-control bypass.

Product impact: ordinary text chat and legacy voice with Live Voice unavailable
again use the base prompt/routing/locale contract. An explicit language choice
in an authorized Live Voice session still persists through its existing BG/EN
client state. Recognition hints, canonical workout localization and spoken
language remain unchanged. No existing test expectation was edited.

All 26 local-only failures now PASS:

- `test_composer_failure_after_blueprint_falls_back_to_blueprint_only_prompt`
- `test_offpath_golden_prompt_identity`
- `test_chat_context_builder_preserves_anonymous_legacy_messages[anonymous_general-profile0-history0-hello]`
- `test_chat_context_builder_preserves_anonymous_legacy_messages[workout-profile1-history1-build a workout]`
- `test_chat_context_builder_preserves_anonymous_legacy_messages[nutrition-profile2-history2-build nutrition]`
- `test_chat_context_builder_preserves_anonymous_legacy_messages[sparse-profile3-history3-hello]`
- `test_chat_context_builder_preserves_anonymous_legacy_messages[full-profile4-history4-hello]`
- `test_chat_context_builder_preserves_anonymous_legacy_messages[no_conversation-profile5-history5-hello]`
- `test_chat_context_builder_preserves_authenticated_prompt_and_history_limit[free]`
- `test_chat_context_builder_preserves_authenticated_prompt_and_history_limit[core]`
- `test_chat_context_builder_preserves_authenticated_prompt_and_history_limit[pro]`
- `test_chat_computes_one_shadow_decision_without_changing_stream_or_prompt`
- `test_active_recommendation_engine_delivers_only_verified_workout_blueprint`
- `test_active_recommendation_engine_keeps_nutrition_on_the_legacy_path`
- `test_active_authority_conflict_falls_back_to_legacy_prompt`
- `test_active_persona_expert_path_uses_blueprint_without_changing_sse_or_persistence`
- `test_active_persona_expert_abstention_falls_back_to_byte_identical_legacy_workout`
- `test_recommendation_engine_flag_off_keeps_legacy_workout_prompt`
- `test_persona_and_expert_shadow_flags_preserve_prompt_sse_and_persistence`
- `test_b2_legacy_outcomes_preserve_openai_messages[build a workout]`
- `test_b2_legacy_outcomes_preserve_openai_messages[plan my nutrition]`
- `test_b2_legacy_outcomes_preserve_openai_messages[I need recovery today]`
- `test_b2_legacy_outcomes_preserve_openai_messages[show my progress]`
- `test_b2_legacy_outcomes_preserve_openai_messages[how much water should I drink?]`
- `test_b2_legacy_outcomes_preserve_openai_messages[hello]`
- `test_persona_expert_communication_flag_is_resolved_once_and_off_keeps_active_prompt_identical`

Full chat comparison rerun with identical environment/configuration and assertions:
base 462 PASS / 7 FAIL; local 462 PASS / 7 FAIL. Failure IDs AND failure messages
match exactly. The base export's app.py, chat test and conftest git object hashes
were verified against dd9e3af before running. The local test-only stream cleanup
from the previous task is retained; assertions and all 469 cases are unchanged.
Artifacts: `C:/tmp/apex-chat-isolation-base.xml` / `.log` and
`C:/tmp/apex-chat-isolation-local.xml` / `.log`.

The unchanged seven base failures, NOT waived or repaired in this task:

- `test_chat_applies_traceable_completed_workout_to_next_training_revision`: existing construction rejection / missing captured system prompt.
- `test_authenticated_chat_applies_only_comparable_persisted_completion_to_new_plan`: existing execution dose type mismatch in fixture.
- `test_training_engine_active_delivers_only_deterministic_training_plan`: old Goblet Squat selection assertion.
- `test_training_engine_uses_default_explanation_when_model_json_is_invalid`: old Goblet Squat selection assertion.
- `test_training_engine_delivers_plan_when_explanation_request_fails`: old Goblet Squat selection assertion.
- `test_arg_001_energy_precedes_macro_and_timing_and_timing_is_presentation_only`: old nutrition copy expectation.
- `test_arg_001_flag_gates_delivery_without_mutating_plan_or_sse`: old nutrition copy expectation.

New tests cover text, disabled legacy voice, unauthorized voice and authorized
Live Voice independently. A text request must never call the new voice language
or routing helpers. Existing BG/EN recognition, language complaints, canonical
workouts and persistent restrictions continue through the same GPT-6 authority.
PostgreSQL budget/kill-switch and TTS controls are unchanged; provider crash
experiments were not repeated during that local repair.

Billing references: [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[mini TTS](https://developers.openai.com/api/docs/models/gpt-4o-mini-tts),
[supported speech request fields](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create).

The local hardening now requires a verified account ID authorized by a private
server-side policy, in addition to the default-OFF flag. All blueprint entry
points return 403 for non-testers. Browser-supplied account IDs are ignored.

`voice/session_store.py` uses the existing `user_preferences` JSON table under the
reserved `voice-test:<account UUID>` namespace. Normal `user:<id>` / `device:<id>`
preferences, profile, coaching memory and entitlements are not used or modified.
SQLite BEGIN IMMEDIATE / PostgreSQL SELECT FOR UPDATE serialize reservations.
Only one reservation may exist. A complete session time allocation is charged up
front; it is never refunded by a browser claim or reset by application restart.
Default: 120 seconds per reservation, 600 reserved seconds per 24-hour window
starting at operator provisioning; allowed bounds: 15-300 / at most 1800 seconds.
Limits are operator configured, never accepted in a browser request. A shared
state failure denies creation. There is no schema change and no minute billing.

The direct browser/provider path has been removed from the browser module.
Non-mock SDP creation returns HTTP 410 and never calls the provider. Instead,
`/api/live-voice/media` accepts an authenticated same-origin WebSocket. The browser
sends 100-ms, 24-kHz mono PCM16 frames only. The APEX worker owns the sole upstream
OpenAI WebSocket, constructs every provider command, and forwards only bounded
transcription/VAD projections. No provider key, session ID or client secret is
issued to the browser. No client response.create/session.update can pass through.

`voice/media.py` checks account policy, auth session and shared limits. The final
second of a reservation is reserved for a provider Close handshake. An independent
deadline timer physically closes the upstream socket even if a DB read blocks.
Logout/revocation signals the owner; it closes upstream before recording success.
An unconfirmed close, partial handshake failure, or crashed worker keeps the
durable reservation blocked. A browser disconnect is not treated as provider ACK.

Tests on 2026-10-17 used a temporary PostgreSQL 17.11 cluster at 127.0.0.1:55439,
never Railway's production database. Two separate APEX workers received 101/429,
with exactly one 15-second reservation. A separate mock-provider process observed
upstream closure on kill of the owner and kill of all app workers: zero further
audio bytes; closure in the same millisecond as kill (measurement resolution).

Real OpenAI relay BG expiry and EN graceful close received provider Close ACKs.
BG/EN transcription events each reported usage.seconds=3. A matching BG relay
benchmark reported 906-ms connection setup and 375 ms from received VAD stop to
transcription (single samples, not percentiles). Across the initial live cases,
setup was 797-1594 ms. The PCM hop requires 384 kbit/s before framing, 100-ms
batching, and at most eight unacknowledged frames. Network backpressure fails
closed to existing voice rather than accumulating an unlimited audio backlog.
This is a bandwidth/reliability tradeoff versus compressed WebRTC, not a claim
that production naturalness or latency is equivalent. The direct reference
benchmark timed out awaiting transcription, so no trustworthy A/B delta exists.

In real OpenAI worker-kill and all-workers-kill tests, 1.5 seconds of synthetic
audio was sent before kill. The downstream socket closed and the durable lease
remained blocked, but no final provider closure/usage record can be recovered from
the killed primary connection. Provider-side residual usage after kill remains
UNCONFIRMED. Mock-provider observations are not equivalent to that evidence.
No Close ACK is expected from a process that has already been killed. Independent
provider closure must still be reported as UNCONFIRMED, not inferred from a local
socket close. The remaining cost-containment evidence is described below. No
production changes have been made.

## Crash cost containment (one bounded real test, 2026-10-17)

The relay now verifies the provider's acknowledged text-only modality, output
cap (1-32 tokens), PCM sample rate and exact `gpt-transcribe` model before any
audio. It also enforces an absolute `reservation.seconds * 24000` sample ceiling,
in addition to pacing and the hard deadline. Browser/provider commands cannot
pass through. The only upstream commands are session.update and audio append;
automatic Responses are disabled. Abrupt relay socket loss stops microphone
capture, discards queued callbacks and does not reconnect or call /chat again.
The durable crashed lease remains reserved, including across worker restart.

One real OpenAI connection used a synthetic account in isolated PostgreSQL,
two localhost workers, a 15-second reservation AND a 15-second aggregate budget.
No coaching, TTS, customer data or production DB access was used. Technical
evidence (no transcript/audio/IDs/secrets) recorded:

- 04:54:23.091 UTC: provider acknowledged gpt-realtime-2.1-mini, text-only,
  max_output_tokens=32, gpt-transcribe and create_response=false.
- 04:54:26.660 UTC: first transcription completed; usage.type=duration,
  usage.seconds=3. At the published rate this received usage represents $0.000225.
- 04:54:29.711 UTC: second turn committed; one transcription pending, zero
  response.created/response.* events throughout the test.
- 04:54:29.720 UTC: both app workers killed. Downstream EOF was observed within
  the same approximately 16-ms monotonic clock tick. Three post-kill downstream
  send attempts produced no new audio.accepted/provider-send evidence. Both
  workers exited; only one provider connection had been created. No automatic
  reconnection occurred, and a new shared reservation was denied.
- 160800 samples / 6.7 seconds had been forwarded; absolute cap was 360000
  samples / 15 seconds. One completed and one pending transcription at kill.

The local netstat probe returned zero matching sockets even BEFORE kill, so it
is inconclusive and is NOT provider-closure evidence. Final provider usage and
remote processing termination remain UNCONFIRMED; the dead connection cannot
deliver a final event. No already-authorized provider cost/usage reporting
surface was available for independent before/after reconciliation. No new
credentials or admin access were requested, and no aggregate project usage was
misrepresented as this test's usage.

Billing is NOT GPT-Live connected-minute pricing. The current rate card for
gpt-realtime-2.1-mini is $0.60/$2.40 per million text input/output tokens and
$10/$20 per million audio input/output tokens. Realtime conversational charges
accrue when a Response is created, not for an idle socket. This relay creates
zero Responses; the 32-token safeguard does not bound input transcription.
The separately selected gpt-transcribe rate is $0.0045 per audio minute.

Published-rate model: charging the ENTIRE 15-second allocation again after kill
would cost 15 / 60 * $0.0045 = $0.001125 in transcription work, before any
undocumented per-turn rounding/minimum and invoice treatment. Charging all 6.7
seconds actually forwarded would be $0.0005025. Neither number is an independently
verified final-invoice upper bound: final pending-turn usage is unavailable and
provider-side duration accounting/rounding has not been reconciled. Realtime
output-token caps do not cap ASR output or prove a provider wall-clock completion
deadline. The bounded input/reconnect guarantee is established; an unconditional
dollar ceiling and provider completion time are not. This historical experiment
did NOT authorize release. The later owner-approved limited-risk pilot policy
above is the release authority; it does not manufacture missing provider evidence.

Sources: [Realtime billing](https://developers.openai.com/api/docs/guides/voice-latency-cost),
[Realtime Mini rates](https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini),
[GPT-Transcribe rate](https://developers.openai.com/api/docs/models/gpt-transcribe).

Post-change gates: 208 focused Python tests and 55 browser tests passed, including
the abrupt relay-close/no-reconnect case, BG/EN, GPT-6 policy, safety and typed
prescriptions. The isolated PostgreSQL two-worker gate again returned 101/429;
mock-provider kill tests observed zero post-kill audio. Compile, JavaScript syntax
and diff checks passed. Core's protected engine block is unchanged, as are
deterministic Training, Brain, Nutrition, DB schema and model policy. These tests
are not a substitute for final provider billing evidence. The temporary PostgreSQL
cluster was cleanly stopped after testing.

## Authority

Realtime is input transport, not a second coach. Only final transcription
events enter the existing `send({voice:true})` -> `/chat` path. GPT-6 policy,
AthleteModel, Brain, constraints and deterministic Training/Nutrition remain there.
Speech comes from the existing validated speech projection and `/speak` adapter.
Automatic Realtime responses are disabled; incoming response/tool events and audio
are not presented. This is not yet an evaluated full-duplex speech-to-speech agent.

Voice facts use the existing `witness('keystroke')` / `witness('replyToken')` hooks.
Core's seven states, engines, physics, gestures and transitions are unchanged.

## Local configuration (default OFF)

- `APEX_LIVE_VOICE_ENABLED=true`: server opt-in; insufficient without account policy.
- `APEX_LIVE_VOICE_TRANSPORT=relay` (default) or direct-loopback `mock`.
- `APEX_REALTIME_MODEL=gpt-realtime-2.1-mini` (or `gpt-realtime-2.1`).
- `OPENAI_API_KEY`: secure server-process injection only; never browser-side or in a file.

An authenticated existing session and exact same-origin WebSocket are required.
Mock transport remains direct-loopback-only; relay additionally accepts the
configured HTTPS APP_URL, but only for a server-authorized account. No profile or
history is put into Realtime config. The mock's process-local counter is not the
authority: real media session/aggregate limits use shared reservations.
Online use is restricted to the owner-approved pilot policy above. The synthetic
preview executable is local-only and is never the production startup command.

Connection deadline: 20 seconds client-side; provider connect/config each at most 5 seconds.
At most two reconnects per explicit Start (250 ms then 1000 ms). Failed reconnect
falls back without replaying a transcript or backend request. Exhaustion requires
explicit restart. These retries handle explicit transport failures; a relay
socket close/session.ended stops instead, with no automatic reconnect or fallback.
Stop, hidden/pagehide and account change close the local socket,
stop microphone tracks, abort handshake and ignore late generation callbacks.

## Language and demo truth

The selected BG/EN response language wins over the language of one utterance.
Only an affirmative language request changes it. `/chat` acknowledges the locale
with `Content-Language` before cards and speech render; the existing account/local
preference is updated through the normal persistence path. A language complaint
is not a workout mutation. Canonical prescription values and IDs are unchanged.

GPT-Transcribe receives `languages` and short language-matched recording context,
not the legacy singular `language` hint. Empty/unsupported detected-language
evidence, unexpected script in a BG session, or reported low token confidence
requests clarification without submitting the transcript as intent. The local
logprob/recognition thresholds are conservative retry gates, not calibrated
recognition-accuracy claims. English training terms remain allowed in BG turns.

Only executable synthetic fixtures set the template's DEMO context. Their app UI
labels all profile/history as synthetic and hides the numeric APEX Position.
The normal application never infers DEMO from a client parameter.

## Synthetic preview

Run `python scripts/run_live_voice_preview.py --port 5001`, then open
`http://127.0.0.1:5001/live-voice-preview`. The executable lab uses isolated temporary
SQLite, a synthetic principal, fixed fixture chat and silent WAV; never real auth
or model calls. Its CSP blocks analytics/provider egress. It is NOT a production
auth path and is not registered by importing the normal app.

## Tests and next gate

Run `pytest tests/test_live_voice.py tests/test_voice_selection.py` and
`playwright test -c tests/playwright/live-voice.config.js live-voice.spec.js`.
These prove MOCK behavior, not live access. Before any live review: validate model
access, provider event schema, BG/EN recognition, echo/barge-in, audio quality,
timeouts, latency/usage, and authenticated safety/constraint parity using synthetic
inputs. No production activation is authorized by this prototype.

Official contracts consulted: [server-owned Realtime WebSockets](https://developers.openai.com/api/docs/guides/voice-websockets?voice-api=realtime)
and [disabling automatic Realtime responses](https://developers.openai.com/api/docs/guides/realtime-conversations).

## Local natural-speech optimization (not released)

The Coach response still completes validation before speech synthesis. MP3-capable
MediaSource browsers can request incremental audio on the same POST `/speak`.
The SDK's `with_streaming_response` uses one provider request and the same shared
pre-reservation. NDJSON audio frames end with an explicit successful-read marker;
missing markers, errors and interruptions never imply playback completion. There
is no retry or second synthesis request. Other browsers retain the original
buffered single-request path. Unknown provider outcomes retain their reservations.

Content-free diagnostics are available in `ApexLiveVoice.timing.snapshot()`:
the last 32 stage/duration pairs, held only in memory. Transcription is measured
from browser receipt of speech-stop to completed transcript; `coach_response`
includes server validation and persistence, not just model compute. TTS timings
are server-monotonic header/first-byte/complete intervals. `playback_start` is
POST start to the browser's `playing` event, not independently verified audibility.
Mock and muted silent-MP3 tests do not establish live speech quality or latency.
The existing TTS model, voices and pilot allocations are unchanged.

Speech streaming contract: [OpenAI Speech API](https://developers.openai.com/api/docs/guides/text-to-speech).
