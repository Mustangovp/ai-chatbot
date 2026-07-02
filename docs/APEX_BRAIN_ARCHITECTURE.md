# THE APEX BRAIN — Deliberation Architecture v1.0

**Status:** Design canon. Extends — never rewrites — the frozen philosophy
("The Mind of APEX" Ch.1–3 + Interlude), the Engineering Blueprint (30 organs),
and the Behavioral Language. This document defines how APEX *reasons its way to
an action*. It is normative for every prescriptive decision.

**Origin:** a real test exposed a foundational flaw. A 69-year-old woman —
prior stroke, diabetes, hypertension, chronic fatigue, poor sleep, 03:00 waking,
shortness of breath, joint pain — asked "Create today's workout." APEX returned
push-ups and planks.

**The flaw is not the workout. It is that generation was the entry point.**
A generator answers *"what exercises?"*. A coach answers a different question,
and only sometimes arrives at exercises at all.

---

## 0. The Architectural Diagnosis

The old pipeline: `request → generate workout → render`. Generation had **no
precondition and no right of refusal**. Nothing sat between "the user asked" and
"here are exercises." So the system could not:

- recognize that push-ups + planks are **contraindicated** here (Valsalva /
  isometric load → acute blood-pressure spike, unsafe with hypertension + stroke
  history; loaded holds aggravate joint pain);
- notice a **red flag** (new/worsening shortness of breath in this risk profile
  is a *see-your-clinician* signal, not a training input);
- conclude that **today's highest-value intervention was not training at all**.

Four independent judgments were missing. The fix is not a better generator. It
is to **demote generation to the last, gated organ** behind a mandatory chain of
reasoning — the way an elite coach's mind actually runs. The coach never begins
with exercises. The coach begins with understanding, and understanding has the
authority to say *no, not today, and here is what instead.*

> **The unit of coaching is not the workout. It is the decision of whether to
> prescribe one — and generation is what happens only after that decision
> clears.**

---

## 1. The Deliberation Cascade

Six stations, evaluated **in order**. Each is a reasoning organ with inputs,
outputs, a confidence, and the authority to **halt or reroute the cascade**.
Control only flows downward when the current station clears. Generation
(Station 6) is reached by a minority of requests and is *impossible* to reach
without the earlier stations' consent.

```
REQUEST (a signal, never a command)
   │
   ▼
 S1  WHO is this human?         → Constraint Set + Capacity Envelope
   │        (trait)
   ▼
 S2  WHAT is their state today? → Readiness + Red-Flag scan
   │        (state)
   ▼
 S3  WHAT matters MOST today?   → ranked Need Vector
   │
   ▼
 S4  Is training appropriate?   → GO / MODIFY / NO-TRAIN  (right of refusal)
   │
   ▼
 S5  Is something better than   → Intervention selected from the full library
   │   training?                   (training is only one option)
   ▼
 S6  Generate — CONSTRAINED     → a plan bounded by S1's constraints, or nothing
   │
   ▼
 EXPRESSION → CONSTITUTION GATE → user   (frozen F + G systems, unchanged)
```

**This is not new philosophy.** It is the frozen Judgment System (E) and
Safeguards (G), composed into the mandatory order for the "what to prescribe"
decision, reading the Athlete Model as its state. Stations map to existing
organs; the genuinely new organs (S1 Constraint model, S2 Red-Flag Sentinel, S4
Appropriateness Gate, S5 Intervention Selector) are noted per station and enter
the Blueprint's organ registry.

---

## 2. The Stations

### Station 0 · Framing — *the request is a signal, not a command*
"Create today's workout" is treated as **evidence of intent**, not an
instruction to emit exercises. Frozen Judgment (Ch.3): *intelligence answers the
question; wisdom questions the question.* The request enters the cascade at S1;
it can never jump to S6. A user can *ask* for a workout; only the cascade can
*grant* one.

### Station 1 · WHO — the Somatic Constraint Model  *(new organ; extends Athlete Model)*
- **Purpose:** convert who-this-human-is into what-is-safe-and-possible — a
  **Constraint Set** and a **Functional Capacity Envelope**. This is the organ
  whose absence caused the failure.
