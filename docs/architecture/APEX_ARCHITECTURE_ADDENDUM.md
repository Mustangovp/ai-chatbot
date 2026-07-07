# APEX Brain — Architecture Addendum 01 · Structural Closure of B-1 & B-2

**Status:** Addendum to the frozen canon. It creates **no** new philosophy, **no** new
organs, and **no** new documents beyond itself. It amends only the *composition* of
existing organs so that two Final-Review blockers become **structurally impossible** —
i.e. no reachable code path can produce the unsafe outcome, not merely an unlikely one.
It preserves the Implementation Roadmap unchanged in milestones, flags, and sequence; it
only tightens the **definition** of two milestone boundaries (M3 shadow, M4 enforce).

**Amends (does not replace):** Brain Architecture §2 (S6) & §8 (info-flow); Implementation
Roadmap §0.3 (fail-open principle), §4 (S6), §5 (M3/M4).

**Blockers closed:**
- **B-1** — S6 constraints were advisory prompt text; "unrepresentable" was aspirational.
- **B-2** — the failure path failed *open* into unconstrained generation, re-arming the
  origin failure on any cascade error.

---

## 1. The two structural invariants (the whole addendum in two sentences)

> **I-1 · The Single Emission Path.** Prescriptive movement content reaches a user **only**
> as the output of one chokepoint that has verified it, movement-by-movement, against S1's
> Constraint Set. There is no second door.
>
> **I-2 · Fail-Safe Prescription.** No exception, timeout, or verification failure can emit
> a workout. Every non-clean path yields *conversation* (a Curiosity ask), never a program.

Both blockers collapse into one principle: **there is exactly one door to prescriptive
output, it is a deterministic gate, and every other path — including every error — produces
an ask or a routed intervention, never a plan.** B-1 is the door being real; B-2 is there
being no way around it.

Neither invariant adds an organ. I-1 gives the **existing F3 Conformance** organ a machine-
checkable spec (S1's Constraint Set) and a shared vocabulary (a Movement Taxonomy = curated
data, like the Constraint Library). I-2 applies the **existing asymmetric-loss law** to the
error path and reuses the **existing D3 Curiosity** ask as the degraded output.

---

## 2. Architectural change

### 2.1 Closing B-1 — deterministic movement conformance (Invariant I-1)

Today S1's Constraint Set is injected into the S6 prompt as prose and hoped-for. The change
makes the Constraint Set a **checklist a deterministic gate enforces on the generated plan
before any of it is shown**:

1. **S6 generates a *structured, tagged* plan, not free prose first.** The candidate workout
   is produced as a list of exercises, each resolvable — via a curated **Movement Taxonomy**
   (data) — to movement attributes in the *same vocabulary* S1's constraints use
   (`valsalva`, `high_impact`, `loaded_spinal_flexion`, `heavy_isometric`,
   `unsupported_balance`, `maximal_exertion`, …).
2. **F3 Conformance runs a set-membership check**, deterministically: for every candidate
   exercise, resolve its tags; if any tag is forbidden at `absolute` tier by the Constraint
   Set → **violation**. `relative`-tier tags are checked against the Capacity Envelope.
   Unknown exercise / unresolved tag → treated as *potentially violating* (fail-safe;
   uncertainty→safety), which also forces taxonomy completeness over time.
3. **On violation:** bounded regeneration with the violated constraint escalated; if still
   violating after *k* attempts → the plan is **discarded** and control passes to I-2's safe
   fallback (a non-training intervention or an ask). A violating plan is never emitted.
4. **On pass:** render to prose → **G1 Constitution Gate** (unchanged: strips any clinical
   label) → stream to the user.

The consequence: a contraindicated movement (push-ups/planks for P-035) is **unrepresentable
in the emitted output**, because the only path to emission runs through a gate whose reject
condition is exactly "this movement is forbidden for this athlete." The guarantee is
**deterministic** (not LLM-dependent) and **language-independent** (F3 checks movement tags,
not Bulgarian/English prose — a genuine safety property on the output side).

**Streaming reconciliation:** only the *training-plan* branch becomes generate-verify-render
(a brief validate step before the plan streams). Refusals and non-training interventions and
ordinary conversation still stream token-by-token as today, because they contain no
prescriptive movement plan to gate. Most red-flag cases never generate a plan at all, so they
are *faster*, not slower.

### 2.2 Closing B-2 — the failure path fails safe, not open (Invariant I-2)

The roadmap's "fail-open to legacy generation" is split along the asymmetric-loss law:

- **Fail-open for conversation** (availability preserved): the chat always answers; the user
  never sees a 500.
