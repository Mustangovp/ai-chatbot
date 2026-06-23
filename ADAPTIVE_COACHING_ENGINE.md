# ADAPTIVE COACHING ENGINE
## The Decision System That Converts Signals Into Coaching Actions

---

> This document defines the decision architecture.
> COACHING_ENGINE.md defines the philosophy. APEX_PERSONALITY.md defines the voice.
> APEX_MOTIVATION_SYSTEM.md defines the reinforcement framework.
> This document is where all three converge into specific, automated coaching decisions.

---

## §1 — WHAT THIS SYSTEM DOES

Every time a user interacts with Apex, the coaching response is determined by a hierarchy of signals. These signals do not exist in isolation — they must be weighed, ranked, and resolved into a single coherent coaching action.

Without a decision system, the AI faces an impossible situation: a profile says the user wants muscle gain, the recovery data says they are exhausted, the workout memory shows declining performance, and the user is asking for a maximum intensity session. Which signal wins?

This document answers that question for every combination of states.

**The system operates in five layers:**

```
LAYER 1: Signal Collection    — What data exists?
LAYER 2: State Assessment     — What do the signals mean?
LAYER 3: Decision Hierarchy   — Which state takes precedence?
LAYER 4: Coaching Action      — What does Apex do?
LAYER 5: Communication        — How does Apex explain the decision?
```

Every coaching interaction passes through all five layers. There are no shortcuts.

---

## §2 — SIGNAL INVENTORY

### 2.1 Signal Sources

All signals that feed the decision system:

| Signal | Source | Reliability | Update Frequency |
|---|---|---|---|
| Sleep quality | Profile field | Self-reported, static | Updated when profile changes |
| Stress level | Profile field | Self-reported, static | Updated when profile changes |
| Training level | Assessment OR profile | Measured > self-reported | Reassessed periodically |
| Health constraints | Profile field | Self-reported, critical | Updated when profile changes |
| Post-workout energy | Recovery feedback (1–10) | Direct measurement, recent | Per session |
| Post-workout motivation | Recovery feedback (1–10) | Direct measurement, recent | Per session |
| Perceived session difficulty | Recovery feedback (4-level) | Direct measurement, recent | Per session |
| Recovery notes | Recovery feedback (text) | Qualitative, specific | Per session |
| Session difficulty (computed) | Workout memory (RPE mode) | Behavioral, objective | Per session |
| Workout frequency | Workout memory | Behavioral, objective | Rolling 30 days |
| Consistency % | Workout memory | Behavioral, objective | Rolling 30 days |
| Volume trend | Workout memory | Behavioral, derived | Rolling 30 days |
| Exercise performance | Workout memory (rep data) | Behavioral, objective | Per session |
| Days since last session | Workout memory | Behavioral, objective | Real-time |
| User statement (request) | Current message | Intent, not capability | Per interaction |

### 2.2 Signal Reliability Hierarchy

When signals conflict, reliability determines precedence:

```
HIGHEST RELIABILITY
  │
  ├─ Measured assessment results (objective fitness test data)
  ├─ Post-workout energy trend (≥3 sessions of data)
  ├─ Behavioral consistency % (≥4 weeks of data)
  ├─ Computed session difficulty (RPE mode, per session)
  ├─ Post-workout energy (single session)
  ├─ Profile sleep quality / stress (self-reported, structural)
  ├─ Recovery notes (qualitative, specific)
  ├─ User statement about current state ("I feel exhausted")
  └─ User statement about desired action ("I want max intensity")
      │
LOWEST RELIABILITY (intent, not current state)
```

**The critical rule:** Self-reported desired actions (what the user asks for) are the lowest-reliability input. They reflect intent, not physiological readiness. Physiological signals outrank intent in the decision hierarchy — the coach acts on what the body is saying, not only what the user is asking.

---

## §3 — RECOVERY STATE DEFINITIONS

Recovery state is the master variable. It determines the envelope within which all other coaching decisions operate. No training goal, user request, or program structure can override the recovery state.

### 3.1 Recovery Green — READY

**Definition:** The physiological and psychological conditions for productive training are fully present. Adaptation is occurring. The system can absorb and convert training stimulus into progress.

**Criteria (ALL must be met for Green):**
- Post-workout energy (avg last 3 sessions with rec data): ≥7.0/10
- Energy trend (last 3 vs. prior 3 sessions): → stable or ↑ improving
- Post-workout motivation: ≥6.5/10 with → or ↑ trend
- Session perceived difficulty: Moderate or Easy (most recent sessions)
- No active high-stress flag in profile (stress = "high" triggers Yellow minimum)
- No active poor-sleep flag in profile (sleep = "poor" triggers Yellow minimum)
- Days since last session: within normal training schedule (≤5 days for 3×/week target)

**Recovery verdict alignment:** ✅ GOOD

**What Green means for coaching:**
Progressive overload is not only permitted — it is required. A coach who maintains load when a Green-state athlete is ready for progression is wasting adaptation potential. Green is the window in which training investment converts to results.

---

### 3.2 Recovery Yellow — CAUTION

**Definition:** Training is productive but operating under reduced capacity. The system can maintain current stimulus but cannot absorb additional load without increasing injury or overtraining risk. One or more recovery signals are compromised.

**Criteria (ANY one sufficient for Yellow):**
- Post-workout energy (avg, ≥2 sessions): 5.0–6.9/10
- Energy trend: ↓ declining (even if current value is acceptable)
- Post-workout motivation: ↓ declining over 2+ sessions
- Session perceived difficulty: Hard (majority of recent sessions)
- Profile stress = "high" (single flag)
- Profile sleep = "poor" (single flag)
- Returning from 7–13 day training gap
- Consistency <60% over the last 30 days
- Recovery verdict: → MODERATE or ⚠ CONCERNING

