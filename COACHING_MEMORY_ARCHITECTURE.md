# COACHING_MEMORY_ARCHITECTURE.md
## Version 1.0 — Intelligence Phase Design Document

---

> **Status:** Design only. No implementation authorized from this document.
> Implementation requires a formal implementation session with regression matrix defined before any code is committed.
>
> **Authority:** This document operates under APEX_GUARDRAILS.md (constitutional layer).
> All memory operations must be verifiable against the Guardrails.
> Where this document conflicts with the Guardrails, the Guardrails win.

---

## PREMISE

The coaching memory system exists for one purpose: to make Apex more accurate about this specific user over time.

Not more engaging. Not more personalized in the marketing sense. More accurate.

A coach who has worked with someone for six months knows things that cannot be captured in a profile form. They know that this person always underestimates their capability on Mondays. That their recovery degrades faster under work stress than the general population. That 40-minute sessions produce better performance data than 60-minute sessions, even when the user asks for 60 minutes. That they respond to challenge better than they respond to encouragement.

None of these are in the profile. They are observed. They accumulate. They form the difference between a coaching plan built from a questionnaire and a coaching plan built from a relationship.

This document designs the system that creates that accumulation.

---

## GUIDING CONSTRAINTS

Before any design decision: the constraints that override everything.

**Constraint 1 — localStorage only.**
The memory system operates on the client. No server-side storage of coaching state. All memory keys live in `localStorage`. This constrains design — volatile, finite, cross-tab-shared — and every lifecycle rule must account for it.

**Constraint 2 — Never invent data.**
GUARDRAILS §2 and §13 are absolute. If information is missing, the memory system surfaces the gap — it does not fill it with inference. An insight that lacks sufficient evidence does not get promoted to a recommendation. The confidence model enforces this structurally.

**Constraint 3 — Profile integrity.**
GUARDRAILS §3. Memory updates never overwrite explicit profile data. If the user explicitly sets their activity level to "moderate," an adaptive memory observation that suggests they behave like "active" informs the coaching — it does not overwrite the profile field. The two layers are distinct.

**Constraint 4 — Explainability is mandatory.**
Every recommendation influenced by memory must be traceable. The coach must be able to answer "why today?" with specific evidence. If the system cannot produce that explanation, the memory source should not influence the recommendation.

**Constraint 5 — Trust over personalization.**
GUARDRAILS FINAL PRINCIPLE. A memory-driven recommendation that the user cannot understand or trust is worse than a generic recommendation. When in doubt, the system recommends the more conservative, more explainable path — not the maximally personalized one.

---

## MEMORY ARCHITECTURE OVERVIEW

The coaching memory is organized into four storage layers and three derived systems:

```
┌─────────────────────────────────────────────────────────────────┐
│  STORAGE LAYERS                                                   │
│                                                                   │
│  L1: PERMANENT MEMORY      — rarely changes, user-controlled     │
│  L2: ADAPTIVE MEMORY       — evolves through observation         │
│  L3: SESSION MEMORY        — rolling window, recent only         │
│  L4: COACHING INSIGHTS     — derived conclusions, not raw data   │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│  DERIVED SYSTEMS                                                  │
│                                                                   │
│  D1: CONFIDENCE MODEL      — evidence → certainty mapping        │
│  D2: DECISION ENGINE       — memory → recommendation pipeline    │
│  D3: EXPLAINABILITY LAYER  — recommendation → traceable reason   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**localStorage key assignments:**

| Layer | localStorage Key | Controlled by |
|---|---|---|
| L1 Permanent | `apexProfile` | User (explicit save) |
| L2 Adaptive | `apexAdaptiveMemory` | System (observed) |
| L3 Session | `apexWorkoutLog`, `apexHistory` | System (per session) |
| L4 Insights | `apexCoachingInsights` | System (derived) |

---

## LAYER 1 — PERMANENT MEMORY

### 1.1 Definition

Permanent memory contains facts about the user that do not change through coaching — they change only when the user explicitly updates them, or when assessed data overrides self-report.

These are not coaching inferences. They are profile facts.

### 1.2 Fields

| Field | Key | Source | Override Rule |
|---|---|---|---|
| Name | `name` | User-entered | Never auto-update |
| Age | `age` | User-entered | Never auto-update |
| Height | `height` | User-entered | Never auto-update |
| Weight | `weight` | User-entered | User may update anytime |
| Gender | `gender` | User-entered | Never auto-update |
| Primary goal | `goal` | User-selected | User may update; triggers plan recalculation |
| Activity level (declared) | `activityLevel` | User-selected | User may update |
| Training level (declared) | `level` | User-selected | Assessment result may shadow (not overwrite) |
| Training level (measured) | `assessmentLevel` | Assessment result | Populated on assessment completion |
| Equipment constraints | `equipment` | User-selected | User may update |
| Injury/health flags | `injuries` | User-entered | User may update; safety-critical |
| Dietary preferences | `dietaryPrefs` | User-selected | User may update |
| Language | `lang` | System-detected/user-selected | User may change |
| Profile created | `createdAt` | System | Immutable |

### 1.3 Update Rules

- **No memory write may overwrite a Permanent Memory field without explicit user action.**
- Assessment results populate `assessmentLevel` as a separate field — they do not overwrite `level`. The coaching engine uses `assessmentLevel` when it exists; `level` is the fallback.
- Weight is the only biometric field the user is likely to update. When weight updates, the TDEE and protein targets recalculate automatically.
- Injury flags are additive, not replaceable. If the user removes an injury flag, the system logs the removal date in `apexAdaptiveMemory.injuryHistory` for reference — the coaching engine no longer restricts for that injury, but the history is preserved.

### 1.4 Coaching Relationship to Permanent Memory

Permanent memory sets the coaching envelope. The goal field determines the caloric target direction, the protein rate, and the session structure type. The injury fields set hard exclusions from exercise selection. The equipment field constrains what can be recommended.

These are not suggestions. They are constraints that the coaching engine applies before any adaptive layer is consulted.

---

## LAYER 2 — ADAPTIVE MEMORY

### 2.1 Definition

Adaptive memory stores observed patterns about how this specific user behaves — patterns that the profile cannot capture because they emerge through doing.

Adaptive memory is never entered by the user. It is always derived from behavior.

### 2.2 Adaptive Memory Schema

```javascript
apexAdaptiveMemory = {

  // SESSION DURATION PREFERENCE
  sessionDuration: {
    preferredMinutes: null,
    avgShortSessionPerf: null,       // avg energy on sessions <40min
    avgLongSessionPerf: null,        // avg energy on sessions >=45min
    observationCount: 0,
    lastUpdated: null
  },

  // TRAINING TIME PREFERENCE
  trainingTime: {
    preferredHour: null,
    avgPerfByTimeBlock: {
      morning: null,                 // 5am–12pm
      afternoon: null,               // 12pm–5pm
      evening: null                  // 5pm–midnight
    },
    observationCount: 0,
    lastUpdated: null
  },

  // WEEKLY ADHERENCE PATTERN
  weeklyAdherence: {
    byDay: {
      0: { scheduled: 0, completed: 0 },
      1: { scheduled: 0, completed: 0 },
      2: { scheduled: 0, completed: 0 },
      3: { scheduled: 0, completed: 0 },
      4: { scheduled: 0, completed: 0 },
      5: { scheduled: 0, completed: 0 },
      6: { scheduled: 0, completed: 0 }
    },
    strongDays: [],                  // >70% completion rate, min 4 opportunities
    weakDays: [],                    // <40% completion rate, min 4 opportunities
    lastUpdated: null
  },

  // RECOVERY SENSITIVITY
  recoverySensitivity: {
    energyDropOnHighStress: null,
    energyDropOnPoorSleep: null,
    recoveryTimeAfterHard: null,
    baseline: null,
    observationCount: 0,
    lastUpdated: null
  },

  // EXERCISE RESPONSE
  exerciseResponse: {
    highPerformance: [],
    avoidance: [],
    recentSkips: [],                 // [{exerciseName, skipCount, lastSkipped}]
    lastUpdated: null
  },

  // COACHING RESPONSE PATTERN
  coachingResponse: {
    overrideCount: 0,
    overrideOutcomes: [],
    conservativeOutcomes: [],
    autonomyScore: null,             // 0.0–1.0
    lastUpdated: null
  },

  // INJURY HISTORY
  injuryHistory: [
    // { area, firstNoted, lastNoted, resolved, resolvedAt, occurrenceCount }
  ],

  // PROGRESS RATE
  progressRate: {
    avgWeightIncrement: null,
    avgRepIncrement: null,
    plateauLength: null,
    respondsToBetter: null,          // 'volume' | 'intensity' | 'variety'
    observationCount: 0,
    lastUpdated: null
  }

}
```

### 2.3 Update Rules

| Trigger | Fields updated |
|---|---|
| Session completed | `sessionDuration`, `trainingTime`, `weeklyAdherence`, `exerciseResponse` |
| Recovery feedback submitted | `recoverySensitivity` |
| User overrides recommendation | `coachingResponse` |
| User skips scheduled exercise | `exerciseResponse.recentSkips` |
| User resolves injury flag | `injuryHistory` |
| Weight increment applied | `progressRate` |
| Plateau identified | `progressRate.plateauLength` |

**Minimum observations before a field is populated:** 3. Before reaching 3 observations, adaptive memory fields remain `null` and do not influence recommendations.

**Maximum age of adaptive observations:** Fields not updated in 90 days are flagged as stale and do not influence recommendations until refreshed.

### 2.4 Adaptive Memory and Profile Interaction

Adaptive memory never replaces profile data. It runs alongside it.

If the profile states `activityLevel: 'moderate'` but 45 sessions show behavior consistent with 'active,' the coaching engine notes the mismatch and modulates recommendations accordingly — but does not overwrite the profile field. The mismatch is surfaced to the user at the next profile review.

---

## LAYER 3 — SESSION MEMORY

### 3.1 Definition

Session memory is the recent history the coach reads before every session. Not the full log — the relevant window. Most coaching decisions require only the last 4–8 sessions. Session memory defines that window.

**The coaching window:** The last 30 days OR the last 12 sessions, whichever is larger.

### 3.2 Session Memory Fields (per session)

```javascript
{
  sessionId: 'uuid',
  date: 'ISO timestamp',
  dayOfWeek: 0–6,
  duration: minutes,
  exercises: [
    {
      name: 'string',
      sets: number,
      reps: number[],
      weight: number[],
      completedAllSets: boolean
    }
  ],
  perceivedDifficulty: 'easy'|'moderate'|'hard'|'very_hard',
  postWorkoutEnergy: 1–10,
  postWorkoutMotivation: 1–10,
  recoveryNotes: 'string',
  profileFlagsActive: {
    sleep: 'good'|'average'|'poor',
    stress: 'low'|'moderate'|'high'
  },
  coachingState: {
    recoveryColor: 'green'|'yellow'|'red',
    trainingState: 'progress'|'maintain'|'deload',
    recommendationFollowed: boolean
  }
}
```

### 3.3 Derived Signals (computed on demand, never stored separately)

| Derived signal | Source | Used by |
|---|---|---|
| Average post-workout energy (last 3) | `postWorkoutEnergy` × 3 | Recovery State assessment |
| Energy trend (last 3 vs prior 3) | Rolling delta | Recovery State assessment |
| Average motivation (last 3) | `postWorkoutMotivation` × 3 | Recovery State assessment |
| Consistency % (last 30 days) | completed/scheduled | Training State assignment |
| Days since last session | max(date) delta | Gap detection |
| Difficulty trend (last 3) | `perceivedDifficulty` mode | Load assessment |
| Pain language detected | scan of `recoveryNotes` | Safety escalation |
| Volume trend per muscle group | Sets/week rolling | Imbalance detection |

Derived values are computed on demand — not stored — to eliminate synchronization risk.

### 3.4 Missing Session Memory

When the coaching window is empty (new user or data loss):
- Recovery state defaults to Yellow (insufficient data for Green)
- Training state defaults to Conservative Entry
- No adaptive memory influence on first session
- System explicitly acknowledges missing data in coaching output

---

## LAYER 4 — COACHING INSIGHTS

### 4.1 Definition

Coaching insights are the system's conclusions — derived from accumulated observation, elevated above raw data, treated as established facts about this user until contradicted.

**Session Memory records what happened. Coaching Insights records what it means.**

An insight is never entered. It is always promoted from evidence. Evidence accumulates in Layers 2 and 3. When evidence crosses a threshold, the insight is promoted and assigned a confidence score.

### 4.2 Coaching Insights Schema

```javascript
apexCoachingInsights = {
  insights: [
    {
      id: 'uuid',
      type: InsightType,
      claim: 'string',               // plain-language conclusion
      evidence: Evidence[],
      contraEvidence: Evidence[],
      confidence: 0.0–1.0,
      evidenceCount: number,
      contraCount: number,
      status: 'forming'|'active'|'weakening'|'expired',
      createdAt: timestamp,
      lastUpdated: timestamp,
      expiresAt: timestamp|null,
      influencesDecisions: boolean   // false while confidence < 0.5
    }
  ],
  archive: []                        // expired insights — preserved for history
}
```

### 4.3 Insight Types

**DURATION_PREFERENCE**
```
Claim: "Sessions under [N] minutes produce significantly better recovery scores."
Evidence threshold: 6 sessions with duration-performance correlation r > 0.5
Minimum confidence to influence: 0.60
Coaching effect: Session duration capped at preference threshold
```

**DAY_AVOIDANCE**
```
Claim: "[Day] sessions have [N]% adherence — structurally unreliable."
Evidence threshold: 4 scheduled sessions on this day with <40% completion
Minimum confidence to influence: 0.70
Coaching effect: Coach avoids scheduling sessions on flagged days
```

**STRESS_RECOVERY_SENSITIVITY**
```
Claim: "Recovery energy drops [N] points on average when stress flag is active."
Evidence threshold: 5 sessions with stress=high and measured post-workout energy
Minimum confidence to influence: 0.65
Coaching effect: Yellow/Red threshold lowered when stress flag is active
```

**SLEEP_RECOVERY_SENSITIVITY**
```
Claim: "Recovery energy drops [N] points on average when sleep flag is poor."
Evidence threshold: 5 sessions with sleep=poor and measured post-workout energy
Minimum confidence to influence: 0.65
Coaching effect: Yellow/Red threshold lowered when sleep flag is active
```

**EXERCISE_PREFERENCE**
```
Claim: "[Exercise] produces consistently [lower/higher] performance ratings."
Evidence threshold: 4 logged instances with consistent difficulty or skip pattern
Minimum confidence to influence: 0.60
Coaching effect: Exercise deprioritized or prioritized in session design
```

**PROGRESSION_RATE**
```
Claim: "This user responds to [volume/intensity/variety] intervention more effectively."
Evidence threshold: 3 plateau instances with plateau-breaking intervention data
Minimum confidence to influence: 0.70
Coaching effect: Plateau response protocol adjusted to favored intervention type
```

**AUTONOMY_PATTERN**
```
Claim: "This user overrides conservative recommendations with above-average success rate."
Evidence threshold: 5 overrides with measurable outcomes
Minimum confidence to influence: 0.75
Coaching effect: Conservative threshold adjusted; less restriction language
```

**PHASE_DETECTION**
```
Claim: "User has entered Phase [1/2/3] of the transformation arc."
Evidence threshold: Behavioral signals defined in ADAPTIVE_COACHING_ENGINE §13
Minimum confidence to influence: 0.80
Coaching effect: Coaching mode shifts per the canonical mapping
```

---

## DERIVED SYSTEM D1 — CONFIDENCE MODEL

### Confidence Accumulation Rules

```
INITIAL (first qualifying observation):
  confidence = 0.20

