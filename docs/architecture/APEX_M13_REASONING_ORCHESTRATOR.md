# APEX M13 — The Reasoning Orchestrator

**Type:** Architecture only. No runtime, no Brain change, no Human State change, no Coaching
implementation, no deployment. This document designs the **cognitive conductor** — the layer that
decides *how APEX thinks* by coordinating the organs that already exist. It contains **no knowledge, no
safety, no coaching**; it sequences, prioritizes, resolves conflicts, and guarantees explainability.

> **The one rule.** The Orchestrator is a **control plane, not a data plane.** It never produces a
> verdict, a workout, a diagnosis, or a coaching line. It calls the organs that do, in the right order,
> under the right priority, and refuses to let any lower organ expand what a higher organ permitted.

---

## 0. Where it sits in the canon

```
                       ┌─────────────────────────────────────────────┐
                       │        M13 REASONING ORCHESTRATOR            │  ← this doc (conductor)
                       │  (sequence · priority · conflict · trace)    │
                       └───────────────┬─────────────────────────────┘
   consults, in order, organs it does NOT own:
        │            │             │            │            │            │
   ┌────▼───┐  ┌─────▼────┐  ┌─────▼────┐  ┌────▼─────┐ ┌────▼─────┐ ┌────▼──────┐
   │ BRAIN  │  │  HUMAN   │  │TRAJECTORY│  │ GENOME   │ │CONSTITU- │ │ ADAPTIVE  │
   │ (M3/M4 │  │  STATE   │  │ (BUILD-4)│  │(SP-002,  │ │ TION (M9,│ │  COACH    │
   │ FROZEN)│  │(BUILD-1/2│  │          │  │ validated│ │ candidate│ │(BUILD-3,  │
   │        │  │ read)    │  │ read)    │  │ SP-002.1)│ │ only)    │ │ soften)   │
   └────────┘  └──────────┘  └──────────┘  └──────────┘ └──────────┘ └───────────┘
```

The Brain remains **frozen and supreme**. The Orchestrator's authority is *procedural* (ordering and
constraint propagation), never *substantive* (it cannot decide what the Brain decides).

**Design inputs carried forward from SPRINT-002.1 (validated findings):**
- **Safety is a supreme interrupt above every domain** (the safety-interrupt gap). → §3 priority graph,
  §2 stage S2, §5 timeline.
- **Gate on response *trend*, not raw inputs** (input-vs-response gating). → §6 attention, §2 stage 6.
- **Bias every referral threshold toward over-referral.** → §7 failure recovery (unknown condition).
- **Route problems to the right domain (intake triage); models are boundary-blind.** → §2 stage 1, §7.

---

## 1. Architecture — what the Orchestrator is and is not

| It IS | It is NOT |
|---|---|
| a sequencer of reasoning stages | a source of knowledge |
| a priority enforcer (harm gradient) | a safety authority (that is the Brain) |
| a conflict resolver (deterministic) | a coach (that is the Adaptive Coach) |
| an attention allocator | a data store (it reads snapshots) |
| an explainability recorder | a place where the Brain can be overridden |
| a failure-recovery controller | a runtime component (this is design) |

The Orchestrator manipulates **three things only**: (a) the **order** organs are consulted, (b) the
**envelope** — a monotonically *shrinking* set of permissions passed down the pipeline, and (c) the
**trace** — the record of why the final answer is what it is.

**The Envelope invariant (central mechanism).** Each stage receives an envelope and may only
**tighten** it (remove permissions, add constraints) — never loosen it. Safety/medical produce the
tightest floor; every later stage operates strictly inside it. This single rule makes "lower organs
cannot expand higher permissions" structural, not merely intended.

---

## 2. The cognitive pipeline (every stage fully specified)