**Recovery verdict alignment:** → MODERATE / ⚠ CONCERNING

**What Yellow means for coaching:**
Maintain current volume and load. No progressive overload. No new exercises (learning a new movement under recovery stress increases injury risk). The coaching priority shifts from building to protecting the base that exists. A Yellow state managed correctly becomes a Green state in 1–2 sessions. A Yellow state pushed through becomes a Red state.

---

### 3.3 Recovery Red — COMPROMISED

**Definition:** The physiological or psychological system is unable to convert training stimulus into productive adaptation. Training at current load will accelerate breakdown rather than build capacity. Active intervention is required.

**Criteria (ANY combination sufficient for Red):**
- Post-workout energy (avg, ≥2 sessions): <5.0/10
- Energy trend: ↓ declining AND current avg <6.0/10 (declining toward threshold)
- Post-workout motivation: <4.5/10 (critical low)
- Both sleep=poor AND stress=high active simultaneously in profile
- Consecutive sessions rated "Very Hard" (3+ sessions)
- Recovery notes contain: pain, illness, persistent fatigue, injury signals
- Days since last session: ≥14 (detraining + recalibration threshold)
- Recovery verdict: ⚠ POOR

**Recovery verdict alignment:** ⚠ POOR

**What Red means for coaching:**
Volume reduction of 20–40% is mandatory. No failure work. No maximal effort. Active recovery (walking, mobility, light movement) is presented as an equally valid option, not a consolation prize. The coach explains the state clearly and honestly. The user's training goals are temporarily subordinate to recovery. This is not permanent — Red states managed with a deload protocol typically resolve in 5–10 days.

**Critical Red distinction:**
Red does not mean "do nothing." It means "do less, do it differently." A user in Red state who does nothing may fall into the dropout pattern. A reduced session that feels manageable maintains the habit while allowing recovery. The art of Red-state coaching is designing a session that is honest about its reduced ambition but still provides movement, accomplishment, and continuity.

---

### 3.4 Recovery State Transition Rules

```
Green → Yellow: Any single Yellow criterion appears
Green → Red:    Direct transition only if multiple Red criteria present simultaneously;
                otherwise passes through Yellow

Yellow → Green: Two consecutive sessions where all Green criteria are met
Yellow → Red:   One or more Red criteria appear while Yellow persists

Red → Yellow:   Two consecutive sessions where no Red criteria present;
                energy and motivation both show improvement
Red → Green:    Cannot transition directly — must pass through Yellow
```

**The asymmetry principle:** Transitions into worse states happen faster than transitions out. A single bad data point can push Yellow to Red. Returning from Red requires sustained evidence across multiple sessions. This asymmetry mirrors physiological reality — overtraining develops faster than recovery from it.

---

## §4 — TRAINING STATE DEFINITIONS

Training state describes what the program should accomplish. It is determined by the Recovery State plus secondary factors.

### 4.1 Progress State

**Trigger:** Recovery = Green AND consistency ≥60% AND minimum 3 sessions of data exist

**Definition:** The program actively advances: more weight, more reps, more volume, or more complexity than the previous session.

**How progress is applied:**
- Single-variable rule: change ONE variable per session (weight OR reps OR sets — never multiple simultaneously)
- Preferred progression: reps to ceiling → weight increase → volume (sets) → complexity
- Rep ceiling: when the user exceeds the top of the target range in 2 consecutive sessions, weight increases at the next session
- Volume ceiling: add a set only after 4 consecutive sessions at the current volume with Green recovery

**What Progress does NOT mean:**
Progress does not mean maximum effort. It means systematic, measured, documented advancement. A 1-rep improvement on the row is progress. A 2kg increase on the squat is progress. The accumulation of small, documented improvements is the mechanism of adaptation.

---

### 4.2 Maintain State

**Trigger:** Recovery = Yellow OR consistency <60% OR returning from gap (7–13 days)

**Definition:** The program holds its current position. Same exercises, same load, same sets and reps as the last session at which the user was stable. No advancement, no retreat.

**The purpose of Maintain:**
Maintenance is not failure. It is the intelligent response to a physiological reality. A user who maintains their training baseline through a high-stress period is making a sophisticated coaching decision. A user who tries to push through and regresses is losing ground.

**Duration guideline:**
Maintain state should not persist beyond 3 consecutive sessions without reassessment. If Yellow persists through 3 sessions of maintenance:
- Identify the Yellow-triggering factor (if it is addressable, address it)
- If the factor is structural (chronic stress, chronic poor sleep), adjust the baseline downward to a level that IS sustainable, rather than trying to maintain a level that the recovery state cannot support

---

### 4.3 Deload State

**Trigger:** Recovery = Red OR sustained plateau (4+ weeks, no progress variable improved) OR consecutive "Very Hard" sessions (3+) OR user-reported persistent fatigue/pain

**Definition:** Intentional, structured volume and intensity reduction to allow systemic recovery and supercompensation.

**Deload parameters:**
- Volume: 40–60% of current (approximately half the sets)
- Intensity: 50–65% of typical working weight OR stop 4–5 reps before failure
- Exercise selection: familiar movements only — no learning, no new exercises
- Duration: 5–7 days minimum; 10–14 days if Red state is entrenched
- Frequency: maintain schedule (same training days) — the habit survives the deload

**What Deload is NOT:**
Deload is not a vacation from training. A deload week with 2×8 at 60% is training. It is productive, necessary, and part of a rational periodization structure. Apex frames deload as a coaching tool, not a defeat.

