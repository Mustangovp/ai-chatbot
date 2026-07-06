# APEX Brain — Architecture Addendum 02 · S2 Halt Contract & Input Scope

**Status: FROZEN** (2026‑07‑06). Addendum to the frozen canon (sits beside
Addendum 01). Creates **no** new philosophy, **no** new organs, **no** roadmap
restructure, and edits **no** frozen file. It resolves the two pre‑build S2 findings
from the S2 architecture audit, after an adversarial review of those findings, and
carries the approved **temporal‑persistence clarification** (§A2‑1.1):

- **B‑1 (EMERGENCY halt) — false positive.** The frozen Brain Architecture already
  guarantees the halt structurally (§1: generation is *"impossible to reach without
  the earlier stations' consent"*; §2: a red flag makes S2 *"halt"* and *"stop the
  cascade here"*). No new guarantee is created. A **clarifying affirmation** (§A2‑0)
  reconciles the Implementation Roadmap's S4 wording so an implementer cannot build
  the discretionary variant.
- **B‑2 (cross‑turn hiding) — confirmed gap.** The architecture scopes S2's symptom
  scan to *"the message itself,"* and no frozen mechanism carries a free‑text symptom
  across turns. §A2‑1 amends S2's **input scope** — the minimum necessary.

**Amends (does not edit):** Brain Architecture §1 (control‑flow) & §2 (S2); the
Implementation Roadmap §4 (S2 inputs, S4 rule). Milestones, flags, sequence, organs,
and libraries are unchanged.

---

## A2‑0 · Affirmation — the S2 halt is structural (B‑1, no new guarantee)

The frozen architecture already binds this; the affirmation only removes a
documentation-consistency hazard between the Architecture and the Roadmap.

- **"Clears," defined for S2.** S2 *clears* iff it raised **no EMERGENCY red flag**
  and — for a request that could result in a prescription — **no URGENT red flag**.
- **On non‑clear, S2 halts (per §1/§2).** Control passes directly to the **G3**
  route/handoff intervention (and S5's non‑training branch selects the safe
  alternative). S3 and S4 are **not** consulted for the train/don't‑train decision;
  **S4's GO/MODIFY branches are unreachable for a halted request.** This is a
  restatement of §1 (*"control only flows downward when the current station clears"*;
  *"impossible to reach [generation] without the earlier stations' consent"*), not an
  addition to it.
- **Roadmap reconciliation.** The Roadmap §4 rule *"any EMERGENCY/URGENT red flag →
  NOT_YET/NO_TRAIN"* is retained only as **defense‑in‑depth** should S4 ever be
  reached in error; it is **not** the enforcement point. The enforcement point is the
  S2 halt.
- **Invariant (extends Addendum 01's single door).** No execution path may reach S6
  generation while an S2 halt is set. The Addendum‑01 single‑emission‑path CI check is
  extended to assert this.

*This clause changes nothing an implementer of the Brain Architecture would not
already build; it forecloses the misreading the Roadmap's S4 phrasing invites.*

---

## A2‑1 · Amendment — S2 input scope (B‑1's gap; the substantive change)

**Frozen text amended:** Brain Architecture §2 (S2) *"Reads: … the message itself"*
and Roadmap §4 (S2) *"Inputs: `ctx.message` (symptom scan)."*

**Amended to:** S2's red‑flag scan reads, in addition to the current message:

1. the **recent conversation window** — the account‑owned transcript already stored
   in `conversations` and already loaded server‑side for context (the same bounded
   window used for the chat), so a symptom disclosed in a prior turn is in scope;
2. **profile‑derived condition flags** (S1's detected conditions / `healthNotes`); and
3. **Athlete Model state** (already specified).

**Semantics.**
- A red flag detected **anywhere in the window** halts a later prescription request
  exactly as if it appeared in the current message (subject to §A2‑0's halt contract).
- The window is **bounded and deterministic** (reuse the already‑loaded window; no new
  storage, no unbounded scan) — replay/regression stays deterministic.
- **Symptom persistence.** A red flag detected in a prior turn is treated by the
  existing **D2 Hypothesis Manager** as *presumed active until countervailing
  evidence*, per the temporal‑persistence rule in §A2‑1.1. This reuses the frozen
  uncertainty machinery — no new organ, no new philosophy.

### A2‑1.1 · Temporal‑persistence rule (approved clarification)

Disambiguates the overlap between the bounded scan window and the D2
held‑hypothesis, **by urgency tier** — using only existing organs (D2, the Event
Ledger `brain_decisions`/`coach_memory`, and the frozen provenance model). It
governs **M4 enforcement**; shadow (M2/M3) exposes no user.

- **EMERGENCY / URGENT (halting) flags** are governed by the **D2 held‑hypothesis,
  persisted in the existing Event Ledger** — **not** re‑derived solely from the
  bounded scan window. Age, conversational noise, and silence therefore **cannot
  evict** a critical unresolved symptom (no premature forgetting). Such a flag
  remains **presumed active (halting)** until **explicit user‑reported medical
  clearance**:
  - **Clearance** = the user's own reported statement that the symptom has been
    medically cleared, accepted at **`reported` provenance** — the halt lifts, but
    the coach frames it as *provisional* ("assuming you've been cleared"), never as
    a measured fact (frozen provenance model + NOT_YET re‑entry, verification V‑030).
    The architecture is **independent of exact wording**: it recognises the *concept*
    of user‑reported medical clearance, not any fixed phrase.
  - **NOT clearance:** a bare denial, minimisation, ambiguity, silence, age, or
    noise. Per §10 (distrust optimistic self‑report) and §3 (coach to the worse
    case), these leave the flag **active**.
  - A re‑mention **reinforces**, never escalates beyond tier (deduped by `class_key`).
- **ROUTINE (soft, non‑halting) flags** gate nothing, so they follow the **bounded
  window** and may age out — causing neither premature forgetting (they halt nothing)
  nor a permanent alarm (they never alarm).
- **Bounds (proven).** Every halting flag has a defined clearance path (explicit
  user‑reported medical clearance) → **no permanent false alarm**. Halting flags are
  ledger‑persisted and denial/age/noise cannot clear them → **no premature
  forgetting.** *(For anonymous users the ledger identity is device/session‑scoped, so
  critical‑flag persistence holds within the session/window — a documented limit, not
  a hole, since anonymous state is ephemeral by design.)*

**Why this is minimal.** It changes only S2's **read set** (which data the existing
S2 organ scans). It uses data already persisted and already loaded. It introduces no
new table, endpoint, organ, flag, or milestone.

---

## What is explicitly NOT changed

- **No new organs.** S1, S2, S3, S4, S5, S6, G1–G3, D2 are unchanged as organs.
- **No new philosophy.** §A2‑0 restates §1; §A2‑1 widens an input using existing data
  and the existing D2 machinery.
- **No roadmap restructure.** Milestones (M0–M6), the two flags, shadow‑first sequence,
  and the corpus‑as‑gate discipline are identical. M2 still builds S2 in shadow.
- **No library change in kind.** The red‑flag and constraint libraries are unaffected
  by this addendum (their bilingual/recall refinements — audit R5–R7 — remain separate
  open items, out of scope here).
- **The Constitution Gate (G1)** is untouched; routes and constraints only, never
  labels.

---

## Validation tests (regression, added when S2 is built)

- **B‑2 · cross‑turn halt.** A red flag disclosed in turn *N* must halt a workout
  request in turn *N+k* within the window (the case the single‑turn 140‑persona
  verification is structurally blind to). Include a symptom‑then‑clearance case
  (D2: re‑enable training only on reported clearance).
- **B‑1 · unreachable‑generation invariant.** Assert no execution path reaches S6
  generation when an S2 halt is set (single‑door CI check extended to S2 halts).
- **Determinism preserved.** The bounded window keeps the inspector/replay traces
  deterministic (same evidence + window + library + code → same canonical trace).

---

## Scope note

This addendum addresses **only** B‑1 and B‑2, as directed. The remaining S2 audit
refinements — R3 (S1/S2 precedence), R4 (uncertainty→question), R5 (deterministic
detection floor), R6 (BG/EN parity), R7 (structural non‑diagnosis) — are **not**
resolved here and remain open for a separate decision before S2 enforcement (M4).

*End of Architecture Addendum 02.*