- **Reads:** profile (age, sex, stated conditions, medications, injuries,
  surgeries, limitations, equipment); Athlete Model long-term traits
  (recovery_capacity, adaptation, adherence); history.
- **Produces:**
  - **Constraint Set** — typed, never diagnostic:
    `absolute` (never program), `relative` (modify/avoid-load), `monitor`
    (permit but watch). Constraints are **movements and intensities**, not
    diseases: e.g. hypertension → *avoid Valsalva, breath-holds, heavy
    isometrics, inversions*; stroke history → *balance-supported, symmetry-aware,
    no maximal exertion*; joint pain → *pain-free ROM, unloaded holds*; certain
    meds → *fall-risk / hypoglycemia / exertional-caution flags*. The mapping
    lives in a **curated, conservative Constraint Library** maintained with
    professional review — never invented per-request by a language model.
  - **Capacity Envelope** — a ceiling on intensity/complexity/volume derived
    from age, training age, condition load, and Athlete Model estimates. An
    elite athlete's envelope is wide; a deconditioned 69-year-old's is narrow.
    Same organ, different envelope — this is how populations differ (§7).
- **Confidence:** proportional to how much the profile actually specifies.
  Sparse profile → low confidence → the whole cascade biases conservative and
  the Curiosity Engine (frozen D3) queues the missing question.
- **The bright line:** this organ recognizes **constraints and contraindications**
  (a coach's job). It never assigns a **diagnosis** (a clinician's job). It holds
  "avoid Valsalva," never "you have heart failure." (§7, and enforced by G1.)
- **Blueprint home:** new; sits beside the Athlete Model, feeds Judgment.

### Station 2 · STATE — Readiness & the Red-Flag Sentinel  *(new sentinel; extends G2/G3)*
- **Purpose:** distinguish **trait** (S1: who they are) from **state** (how they
  are *today*), and scan for signals that outrank the entire training question.
- **Reads:** Athlete Model live estimates (physical/mental fatigue, sleep,
  stress, recovery); today's self-report; recent load; the message itself.
- **Produces:**
  - **Readiness** (value + confidence) — today's capacity within the envelope.
  - **Red-Flag scan** — reported symptoms that, in context, warrant deferral to
    a human professional: new/worsening dyspnea, chest symptoms, syncope,
    neurological change, uncontrolled glucose signs, acute pain. A red flag does
    **not** produce a diagnosis; it produces a **route** (Handoff Reflex, G3) and
    a cascade **halt** toward safe non-exertional options. In the test case, the
    reported shortness of breath alone should stop the cascade here.
- **Confidence & honesty:** low-confidence state → conservative default (never an
  optimistic guess). Self-report is `reported` tier — believed but weighted, per
  the Athlete Model's provenance ceilings.
- **Blueprint home:** specialization of Compliance Sentinel (G2) + Handoff
  Reflex (G3), scoped to prescription-time symptom routing.

### Station 3 · PRIORITY — the Need Vector  *(frozen E1 Stakes Arbiter)*
- **Purpose:** compute *what matters most today* **before** deciding to train.
- **Reads:** S1 constraints, S2 readiness + red flags, Athlete Model, goals.
- **Produces:** a **ranked Need Vector** over the whole space of what could help:
  medical follow-up, sleep, stress reduction, recovery, gentle movement,
  nutrition, conversation, *and* training. Ranking uses the frozen stakes order
  (safety > relationship > habit > adaptation > today) and *feed-the-scarcer-
  account* (§6). For the test case the vector tops out at medical follow-up +
  protection + gentle activity; training adaptation ranks near the bottom.
- **Why here:** the old system implicitly hard-coded "the need is a workout."
  This organ makes the need a **computed conclusion**, and usually it isn't a
  workout.
- **Blueprint home:** frozen E1, used verbatim.

### Station 4 · APPROPRIATENESS — the Go/No-Go Gate  *(new organ; the missing authority)*
- **Purpose:** decide, explicitly, whether physical training is appropriate
  today. This is the organ with the **right of refusal** the architecture lacked.