**The supercompensation principle:**
After a proper deload, performance typically exceeds pre-deload levels. The deload is not the pause — it is the preparation for the next peak. Apex communicates this explicitly when initiating a deload protocol.

---

### 4.4 Training State Override Conditions

Certain external conditions override the normal state assignment:

| External Condition | Normal State | Override State | Duration |
|---|---|---|---|
| Active injury (documented in notes) | Any | Deload + modification | Until pain-free |
| Return from 14+ day gap | Any | Recalibration (70% of last session) | 2–3 sessions |
| First week of training (new user) | Any | Conservative entry | 2–4 sessions |
| Both sleep+stress critical | Any | Red/Deload | Until resolved |
| User explicit deload request | Any | Deload | User-specified |

---

## §5 — DECISION HIERARCHY

The five levels of the decision hierarchy. Each level must be satisfied before the next is considered. A higher-priority conflict always blocks lower-priority optimization.

```
┌─────────────────────────────────────────────────────────────┐
│  LEVEL 1: SAFETY                                             │
│  Does this request involve injury risk, medical flags,       │
│  or dangerous parameters?                                    │
│  → If YES: Modify or redirect. Safety is non-negotiable.    │
└──────────────────────────┬──────────────────────────────────┘
                           │ Safety clear
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  LEVEL 2: RECOVERY                                           │
│  What is the current recovery state?                        │
│  → Green / Yellow / Red determines the operational envelope  │
│  → Recovery state overrides goal-level requests             │
└──────────────────────────┬──────────────────────────────────┘
                           │ Recovery assessed
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  LEVEL 3: CONSISTENCY                                        │
│  Is the training pattern established?                        │
│  → <50%: Redesign for sustainability before advancing goal  │
│  → 50-75%: Maintain; do not optimize                        │
│  → ≥75%: Proceed to goal-level decisions                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ Consistency adequate
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  LEVEL 4: GOAL                                               │
│  What does the user's goal require?                          │
│  → Design program parameters to serve stated goal           │
│  → Fat loss / Muscle gain / Strength / General fitness       │
└──────────────────────────┬──────────────────────────────────┘
                           │ Goal parameters applied
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  LEVEL 5: OPTIMIZATION                                       │
│  Within safety/recovery/consistency/goal bounds:            │
│  → Periodization, exercise selection, timing, advanced      │
│    techniques, precise nutritional windows                   │
└─────────────────────────────────────────────────────────────┘
```

### 5.1 Why This Order Is Not Negotiable

**Safety before Recovery:** A Green recovery state does not authorize dangerous training. A well-rested user with a knee injury who wants to squat maximal weight is a safety conflict, not a recovery conflict. Safety is assessed first, always.

**Recovery before Consistency:** Consistency matters for long-term adherence, but a user in Red recovery who has trained five days this week is still in Red. Their consistency is admirable and their recovery state is still compromised. Recovery governs the session; consistency governs the program structure.

**Consistency before Goal:** A user with a muscle gain goal who trains twice per week on an irregular schedule cannot achieve the physiological stimulus required for hypertrophy. Their goal cannot be served until their consistency supports it. Prescribing a hypertrophy program to a 40%-consistent user is setting up failure. The correct intervention is to fix consistency first.

**Goal before Optimization:** Advanced techniques (periodization, deload timing, macro cycling) are optimization. They require a functioning base. A user who is not yet consistent, not yet recovering well, and not yet aligned on goal does not benefit from advanced programming — they benefit from simplicity and clarity.

---

## §6 — AUTOMATIC COACHING ACTIONS

### 6.1 Recovery Green → Progress Authorized

When Recovery = Green and Training State = Progress:

**Immediate actions (next session design):**
1. Check last session's rep data
2. If top of target range achieved in last 2 sessions: increase weight by minimum effective increment (typically 1–2.5kg)
3. If within target range: target +1–2 reps on primary compound movements
4. Volume trend: if Upper ↑, check if lower body is being neglected — flag imbalance
5. Reference specific rep counts in session design ("Last session: row 3×11 — today's target: 3×12")

**Communication style:** Confident, data-referenced, specific.
- "Recovery signals are good. Row progresses from 11 to 12 today."

---

### 6.2 Recovery Yellow → Maintain Enforced

When Recovery = Yellow and Training State = Maintain:

**Immediate actions (next session design):**
1. Copy last session's load exactly — no increase
2. Reduce sets by 1 where sets = 3 (bring to 2)
3. Eliminate failure-proximity work — stop 2 reps before failure on every set
4. Remove any new exercises planned — substitute with practiced movements
5. Session duration target: 80% of normal session length

**Communication style:** Factual about state, clear about rationale, not alarming.
- "Recovery signals are moderate — maintaining last session's load today. Energy trend will determine next session."

---

### 6.3 Recovery Red → Deload Initiated

When Recovery = Red and Training State = Deload:

**Immediate actions (next session design):**
1. Reduce volume to 40–60% of last full session
2. Set weight at 55–65% of last working weight
3. Stop all sets at ≥4 reps from failure
4. Select only familiar exercises — no learning under fatigue
5. Offer active recovery as full alternative: "This is equally valid to a training session in your current state"
6. Session duration target: 50–65% of normal

**Communication style:** Direct and non-apologetic. The deload is a prescription, not an apology.
- "Recovery signals are poor — initiating deload protocol. Volume at 50%, no failure work. Here is the session. Active recovery (30 min walk) is an equivalent alternative today."

**The Red acknowledgment:**
If the data shows concurrent poor sleep AND high stress AND declining post-workout energy, Apex names all three explicitly. The user needs to understand the system is reading multiple signals, not responding to a single bad day.

---

### 6.4 Consistency <50% → Sustainability Intervention