- **Fail-closed for prescription** (harm prevented): on *any* cascade exception, timeout, or
  unresolved F3 violation, the system **must not** call the unconstrained generator. It routes
  to **Degraded Safe Mode** — a single conservative D3 Curiosity ask ("Before I program
  anything, I want the full picture — what's your goal and how are you feeling today?"),
  rendered in APEX's voice, streamed, G1-filtered.

Structurally: the legacy `create()` generation call is **removed as an error-path fallback**.
The only remaining invocation of the generator for prescriptive content is inside the S6 →
F3 → G1 pipeline (I-1). The `except` branch can reach Degraded Safe Mode, and nothing else.
Because the error path *cannot construct a workout*, B-2 is impossible: a crash in S0–S6, or
a validator timeout, yields an ask — the safest possible recoverable output — not a program.

**Why this is not a redesign:** Degraded Safe Mode is the frozen "null / ask" action (D3
Curiosity + E5 Paternalism) that already exists; the asymmetric-loss law already mandates
"prefer the mistake you can take back." The addendum only forbids the *one* fallback edge
that violated that law.

---

## 3. Affected files

*(All within the roadmap's already-planned `brain/` package and the single `/chat` host.)*

| File | Change |
|---|---|
| `brain/conformance.py` *(realizes existing organ F3)* | new home for the F3 movement-conformance gate: `conform(plan, constraint_set, envelope) -> ConformanceResult`. Pure, deterministic. |
| `brain/libraries/movement_taxonomy.py` *(curated data)* | exercise → movement-attribute tags, in S1's constraint vocabulary. Human/clinically reviewed, versioned, never LLM-authored (same governance as the Constraint Library). |
| `brain/s6_generate.py` | S6 becomes generate-verify-render: emit a *structured tagged plan*, run F3, bounded-regen on violation, render prose only after pass. |
| `brain/cascade.py` | defines the **single emission chokepoint** `emit(decision, ctx) -> stream`; encodes I-1 (workout only via S6→F3→G1) and the I-2 routing of errors/violations to Degraded Safe Mode. |
| `brain/s5_selector.py` | gains `degraded_safe_ask()` (the D3 Curiosity fallback intervention). |
| `app.py` `/chat` [app.py:1496](app.py:1496) `generate()` | the SSE generator routes training emission through the chokepoint; the `except` branch calls Degraded Safe Mode, **not** the legacy generator. The legacy `client.chat.completions.create` at [app.py:1499](app.py:1499) is reachable only inside the S6 pipeline. |
| `brain/ledger.py` / `brain_decisions.trace` (JSON) | record conformance pass/violation + any degraded-mode trigger. **No DB schema change** — `trace` is already JSON. |
| `brain/config.py` | `F3_ENFORCE` and `DEGRADED_SAFE_MODE` are *bound to* `BRAIN_ENFORCE` — they cannot be independently disabled (see Rollback). |

No new tables, no new columns, no migration beyond what the roadmap already schedules.

---

## 4. Affected organs (all existing; specs tightened, none added)

| Organ | Change |
|---|---|
| **F3 Conformance** (F Expression system) | given a machine-checkable spec — S1's Constraint Set + the Movement Taxonomy — becoming a *deterministic movement gate*, not only a voice/format check. |
| **G1 Constitution Gate** | unchanged role; now strictly *downstream* of F3 (labels filtered after movements are verified). |
| **S1 Somatic Constraint Model** | its Constraint Set is now *consumed* by F3 as a checklist, not merely narrated into a prompt. Output contract unchanged. |
| **S6 Generation** | becomes generate-verify-render; its emission is conditional on F3 pass. |
| **D3 Curiosity + E5 Paternalism** | supply Degraded Safe Mode (the fail-safe ask). |
| **Asymmetric-loss law** (Judgment) | now governs the *failure* path, not only the prescription path. |

---

## 5. Sequence of execution

### 5.1 Runtime order inside one `/chat` (the single-door proof)

```
load context ──► cascade.decide()  ── exception? ─────────────► DEGRADED SAFE MODE (ask) ─► G1 ─► stream   [no plan]
                        │ (Decision)
                        ▼
        verdict ∈ {NOT_YET, NO_TRAIN, emergency}? ──► render route / intervention ─► G1 ─► stream         [no plan]
                        │ generate_training == True
                        ▼
        S6 generate structured tagged plan ──► F3 conform(plan, constraints, envelope)
                        │                              │ violation
                        │ pass                         ▼
                        ▼                    bounded regen ×k ── still violating ──► DEGRADED SAFE MODE / non-training S5   [no plan]
        render prose ─► G1 ─► stream   ◄── the ONLY path that emits a plan
```

Every branch except the bottom-left "pass" produces conversation or a route. The one branch
that produces a plan has already passed the deterministic gate. That is I-1 and I-2 as a
single control-flow invariant.

### 5.2 Fit into the roadmap (milestones preserved; two boundaries tightened)

- **M1–M3 (unchanged milestones):** build `conformance.py` + `movement_taxonomy.py` alongside
  S1/S6. During **M3 shadow**, F3 runs on shadow-generated plans and **logs** conformance
  violations — proving taxonomy coverage and the gate's correctness *before it gates
  anything*. (Tightening: M3's exit gate now also requires "zero unresolved-tag rate above
  threshold" in shadow.)
- **M4 (unchanged milestone, tightened definition):** "enforce" is *redefined* to mean
  **I-1 + I-2 together** — flipping `BRAIN_ENFORCE` routes all prescriptive emission through
  the single door and reroutes the error path to Degraded Safe Mode. There is no intermediate
  "enforce refusals but skip conformance" state; that state is architecturally disallowed.
- **M5, M6:** unchanged.

No milestone is added, removed, reordered, or renamed. The flags are the same. The shadow-
first discipline is the same. Only *what M3 must prove* and *what M4's switch means* are made
stricter.

---

## 6. Rollback strategy

- **Coarse, all-or-nothing, to a known baseline.** `BRAIN_ENFORCE=off` reverts the entire
  enforced path to the pre-Brain legacy behaviour (the documented prior production baseline).
  This is a deliberate, known state — not a half-enforced one.
- **No unsafe partial state exists by construction.** `F3_ENFORCE` and `DEGRADED_SAFE_MODE`
  are *bound to* `BRAIN_ENFORCE`; they cannot be toggled independently. There is deliberately
  **no** "enforce but skip validation" and **no** "enforce but fail-open" configuration —
  those are exactly the blocker states, so they are made unrepresentable in config too.
- **Shadow rollback (M1–M3):** flags off; `conformance.py` and the taxonomy are inert data
  and pure functions with zero user impact.
- **Tuning without rollback:** if Degraded Safe Mode fires too often (over-asking), the lever
  is the F3 *unknown-tag* strictness and the regen count *k* in `brain/config.py` — tuned,
  alarmed, and reviewed like the CONCERN-ledger contract. The *invariant never loosens*: a
  confirmed `absolute` violation is always non-emittable.
- **Taxonomy is hot-fixable data:** a missing exercise tag is corrected in
  `movement_taxonomy.py` (reviewed data change) without a code deploy or a rollback.

---

## 7. Validation tests

The two blockers become two permanent regression suites; both are language-independent on the
output side because they check movement tags, not prose.

1. **F3 conformance unit tests (deterministic, no LLM).** For each corpus persona carrying an
   `absolute` constraint, feed F3 an intentionally-violating plan (push-ups/planks for P-035;
   loaded sit-ups for P-040; Valsalva grinders for P-085) → **must reject**. Feed a compliant
   plan → **must pass**. Feed an unknown exercise → **must reject (fail-safe)**.
2. **B-1 adversarial-generation regression (the origin failure, as a test).** Drive S6 with
   jailbreak/edge prompts attempting to elicit a contraindicated movement for P-035; assert
   `emit()` **never** streams it (regenerates or falls to safe mode). This is the origin
   failure encoded as an automated, permanently-run test.
3. **B-2 fault-injection regression.** Force a cascade exception (mock S2 to raise) and force
   an F3 timeout, on P-035's input; assert the response is a conversational **safe ask**,
   contains **no exercises**, and returns **200** (availability preserved). Repeat for a GO
   persona (P-067): assert the same — error still yields an ask, never a workout.
4. **Single-door static/architecture test (maintainability guard).** A CI check asserting the
   generator is invoked for prescriptive content from **exactly one** call site (the S6→F3
   pipeline); any future code that re-introduces a bypass fails the build. This keeps the
   invariant true over the codebase's life, not just at launch.
5. **Movement Taxonomy coverage test.** The set of exercises the generator realistically emits
   must resolve to tags; the unresolved-tag rate is a tracked metric with a shadow-phase gate
   (M3 exit) and a production alarm.
6. **Distribution guard.** Assert Degraded Safe Mode and F3-reject rates stay within expected
   bounds (a spike = a taxonomy gap or an over-strict gate, not a silent failure).

All six run in CI on the enforced path and are required-green to widen enforcement past
canary — folded into the roadmap's existing corpus acceptance gate (§8), adding no new gate.

---

## 8. Result

- **B-1 is structurally closed:** the only path to a workout is a deterministic gate whose
  reject condition is "forbidden movement for this athlete." Contraindicated output is not
  *discouraged* — it is *unemittable*, independent of the LLM and of language.
- **B-2 is structurally closed:** no error path can construct a workout; every failure yields
  a Curiosity ask. Availability is preserved for conversation; prescription fails safe.
- **The roadmap is preserved:** same milestones, same flags, same shadow-first sequence — M3
  must now *prove* the gate, and M4's switch *means* the two invariants; nothing else moves.
- **No new organ, no new philosophy:** F3 Conformance, G1, S1, S6, D3, E5, and the asymmetric-
  loss law — all existing — are recomposed so the two doors the review found are welded shut.

> The Final Review asked for the guarantee to become real rather than aspirational. This
> addendum makes it real by making the failure *unrepresentable in the control flow*: one
> gated door in, and every other road — including the road through a crash — leads to a
> question, never to a program.

*End of Architecture Addendum 01.*