- **Reads:** S1, S2, S3.
- **Produces one of:**
  - **NO-TRAIN** — an absolute contraindication or active red flag present, or
    state below the safety floor, or confidence too low to prescribe safely.
    Routes to S5's non-training branch with a reason.
  - **MODIFY** — training permissible only inside a tightened envelope
    (deload / gentle / supported / pain-free-ROM only).
  - **GO** — training is appropriate within the S1 envelope.
- **Decision rule (uncertainty → safety):** because the loss is asymmetric —
  over-prescribing can injure (sometimes irreversibly), under-prescribing merely
  slows progress (fully recoverable) — the gate defaults toward NO-TRAIN/MODIFY
  under uncertainty. This is frozen Judgment Ch.3 ("prefer the mistake you can
  take back"), applied to programming.
- **NO-TRAIN is a first-class success, not a failure** (§5).
- **Blueprint home:** new; a specialization of E3 Action Selector + E5
  Paternalism Governor for the train/don't-train boolean.

### Station 5 · INTERVENTION — the Selector  *(new organ; generalizes the output space)*
- **Purpose:** even when training is *permitted*, choose whether it is *optimal*.
  Selects the single highest-value intervention against the Need Vector from the
  full library: **recovery · sleep · walking · breathing · mobility · stress
  reduction · nutrition · conversation · medical follow-up · training.**
- **Reads:** S3 Need Vector, S4 verdict, Athlete Model, receptivity (frozen E4
  Kairos).
- **Produces:** the chosen intervention + its rationale (frozen: explain *why*).
  Training is one option among ten and frequently not the winner — this single
  organ is what turns APEX from a workout generator into a coach. For the test
  case it selects a gentle-walk / breathing / sleep focus plus a medical-follow-up
  nudge; a strength session is never even a candidate (S4 already said NO-TRAIN).
- **Blueprint home:** new; the concrete realization of E3's candidate generation
  over a non-training-inclusive action space (the frozen "null action" and
  "redirect" become real, named alternatives here).

### Station 6 · GENERATE — the Constrained Terminal
- **Reached only if** S4 = GO/MODIFY **and** S5 selected training.
- **Generation is bounded by S1's Constraint Set and Capacity Envelope** as hard
  inputs, not suggestions. Even if a request somehow reached here in error, the
  envelope makes contraindicated output (push-ups/planks for this athlete)
  *unrepresentable*. Constraints are a filter on the generator's action space,
  not a warning appended after.
- Output carries its reasoning and its expectations (frozen D1 Prediction
  Engine — every prescription is a falsifiable hypothesis).

---

## 3. The Confidence & Uncertainty Model

Confidence is not a display value; it is a **control signal that flows downhill
and gets more conservative as it falls.**

- Every station emits `(result, confidence)`. Low confidence at any station
  **widens constraints and lowers the capacity envelope** downstream. The system
  is *most cautious when it knows least* — the inverse of the failure, which was
  boldest when it knew nothing.
- **Three uncertainties, three responses** (frozen mapping):
  1. **Missing data** → *ask* (Curiosity Engine, D3). The cascade may pause and
     pose the one question of highest value-of-information rather than guess.
  2. **Conflicting data** → *hold hypotheses + hedge + coach to the worse case*
     (Hypothesis Manager, D2). "Sleep well" but declining performance → prescribe
     as if recovery is compromised while investigating.
  3. **Out of competence** → *route to a human* (Handoff Reflex, G3). Red flags
     and anything past the coaching mandate leave the cascade entirely.
- **The asymmetric-loss law governs the whole brain:** under uncertainty, do
  less, ask more, defer sooner. Slow is recoverable; harm may not be.

---

## 4. How APEX Decides NOT To Train

Declining to train is a **designed output of equal standing** to prescribing —
the frozen "null / redirect action" made explicit and dignified. It fires when
S4 returns NO-TRAIN, on any of:

- an **active red flag** (S2) → route to medical follow-up;
- an **absolute contraindication** with no safe modification (S1);
- **state below the safety floor** (S2) — e.g. severe fatigue, acute illness;
- **confidence too low** to prescribe safely (the cascade would rather ask);
- the **Need Vector** placing a non-training need decisively on top (S3/S5).

And it is *delivered* per the frozen constitution:
- **With the reason** (explain *why*: "your reported breathlessness comes first —
  that deserves a clinician, not a workout").
- **Without shame or alarm** (accountability-and-care without fear; the organism
  narrows to its protective register — Behavioral Language).
- **With an alternative** (S5 always pairs a NO-TRAIN with something that *does*
  help today). APEX never leaves a person with nothing.
- **Never as a diagnosis** ("this warrants a doctor's look," never "you have X").

A coach who cannot say *not today* is not a coach. This organ gives APEX that
sentence, and makes saying it a form of competence rather than a gap.

---

## 5. Prioritizing Competing Needs

Handled entirely by frozen organs, so no new philosophy: the **Stakes Arbiter
(E1)** ranks by `safety > relationship > habit > adaptation > today`, and
**feed-the-scarcer-account** resolves genuine ties (spend down the abundant
account, protect the scarce one). The population-dependent part is only the
*weights*: for a fragile athlete, safety and relationship dominate and adaptation
is nearly silent; for an elite athlete in a hard block, adaptation may lead. The
**ranking machinery is identical for everyone** — the constraint set and capacity
envelope (S1) supply the different weights. One brain, not many.

---

## 6. Population Adaptation Without Becoming a Diagnostic System

Every human — elite athlete, sedentary beginner, elderly adult, stroke survivor,
person with obesity or chronic disease — runs the **identical six-station
cascade**. Nothing branches on "patient type." Only three things vary, all
outputs of S1 from profile + Athlete Model evidence:

1. **The Constraint Set** — which movements/intensities are absolute / relative /
   monitor.
2. **The Capacity Envelope** — the intensity/complexity/volume ceiling.
3. **The Stakes weights** — how loudly safety speaks relative to adaptation.

This is what lets one architecture serve an Olympian and a stroke survivor
without either a separate "medical mode" or a diagnosis. The Olympian gets a wide
envelope, few constraints, adaptation-weighted stakes. The stroke survivor gets a
narrow envelope, several movement constraints, safety-weighted stakes — and the
*same respect, same voice, same cascade.*

**The line APEX never crosses — structural, not stylistic:**

| APEX MAY (a coach's job) | APEX MAY NOT (a clinician's job) |
|---|---|
| Recognize **movement constraints** implied by stated conditions/meds | **Diagnose**, or name a condition the user didn't state |
| Recognize **red-flag symptoms** the user reports and **defer/route** | Interpret symptoms into a medical conclusion |
| **Refuse to program** contraindicated movements | Prescribe, adjust, or comment on **medication or treatment** |
| Recommend **seeing a professional** | Replace, delay, or contradict that professional |

The mechanism that guarantees the line: red flags and conditions produce
**routes and constraints, never labels**, and the **Constitution Gate (G1)** —
which already forbids clinical language user-facing — is the final filter on
every word out. Recognizing that burpees are unsafe for someone reporting chest
pain is not diagnosis; it is competence. A skilled physiotherapist does exactly
this every day and never writes a diagnosis. APEX occupies precisely that seat.

---

## 7. The Test Case, Re-Run Through the Brain (defense in depth)

The 69-year-old, same request, new architecture — and note that **four
independent organs each, alone, prevent the failure:**

- **S1** builds constraints from her profile: *no Valsalva / no heavy isometrics
  / balance-supported / pain-free ROM*, and a **narrow capacity envelope**.
  Push-ups and planks are now outside the representable action space. *(Failure
  blocked once.)*
- **S2** Red-Flag Sentinel catches the reported **shortness of breath** → route
  to clinician, halt toward non-exertional options. *(Blocked twice.)*
- **S3/S4** compute the Need Vector and the gate returns **NO-TRAIN** — red flag
  plus state below floor plus low confidence, all pointing the same way.
  *(Blocked thrice.)*
- **S5** selects **medical follow-up + gentle walking + breathing + a sleep
  conversation**; a strength session is never a candidate. *(Blocked four times.)*

The response she receives is a calm, non-alarming, non-diagnostic message: her
breathlessness deserves a doctor's attention first; meanwhile a short easy walk
and a few minutes of slow breathing are the right work for today; and the coach
will be here when she's cleared. No push-ups. No planks. No diagnosis. No shame.
**That is the difference between a workout generator and a coach — and it is now
architectural, not a matter of the model behaving well on a given day.**

---

## 8. Information Flow (normative)

```
Athlete Model (state, provenance, confidence)  ─┐
Profile + Constraint Library ───────────────────┤
History / Episodes ─────────────────────────────┘
        │
        ▼   reads only; the cascade writes nothing but a decision record → Ledger
  ┌─────────────────── DELIBERATION CASCADE ───────────────────┐
  │ S1 Constraint+Capacity → S2 Readiness+RedFlag → S3 Needs    │
  │ → S4 Gate → S5 Intervention → (S6 Constrained Generate)     │
  └────────────────────────────────────────────────────────────┘
        │  action (train | decline+alternative | route-to-human | ask)
        ▼
  Expression Governor (F1) → Voice Renderer (F2) → Conformance (F3)
        ▼
  Constitution Gate (G1, fails closed — no clinical labels, ever)
        ▼
  user     (+ Prediction Engine D1 arms a falsifiable expectation)
```

The cascade is **stateless over the model**: it reads the Athlete Model and
writes only a decision record to the Event Ledger. Learning happens where it
already does (Consolidator, Prediction resolution) — the brain *decides*, the
Athlete Model *remembers*. No duplicated state.

---

## 9. Traceability & What Is Genuinely New

| Cascade element | Frozen organ it uses / extends |
|---|---|
| S0 request-as-signal | Judgment Ch.3 (question the question) |
| S1 Constraint + Capacity | **new**, beside Athlete Model |
| S2 Readiness | Athlete Model projection |
| S2 Red-Flag Sentinel | **new**, extends G2 Compliance Sentinel + G3 Handoff |
| S3 Need Vector | E1 Stakes Arbiter (verbatim) |
| S4 Appropriateness Gate | **new**, extends E3 + E5 |
| S5 Intervention Selector | **new**, realizes E3 over a non-training action space |
| S6 Constrained Generate | the old generator, demoted + envelope-bounded |
| uncertainty → ask/hedge/route | D3 Curiosity · D2 Hypothesis · G3 Handoff |
| decline-to-train | frozen null/redirect action, made first-class |
| population weights | S1 outputs → E1 weights |
| no clinical labels | G1 Constitution Gate (final filter) |

Four new organs; everything else is the frozen canon, re-ordered so that
**understanding precedes, and can veto, generation.**

---

## 10. Failure Modes of the Brain Itself

- **Over-caution / infantilization** → the envelope must never forbid *survivable
  struggle* (frozen: protect from harm, never from struggle); MODIFY is preferred
  to NO-TRAIN whenever a safe modification exists.
- **Constraint Library staleness or gaps** → conservative defaults on unknown
  meds/conditions + human-curated review; the library is never LLM-authored.
- **Red-flag over-trigger** (crying wolf) → graded routing; a soft "worth
  mentioning to your doctor" for weak signals, hard halt only for strong ones.
- **Cascade latency** → S1–S5 are cheap state reads; only S6 calls the generator,
  and only when earned — so most requests are *faster*, not slower.
- **Model gaming** (a user under-reporting to unlock training) → provenance
  weighting already distrusts optimistic self-report; behavior outranks words.

---

## The Architecture in One Sentence

**APEX no longer generates workouts; it decides what a specific human needs today
— and a workout is one possible answer, reachable only after who-they-are,
how-they-are, what-matters-most, and is-training-even-appropriate have each been
answered and each been given the power to say no.**

---

### Status note (honest)
This is design canon; it is not yet wired into the live `/chat` path. Until the
cascade — minimally S1 Constraint Set + S2 Red-Flag Sentinel + S4 Gate — sits in
front of generation on the server, the production system retains the demonstrated
hazard. The Athlete Model substrate (`athlete_model.py`) is the state layer this
brain reads; the cascade is the next build, and given the safety exposure it
should precede any further feature work.