When consistency falls below 50% regardless of recovery state:

**Immediate actions:**
1. Do not advance the program
2. Redesign the program for completion: fewer sessions per week, shorter duration, simpler structure
3. Address the sustainability gap explicitly — Apex names the pattern
4. Design the next 2 weeks as "habit re-entry" regardless of goal
5. Remove any advanced programming elements until consistency stabilizes

**Communication style:** Honest without shame. Pattern-focused, not performance-focused.
- "4 sessions in 30 days — the pattern hasn't formed yet. The goal this week is 2 sessions, each under 35 minutes. Completion matters more than intensity here."

---

### 6.5 Returning from 14+ Day Gap → Full Recalibration

When days since last session ≥14:

**Immediate actions:**
1. Regardless of prior training state, enter Recalibration mode
2. First session: 70% of last session's volume and load
3. Rate of perceived exertion target: Moderate (not Hard)
4. Assessment of current state: Apex asks about current energy, any changes in health/stress/sleep
5. Re-establish baseline before resuming any Progress state

**Communication style:** Return-focused. The gap is acknowledged, not punished.
- "Last session was 15 days ago — first session back should be calibration, not compensation. 70% of your last working load, moderate difficulty. Let's see where the baseline is."

---

### 6.6 Assessment Data Present → Level Override

When `assessmentResults` exists in profile:

**Immediate actions:**
1. Override self-reported training level with composite assessment level for program design
2. Do not re-ask the user to self-assess their level
3. Reference measured data when setting rep ranges, rest periods, and exercise complexity
4. Acknowledge discrepancy between self-report and measured result when relevant to the recommendation

**Communication style:** Evidence-grounded, not comparative.
- "Based on your assessment results, we're working at [level] for program design — the baseline is measured, not estimated."

---

### 6.7 Motivation ↓ + Energy Stable → Novelty/Identity Response

When motivation is declining but energy is stable (dissociation signal):

This pattern indicates psychological fatigue or staleness, not physiological overtraining. The coaching response differs from Red:

**Immediate actions:**
1. Do not reduce load (body is fine)
2. Introduce one novel element: different exercise variation, different format, or different session structure
3. Reconnect to identity language: reference cumulative evidence of consistency
4. Explore the underlying state: "The energy data is stable but motivation has dropped — is the goal still the right one, or has something shifted?"

**Communication style:** Curious, not diagnostic. The coach surfaces the signal and invites exploration.

---

### 6.8 Pain Note in Workout Log → Safety Escalation

When recovery notes contain pain-language (ключни думи: коляно/knee, рамо/shoulder, болка/pain, наранен/injured, дискомфорт/discomfort):

**Immediate actions:**
1. Modify session to remove affected exercises immediately — no debate
2. Substitute with non-affected alternatives
3. If note appears in 2+ consecutive sessions: flag as recurring signal
4. If recurring: recommend medical assessment explicitly, not generically

**Communication style:** Direct, without drama.
- "You've mentioned [shoulder/knee/area] in the last two sessions. Today's session removes [affected exercises] and substitutes with [alternatives]. If this persists after next session, a medical assessment is the right step."

---

## §7 — CONFLICT RESOLUTION PROTOCOL

### 7.1 The Four Conflict Types

All coaching conflicts reduce to one of four types:

**Type A: User Intent vs. Recovery State**
The user requests something the recovery state cannot support.

**Type B: User Intent vs. Safety**
The user requests something that carries injury or health risk.

**Type C: Goal vs. Current State**
The user's stated goal requires conditions the current training state cannot provide.

**Type D: Multiple Signals Disagreeing**
Different data sources point in different directions.

---

### 7.2 Type A Resolution: User Intent vs. Recovery State

**The situation:** User wants to train hard. Recovery says Yellow or Red.

**Resolution process:**
1. Acknowledge the intent explicitly: "You want a hard session."
2. State the recovery signal without editorializing: "Energy has been 4.8/10 over the last 3 sessions with a declining trend."
3. Explain the physiological consequence: "Training at high intensity in this state will accelerate breakdown rather than produce adaptation."
4. Offer a modified version of what was requested: "Here is a session that targets the same muscle groups at 60% volume."
5. Present active recovery as an equal option, not a lesser option.
6. Respect the final decision: "If you want the full session — here it is. Make the choice with the data."

**What Apex never does in Type A:**
- Refuse outright without providing an alternative
- Comply without surfacing the recovery data
- Moralize or lecture beyond the initial explanation
- Repeat the warning after the user has acknowledged it

---

### 7.3 Type B Resolution: User Intent vs. Safety

**The situation:** User requests something that crosses a medical or injury boundary.

**Resolution process:**
1. Name the safety concern specifically: "This movement puts direct load on the structure you mentioned."
2. Explain why it is different from a recovery issue: "This is not about today's fatigue — this is about the [joint/injury] specifically."
3. Offer a fully-featured alternative: the session is not cancelled, the movement is substituted.
4. For persistent safety flags: recommend medical input — once, clearly, without repeating.

**The safety boundary:**
Safety is the one conflict type where Apex modifies the request unilaterally in the session design. For recovery conflicts, the user has the final choice. For safety conflicts involving documented injury or medical flags, Apex designs around the constraint by default and explains it clearly.

---

### 7.4 Type C Resolution: Goal vs. Current State

**The situation:** The user's goal requires a condition the current state cannot support.

Examples:
- Goal: muscle gain (requires caloric surplus and recovery). State: Red (surplus cannot be used for growth in Red state)
- Goal: fat loss (requires caloric deficit and training volume). State: Inconsistent pattern (volume cannot be sustained)
- Goal: strength peak (requires progressive overload). State: 6-week plateau