GROWTH (each additional consistent observation):
  If current < 0.50: +0.10 per observation
  If current 0.50–0.75: +0.07 per observation
  If current > 0.75: +0.04 per observation (diminishing returns)

CONTRADICTION (each contradicting observation):
  confidence -= 0.12
  Minimum post-contradiction: 0.10
  If contraCount / evidenceCount > 0.40: status → 'weakening'

RAPID CONTRADICTION (3+ contradictions in 5 sessions):
  status → 'expired'; archived

TIME DECAY:
  No supporting observation in 60 days: -0.05/week
  Expires below 0.15
```

### Confidence Thresholds for Action

| Confidence | Status | Coaching Effect |
|---|---|---|
| 0.00–0.19 | Not stored | Observation tracked in adaptive memory only |
| 0.20–0.49 | Forming | Stored; does not influence recommendations |
| 0.50–0.64 | Active (moderate) | Influences soft recommendations |
| 0.65–0.79 | Active (strong) | Influences recommendations; modifies session design |
| 0.80–0.89 | Active (high) | Stated as established pattern |
| 0.90–1.00 | Active (definitive) | Treated as user-specific fact |

### The Non-Invention Guarantee

An insight cannot reach 0.50 (minimum for influence) with fewer than three consistent observations. The confidence model is the structural implementation of GUARDRAILS §2: "Never guess. Never invent."

---

## DERIVED SYSTEM D2 — DECISION ENGINE

### The Pipeline

Every coaching recommendation passes through five stages. No stage may be skipped.

```
STAGE 1: MEMORY ASSEMBLY
  Pull all four layers: who is this person / what patterns / what happened / what concluded

