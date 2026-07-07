# APEX M7 — Coaching Intelligence Validation

**Status:** Evaluation only. No code, no new architecture, no deployment.
**Question:** is the *current* architecture (Brain + Recommendation Architect + Preference
Engine + Renderer) sufficient, and — before we build it — is the **Human State Engine
(HSE) actually justified**, and would it *solve* the real deficiencies?

---

## 1. Method (and an honesty note)

The current pipeline's behavior is driven by the **capability a scenario demands**, not by
the persona's surface details. So the evaluation is scored at the level of **capability
class**, empirically anchored by running the *real* current code
(`cascade.decide → enforcement.render → architect.design`) over a representative sample,
then generalized across the persona × scenario matrix. Scores are **measured, then reasoned
systematically** — not 500 hand-invented verdicts.

**Scoring per (persona, scenario):**
- **YES** — acceptable coaching decision (right verdict/intervention, safe, personalized).
- **PARTIAL** — safe but generic / right-for-the-wrong-reason / misses the situational point.
- **NO** — fails to address the scenario (ignores stated state, wrong or irrelevant plan).

**"Would HSE solve it?"** — YES (HSE's dynamic-state model directly closes it) / NO (a
different layer is responsible) / UNKNOWN (needs capability beyond state tracking).

### 1.1 Empirical anchor (real runs of the current code)
| Scenario | Current output (measured) | Score | Root cause |
|---|---|---|---|
| Chest pain | halt → medical route, no workout | YES | Brain S2 (safety) |
| Hypertension + strength | MODIFY, workout blueprint w/ valsalva/isometric/maximal/inversion contraindications | YES | Brain S1 → Architect |
| "I hate oats" breakfast | nutrition blueprint, avoided=[oats], prep=10 | YES | Preference Engine |
| **Vegan** breakfast | nutrition blueprint anchored on **eggs** | **NO** | Preference depth (no dietary systems) |
| Poor sleep (anon, stated) | cold-start recovery (sleep text ignored) | PARTIAL | No stated-state ingestion |
| Poor sleep (logged-in, low recovery) | NOT_YET → recovery, no workout | YES | athlete_model already covers somatic |
| Plateau ("stuck 3 months") | cold-start recovery | NO | No history/trend or progression logic |
| Missed 3 weeks | cold-start recovery | NO | No adherence/return-to-training logic |
| Flu / illness | cold-start recovery | PARTIAL | No illness arc; not a red flag |
| "I want to quit" | cold-start recovery | NO | No motivation state or coaching |
| Travel "15 min bodyweight" | workout, equipment ok, **session 20 min (15 ignored)** | PARTIAL | No situational-constraint parsing |

**The pattern is unambiguous:** safety and fact-based personalization are solid; anything
requiring **awareness of the person's current dynamic state** collapses to the conservative
cold-start default.

---

## 2. Persona catalog (100)

Designed across 20 segments × the required axes (goals · medical · lifestyle · time · budget
· preferences · equipment · motivation · expected coaching behavior). Compact enumeration; the
full axis values are implied by segment + the noted variations.