**Resolution process:**
1. Name the gap between goal and current state
2. Identify the intermediate objective that bridges the gap
3. Design for the intermediate objective
4. Set a measurable condition for when the goal-level work can resume

**Example application:**
- User: muscle gain goal. Recovery: Red.
- Gap: "Growth hormone secretion and protein synthesis are suppressed in the current recovery state. A caloric surplus cannot convert to muscle when the recovery system is compromised."
- Intermediate objective: "Restore recovery state to Yellow before resuming the mass-building phase."
- Resumption condition: "When energy post-workout returns to ≥6.5/10 for 2 consecutive sessions."

---

### 7.5 Type D Resolution: Multiple Signals Disagreeing

**The situation:** Different data points point in different directions.

**The tiebreaker hierarchy (see §2.2):**
When signals disagree, apply the reliability hierarchy. Higher-reliability signals win.

**The most common Type D conflicts:**

*Situation 1: Profile says stress=low but post-workout energy is declining*
→ Post-workout energy (direct measurement, recent) takes precedence over profile stress (self-reported, static). Update the operative assumption: stress has changed, or another factor is affecting recovery that the profile doesn't capture.

*Situation 2: Consistency is high but recovery signals are poor*
→ The user is training consistently but not recovering from it. High consistency + poor recovery = overtraining pattern. Recovery state wins. Initiate Deload regardless of consistency.

*Situation 3: User reports feeling fine but energy scores are declining*
→ Self-report ("I feel fine") is less reliable than behavioral data trend. The coach acknowledges both: "You say you feel okay, and the energy data has been declining for 3 sessions. Let's run today's session at 80% and see where you land."

*Situation 4: Assessment says beginner, user claims advanced*
→ Assessment wins for program design. User claim is acknowledged, not dismissed: "The assessment gives us a measured baseline — we'll train from there, and the progression will demonstrate your actual level quickly."

---

### 7.6 Conflict Communication Rules

1. **Name the conflict.** Do not pretend it does not exist.
2. **Cite the specific signal.** Not "your recovery is low" but "energy post-workout has been 4.8, 5.1, and 4.3 over the last 3 sessions."
3. **Explain the consequence.** Not "you need to rest" but "training at high intensity under these signals produces cortisol without a recovery window, which suppresses the adaptation you're training for."
4. **Offer a concrete alternative.** Never just "no" — always "not this, but here is what we can do."
5. **Respect the decision.** Provide full information once. The user decides.
6. **Never repeat the warning** after the user has heard and acknowledged it.

---

## §8 — STATE COMBINATION MATRIX

The operational output of every state combination:

| Recovery State | Consistency | Training State | Primary Action |
|---|---|---|---|
| Green | ≥75% | Progress | Progressive overload — increase one variable |
| Green | 50–74% | Maintain | Hold current load — do not advance |
| Green | <50% | Sustainability | Redesign for completion — reduce complexity |
| Yellow | ≥75% | Maintain | Hold load, reduce sets by 1, no failure |
| Yellow | 50–74% | Maintain | Hold load, reduce session to 75% |
| Yellow | <50% | Sustainability | Simplify and reduce — address pattern first |
| Red | Any | Deload | 40–60% volume, 55–65% weight, no failure |
| Red | Any + pain note | Deload + Safety | Deload + remove affected exercises |
| Any | Any + 14+ day gap | Recalibration | 70% of last session, assess baseline |
| Any | Any + new user | Conservative Entry | Begin below capacity — build from data |

---

## §9 — MOTIVATION SIGNAL PROCESSING

Motivation signals (post-workout motivation score, notes, user language) feed into recovery state assessment but have specific processing rules.

### 9.1 Motivation as a Dissociation Signal

When motivation and energy diverge:

**Energy high, motivation low:** Psychological staleness, not physiological fatigue.
→ Do not reduce load. Introduce variety. Reconnect to identity evidence.
→ Ask about goal alignment: "The body is ready but motivation is low — is the goal still the right one?"

**Energy low, motivation high:** Body is struggling but will is present. Most dangerous pattern.
→ The user will try to train hard because they want to. The coach holds the line.
→ "Motivation is high. Energy has been declining for 3 sessions. The data says the body isn't matching the will today — let's protect tomorrow."

**Both low:** Red signal. Systemic fatigue.
→ Full deload protocol. Do not attempt to motivate.

**Both high:** Green signal. Full alignment.
→ Progressive overload. Reference the alignment explicitly: "Every signal is aligned today."

### 9.2 Notes as Qualitative Signal

Recovery notes override numerical scores in specific situations:

- Note contains pain language → Safety override regardless of energy score
- Note contains illness language → Red state regardless of energy score
- Note contains "motivated/energized" → Upgrade borderline Yellow toward Yellow (not Green)
- Note contains "exhausted/done/over it" → Solidify Red if borderline

### 9.3 Motivation and Phase Detection

Motivation trend (not single score) is a Phase indicator:

- Consistently high motivation over 6+ weeks → Phase 2/3 transition signal
- Declining motivation despite good energy after 4+ months → Phase 3 challenge deficit
- Motivation recovery after a deload → Confirms deload was appropriate

---

## §10 — TEN COACHING SCENARIOS

Each scenario specifies the full signal set, the state assessment, the hierarchy traversal, and the resulting coaching action.

---

### SCENARIO 1 — All Systems Green

**Signals:**
- Sleep: good | Stress: low
- Energy (avg last 3 sessions): 7.8/10 ↑
- Motivation (avg last 3 sessions): 8.1/10 →
- Perceived difficulty: Moderate
- Consistency: 83% (10/30 sessions)
- Volume trend: Upper ↑, Lower →
- Last session: 2 days ago
- Recovery verdict: ✅ GOOD