Attributes per stage: **Purpose · Inputs · Outputs · Priority · Failure Mode · Interrupt? · Defer? ·
Override?** ("Interrupt" = may halt the pipeline into a terminal response. "Defer" = may hand off /
ask for more / route to another domain. "Override" = may change an earlier stage's output.)

### Stage 0 · Ingress / Normalization
- **Purpose:** normalize the raw message (language, encoding, attachments) into a clean turn object.
- **Inputs:** raw user message, session id, locale. **Outputs:** normalized turn.
- **Priority:** infrastructural. **Failure Mode:** malformed input → pass through as opaque text.
- **Interrupt?** no · **Defer?** no · **Override?** no.

### Stage 1 · Intent Recognition + Domain Triage
- **Purpose:** identify what the user wants *and which domain owns it* (the SPRINT-002.1 anti-
  boundary-blindness triage): is this a safety/medical matter, a training question, nutrition, behavior,
  psychology, communication, or mixed?
- **Inputs:** normalized turn, short conversation context. **Outputs:** intent label(s), domain routing
  hints, extracted candidate signals (not yet trusted).
- **Priority:** high (mis-routing propagates). **Failure Mode:** ambiguous intent → mark low-confidence,
  widen downstream attention, prefer a clarifying question.
- **Interrupt?** no · **Defer?** **yes** (ask to disambiguate if intent is decision-critical) ·
  **Override?** no.
- *Note:* intent recognition **classifies**, it does not decide. It may *suggest* a domain; only the
  Brain and the priority graph dispose.

### Stage 2 · Safety Pre-Screen  ⟵ supreme interrupt
- **Purpose:** consult the Brain's safety-front (M4) and a red-flag screen **before any other reasoning**,
  so a medical/safety signal can halt everything. This is where SPRINT-002.1's finding is enforced
  procedurally: no domain (nutrition, psychology, communication) may reach its own decision before safety.
- **Inputs:** normalized turn, intent, candidate signals. **Outputs:** `{clear | red_flag → route_out |
  halt}` and the **safety floor** of the envelope.
- **Priority:** **supreme.** **Failure Mode:** uncertainty → **treat as potential red flag** (over-
  referral bias) and take the conservative branch.
- **Interrupt?** **YES** (halts to a refer-out / conservative terminal response) · **Defer?** yes (route
  to medical) · **Override?** **YES** — the only stage that can override everything below it, because it
  *is* the Brain's safety authority, surfaced early.

### Stage 3 · Brain Decision (frozen cascade S1–S5)
- **Purpose:** obtain the authoritative Decision (verdict, constraints, capacity envelope, red flags,
  intervention) from the frozen cascade. The Orchestrator **calls**, it does not compute.
- **Inputs:** profile/evidence assembled from the turn (+ athlete model if present). **Outputs:** the
  `Decision` object. **Priority:** authoritative (below only the safety-front, which is itself part of the Brain).
- **Failure Mode:** Brain error/timeout → **fail safe** to the most conservative Decision (no generation,
  no load) — never fail open. **Interrupt?** no (it produces the verdict, doesn't halt) · **Defer?** no ·
  **Override?** no (nothing downstream may override it).

### Stage 4 · Enforcement Directive (frozen M4 render)
- **Purpose:** turn the Decision into the operational envelope — *may we generate a workout? is there a
  halt? what constraints/red-flag routing apply?* (ADR-001 cold-start lives here.)
- **Inputs:** Decision. **Outputs:** directive `{should_generate_workout, halt, constraints, addenda}` =
  the **hard envelope** every later stage must stay inside.
- **Priority:** authoritative. **Failure Mode:** render error → conservative directive (withhold).
- **Interrupt?** yes (a halt terminates into a safe message) · **Defer?** no · **Override?** no.

### Stage 5 · Human State Snapshot (read-only)
- **Purpose:** read the fresh, confidence-weighted Human State view (never write). Supplies *current*
  person context (sleep, stress, pain, motivation, constraints, preferences).
- **Inputs:** subject id, now. **Outputs:** fresh state map with per-variable confidence + freshness.
- **Priority:** below safety/medical/contraindication, above trajectory (§3). **Failure Mode:** missing/
  stale → proceed on Brain + population priors; do **not** fabricate (see §7).
- **Interrupt?** no · **Defer?** yes (may request a datum if decision-critical) · **Override?** **no** —
  state may **shape within** the envelope, never expand it (a rested reading cannot unlock a withheld workout).

### Stage 6 · Trajectory Snapshot (read-only)
- **Purpose:** read the direction of travel (recovery/adherence/confidence trend, volatility, risk) over
  existing history. **Enforces the SPRINT-002.1 fix:** gate on *response trend*, not a single raw input.
- **Inputs:** subject history (≥ min points). **Outputs:** trajectory + risk level, or `insufficient`.
- **Priority:** below Human State, above Goal. **Failure Mode:** < min points → return `insufficient`,
  fall back to the snapshot; never assert a trend from noise.
- **Interrupt?** no · **Defer?** no · **Override?** no (advisory to coaching only).

### Stage 7 · Relevant Genome Genes (select)
- **Purpose:** select the **called genes** (SPRINT-002 / validated SPRINT-002.1) whose *expression
  conditions* the situation fires (e.g., DG-U-06 respect-the-ceiling, DG-U-07 adherence, DG-U-10 safety).
- **Inputs:** intent, state, trajectory, envelope. **Outputs:** active gene set with their boundaries +
  alleles (context-selected). **Priority:** advisory constraints — may only **tighten** the envelope.
- **Failure Mode:** no gene fires → proceed with base reasoning (genes are guidance, not gates).
- **Interrupt?** no (except a **safety-flagged** gene may *raise* a conservative flag, never lower one) ·
  **Defer?** no · **Override?** no.
- *Rule:* a gene may **support** a safety/medical constraint (tighten) but may **never weaken** one
  (`safety_flag` genes are one-directional) — the genetic form of the supremacy rule.

### Stage 8 · Constitution Constraints (apply)
- **Purpose:** apply **ratified** APX principles as constraints (context-map + alleles for conflicts).
- **Inputs:** active genes, envelope, context. **Outputs:** constraint set narrowing the envelope.
- **Priority:** advisory-tightening. **Failure Mode / current status:** the Constitution is **candidate,
  not ratified** (SPRINT-002.1) → M13 treats principles as **advisory-only**; they may bias, not bind,
  until human ratification. Safety principles (`APX-SAF-*`) may only *strengthen* safety.
- **Interrupt?** no · **Defer?** no · **Override?** no.

### Stage 9 · Coaching Strategy (Adaptive Coach, soften-only)
- **Purpose:** decide *how* to deliver within the envelope — tone, volume/intensity shaping *downward*,
  recovery/nutrition/motivation emphasis, education — citing variable · reason · rule · principle.
- **Inputs:** envelope (post gene/constitution), state, trajectory, intent. **Outputs:** coaching
  adaptations + style, each explainable. **Priority:** low (delivery, not decision).
- **Failure Mode:** coach error → omit adaptations, deliver the Brain's directive plainly (fail to plain,
  never to unsafe). **Interrupt?** no · **Defer?** no · **Override?** **no** — the coach *only softens*:
  it never adds a withheld workout, raises load, or removes a constraint.

### Stage 10 · Response Blueprint (assemble)
- **Purpose:** compose the answer plan: content permitted by the envelope + coaching shaping + required
  safety addenda + citations. A structured intermediate, not prose.
- **Inputs:** envelope, coaching strategy, directive addenda. **Outputs:** blueprint (sections, tone,
  constraints, citations, trace-refs). **Priority:** assembly. **Failure Mode:** conflict in blueprint →
  drop the lower-priority element (§3/§4), keep safety addenda.
- **Interrupt?** no · **Defer?** no · **Override?** no.

### Stage 11 · Renderer
- **Purpose:** turn the blueprint into the final localized message (BG/EN). Wording only.
- **Inputs:** blueprint, locale. **Outputs:** final text. **Priority:** presentation. **Failure Mode:**
  render error → deliver the blueprint's safe core text. **Interrupt?** no · **Defer?** no · **Override?** no.

### Stage 12 · Explainability Ledger (record)
- **Purpose:** write the trace (see §8) so every answer is reconstructable: Brain verdict → genes → state
  → constitution → coach strategy. **Inputs:** all stage outputs. **Outputs:** one trace record per turn.
- **Priority:** mandatory (a turn without a trace is a defect). **Failure Mode:** trace write fails →
  the *answer still ships*, but the turn is flagged non-explainable for review. **Interrupt/Defer/Override?** no.

**Summary of who may do what:**

| Capability | Stages that hold it |
|---|---|
| **Interrupt** (halt pipeline) | 2 Safety Pre-Screen, 4 Enforcement (halt) |
| **Defer** (ask / route) | 1 Intent+Triage, 2 Safety, 5 Human State |
| **Override** (change earlier output) | **only** 2 Safety Pre-Screen (it is the Brain's safety authority) |
| **Soften-only** | 5 State, 6 Trajectory, 7 Genes, 8 Constitution, 9 Coach |

---

## 3. Reasoning Priority Graph

```
 SAFETY  ▶  MEDICAL  ▶  CONTRAINDICATIONS  ▶  HUMAN STATE  ▶  TRAJECTORY  ▶  GOAL  ▶  BEHAVIOR  ▶  COMMUNICATION
 (harm now)  (condition)   (known interaction)   (today's state)   (direction)   (want)   (habit)     (delivery)
   └────────────── HARD FLOOR (Brain / M4) ──────────────┘ └──────── SHAPE WITHIN THE FLOOR (soften-only) ───────┘
```

**Why this exact order — the harm-and-reversibility gradient.** Each level is a *constraint* on every
level to its right, and is ranked by how irreversible the harm is if it is wrong:

1. **Safety > Medical.** Acute physical harm (injury-provoking load, an emergency symptom) is more
   immediate and irreversible than a manageable diagnosable condition. A safety halt pre-empts everything.
2. **Medical > Contraindications.** A live condition (e.g., diabetes, pregnancy) frames what is even
   admissible; specific interactions are evaluated *inside* that frame.
3. **Contraindications > Human State.** A known interaction (a movement that a diagnosis forbids) binds
   regardless of how the person feels today; a good day cannot unlock a contraindicated action.
4. **Human State > Trajectory.** *Where you are now* outranks *where you're heading* — a current red flag
   (acute pain, illness) dominates a positive trend. (And, per SPRINT-002.1, trend is used to *interpret*
   state, never to *override* a present hard signal.)
5. **Trajectory > Goal.** The realistic direction of travel constrains what goal is pursuable now (a
   declining recovery trend tempers an aggressive goal), because chasing the goal against the trend causes
   harm/dropout.
6. **Goal > Behavior.** The chosen adaptation orders which behaviors to build; behavior design serves the
   goal, not vice-versa.
7. **Behavior > Communication.** *What* durable action to encourage precedes *how* to say it; a perfectly
   worded message toward the wrong behavior is still wrong.

**The cut line.** Everything left of Human State is the **Brain's hard floor** (M3/M4, frozen) — it can
only be *consulted*, never softened. Everything from Human State rightward may only **shape within** the
floor. This is the priority graph expressed as the Envelope invariant (§1).

---

## 4. Conflict Resolution

**General rule.** A conflict is resolved by the priority graph: the higher-priority signal **constrains**
the lower; the lower may only operate in the space the higher leaves. **Safety/medical conflicts are
never averaged.** Within a single priority level, ties are resolved by the Constitution's context-map
(alleles): pick the context-valid variant; if genuinely contested, take the **conservative default** and,
if the trade-off is the user's to make, **present it and defer to the user** (§7).

Worked examples (each shows: signals → priority resolution → envelope effect → coaching shaping):

**A · High motivation + Low recovery.**
- Priority: **Human State (low recovery) > Goal/Behavior (motivation).** Recovery is a present hard-ish
  state; motivation is a delivery/behavior signal. Gene DG-U-06 (respect-the-ceiling, *response-trend
  aware*): if the trend confirms genuine under-recovery, the envelope **caps load**; motivation cannot
  raise it.
- Resolution: enforce the recovery-limited envelope; the Coach uses the high motivation to *redirect*
  energy into a quality, lighter session (or recovery task) — **shaping, not loading**. Never "reward"
  motivation with more load. (If motivation is high *and* the trend shows recovered, DOSE proceeds — the
  trend fix prevents over-gating a true responder.)

**B · Travel + Competition.**
- Priority: **Contraindications/Constraints + Goal.** No medical conflict. The Brain/enforcement envelope
  favors a **taper** (fatigue management for the competition); the **constraint** (travel: no gym,
  time/equipment limits) narrows *how* the taper is delivered.
- Resolution: envelope = taper; constraint handler = bodyweight/hotel-friendly, minimal-equipment
  programming; Communication sets expectation (peak > volume this week). The goal (compete well) is served
  *through* the constraint, not against it.

**C · Muscle gain + Diabetes.**
- Priority: **MEDICAL dominates.** DG-U-10 (safety/refer-out) fires with `safety_flag`. The medical frame
  is the floor: nutrition/training for muscle gain is admissible **only inside** diabetes-safe bounds, and
  anything requiring clinical judgment **routes to a professional** (over-referral bias).
- Resolution: Orchestrator does **not** prescribe around the condition. Envelope = "coordinate with the
  user's medical care; general, safe guidance only." Coaching supports adherence/identity *within* that
  boundary. Muscle-gain goal is pursued *subordinate* to the medical constraint, never traded against it.

**D · Pain + Need to perform.**
- Priority: **SAFETY/Contraindication > Goal.** Stage 2 fires: pain-with-load is a provocation signal
  (McGill genes). The "need to perform" (a goal/psychological pressure) is **subordinated**. SPRINT-002.1
  fear/pain triage: distinguish protective pain (route to D3/medical) from mere discomfort.
- Resolution: envelope = pain-free ranges only / route out if red-flagged; the Coach reframes performance
  toward what is safely trainable and addresses the pressure (Communication/Psychology) — **without**
  loading through pain. Under uncertainty, conservative branch (over-refer).

**E · Low confidence + Good physiology.**
- Priority: physiology imposes **no constraint** (envelope open on the physical side); therefore the
  binding limiter is **Behavior/Communication/Psychology**. Genes DG-U-08 (identity anchor), DG-U-09
  (process-over-outcome).
- Resolution: no physical restriction; the entire response weight shifts right on the graph — Coaching
  builds confidence via mastery framing, small winnable actions, process focus, and reassurance. This is
  the mirror case: when the floor is clear, communication *becomes* the leverage.

**Conflict graph (who wins, structurally):**
```
                 ┌───────── if present, always wins ─────────┐
  SAFETY ─▶ MEDICAL ─▶ CONTRAINDICATION ─▶ HUMAN STATE ─▶ TRAJECTORY ─▶ GOAL ─▶ BEHAVIOR ─▶ COMMUNICATION
     ▲ never averaged · never softened ▲          ▲ shape-only from here right (soften) ▲
  tie within a level → Constitution context-map (allele) → else conservative default → else defer to user
```

---

## 5. Reasoning Timeline

Different reasoning runs at different cadences; the Orchestrator schedules them so the fast, high-stakes
checks never wait on the slow, deliberative ones.

| Band | Latency | What runs | Property |
|---|---|---|---|
| **Reflex (fast)** | pre-response, deterministic | Safety Pre-Screen · Intent · Brain verdict · Enforcement | must be quick + fail-safe; can interrupt |
| **Deliberate (slow)** | within the turn | Gene selection · Constitution constraints · conflict resolution · Coaching strategy · Blueprint | reasoned, bounded by the fast floor |
| **Persistent** | across turns (memory) | Human State (facts, preferences, TTL-decayed) | read as snapshot each turn; written post-turn only |
| **Conversation** | within a session | topic continuity · intra-session state changes · immediate trajectory | shapes coherence, not the floor |
| **Long-term** | across sessions | Trajectory over history · adherence/identity trends · goal stability | informs (never overrides) present-turn floor |

**Rule:** the **Reflex band is authoritative and blocking** — nothing in the Deliberate/Persistent/Long-
term bands may proceed on a permission the Reflex band did not grant. Long-term reasoning may *tighten*
(e.g., a worsening trend biases conservative) but never *loosen* the present safety floor.

---

## 6. Attention Allocation

**Salience score** for any signal = `priority (§3) × confidence × freshness × relevance-to-intent`.
The Orchestrator spends attention in descending salience.

- **Examined first (always):** safety/medical red-flag signals — cheap to check, catastrophic to miss.
  They are evaluated **before** intent is even fully resolved (Stage 2 precedes trust in Stage 1 signals).
- **Examined next:** the Brain verdict + the current hard state variables relevant to the intent.
- **Can be ignored (this turn):** low-confidence inferences, stale (TTL-expired) state, trajectory below
  min-points, and any variable irrelevant to the current intent. Ignored ≠ deleted — it simply doesn't
  earn attention now.
- **Attention shifts when:** (a) a **higher-priority signal appears** (a red flag interrupts everything —
  the supreme interrupt), (b) **intent changes** mid-conversation (re-triage), or (c) a **trend crosses a
  risk threshold** (trajectory promotes a variable's salience). Per SPRINT-002.1, a *single raw input*
  does not by itself seize attention — it must be corroborated by trend or confidence before it reweights
  a decision (prevents input-based over-gating).

**Attention loop (reasoning graph):**
```
   new turn ─▶ compute salience over all signals
                     │  (priority × confidence × freshness × relevance)
                     ▼
        pick highest-salience signal ─▶ does it interrupt? ──yes──▶ Stage 2 halt/route
                     │ no
                     ▼
        fold it into the envelope (tighten only) ─▶ more salient signals? ──yes──┐
                     │ no                                                          │
                     ▼                                                             │
        proceed to Coaching/Blueprint  ◀───────────────────────────────────────── ┘
```

---

## 7. Failure Recovery

Principle: **fail safe, never fail open; never fabricate; when unsure, tighten.**

| Failure | Detection | Recovery |
|---|---|---|
| **Missing Human State** | empty/expired snapshot | proceed on Brain + population priors; if the missing datum is *decision-critical*, **defer** and ask one clarifying question; never invent state. |
| **Contradictory data** | two signals disagree | prefer **higher priority**, then higher confidence, then fresher; if safety-relevant, take the **conservative** branch regardless of confidence. |
| **Unknown condition** | unrecognized medical/term | treat as **potential red flag** → conservative default + **refer out** (over-referral bias, SPRINT-002.1); do not reason around an unknown. |
| **Incomplete history** | trajectory < min points | return `insufficient`; fall back to the **snapshot**; widen uncertainty; make no trend claim. |
| **Conflicting goals** | ≥2 incompatible goals | resolve by priority graph + **goal-stability** (hold one goal long enough); if the trade-off is genuinely the user's, **present it and defer to the user** — never silently average. |
| **Brain/organ error** | timeout/exception | **fail to the most conservative Decision** (no generation, no load); ship a safe message; flag the turn. |
| **Trace write fails** | ledger error | ship the answer, **flag turn non-explainable** for review (explainability is mandatory but must not block a safe answer). |

**State diagram (pipeline control):**
```
        ┌─────────┐   red flag / halt    ┌───────────────┐
        │ RUNNING │ ───────────────────▶ │  TERMINAL-SAFE│ (refer-out / conservative)
        └────┬────┘                      └───────────────┘
             │ missing/ambiguous critical datum
             ▼
        ┌─────────┐   user provides / resolves   ┌─────────┐
        │ DEFERRED│ ───────────────────────────▶ │ RUNNING │
        └────┬────┘                              └─────────┘
             │ organ error
             ▼
        ┌───────────────┐   conservative Decision   ┌─────────┐
        │ DEGRADED-SAFE │ ────────────────────────▶ │ RENDER  │
        └───────────────┘                           └─────────┘
```
Every terminal path is **safe by construction** — there is no transition that ends in an un-vetted,
load-bearing, or medically-unscreened answer.

---

## 8. Reasoning Explainability

**Requirement:** every final answer is traceable back through **Brain → Genome → Human State →
Constitution → Coach Strategy.** The Orchestrator emits one **trace record** per turn:

```
TRACE {
  turn_id, subject, locale
  brain:        { decision_id, verdict, halt, generate, constraints[], red_flags[] }   # authoritative
  safety:       { screen_result, routed_out?, interrupt_stage? }
  genes:        [ { gene_id, fired_because, allele, tightened_envelope_how } ]         # active called genes
  human_state:  [ { key, value, confidence, freshness, used_for } ]                    # read-only, cited
  trajectory:   { sufficient?, directions{}, risk }                                    # or "insufficient"
  constitution: [ { principle_id, status: candidate|ratified, applied_as } ]           # advisory today
  coaching:     [ { variable, reason, rule, principle } ]                              # soften-only, each cited
  blueprint:    { sections[], addenda[], dropped_by_priority[] }
  envelope_log: [ stage → permissions_removed / constraints_added ]                    # monotone shrink proof
  outcome:      { rendered?, explainable?, degraded? }
}
```

**Traceability guarantees:**
- Every coaching line cites its `variable · reason · rule · principle` (BUILD-3 contract).
- Every genome influence names the **gene** and *why it fired* + how it **tightened** the envelope.
- The `envelope_log` proves the **monotone-shrink** property (no stage expanded permissions) — this is the
  machine-checkable form of Brain supremacy.
- A human can reconstruct any answer as: *"the Brain permitted X; genes G tightened to Y; state S (conf/
  fresh) and trend T shaped delivery; constitution C advised; the coach softened by D — therefore this
  message."* If any link is missing, the turn is flagged non-explainable.

---

## 9. End-to-end sequence diagram

```
User │ Orchestrator │ Brain(frozen) │ HumanState │ Trajectory │ Genome │ Constitution │ Coach │ Renderer
  │  msg  │             │              │           │           │        │              │       │
  ├──────▶│ 0 normalize │              │           │           │        │              │       │
  │       │ 1 intent+triage            │           │           │        │              │       │
  │       │ 2 SAFETY PRE-SCREEN ──────▶│ (M4)      │           │        │              │       │
  │       │◀── clear | RED FLAG ───────┤           │           │        │              │       │
  │◀ (if red flag: TERMINAL-SAFE refer-out — pipeline halts here) ──────────────────────────────┤
  │       │ 3 Brain decide ───────────▶│ S1..S5    │           │        │              │       │
  │       │◀── Decision ───────────────┤           │           │        │              │       │
  │       │ 4 enforce (envelope floor)─▶│ (M4)      │           │        │              │       │
  │       │◀── directive ──────────────┤           │           │        │              │       │
  │       │ 5 read state ─────────────────────────▶│           │        │              │       │
  │       │ 6 read trajectory ────────────────────────────────▶│        │              │       │
  │       │ 7 select genes ──────────────────────────────────────────▶ │ (tighten)    │       │
  │       │ 8 apply constitution (advisory) ───────────────────────────────────────▶  │       │
  │       │ 9 coaching strategy (soften within envelope) ───────────────────────────▶ │       │
  │       │ 10 blueprint · 11 render ──────────────────────────────────────────────────────▶ │
  │◀───────────────────────── final message ───────────────────────────────────────────────────┤
  │       │ 12 write TRACE (Brain→Genome→State→Constitution→Coach)                              │
```

---

## 10. Worked example (full trace, non-safety) + one failure analysis

**Example — "I'm super motivated, let's go heavy today" (subject slept 4h × 3 nights, adherence trend
down).**
1. Intent: training request; domain = performance/behavior. 2. Safety pre-screen: clear (no red flag).
3. Brain: MODIFY, generate=yes, capacity envelope moderate. 4. Enforcement: workout permitted, no halt.
5. State: sleep=low(0.9, fresh), motivation=high(0.8). 6. Trajectory: recovery **declining**, adherence
**declining**, risk elevated. 7. Genes: DG-U-06 fires (trend-confirmed under-recovery → **cap load**),
DG-U-07 (adherence) fires. 8. Constitution: APX-REC-030 (advisory) supports the cap. 9. Coach: redirect
motivation into a quality lighter session; warm, relapse-preventive tone; cite sleep/recovery_trend.
10/11: blueprint + render a lighter, winnable session framed positively. 12: trace records the envelope
shrink (Brain moderate → gene cap) and every citation. **Result:** motivation is honored as *delivery
energy*, never as *load* — the priority graph did its job.

**Failure analysis — the SPRINT-002.1 danger case: "chest tightness during my run, probably just
anxiety, push me through."**
- *Naïve psychology-first path (the validated failure):* a mind-first model reads "anxiety" and applies
  regulate/encourage → **misses a possible cardiac emergency.**
- *M13 path:* Stage 2 Safety Pre-Screen runs **before** any psychology reasoning; "chest tightness during
  exertion" is a hard red flag → **INTERRUPT → TERMINAL-SAFE**: stop, do not push, advise urgent medical
  evaluation. The psychology layer is *never reached*. The Orchestrator's supreme-interrupt ordering is
  precisely the structural fix for SPRINT-002.1's most dangerous finding.

---

## 11. Invariants / guardrails

1. **The Brain is frozen and supreme.** The Orchestrator calls it; nothing downstream overrides it.
2. **The Orchestrator holds no knowledge, no safety, no coaching.** It only orders, constrains, and traces.
3. **Envelope monotonicity.** Every stage may only *tighten* permissions; none may expand them. Proven per
   turn by the `envelope_log`.
4. **Safety is a supreme interrupt** (SPRINT-002.1) — it precedes and can halt every other domain.
5. **Soften-only downstream.** State, Trajectory, Genes, Constitution, Coach may shape *within* the floor,
   never add a withheld workout, raise load, or remove a constraint.
6. **Gate on trend, not raw input; bias referral toward over-referral; triage to the right domain** —
   the three SPRINT-002.1 corrections are encoded structurally (§6, §7, §2/§1).
7. **Constitution is advisory until human-ratified** (candidate status); `safety_flag` genes/principles
   may only strengthen safety.
8. **Fail safe, never fail open; never fabricate state.**
9. **Every answer is explainable** (Brain→Genome→State→Constitution→Coach) or the turn is flagged.
10. **This is architecture.** No runtime, no Brain change, no deployment, no feature flags. The Orchestrator
    is the cognitive *conductor*; the organs remain the musicians.
