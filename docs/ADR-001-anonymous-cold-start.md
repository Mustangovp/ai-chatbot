# ADR-001 — Anonymous cold-start: NOT_YET for every new user

**Status:** PROPOSED (decision recorded; **no code implemented**).
**Author:** Principal Product Architect.
**Decision date:** 2026-07-06.
**Scope:** Whether the Brain's behavior for a brand-new anonymous user is intended
architecture, and the GO/NO-GO for enabling `BRAIN_ENFORCE` globally.

---

## Context

Enabling `BRAIN_ENFORCE=1` globally makes the shadow `Decision` authoritative in
`/chat`. Validation showed that a **healthy anonymous user asking for a workout is
deferred (`NOT_YET` → no workout)**. This ADR determines whether that is intended.

Constraint on this investigation: `BRAIN_ENFORCE` could not be toggled in
production (no Railway access from the analysis environment). Because the cascade
is **pure and deterministic** and production `/chat` calls `cascade.decide`
identically for anonymous users, the enforced Decision was reproduced exactly with
the frozen Brain, and corroborated against the live `/chat` endpoint (enforce-off).

---

## Evidence

### E1 — Deterministic cascade trace (frozen Brain; = what prod computes)
Anonymous input (`profile={}`, `physiology=None`), exactly as prod `/chat` invokes it:

| Scenario | env.confidence | S4 confidence | halt | red flags | Verdict | Cause |
|---|---|---|---|---|---|---|
| Healthy adult → workout | **0.000** | 0.000 | False | — | **NOT_YET** | **S4 rule 2 (conf < 0.15)** |
| Healthy 73-yo → workout | **0.000** | 0.000 | False | — | **NOT_YET** | **S4 rule 2** |
| Chest pain | 0.000 | 0.000 | **True** | `exertional_chest` | NOT_YET | **S4 rule 1 (halt)** ✅ safety |
| Previous stroke (in message) | 0.000 | 0.000 | False | — | NOT_YET | **S4 rule 2** (history not captured — it's not in `profile.healthNotes`) |
| Sleep deprivation (in message) | 0.000 | 0.000 | False | — | NOT_YET | **S4 rule 2** (state not captured — no physiology) |

**Root cause (single, precise):** an empty profile yields **`env.confidence = 0.000`**
from S1; S4's uncertainty floor (`rule 2: confidence < 0.15 → NOT_YET`) then fires.
Every anonymous user defers on **ignorance**, before any need-vector or safety logic.
The safety path is intact and independent — chest pain still halts via **rule 1**.

### E2 — With data, the same users are permitted
Same healthy 25-yo and 73-yo, but as a logged-in user **with an athlete model**
(`recovery 0.9, fatigue 0.1`) → **`GO` → workout generated**. So the defer is caused
solely by *absence of data*, not by anything about the user.

### E3 — Live production `/chat` (anonymous, enforce currently OFF)
- Both probes returned `decision_event = null` → **`BRAIN_ENFORCE` is OFF in prod** (confirmed on the real endpoint).
- **Chest pain → a normal coaching reply with no medical routing.** This is today's
  **live safety gap**: without the Brain, an exertional-chest-pain message is treated
  as an ordinary workout request. (This is *why* enforcement matters — and why the
  answer is "fix the cold-start, then enforce," not "don't enforce.")

---

## The question, answered

**Does a healthy anonymous user always receive `NOT_YET`?** **Yes** — deterministically,
via S4 rule 2, for any empty/near-empty profile.

**Is this (a) intentional architecture, (b) product design flaw, or (c) implementation bug?**

- **Not (c) an implementation bug.** Every organ does exactly what it was designed to:
  S1 reports zero confidence when it has no data; S4 conservatively defers under low
  confidence. Deterministic and per-spec.
- **Partly (a) intentional.** "Bias conservative when you know nothing, never guess
  optimistically" is a deliberate, correct **safety** stance at the organ level.
- **Ultimately (b) a product design flaw** — in the **enforcement policy**, not the
  reasoning. The architecture *internally distinguishes* risk from ignorance (a
  cold-start Decision has **no halt, no red flags, no constraints** — provably zero
  risk signals), but the enforcement layer **collapses that distinction**, treating an
  *ignorance* `NOT_YET` identically to a *safety* `NOT_YET`. No one ever decided "new
  users are refused a workout"; it emerged from composing conservative organs with a
  hard, undifferentiated enforcement of `NOT_YET`.

**Principle violated:** *low confidence is only a reason to defer when there is
something risky to be uncertain about.* With **zero risk signals**, low confidence
should yield the **most conservative safe workout**, not a refusal — and then the
system learns (Event Ledger → Athlete Model) and sharpens on the next turn.

---

## Proposed smallest change (NOT implemented — for a future, separately-approved commit)

Introduce an explicit **cold-start** state, defined entirely from the existing
Decision with **no new reasoning**:

> **cold-start ⟺ `verdict == NOT_YET` AND `halt == False` AND `red_flags == []` AND
> `constraints` is empty.**

In that state — and only that state — render a **conservative beginner workout** in a
fixed minimal-safe envelope (low intensity ceiling, technique-first, supported,
short volume) instead of a deferral.

**Recommended locus — the enforcement policy layer (`brain/enforcement.py`), not the
cascade.** Rationale: it is the smallest touch-point that preserves every stated
invariant *literally*:
- **Safety guarantees preserved** — the rule is gated on *no halt ∧ no red flags ∧ no
  constraints*, so it can **never** override a safety `NOT_YET` or a red-flag halt.
  Any risk signal (chest pain, a constraint, a flag) still routes/defers unchanged.
- **S1–S5 philosophy preserved** — zero organ changes; the deliberation cascade is
  untouched.
- **Replay determinism preserved** — `cascade.decide` / inspector / replay are not
  modified; the Decision for a given input is byte-identical.
- **Event Ledger preserved** — the true Decision (`NOT_YET`) is still logged; the
  cold-start override is recorded as an explicit outcome marker on the decision event
  so the audit trail stays honest (Decision vs. action never silently diverge).
- **Delivers the goal** — a healthy anonymous first-timer receives a conservative
  beginner workout.

**Alternative (cleaner audit, larger blast radius) — a first-class S4 cold-start
verdict** so Decision == action. Rejected as the *first* step because it modifies a
frozen organ (S4) and pulls in S5 selection; hold it for a later milestone if the
override marker proves insufficient for telemetry.

**Known limitation (documented, acceptable):** anonymous sleep-deprivation / stated
history in free text are **not** detected (they require physiology / structured
profile). Under cold-start they receive a *conservative beginner* session — strictly
safer than today's legacy full workout, and upgraded to state-aware deferral once the
user has an Athlete Model. No new message-parsing capability is proposed (out of scope).

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Cold-start override masks a real safety `NOT_YET` | High if mis-scoped | Gate on *no halt ∧ no flags ∧ no constraints* — the override is impossible when any risk signal exists (this gate **is** the safety proof) |
| Decision (`NOT_YET`) vs action (generate) divergence confuses telemetry | Medium | Emit an explicit `cold_start` marker on the decision event / ledger |
| Undetected state (tired/ill) anonymous user gets a starter | Low | Envelope is minimal/beginner (low-risk for anyone healthy); still safer than legacy; state-aware path activates with data |
| Scope creep into a Brain redesign | Medium | Enforcement-layer rule only; no organ, cascade, replay, or ledger-schema change |

---

## Decision — GO / NO-GO for global `BRAIN_ENFORCE`

**NO-GO** for enabling `BRAIN_ENFORCE` globally **now**.

- Reasoning: global enforcement on the current Brain defers **every** anonymous / new /
  no-data user (`NOT_YET` → no workout), breaking the core acquisition funnel (the
  landing promise of an instant plan). It is **safe** (it never prescribes unsafely)
  but is **not the intended product behavior** and is commercially fatal at the top of
  funnel.
- **Condition to flip to GO:** (1) land the cold-start rule above (separate, approved
  commit + tests: healthy cold-start → conservative workout; chest pain / constraint /
  flag → still route/defer), (2) run the `BRAIN_SHADOW` soak and confirm the
  distribution (handbook §2.6), (3) then enable enforcement — ideally cohort-gated
  first per the rollout handbook.
- **Interim recommendation:** enable **`BRAIN_SHADOW=1` only** (invisible, logs
  decisions) so the cold-start prevalence and the fix's effect can be measured on real
  traffic before any user-visible enforcement.

---

## Consequences
- The Brain's safety architecture is validated as **correct** (chest pain halts; the
  organs behave as designed).
- The blocker to enforcement is a **narrow, well-scoped product-policy gap** (cold-start),
  not a redesign — closable in one small enforcement-layer change without touching S1–S5.
- Until that change ships and `BRAIN_SHADOW` validates it, `BRAIN_ENFORCE` stays **OFF**.