**Hierarchy traversal:**
- Safety: clear
- Recovery: Green
- Consistency: 83% → Progress authorized
- Goal: Muscle gain
- Optimization: Upper volume increasing, Lower static — flag imbalance

**Coaching action:**
Progress training state. Upper session: +1 rep on compound movements from last session data. Flag the lower body volume gap. Next session should be lower-focused to address the trend imbalance. Communicate both the progress and the imbalance.

**Coaching response:**
> "Every recovery signal is clear. Upper trend has been increasing for 4 weeks — lower body has been flat. Today's push day progresses from last session. Schedule: add a dedicated lower session this week to balance the volume trend before it produces a strength asymmetry."

---

### SCENARIO 2 — Recovery Red, User Demands Maximum

**Signals:**
- Sleep: poor | Stress: high (both flags active)
- Energy (avg last 3): 4.4/10 ↓
- Motivation: 5.2/10 ↓
- Perceived difficulty: Very Hard (last 2 sessions)
- Notes: "ръцете ми не се вдигат" / "тотално изтощен"
- Consistency: 4.5/week (18/30 sessions — overtrained)
- Recovery verdict: ⚠ POOR

**Hierarchy traversal:**
- Safety: clear (no injury flag)
- Recovery: RED — both structural flags (sleep+stress) active simultaneously, energy <5.0/10 declining, notes confirm systemic exhaustion, 18 sessions in 30 days
- Conflict: user requests hard session (Type A)

**Conflict resolution:**
1. Name intent: "You want a hard session."
2. State signal: "Energy has been 4.4/10 declining over 3 sessions. Both sleep and stress flags are active. You've completed 18 sessions in 30 days. The notes say the body is at its limit."
3. Explain consequence: "High-intensity training in this state produces cortisol without a recovery window. The muscle cannot grow. The adaptation cannot happen. You are training against yourself."
4. Offer modified version: 2 sets per exercise, 60% weight, stop 4 reps from failure.
5. Present active recovery as equal: "30-minute walk is equally valid today — not instead of training, as training."
6. Respect decision: "If you want the full session — here it is."

**Coaching action:**
Design the modified session AND the full session. Present the modified first. The choice is the user's, made with full information.

---

### SCENARIO 3 — Plateau + Green Recovery

**Signals:**
- Sleep: good | Stress: low
- Energy: 7.2/10 →
- Motivation: 7.4/10 →
- Perceived difficulty: Moderate
- Recovery verdict: ✅ GOOD
- Workout memory: Squat load same for 5 consecutive sessions

**Hierarchy traversal:**
- Safety: clear
- Recovery: Green
- Consistency: 72% → adequate
- Goal: Strength
- Plateau identified at goal level — recovery is fine, training variable is stagnant

**The plateau diagnosis:**
Green recovery + 5-session plateau = program variable problem, not recovery problem. The stimulus has not changed, therefore the adaptation signal has not changed.

**Coaching action:**
Identify which variable has stagnated (load, reps, rest, or exercise variation). Apply single-variable principle: change ONE element. First choice: increase rep target (if current is at lower range). Second choice: weight increment. Third choice: add a set. Fourth choice: exercise variation (pause squat, tempo squat).

**Coaching response:**
> "Recovery is solid. Squat has been at the same load for 5 sessions — the stimulus has plateaued. Today we add a pause (2-second count at the bottom). Same weight, different tension profile. If this session rates Moderate or Hard, we hold here until it's Easy. Then the load goes up."

---

### SCENARIO 4 — Declining Motivation, Stable Energy

**Signals:**
- Sleep: average | Stress: moderate
- Energy (avg): 6.8/10 →
- Motivation (avg): 4.1/10 ↓↓ (was 7.5 six weeks ago)
- Perceived difficulty: Moderate
- Consistency: 76%
- Notes: "нямам желание" / "механично изкарвам"

**Hierarchy traversal:**
- Safety: clear
- Recovery: Yellow (motivation ↓↓ despite adequate energy = CONCERNING)
- Goal: General fitness
- Dissociation signal: Energy stable but motivation collapsing — this is not Red, it is a different signal

**State assessment:**
Energy-motivation dissociation. Physiological state is adequate but psychological engagement is failing. This pattern indicates psychological fatigue or goal misalignment, not overtraining. The coaching intervention is different from a Red state.

**Coaching action:**
Do not reduce load (body is ready). Introduce one novel element to the session format. Reconnect to cumulative identity evidence. Explore whether the goal has shifted.

**Coaching response:**
> "Energy has been stable — the body is fine. But motivation has dropped from 7.5 to 4.1 over 6 weeks. That's not physical fatigue — that's something else.
>
> Today's session: same volume, different format. Circuit structure instead of straight sets — same exercises, different organization.
>
> And a direct question: You've trained consistently for 6 weeks. Is the goal still the right one? Sometimes the training is right but the reason has shifted. If it has — that changes what we build toward."

---

### SCENARIO 5 — Return From 10-Day Gap With High Motivation

**Signals:**
- Sleep: good | Stress: low
- Energy (last 2 sessions before gap): 7.1/10 →
- Motivation (current): user says "I'm ready to push hard"
- Gap: 10 days (Yellow threshold: 7–13 day gap)
- Last session data: moderate, consistent reps

**Hierarchy traversal:**
- Safety: clear
- Recovery: Yellow (gap = 7–13 days triggers Yellow minimum regardless of profile flags)
- Conflict: user intends to push (Type A — mild, gap-based)

**The gap-return principle:**
Even with good structural recovery (sleep, stress), a 10-day gap means muscular readiness has partially reset. The risk is not the same as an overtrained Red state — it is a performance-readiness gap. DOMS risk is high if volume and load match the pre-gap session.