STAGE 2: STATE ASSESSMENT
  Compute Recovery State (Green/Yellow/Red) from Layer 3 signals
  Apply insight-modified thresholds if confidence ≥ 0.65

STAGE 3: HIERARCHY TRAVERSAL
  Apply ACE §5 decision hierarchy: Safety → Recovery → Consistency → Goal → Optimization
  Active insights modulate at each level
  No insight overrides Safety or Recovery state directly

STAGE 4: RECOMMENDATION GENERATION
  Session design from Training State
  Duration from DURATION_PREFERENCE insight (if active)
  Day from WEEKLY_ADHERENCE data (if active)
  Exercise selection avoiding EXERCISE_PREFERENCE:low entries
  Volume from PROGRESSION_RATE insight (if active)
  Mode from PHASE_DETECTION + ACE §13 canonical map

STAGE 5: EVIDENCE PACKAGING
  Every recommendation carries: memory sources cited, confidence scores,
  plain-language explanation, recommendation type (baseline/insight-augmented)
```

### What Insights May and May Not Do

**Insights MAY:**
- Lower or raise energy threshold for Yellow/Red transitions
- Modify preferred session duration
- Deselect specific exercises
- Shift recommended training day
- Adjust plateau-breaking strategy
- Shift coaching mode toward Elite earlier

**Insights MAY NOT:**
- Override a Safety flag
- Override an explicitly set Red recovery state
- Remove an injury-based exercise exclusion from Permanent Memory
- Promote Deload to Progress
- Modify the TDEE calculation

---

## DERIVED SYSTEM D3 — EXPLAINABILITY LAYER

### The Standard

Every coaching output influenced by memory must be answerable to: **"Why are you recommending this today?"**

The Explainability Layer produces two outputs:

**Short Form** — displayed with every recommendation, one sentence:
```
"Shorter session today (35 min) — energy runs 1.8 points higher after sessions under 40 minutes."
```

**Full Form** — produced on "why?" query, full evidence citation:
```
"I'm recommending 35 minutes because of a pattern across your last 11 sessions.
Sessions under 40 minutes: avg energy 7.4/10 (Feb 3, Feb 8, Feb 14, Feb 19, Feb 22, Mar 1).
Sessions over 45 minutes: avg energy 5.6/10 (Jan 29, Feb 11, Feb 25, Mar 4).
The 1.8-point difference is consistent across 5 pairs. I'll recommend 35–40 minutes
until the pattern changes."
```

### Explainability Requirements

1. Every insight-driven recommendation cites the underlying observations — not the insight label, but the actual data.
2. Confidence scores are never shown to the user. They translate to language: "a pattern I've noticed" (0.50–0.65) / "consistently" (0.65–0.80) / "established" (0.80+).
3. Baseline recommendations (no insight applied) cite the decision hierarchy directly.
4. When an insight conflicts with user intent, the tension is named: "Motivation is high. Energy has been declining for 4 sessions."

---

## MEMORY LIFECYCLE

### Creation
First qualifying observation → enters `apexAdaptiveMemory` with `observationCount: 1`. Does not enter `apexCoachingInsights` until confidence reaches 0.20 (3 consistent observations).

### Promotion
When minimum observation count is reached: Insight Evaluator checks evidence consistency → computes initial confidence → creates Insight with `influencesDecisions: false` → promotes to `influencesDecisions: true` at confidence ≥ 0.50.

### Contradiction and Weakening
Contradicting observation → confidence −0.12 → if `contraCount / evidenceCount > 0.40`: status `'weakening'` → if confidence < 0.15: expires.

### Expiry
- **Time decay:** No supporting observation in 60 days → −0.05/week → expires below 0.15.
- **Rapid contradiction:** 3+ contradictions in any 5-session window → expires immediately.
- **User profile goal change:** Expires DURATION_PREFERENCE, PROGRESSION_RATE, EXERCISE_PREFERENCE insights (different goal requires different training patterns).

### Archival
Expired insights move to `apexCoachingInsights.archive[]` with: final confidence, expiry reason, active date range, evidence summary. The archive is consulted as historical context — not as current fact.

---

## CONFLICT RESOLUTION

### Conflict Resolution Hierarchy

```
LEVEL 1 (HIGHEST): Safety — always overrides all memory layers
LEVEL 2: Current recovery state from Session Memory
LEVEL 3: High-confidence active insights (confidence ≥ 0.80)
LEVEL 4: Adaptive memory (confidence 0.50–0.79)
LEVEL 5 (LOWEST): Permanent memory defaults
```

**The critical rule:** No insight, regardless of confidence, can promote a Yellow recovery state to Green or override a Red state. Memory refines the coaching within physiological reality — it does not override physiology.

### The Staleness Override
When an insight is based on observations older than 45 days and a recent contradicting observation exists, the recent observation takes precedence regardless of confidence score. This implements ACE §2.2: recent behavioral data outranks historical pattern.

### Explicit User Override
5 overrides with consistent positive outcomes → AUTONOMY_PATTERN insight begins forming. At 0.75 confidence: coaching recommendations shift to less restrictive framing, harder option presented earlier. The system learns from overrides — it does not punish them.

---

## EXAMPLE USER TIMELINE — DAY 1 TO DAY 180

**User:** Aleksander, 31yo male, 88kg, 181cm, fat_loss, moderate activity, beginner.

---

**DAY 1** — Profile created. Permanent Memory initialized. TDEE: 2,847 kcal. Target: 2,397 kcal. Protein: 158g/day. All adaptive fields null. No insights. Coaching mode: Supportive (Phase 1). Conservative Entry protocol.

**DAY 4** — Session 1: 38 min, Hard, energy 6.1. Session Memory: 1 entry. Adaptive memory observationCount: 1 for duration, weeklyAdherence. No insights yet.

**DAY 8** — Session 2: 42 min, Hard, energy 5.8. Energy trending down (6.1→5.8). Recovery State: Yellow (avg 5.95 borderline, declining trend). Training State: Maintain. No progress this session.

**DAY 12** — Session 3: 35 min (time-constrained), Moderate, energy 7.1. Three duration observations now exist. Insight Evaluator runs. Pattern: shorter session → higher energy. Initial DURATION_PREFERENCE insight created: confidence 0.20, `influencesDecisions: false`.

**DAY 18** — Session 4: 45 min, Hard, energy 5.6. DURATION_PREFERENCE confidence → 0.30. Pattern strengthening. Recovery Yellow again.

**DAY 23** — Session 5: 37 min, Moderate, energy 7.4. DURATION_PREFERENCE confidence → 0.40. Short session avg: 7.25. Long session avg: 5.7. Approaching influence threshold.

**DAY 30** — 5 sessions completed, 1 missed (Wednesday). Adherence 83%. Weekly adherence pattern forming — Wednesday is 0/1. DAY_AVOIDANCE not yet created (needs 4 scheduled instances). DURATION_PREFERENCE still forming (0.40). Phase 1 solid — consistency ≥60%.

**DAY 35** — Session 6: 39 min, energy 7.2. **DURATION_PREFERENCE confidence → 0.50. `influencesDecisions: true`.** First moment memory influences a recommendation. Next session design capped at 35–40 minutes. Short form explanation produced: "Тренировки до 40 минути дават средна енергия 7.2/10. По-дългите — 5.7/10."

**DAY 42** — User overrides duration recommendation, trains 50 min. Energy: 5.3. Override logged. DURATION_PREFERENCE gains a supporting observation (long session, low energy). Confidence → 0.57. `coachingResponse.overrideCount: 1`.

**DAY 58** — Profile updated: stress = high (work deadline). No adaptive memory update — profile change, not behavioral observation.

**DAY 62** — Session under stress flag: 38 min, Hard, energy 5.8 (vs baseline avg 7.2 on short sessions). `recoverySensitivity.energyDropOnHighStress: [1.4]`. observationCount: 1. No insight yet.

**DAY 75** — Stress resolved. Three sessions during stress period: energies 5.8, 5.3, 6.0. Three prior: 7.2, 7.4, 7.1. Delta: 1.53 points. STRESS_RECOVERY_SENSITIVITY insight created: confidence 0.20.

**DAY 90** — 16 sessions in 90 days. Adherence 89%. Avg energy: 6.8/10. DURATION_PREFERENCE: 0.72 (active, strong). STRESS_RECOVERY_SENSITIVITY: 0.30 (forming). Phase 2 signals present: questions shift from "what should I do?" to "am I doing enough sets?" **Phase 1 → Phase 2 transition.** Coaching mode: Balanced. Retrospective surfaced: "16 тренировки за 3 месеца. Вече не питаш какво да правиш — питаш дали правиш достатъчно. Това е различно ниво."

**DAY 105** — Wednesday missed: 5 of 6 scheduled (17%). DAY_AVOIDANCE insight created and activated: confidence 0.72. Schedule stops placing sessions on Wednesdays. Pattern named explicitly.

**DAY 120** — STRESS_RECOVERY_SENSITIVITY reaches 5 observations, confidence 0.68. `influencesDecisions: true`. Yellow/Red threshold now lowers when stress flag is active. Invisible to user — coaching output simply responds more conservatively under stress, explanation cites the specific pattern when relevant.

**DAY 140** — 4 recommendation overrides. Three positive outcomes, one negative (5.4). AUTONOMY_PATTERN: confidence 0.30 (forming). One more successful override approaches influence threshold.

**DAY 155** — Squat load static for 6 sessions. Energy Green, consistency 84%. Plateau detected. `progressRate.plateauLength` not yet populated (first plateau). Default plateau intervention: variety (pause squat, 2 sessions). Sessions 157, 162: energy 7.3, 7.5, Moderate. Weight increases on session 163. `progressRate.respondsToBetter: 'variety'`, observationCount: 1.

**DAY 180** — **Six-month retrospective.**

State:
- 34 sessions / 38 scheduled. Adherence: 89%.
- Avg energy: 6.9/10 (up from 6.1 at month 1).
- Weight: 83.5kg (−4.5kg from 88kg).
- DURATION_PREFERENCE: confidence 0.88 (definitive).
- STRESS_RECOVERY_SENSITIVITY: confidence 0.73 (strong).
- DAY_AVOIDANCE (Wednesday): confidence 0.81 (high).
- PROGRESSION_RATE: 1 of 3 plateau observations (forming).

Phase 3 check: Consistency ≥75% sustained 6+ months ✓. Self-initiated deload at Day 148 without asking ✓. **Phase 2 → Phase 3 transition.**

Coaching mode: Balanced, eligible for Elite.

Retrospective: "34 тренировки за 6 месеца. Енергията след тренировка е нараснала от 6.1 на 6.9/10. Теглото е 83.5кг — 4.5кг по-малко. Взе сам решение за deload седмица на Ден 148 — без да питаш. Следващият въпрос не е дали да тренираш, а какво искаш да направиш с тази основа."

Horizon Expansion offered: "3 тренировки/седмица са стабилни от 6 месеца. Готов си да мислиш за четвърта — но първо: какво не ти дават сегашните три?"

---

## INTEGRATION WITH EXISTING DOCUMENTS

| Document | Relationship to Memory Architecture |
|---|---|
| `APEX_GUARDRAILS.md` | Constitutional authority. §2 (never guess) is the foundation of the confidence model. §3 (profile integrity) governs the L1/L2 separation. |
| `ADAPTIVE_COACHING_ENGINE.md` | The ACE §5 decision hierarchy is the framework into which memory is injected at Stage 4. Recovery State definitions (ACE §3) are what STRESS/SLEEP_RECOVERY_SENSITIVITY insights modulate. The ACE §13 canonical mapping governs mode transitions triggered by PHASE_DETECTION. |
| `APEX_PERSONALITY.md` | The Explainability Layer produces output in Apex voice. Confidence-to-certainty translation ensures insight-driven recommendations sound like a coach speaking from evidence. |
| `APEX_MOTIVATION_SYSTEM.md` | PHASE_DETECTION maps to the Transformation Arc (AMS §3). Progress Evidence (AMS §4.2) is powered by Session Memory. Pattern Recognition (AMS §4.4) requires minimum 4 weeks of consistent memory data. |

---

## WHAT THIS SYSTEM IS NOT

**Not chat memory.** The system remembers what the user did through their body — how hard they trained, how well they recovered, which days they showed up. Not what they said.

**Not LLM context.** Insights are structured data. The LLM consumes them as structured inputs, not conversation history.

**Not an engagement engine.** A DAY_AVOIDANCE insight that results in fewer session recommendations on Wednesday is a success. Fewer bad sessions is better coaching.

**Not dependent on perfect data.** Missing data defaults to conservative behavior. The system becomes more precise as evidence accumulates — it does not malfunction when data is sparse.

---

*Version 1.0 — 2026-06-27*
*Design only. No implementation authorized from this document.*
*Constitutional authority: APEX_GUARDRAILS.md*