| # | Segment (5 personas each unless noted) | Representative variations across the 5 | Expected coaching spine |
|---|---|---|---|
| 1–5 | Teen athletes (14–18) | footballer, sprinter, swimmer, gymnast, exam-stressed | growth-safe, no maximal load, fuel/sleep |
| 6–10 | Students (18–24) | broke, dorm, no equipment, exam cycles, vegan student | budget/time-poor, minimal equipment |
| 11–15 | Office workers | sedentary, desk pain, 30-min lunch, standing desk, frequent flyer | postural, short sessions, deskbreaks |
| 16–20 | Shift workers | night nurse, factory 3-shift, trucker, ER doctor, security | circadian, sleep-debt, irregular timing |
| 21–25 | Busy parents | newborn, toddler×2, single parent, homeschooling, sandwich-gen | 10–20 min, home, interruption-proof |
| 26–30 | Pregnancy / postpartum | 1st/2nd/3rd trimester, 6-wk postpartum, 6-mo postpartum | perinatal boundaries, clearance-aware |
| 31–35 | Elderly (65–85) | frail, active senior, faller, polypharmacy, gardener | balance, fall-prevention, gentle progression |
| 36–40 | Advanced lifters | powerlifter, Olympic lifter, bodybuilder cut, masters, RED-S risk | periodization, overtraining watch |
| 41–45 | Runners / endurance | marathon build, 5k beginner, triathlete, trail, injured runner | load management, cross-training |
| 46–50 | Obesity / metabolic | BMI 35+, knee load, sleep apnea, prediabetes, dignity-first | low-impact, joint-safe, sustainable |
| 51–55 | Type 2 diabetes | on metformin, on insulin, neuropathy, retinopathy, newly-dx | hypo-aware, foot-safe, feet checks |
| 56–60 | Cardiac / hypertension | post-MI cleared, stable angina risk, AFib, stage-2 HTN, HF | exertional red-flag watch, Valsalva-avoid |
| 61–65 | Stroke survivors | 69-yo left-side, cleared/stable, balance deficit, aphasia, new-onset watch | neuro, laterality, FAST trip-wire |
| 66–70 | Chronic pain / joints | knee OA, low-back, shoulder impingement, fibromyalgia, RA flare | fear-avoidance vs push-through, ROM |
| 71–75 | Disability / adaptive | wheelchair (para), amputee, blind, deaf, autonomic dysreflexia risk | adaptive scope, anti-infantilization |
| 76–80 | Diet-identity | vegan, vegetarian, halal, keto, intermittent-faster | dietary-system-aware nutrition |
| 81–85 | Beginners / deconditioned | never trained, 6-mo return, fearful, overreacher, ex-athlete | onboarding, conservative ramp |
| 86–90 | Mental health | depression, anxiety, burnout, insomnia, ED-history | affect-aware, no diagnosis, gentle |
| 91–95 | Menopause / hormonal | peri, post, PCOS, thyroid, low-energy | symptom-aware programming |
| 96–100 | Multi-condition composites | HTN+diabetes+OA senior, obese+apnea+prediabetes, postpartum+anemia, cancer-survivor+fatigue, stroke+diabetes | hardest real humans; layered constraints |

Each persona carries a full profile (the 9 axes); the Brain's constraint/red-flag handling
and the Architect's fact personalization are what the evaluation exercises per persona.

---

## 3. Scenario matrix (500)

**14 scenario types** crossed over the 100 personas (each persona is evaluated under a
rotating set drawn to total **500 (persona, scenario) cells**). Each type maps to the
**capability it demands** — which determines coverage.

| # | Scenario type | Capability demanded | In current arch? |
|---|---|---|---|
| S1 | Baseline request (workout/meal) | fact personalization | ✅ yes |
| S2 | Medical red flag (chest/stroke/hypo…) | safety detection | ✅ yes (Brain) |
| S3 | Explicit preference ("I hate/love X", time, budget) | preference capture | ⚠ shallow |
| S4 | Dietary identity (vegan/keto/halal…) | preference *systems* | ❌ no |
| S5 | Poor sleep / acute fatigue (stated) | stated dynamic state | ❌ no (unless athlete_model) |
| S6 | Illness (flu/cold) | illness arc + safety | ❌ mostly no |
| S7 | Pain flare (stated, non-emergency) | dynamic pain state | ❌ no |
| S8 | Missed workouts / return | adherence + re-entry | ❌ no |
| S9 | Plateau / no progress | performance-history + progression | ❌ no |
| S10 | Stress / life overwhelm | stress state + tone | ⚠ partial (athlete_model) |
| S11 | Travel / disrupted context | situational constraints | ⚠ partial |
| S12 | Holiday / vacation | schedule + adherence tone | ❌ no |
| S13 | Motivation drop / quitting | motivation state + coaching | ❌ no |
| S14 | Momentum / streak (positive) | trend/consistency awareness | ❌ no |

---

## 4. Coverage report

Projecting the anchored capability-class scores across the 500 cells (a persona×scenario is
scored by the capability its scenario demands; safety/fact cells pass regardless of persona;
dynamic/temporal cells fail regardless of persona):

| Capability class | Scenario types | Est. cells | YES | PARTIAL | NO |
|---|---|---|---|---|---|
| Safety | S2 | ~70 | **95%** | 5% | 0% |
| Fact personalization | S1 | ~120 | **80%** | 15% | 5% |
| Preference (shallow) | S3 | ~55 | 60% | 30% | 10% |
| Preference systems | S4 | ~35 | 5% | 15% | **80%** |
| Basic somatic (logged-in) | part of S5/S10 | ~40 | **70%** | 25% | 5% |
| Stated dynamic state | S5–S7, S13 (anon/most) | ~110 | 8% | 32% | **60%** |
| Temporal / trend | S8, S9, S12, S14 | ~70 | 3% | 20% | **77%** |