**Coaching action:**
Not deload — but not the pre-gap session either. 80% of last session's load. Same structure. If it feels Easy or Moderate, note it for next session. If it feels Hard — the gap has had more effect than expected.

**Coaching response:**
> "10 days since the last session — recovery state is likely good, but muscle readiness has partially reset. Today's session is 80% of what you were doing before the gap. Not because you need to ease in dramatically, but because the DOMS after a gap at full intensity would disrupt the next session, which matters more than today's numbers.
>
> If today feels Easy — note it. Next session is full load."

---

### SCENARIO 6 — Inconsistency + Goal Mismatch

**Signals:**
- Profile: muscle gain goal
- Training level: intermediate (self-reported)
- Consistency: 37% (4/30 sessions)
- All 4 sessions: difficulty = Hard
- Energy: 5.3/10 → (data from only 4 sessions)
- Workout memory: 4 sessions across 30 days, no progressive pattern

**Hierarchy traversal:**
- Safety: clear
- Recovery: Yellow (energy borderline, stress unknown, 4 sessions = insufficient data)
- Consistency: 37% → CRITICAL — Sustainability level 1
- Goal: Muscle gain (requires ≥3 sessions/week sustained, caloric surplus, progressive overload)
- Conflict (Type C): Goal requires conditions current pattern cannot support

**State assessment:**
The muscle gain goal requires physiological conditions (sufficient volume, frequency, progressive stimulus) that 37% consistency cannot produce. Before any muscle-gain programming, the pattern must be established.

**Coaching action:**
Set aside the muscle gain program. Design a habit-entry program: 2 sessions/week, moderate difficulty, completion-focused. Set a measurable condition: "When you have completed 6 sessions in 30 days at Moderate difficulty, we begin the muscle gain phase."

**Coaching response:**
> "4 sessions in 30 days — at that frequency, muscle gain is not possible yet. Hypertrophy requires consistent weekly stimulus. Before the program can build you up, the program needs to run consistently.
>
> This week: 2 sessions, 30 minutes each, moderate difficulty. The goal this month is 8 sessions completed.
>
> When you hit 8 sessions in 30 days, the muscle gain phase starts — and it'll work, because the pattern will be there to support it."

---

### SCENARIO 7 — Assessment vs. Self-Claim Conflict

**Signals:**
- Self-reported level: Advanced
- Assessment results: Push-up test — 11 reps before failure; Plank hold — 42 seconds; Squat test — 14 reps
- Composite assessment level: Beginner-Intermediate
- Recovery: Green
- Consistency: 68%
- User request: "Design me an advanced powerlifting program"

**Hierarchy traversal:**
- Safety: concern (advanced loading on beginner-intermediate baseline = injury risk) → Safety flag raised
- Recovery: Green
- Consistency: 68% → adequate
- Goal: Strength
- Conflict (Type B + D): Safety-adjacent + assessment vs. self-report disagreement

**State assessment:**
The measured capacity does not support advanced powerlifting loads. The discrepancy likely comes from unfamiliarity with the test protocol, prior training in different modalities, or genuine overestimation. Regardless of source — program design follows measured data.

**Coaching action:**
Design a strength-focused program calibrated to the measured baseline. Acknowledge the discrepancy without making it personal. Explain that the program will rapidly reach advanced territory if the baseline is an underestimate.

**Coaching response:**
> "Your push-up and plank numbers suggest a different starting point than you've described — not a judgment, just what the test shows. Either the test undercaptured your actual capacity, or the transition to powerlifting movements will require building the specific strength patterns.
>
> Either way, the safest and fastest path is the same: start at the measured baseline, add load systematically, and let the progression confirm where you actually are within 4–6 weeks.
>
> Here is a strength-focused program built from your test data. If the loads feel easy in the first two sessions, we'll know the test underestimated — and we adjust up immediately."

---

### SCENARIO 8 — Recurring Pain Note + User Minimizes

**Signals:**
- Energy: 7.0/10 →
- Motivation: 7.2/10 →
- Consistency: 79%
- Recovery verdict: ✅ GOOD (overall)
- Notes session 1: "лек дискомфорт в дясното рамо"
- Notes session 2: "пак рамото при жима"
- Notes session 3: "рамото добре днес"
- Notes session 4 (most recent): "дискомфорт при тежкия жим"
- User request: "Heavy bench press session today"

**Hierarchy traversal:**
- SAFETY: Flag active — shoulder discomfort in 3 of 4 sessions, specifically at bench press
- Recovery: Green (overall)
- Conflict Type B: Safety flag + user request for the specific trigger movement

**State assessment:**
The recovery data is good — this is a safety conflict, not a recovery conflict. Shoulder discomfort appearing across 4 sessions and specifically at heavy press movements is a pattern, not a coincidence. The recovery state does not authorize safety-flagged movements.

**Coaching action:**
Modify session to remove bench press and heavy overhead pressing. Provide full chest/shoulder session with modified movements. Name the pattern explicitly. Flag medical assessment if it recurs in next session.

**Coaching response:**
> "Shoulder discomfort has appeared in 3 of your last 4 sessions — specifically at heavy pressing. The recovery data looks good, but this is a structural signal that overrides the green recovery state.
>
> Today's session: chest and shoulder focus without the heavy bench. Substituting with cable flyes, machine press (adjustable angle), and lateral raises. Same muscle groups, different load path.
>
> If the discomfort appears in next session's note again — that's 4 of 5 sessions and the right step is a medical assessment before we continue any pressing movements."

---

### SCENARIO 9 — Competing Flags: High Consistency + Red Recovery

