# APEX Phase 1 Text Model Policy

This is an un-deployed migration candidate. Production activation requires the
controlled live evaluation gate; mocked SDK acceptance does not prove API access.

All text paths remain on Chat Completions. `llm_policy.py` is the shared request
configuration. Brain, Training Engine, and Nutrition validators retain authority.

| Role | Model | Reasoning | max_completion_tokens |
| --- | --- | --- | --- |
| FREE / CORE conversation, nutrition, training explanation | gpt-6-luna | none | 1500 |
| PRO conversation, nutrition, training explanation | gpt-6.1-sol | low | 8000 |
| FREE / CORE nutrition repair | gpt-6.1-sol | low | 5500 |
| PRO nutrition repair | gpt-6.1-sol | low | 8000 |
| First-contact extraction | gpt-6-luna | none | 1500 |
| Background learning extraction | gpt-6-luna | none | 300 |

Sol budgets preserve the previous 4000/1500 visible-output intent plus an initial
4000-token reasoning reserve. The API limit covers reasoning and visible output
together: it is not a separate or guaranteed visible-output allowance. Measure
reasoning use, truncation, and latency before approving these limits for rollout.
Luna has no reasoning reserve. Profile extraction now has an explicit 1500-token
bound; background extraction retains its 300-token intent. Extraction temperature
remains zero only with `reasoning_effort=none`; Sol has no sampling parameters.

Existing `json_object` requests and deterministic response validators remain
unchanged. Learning retains prompt-only JSON and its local keyword fallback.
Nutrition retains one repair attempt, source-backed fallback, and controlled
failure. Training explanation failure retains deterministic default prose.
Model streams remain buffered until complete and validated; interrupted output
is discarded. Learning remains detached and best-effort.

`openai==3.3.1` remains pinned. SDK compatibility tests use an in-memory HTTP
transport to verify serialized requests and completion/SSE parsing, not live
API acceptance or real model behavior. TTS and its environment overrides
are unchanged. No pricing, paid-plan availability, or feature flags are changed.

## Controlled Live Evaluation Gate

Use synthetic BG/EN cases only: profile extraction, conversation, workout,
persistent overhead-pressing restriction followed by harder workout, nutrition
generation/rejection/repair, safety evidence, terminal/interrupted streams,
and learning extraction. Require zero deterministic authority, constraint,
privacy, or persistence regressions. Record only model, elapsed time, token usage,
reasoning tokens, and bounded success/fallback outcome; never private content.

Compare measured request latency with the unchanged 75-second browser inactivity
watchdog and 180-second Gunicorn timeout. Sequential generation/repair and SDK
retries must fit the delivery envelope. Do not deploy if API credentials/access
are unavailable or the live gate has not passed.

Brain trace metadata and nutrition-plan provenance continue storing model names
as strings; preserve historical names on replay. Aggregate Brain analytics does
not provide per-model token/cost telemetry. No database migration is needed.