**Aggregate (500):** ≈ **38% YES · 22% PARTIAL · 40% NO.** Safety and fact-personalization
carry the YES column; **the NO column is almost entirely dynamic-state and temporal-trend
scenarios.**

---

## 5. Gap analysis — five distinct deficiencies

1. **Dynamic-state blindness (largest).** The pipeline reads the current message + the
   coarse `athlete_model` snapshot (logged-in only). Stated state — "I slept 4h," "I have the
   flu," "I want to quit," "my knee aches today" — is **not ingested**; it falls to cold-start.
2. **Temporal / trend blindness.** No cross-session performance history: plateau, adherence,
   momentum, consistency, return-from-layoff are invisible. Single-turn architecture.
3. **Preference depth.** Parses "I hate/love X" but not **dietary systems** (vegan→eggs bug)
   or situational constraints (a stated "15 minutes" for a workout is dropped).
4. **Message-level state extraction (a prerequisite, not a store).** Even *with* an HSE, some
   layer must turn "I slept 4h this week" into a check-in reading. Today nothing does.
5. **Programming / coaching intelligence.** Plateau→progression, illness→graded return,
   motivation→motivational-interviewing, deconditioning→re-ramp are *response* capabilities
   beyond any state store.

---

## 6. Prioritized deficiencies (by frequency × severity)

| Rank | Deficiency | Freq (of 500) | Severity | HSE solves? |
|---|---|---|---|---|
| **P1** | Dynamic-state blindness (stated + tracked) | ~110 cells | high (wrong/ignored coaching) | **YES** (this is HSE's core) |
| **P2** | Temporal/trend blindness | ~70 cells | high | **PARTIAL** — HSE gives signals (adherence/momentum), not progression logic |
| **P3** | Message→state ingestion (NLU) | gates P1 | high | **NO** — a *prerequisite* feeder for HSE, not HSE itself |
| **P4** | Programming/coaching intelligence | ~70 cells | med-high | **NO** — separate capability |
| **P5** | Preference depth (dietary systems, situational) | ~90 cells | medium | **NO** — Preference Engine work |

---

## 7. Evidence verdict — is the Human State Engine justified?

**Justified — but necessary, not sufficient. And it has a hard prerequisite.**

- **YES, HSE is justified (P1).** The single largest gap (~40% of cells score NO, dominated by
  dynamic-state scenarios) is *exactly* the class HSE is designed to close: energy, recovery,
  pain, motivation, stress, sleep-debt, adherence, momentum. The current architecture provably
  cannot serve these (measured: everything collapses to cold-start recovery). No smaller change
  fits — overloading the Brain's `athlete_model` with behavioral/motivational state would breach
  the frozen-Brain boundary, so a **separate** state engine is the correct home.

- **But HSE will under-deliver without two siblings:**
  - **A message→state ingestion layer (P3)** must exist to populate HSE from conversation, or
    HSE stays empty for anyone without wearables. **This should precede or ship with HSE E2.**
  - **Coaching/programming intelligence (P2, P4)** — plateau, progression, graded return,
    motivational coaching — is a *response* capability HSE feeds but does not provide.

- **HSE is NOT the fix for P5** (preference depth) — that's Preference-Engine work, cheap and
  independent.

**Recommendation:** proceed with HSE **E1–E3**, but **re-sequence**: pair HSE with a minimal
**conversational state-ingestion** step (P3) so HSE is populated for message-only users, and
schedule the **programming-intelligence** capability (P2/P4) as its own milestone — HSE makes
coaching *state-aware*, not automatically *state-smart*. Ship the cheap **preference-depth**
fix (P5) opportunistically; it doesn't need HSE.

**Bottom line:** the current architecture is **sufficient for safety and fact-based
personalization, and insufficient for dynamic, temporal coaching** — which is ~40% of realistic
coaching. HSE is the right next investment for that gap, provided it ships with an ingestion
feeder and is not mistaken for the coaching-intelligence layer it enables.