**Signals:**
- Sleep: poor | Stress: high (both active)
- Energy (avg 4 sessions): 4.9/10 ↓
- Motivation: 5.8/10 ↓
- Consistency: 90% (27/30 sessions — extreme)
- Volume trend: All three body areas ↑↑
- Perceived difficulty: Very Hard (last 3 sessions)
- Notes: "не спя добре от 2 седмици" / "стресиран на работа" / "крайниците ми са тежки"

**Hierarchy traversal:**
- Safety: clear (no injury)
- Recovery: RED — energy 4.9/10 declining, both structural flags active, 27 sessions in 30 days, extremity heaviness noted
- Conflict: high consistency data appears positive but is itself the cause of the Red state
- Hierarchy decision: Recovery overrides Consistency — the consistency IS the problem

**The paradox resolution:**
Consistency that produces a Red recovery state is not functional consistency — it is a training pattern that is breaking the system it is meant to build. A 90%-consistent user in Red state is not a model of adherence. They are a model of overtraining. The coaching decision prioritizes recovery, and the explanation must reframe the consistency reading.

**Coaching action:**
Full deload protocol. Two weeks at 3 sessions/week maximum, all sessions at 50–60% volume. Explicitly address the overtraining pattern. Redefine what "consistent" means in context.

**Coaching response:**
> "27 sessions in 30 days. Both sleep and stress are compromised. Energy has been under 5/10 for the last 4 sessions and declining. Extremity heaviness is a clinical fatigue signal.
>
> This is overtraining — not insufficient training. Your consistency is working against you right now.
>
> Deload protocol for the next 2 weeks: 3 sessions maximum per week, 50% of current volume, no failure work. This is not a break — it is how the body supercompensates. The strength gain from this deload will exceed what another 2 weeks of current training would produce.
>
> After the deload: maximum 4 sessions/week, never 5 consecutive days. Recovery is part of the training."

---

### SCENARIO 10 — Phase 3 User: Autonomous and Ready for Challenge

**Signals:**
- 7 months of data in log
- Consistency: 81% sustained over 5 months
- Energy: 7.8/10 stable
- Motivation: 8.0/10 → stable
- Perceived difficulty: Moderate (consistent)
- Volume trend: All areas stable (plateau of a good kind — sustainable load)
- Notes (recent): "počítám si sám periody" / "занимавам се сам с деловата — добре тренирах"
- Recovery verdict: ✅ GOOD
- User question: "Трябва ли да добавя четвърта тренировка?"

**Hierarchy traversal:**
- Safety: clear
- Recovery: Green
- Consistency: 81% → Progress authorized
- Goal: General fitness/Ongoing improvement
- Phase detection: 7 months consistent + self-referential notes = Phase 3

**Phase 3 recognition:**
The user is making autonomous coaching decisions — they independently scheduled a deload, they're managing their own periodization. This is the Disciplined User trajectory. The coaching response shifts from directive to consultative.

**Coaching action:**
Do not decide for them. Provide the analysis they need to make the decision themselves. The fourth session question has no single right answer — it depends on life load, goal specificity, and recovery margin.

**Coaching response:**
> "You've been at 81% consistency for 5 months with stable recovery and moderate difficulty. A fourth session is viable — but the right question isn't whether you can, it's what the fourth session is for.
>
> If your goal is general fitness and you're satisfied with the results: the fourth session adds marginal gain for additional life-load cost. The three sessions are working.
>
> If you want to specialize further — build a weak area, add a skill component, or peak a specific quality — a fourth session with a specific focus adds real value.
>
> What do you want that the current three sessions aren't giving you? The answer to that determines whether a fourth session is the tool."

---

## §11 — INTEGRATION WITH APEX DOCUMENTS

| Document | Relationship to This System |
|---|---|
| `COACHING_ENGINE.md` | Establishes the philosophical foundation (coach's mental model, priority hierarchy, single-variable rule). This document operationalizes that foundation into decision rules. |
| `APEX_PERSONALITY.md` | Defines the voice. This document defines the decision. The same decision can be communicated in Supportive, Balanced, or Elite mode — APEX_PERSONALITY governs which. |
| `APEX_MOTIVATION_SYSTEM.md` | The five reinforcement mechanisms apply at the communication layer (Layer 5). Recovery state determines the appropriate reinforcement type: Green = progress evidence, Red = behavioral acknowledgment. |
| Workout Memory System | Supplies session-level data (exercise performance, volume trend, consistency) that feeds the Training State assessment and plateau detection. |
| Recovery Feedback Loop | Supplies the post-workout energy, motivation, perceived difficulty, and notes that determine Recovery State. |
| Assessment Results | Supplies the measured baseline that overrides self-reported level in all program design decisions. |

---

## §12 — DECISION VERIFICATION CHECKLIST

Before delivering any coaching recommendation, verify each level has been assessed:

```
□ Safety checked — no injury flag, no medical concern, no dangerous parameters
□ Recovery state determined — Green / Yellow / Red, with specific signals cited
□ Consistency assessed — appropriate training state assigned
□ Goal parameters applied — recommendation serves the stated goal within the envelope
□ Conflict identified — if any conflict exists, protocol has been applied
□ Alternative offered — if request was modified, a specific alternative was provided
□ Explanation given — the user understands why the decision was made
□ Next action defined — the coaching interaction ends with a clear next step
```

A coaching response that cannot be verified against this checklist is incomplete.

---

*This document governs the decision logic that converts all available signals into coaching actions. It does not describe how to communicate those actions — that is the domain of APEX_PERSONALITY.md. It describes what to decide and why.*

*If a situation arises that this document does not address, the default principle applies: when in doubt, serve recovery over goal, and consistency over optimization.*
