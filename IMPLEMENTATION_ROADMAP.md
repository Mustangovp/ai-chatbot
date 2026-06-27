# APEX INTELLIGENCE PHASE — IMPLEMENTATION ROADMAP
## Version 1.0

---

> **Authority documents:** COACHING_MEMORY_ARCHITECTURE.md · ADAPTIVE_COACHING_ENGINE.md · APEX_GUARDRAILS.md
> **Source of truth for decisions:** The architecture document. Where this roadmap and the architecture conflict, the architecture wins.
> **Implementation rule:** Every sprint ends with Apex in a fully working state. No partially integrated systems. No dead code paths. No disabled features.

---

## OVERVIEW

| Sprint | Name | Focus | Estimated effort |
|---|---|---|---|
| 1 | Foundation | Storage layer + read/write services | 3–4 days |
| 2 | Adaptive Memory | Behavioral observation accumulation | 3–4 days |
| 3 | Coaching Insights | Evidence → conclusion promotion | 4–5 days |
| 4 | Decision Integration | Memory → recommendation pipeline | 4–5 days |
| 5 | Explainability | Every recommendation answers "Why?" | 2–3 days |
| 6 | Validation | Full regression across all plans/languages/users | 2–3 days |

**Total estimated effort:** 18–24 focused development days.
**Prerequisite before Sprint 1:** Read COACHING_MEMORY_ARCHITECTURE.md in full. Every implementation decision references it.

---

## SPRINT 1 — FOUNDATION

### Goal
Persistent memory infrastructure. The plumbing that every subsequent sprint builds on.

Apex can complete Sprint 1 with zero user-visible changes. The work is entirely in storage layer and service functions.

### Deliverables

#### 1.1 — localStorage Key Initialization

Create a `_memInit()` function that runs on app load (after `checkAccess()`). Responsibility: ensure all memory keys exist with correct schema if not yet present. Never overwrites existing data.

```javascript
function _memInit() {
  if (!localStorage.getItem('apexAdaptiveMemory')) {
    localStorage.setItem('apexAdaptiveMemory', JSON.stringify(_memAdaptiveDefault()));
  }
  if (!localStorage.getItem('apexCoachingInsights')) {
    localStorage.setItem('apexCoachingInsights', JSON.stringify({ insights: [], archive: [] }));
  }
  // apexProfile and apexWorkoutLog already exist — do not touch
}
```

`_memAdaptiveDefault()` returns the full schema from COACHING_MEMORY_ARCHITECTURE.md §2.2 with all fields null/0/[].

#### 1.2 — Permanent Memory Read Service

```javascript
function _memGetProfile()         // Returns parsed apexProfile or null
function _memProfileComplete()    // Returns boolean — all required fields present
function _memGetGoal()            // Returns p.goal or null
function _memGetAssessmentLevel() // Returns p.assessmentLevel if present, else p.level
```

These are thin wrappers around `_pfLoad()` (which already exists). They establish a consistent memory API so future sprints do not scatter raw `JSON.parse(localStorage.getItem('apexProfile'))` calls.

#### 1.3 — Session Memory Read Service

```javascript
function _memGetSessions(n)       // Returns last n sessions from apexWorkoutLog, most recent first
function _memGetCoachingWindow()  // Returns sessions within coaching window (30 days or last 12, whichever larger)
function _memDaysSinceLastSession() // Returns integer or null if no sessions
function _memGetRecoverySignals() // Returns { avgEnergy, energyTrend, avgMotivation, motivationTrend,
                                  //           recentDifficulty, painDetected, lastSessionDate }
                                  // Computed from coaching window. null fields when insufficient data.
```

`_memGetRecoverySignals()` is the most important function in Sprint 1. It reads the coaching window and produces the structured signals that the Decision Engine (Sprint 4) will consume. Building it correctly now prevents refactoring later.

**Recovery signal computation rules (from ACE §3):**
- `avgEnergy`: mean of `rec.energy` across last 3 sessions with recovery data. null if fewer than 2.
- `energyTrend`: compare last 3 vs prior 3. `'up'|'flat'|'down'`. null if fewer than 4.
- `avgMotivation`: mean of `rec.motivation` across last 3. null if fewer than 2.
- `recentDifficulty`: mode of `rec.feel` across last 3 sessions.
- `painDetected`: boolean — scan `rec.note` for pain keywords (BG: болка/наранен/дискомфорт/коляно/рамо/гръб; EN: pain/injured/hurt/discomfort/knee/shoulder/back).

#### 1.4 — Adaptive Memory Read/Write Service

```javascript
function _memGetAdaptive()        // Returns parsed apexAdaptiveMemory
function _memSaveAdaptive(obj)    // Saves full adaptive memory object
function _memUpdateAdaptiveField(path, value) // Updates a nested field by dot-path
```

`_memUpdateAdaptiveField` is a convenience writer that prevents the caller from needing to parse/mutate/stringify the entire object for a single field update.

#### 1.5 — Coaching Insights Read/Write Service

```javascript
function _memGetInsights()        // Returns { insights: [], archive: [] }
function _memSaveInsights(obj)    // Saves full insights object
function _memGetActiveInsights()  // Returns insights where status='active' AND influencesDecisions=true
function _memGetInsightByType(type) // Returns first active insight of given type or null
```

These are simple read/write wrappers in Sprint 1. The logic that creates and updates insights comes in Sprint 3.

#### 1.6 — Memory Integrity Guard

```javascript
function _memValidate()           // Returns { valid: boolean, errors: string[] }
```

Checks: all required keys exist, schemas match expected shape, no corrupt JSON. Called in `_memInit()`. If validation fails, logs errors to console and resets corrupted keys to default (without touching `apexProfile` or `apexWorkoutLog`).

### Exit Criteria

- `_memInit()` runs on every app load without errors.
- `_memGetRecoverySignals()` returns correct values for a user with 4+ sessions containing recovery feedback.
- `_memGetRecoverySignals()` returns null fields gracefully for a new user with no sessions.
- `_memValidate()` correctly detects and reports a manually corrupted `apexAdaptiveMemory` key.
- All existing features (chat, workout, profile, payment) work identically to before Sprint 1. Zero regressions.

### Must NOT include

- Coaching Insights creation or evaluation logic.
- Any change to AI recommendations.
- Any change to the user-visible UI.
- Any backend changes.

### Technical risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `_memGetRecoverySignals()` produces incorrect trend calculation | Medium | Unit-test with known session fixtures before integration |
| `_memInit()` runs before `apexProfile` is available (first visit) | Low | Guard: `_memInit()` runs after `checkAccess()`, profile may be null — all services handle null profile gracefully |
| localStorage quota exceeded on devices with many keys | Low | Adaptive memory schema estimated at <5KB. No concern at this scale. |

### Rollback strategy

Sprint 1 adds new localStorage keys and new JS functions. It does not modify any existing functions. Rollback: remove `_memInit()` call from the app load sequence. All existing keys (`apexProfile`, `apexWorkoutLog`, etc.) are untouched.

---

## SPRINT 2 — ADAPTIVE MEMORY

### Goal
The coach can describe how this user usually trains. No recommendations change yet. The system observes and accumulates — it does not yet act on what it observes.

### Deliverables

#### 2.1 — Session Completion Observer

Add a call to `_memObserveSession(sessionData)` at the end of `_woLogSave()`, after the workout is written to `apexWorkoutLog`.

```javascript
function _memObserveSession(session) {
  _memObserveDuration(session);
  _memObserveTrainingTime(session);
  _memObserveWeeklyAdherence(session);
  _memObserveExerciseSkips(session);
}
```

Each sub-function reads the current adaptive memory, updates the relevant field, and writes back via `_memSaveAdaptive()`.

#### 2.2 — Duration Observation

```javascript
function _memObserveDuration(session) {
  // session.dur: minutes (already in apexWorkoutLog schema)
  // session.rec.energy: post-workout energy (already in apexWorkoutLog schema)
  // Only runs if session has recovery feedback (rec.energy is defined)
  const am = _memGetAdaptive();
  const sd = am.sessionDuration;
  sd.observationCount++;
  // Bucket into short (<40min) or long (>=45min) and update running avg
  // Update sd.lastUpdated = new Date().toISOString()
  _memSaveAdaptive(am);
}
```

**Preferred session duration derivation:** After 6+ observations with energy data, compute `preferredMinutes` as the duration bucket with the higher average energy. Null until 6 observations.

#### 2.3 — Training Time Observation

```javascript
function _memObserveTrainingTime(session) {
  // session.ts: ISO timestamp of workout start
  // Extract hour from timestamp. Bucket into morning/afternoon/evening.
  // Update avgPerfByTimeBlock using running average of rec.energy per block.
  // Only runs if session has recovery feedback.
}
```

#### 2.4 — Weekly Adherence Observation

```javascript
function _memObserveWeeklyAdherence(session) {
  // session.ts: derive dayOfWeek (0=Sunday)
  // Increment byDay[dayOfWeek].completed
  // Note: 'scheduled' increments are tracked separately — see 2.5
}

function _memObserveScheduledDay(dayOfWeek) {
  // Called when a session is recommended for a specific day
  // Increments byDay[dayOfWeek].scheduled
  // Called from the session recommendation function (Sprint 4)
}
```

After 4+ scheduled instances for a day: compute adherence rate. Populate `strongDays` (>70%) and `weakDays` (<40%). Update `lastUpdated`.

#### 2.5 — Exercise Skip Observation

```javascript
function _memObserveExerciseSkips(session) {
  // Compare session.exs (exercises logged) against the originally recommended exercises
  // Exercises in the recommendation that produced no log entries are counted as skips
  // Requires: the original recommendation is stored at session creation (see note below)
  // Update exerciseResponse.recentSkips: [{exerciseName, skipCount, lastSkipped}]
}
```

**Implementation note:** Exercise skip detection requires storing the recommended exercise list at session start, before the user begins. `_wo.plan` already holds the planned exercises at session start. Ensure `_woLogSave()` has access to `_wo.plan` to perform the comparison. This may require a minor addition to the `apexWo` session state object.

#### 2.6 — Recovery Sensitivity Observation

```javascript
function _memObserveRecoverySensitivity(session) {
  // Called from _woSaveRecovery() after recovery feedback is submitted
  // Reads current profile flags (sleep, stress) at the time of the session
  // Compares rec.energy against the user's energy baseline
  // Baseline: avg energy across all sessions with NO stress or sleep flags active
  // Updates recoverySensitivity.energyDropOnHighStress / energyDropOnPoorSleep
}
```

**Baseline computation:** On each observation, recompute baseline from all sessions where `profileFlagsActive.stress !== 'high'` AND `profileFlagsActive.sleep !== 'poor'`. Store running avg. Null until 3 clean sessions exist.

#### 2.7 — Adaptive Memory Summary Function

```javascript
function _memGetAdaptiveSummary(lang) {
  // Returns a token-efficient string describing observed patterns
  // Only includes fields with observationCount >= 3
  // Used in Sprint 4 to inject into AI context
  // Example output (EN):
  // "Behavioral patterns: sessions under 40min avg energy 7.2/10 vs 5.7/10 longer.
  //  Weak adherence day: Wednesday (17%). Recovery drops ~1.5pts under high stress."
}
```

This function is not wired into the AI context yet (that is Sprint 4). Build it now — test it works. Wire it in Sprint 4.

### Exit Criteria

- After completing 6 sessions with recovery feedback, `_memGetAdaptive().sessionDuration.preferredMinutes` is populated with a non-null value.
- `_memGetAdaptive().weeklyAdherence.byDay` correctly increments completed counts for each session day.
- `_memGetAdaptiveSummary('en')` returns a non-empty string for a user with 6+ sessions and accurate null-handling for a new user.
- All existing features work identically. Zero regressions.

### Must NOT include

- Coaching Insights creation (Sprint 3).
- Any change to AI recommendation content.
- Any change to session design or exercise selection.

### Technical risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Recovery sensitivity baseline is computed from too few sessions and produces misleading deltas | Medium | Enforce minimum 3 clean sessions before computing baseline; return null otherwise |
| `_memObserveExerciseSkips` cannot identify which exercises were originally recommended | Medium | Confirm `_wo.plan` is accessible in `_woLogSave()` before building the comparison; add `recommendedExercises` field to `apexWo` schema if needed |
| Adaptive memory grows unbounded over time | Low | Each field stores running averages and counts, not raw observation arrays. No unbounded growth. |

### Rollback strategy

Adaptive memory observation functions are additive calls in `_woLogSave()` and `_woSaveRecovery()`. Rollback: remove the `_memObserveSession()` and `_memObserveRecoverySensitivity()` calls. Adaptive memory keys remain but accumulate no further data.

---

## SPRINT 3 — COACHING INSIGHTS

### Goal
Generate behavioral insights from accumulated adaptive memory. Every insight includes a confidence score, supporting evidence, last-updated timestamp, and expiration rule. No LLM assumptions. Evidence-based conclusions only.

### Deliverables

#### 3.1 — Insight Evaluator

```javascript
function _memEvaluateInsights() {
  // Entry point. Called after every session completion and after every recovery feedback save.
  // Runs all insight type evaluators in sequence.
  // Never blocks the UI — all computation is synchronous but lightweight (no loops over full history).
  _memEvaluateDurationPreference();
  _memEvaluateDayAvoidance();
  _memEvaluateStressRecoverySensitivity();
  _memEvaluateSleepRecoverySensitivity();
  _memEvaluateExercisePreference();
  _memEvaluateProgressionRate();
  _memEvaluateAutonomyPattern();
  _memEvaluatePhaseDetection();
  _memApplyTimeDecay();
}
```

`_memEvaluateInsights()` is called at the end of `_woLogSave()` and `_woSaveRecovery()`, after the adaptive memory observers have run.

#### 3.2 — Per-Type Evaluators

Each evaluator follows the same contract:

```
1. Read relevant adaptive memory field
2. Check if minimum observations are met (type-specific threshold)
3. If no active insight of this type: check if evidence warrants creation (confidence >= 0.20)
4. If active insight exists: update evidence, recompute confidence, update status
5. If confidence < 0.15: expire insight → archive
6. Save updated insights
```

**Example: `_memEvaluateDurationPreference()`**

```javascript
function _memEvaluateDurationPreference() {
  const am = _memGetAdaptive();
  const sd = am.sessionDuration;
  if (sd.observationCount < 6) return; // below evidence threshold

  // Check correlation: avgShortSessionPerf vs avgLongSessionPerf
  if (sd.avgShortSessionPerf === null || sd.avgLongSessionPerf === null) return;

  const delta = sd.avgShortSessionPerf - sd.avgLongSessionPerf;
  if (Math.abs(delta) < 0.8) return; // delta too small to be meaningful

  const existing = _memGetInsightByType('DURATION_PREFERENCE');
  if (!existing) {
    _memCreateInsight({
      type: 'DURATION_PREFERENCE',
      claim: _memBuildDurationClaim(sd, delta),
      confidence: 0.20,
      evidenceCount: sd.observationCount
    });
  } else {
    _memUpdateInsightConfidence(existing.id, sd.observationCount, /* contradictions */ 0);
  }
}
```

#### 3.3 — Confidence Computation

```javascript
function _memComputeConfidence(evidenceCount, contraCount, previousConfidence) {
  // Implements accumulation rules from COACHING_MEMORY_ARCHITECTURE.md D1
  let c = previousConfidence;
  // Apply growth based on new evidence
  // Apply contradiction penalty
  // Clamp to [0.10, 1.00]
  return c;
}

function _memUpdateInsightConfidence(insightId, newEvidenceCount, newContraCount) {
  const insights = _memGetInsights();
  const insight = insights.insights.find(i => i.id === insightId);
  if (!insight) return;
  insight.confidence = _memComputeConfidence(newEvidenceCount, newContraCount, insight.confidence);
  insight.evidenceCount = newEvidenceCount;
  insight.contraCount = newContraCount;
  insight.influencesDecisions = insight.confidence >= 0.50;
  insight.status = insight.confidence >= 0.80 ? 'active'
                 : insight.confidence >= 0.50 ? 'active'
                 : insight.confidence >= 0.20 ? 'forming'
                 : 'expired';
  insight.lastUpdated = new Date().toISOString();
  _memSaveInsights(insights);
}
```

#### 3.4 — Time Decay

```javascript
function _memApplyTimeDecay() {
  const insights = _memGetInsights();
  const now = Date.now();
  insights.insights.forEach(insight => {
    if (insight.status === 'expired') return;
    const daysSinceUpdate = (now - new Date(insight.lastUpdated).getTime()) / 86400000;
    if (daysSinceUpdate > 60) {
      const weeksSince = Math.floor(daysSinceUpdate / 7);
      insight.confidence = Math.max(0.10, insight.confidence - (0.05 * weeksSince));
      if (insight.confidence < 0.15) {
        _memArchiveInsight(insight, 'time_decay');
      }
    }
  });
  _memSaveInsights(insights);
}
```

#### 3.5 — Insight Archive

```javascript
function _memArchiveInsight(insight, reason) {
  const insights = _memGetInsights();
  insight.status = 'expired';
  insight.expiryReason = reason;  // 'time_decay' | 'rapid_contradiction' | 'goal_change'
  insight.expiredAt = new Date().toISOString();
  insights.archive.push(insight);
  insights.insights = insights.insights.filter(i => i.id !== insight.id);
  _memSaveInsights(insights);
}
```

#### 3.6 — Plain-Language Claim Builders

Each insight type has a corresponding claim builder function that produces the plain-language statement in BG or EN. These are the strings that power the Explainability Layer in Sprint 5.

```javascript
function _memBuildDurationClaim(sd, delta, lang)     // "Sessions under X min average Y/10 energy..."
function _memBuildDayAvoidanceClaim(day, rate, lang) // "Wednesday sessions: 17% adherence..."
function _memBuildStressClaim(drop, lang)            // "Energy drops X points when stress is high..."
// etc. per insight type
```

All claim builders produce output in the user's current language. They are called at insight creation time and updated when the underlying data changes significantly (>0.5 point delta in the key metric).

#### 3.7 — Phase Detection Evaluator

Phase detection is the most consequential insight. It follows the signals defined in ACE §13:

```javascript
function _memEvaluatePhaseDetection() {
  const sessions = _memGetCoachingWindow();
  const am = _memGetAdaptive();

  // Phase 1 → Phase 2 signals:
  // - Consistency >= 60% sustained over 4+ weeks
  // - Minimum 8 sessions in the window
  // Phase 2 → Phase 3 signals:
  // - Consistency >= 75% sustained over 6+ months (24+ weeks of data)
  // - coachingResponse.autonomyScore > 0.6 (user making independent decisions)
  // - At least one self-initiated deload detected (gap of 5-10 days followed by return at reduced load)
}
```

Phase detection insight has minimum confidence 0.80 before influencing coaching mode. Phase transitions are significant — they require strong evidence.

### Exit Criteria

- After 6 sessions with recovery feedback where short sessions consistently outperform long ones, `_memGetInsightByType('DURATION_PREFERENCE')` returns an active insight with confidence ≥ 0.50.
- After 4 Wednesday misses, `_memGetInsightByType('DAY_AVOIDANCE')` returns a forming insight.
- After 90 days of simulated data, `_memEvaluatePhaseDetection()` returns a Phase 2 insight with confidence ≥ 0.65.
- Contradicting observations reduce confidence by 0.12 per occurrence.
- `_memApplyTimeDecay()` correctly decays and archives an insight that has not been updated in 70 days.
- All existing features work identically. Zero regressions.

### Must NOT include

- Integration of insights into AI recommendations (Sprint 4).
- Any user-visible UI displaying insight data.
- Any modification to session design.

### Technical risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Phase detection produces false positives on users who train irregularly but happened to hit the consistency threshold briefly | Medium | Phase detection requires sustained consistency — use 28-day rolling window, not 7-day. Confidence floor prevents premature promotion. |
| Claim builder produces awkward BG strings for edge cases (0%, 100% adherence, delta < 1 point) | Medium | Add guard conditions in each builder. Test each builder independently before integration. |
| `_memEvaluateInsights()` called too frequently (every keystroke vs every session) | Low | Call only at `_woLogSave()` and `_woSaveRecovery()` — at most once per session. |

### Rollback strategy

Insight evaluation is additive. Remove `_memEvaluateInsights()` calls from `_woLogSave()` and `_woSaveRecovery()`. Insight keys remain in localStorage but accumulate no further data. No impact on any existing feature.

---

## SPRINT 4 — DECISION INTEGRATION

### Goal
Connect the memory system to the coaching output. Every recommendation from this point forward may be influenced by active insights. The AI receives memory context in the system prompt. Session design, coaching tone, and recovery assessment all update based on what the system has learned.

This is the sprint where memory becomes coaching.

### Deliverables

#### 4.1 — Memory Context Builder

```javascript
function _memBuildContext(lang) {
  // Produces the full coaching context block injected into AI prompt
  // Structure:
  // [MEMORY CONTEXT]
  // Behavioral patterns: {_memGetAdaptiveSummary(lang)}
  // Active insights: {list of active insights with confidence label}
  // Recovery state: {_memGetRecoverySignals() formatted as coaching directives}
  // Training state: {derived from recovery signals + consistency}
  // Memory sources: {which layers contributed}
  // [/MEMORY CONTEXT]
}
```

This block replaces the existing `workoutContext` section in `_build_profile_block()` (which currently calls `_woGetSummary(lang)`). `_woGetSummary()` continues to exist and produces the workout log summary. `_memBuildContext()` wraps it and adds the memory layer on top.

**Token budget:** The full memory context block must not exceed 800 tokens. If insights are verbose, truncate the evidence detail (keep the claim, drop the evidence array text).

#### 4.2 — Recovery State Assessment

```javascript
function _memGetRecoveryState() {
  // Returns { state: 'green'|'yellow'|'red', signals: [], modifiedByInsights: boolean }
  // Implements ACE §3 criteria using _memGetRecoverySignals() as input
  // Applies insight modifications:
  //   If STRESS_RECOVERY_SENSITIVITY.confidence >= 0.65 AND stress=high active:
  //     Lower Yellow threshold by insight.energyDrop * 0.5
  //   If SLEEP_RECOVERY_SENSITIVITY.confidence >= 0.65 AND sleep=poor active:
  //     Lower Yellow threshold by insight.energyDrop * 0.5
  // Returns 'yellow' when insufficient data (new user default)
}
```

This function is the bridge between the memory system and the coaching decision hierarchy. It produces the Recovery State that feeds the SYSTEM_INSTRUCTIONS in `app.py`.

#### 4.3 — Training State Assessment

```javascript
function _memGetTrainingState() {
  // Returns { state: 'progress'|'maintain'|'deload'|'conservative_entry', consistency: number }
  // Derived from recovery state (4.2) + consistency % from session memory
  // Follows ACE §5 decision hierarchy
}
```

#### 4.4 — Session Design Modifiers

```javascript
function _memGetSessionModifiers() {
  // Returns { durationCap: number|null, avoidDays: number[], avoidExercises: string[],
  //           plateauIntervention: string|null, coachingMode: string }
  // Reads active insights and translates them to concrete session design constraints
  // durationCap: from DURATION_PREFERENCE insight if confidence >= 0.60
  // avoidDays: from DAY_AVOIDANCE insights where confidence >= 0.70
  // avoidExercises: from EXERCISE_PREFERENCE insights where confidence >= 0.60
  // plateauIntervention: from PROGRESSION_RATE insight if active
  // coachingMode: from PHASE_DETECTION + recovery state + ACE §13 canonical map
}
```

#### 4.5 — System Prompt Integration

In `app.py`, `_build_profile_block(profile, lang)` currently produces 8 sections. Add a ninth section that receives the memory context:

```python
# Section 9 — COACHING MEMORY (passed from frontend via profile.memoryContext)
if profile.get('memoryContext'):
    block += f"\n\n## COACHING MEMORY\n{profile['memoryContext']}"
    block += "\n\nACTION: Apply all ACTIVE INSIGHTS and RECOVERY STATE when designing this response. "
    block += "Every recommendation must be traceable to a memory source."
```

On the frontend, `send()` injects `_memBuildContext(lang)` into the profile object before sending:

```javascript
// In send(), before building the chat request:
const profile = _pfLoad() || {};
profile.workoutContext = _woGetSummary(lang);
profile.memoryContext = _memBuildContext(lang);
```

#### 4.6 — Recovery Verdict in System Instructions

The existing SYSTEM_INSTRUCTIONS already have a RECOVERY VERDICT section (added with the Recovery Feedback Loop). Extend it to use the computed Recovery State:

The frontend now computes `_memGetRecoveryState()` and sends `profile.recoveryState` in the request body. The backend validates and uses it in the prompt:

```python
recovery_state = body.get('recoveryState', 'yellow')  # default yellow (insufficient data)
# ... inject into system instructions as before
```

#### 4.7 — Coaching Mode in System Instructions

`_memGetSessionModifiers().coachingMode` is sent as `profile.coachingMode` in the request body. The backend maps it to the corresponding APEX_PERSONALITY.md mode instructions.

### Exit Criteria

- For a user with 10+ sessions and an active DURATION_PREFERENCE insight (confidence ≥ 0.60), the AI response recommends a session under the preferred duration threshold.
- For a user in Recovery Red state (3 sessions with energy <5.0/10), the AI response initiates a deload protocol without being asked.
- `_memBuildContext('en')` returns a non-empty string under 800 tokens for a 90-day user.
- `_memBuildContext('bg')` returns the equivalent in Bulgarian.
- `_memBuildContext()` returns an empty string (not null) for a new user with no sessions.
- All existing chat/workout/payment features work identically. Zero regressions.

### Technical risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Memory context exceeds token budget and inflates API costs | Medium | Hard-cap at 800 tokens. Implement `_memTruncateContext(text, maxTokens)` utility. Test with a full 180-day user profile. |
| Recovery state computed in JS diverges from what the AI produces without it | Medium | Add explicit Recovery State to system prompt as a directive, not a suggestion: "RECOVERY STATE: RED — apply deload protocol for this response." AI cannot override its own computed state. |
| Backend change to `_build_profile_block()` breaks existing profile context | Low | Section 9 is strictly additive. All 8 existing sections unchanged. `memoryContext` is optional — backend handles its absence gracefully. |
| `send()` building profile.memoryContext on every keystroke (if called inside onChange) | N/A | `send()` is called once per message send, not on keystroke. No risk. |

### Rollback strategy

Remove `profile.memoryContext`, `profile.recoveryState`, and `profile.coachingMode` from the `send()` payload. Remove Section 9 from `_build_profile_block()`. The existing 8-section profile block remains. No other changes required.

---

## SPRINT 5 — EXPLAINABILITY

### Goal
Every recommendation answers "Why?" The explanation originates from stored evidence, not from the AI's reasoning. The user can always trace a recommendation back to specific observations.

### Deliverables

#### 5.1 — Explanation Generator

```javascript
function _memGetExplanation(recommendationType, lang) {
  // Returns { shortForm: string, fullForm: string }
  // recommendationType: 'duration'|'day'|'recovery'|'progression'|'mode'|'baseline'
  // shortForm: one sentence for inline display
  // fullForm: paragraph with specific evidence citations for "why?" query
}
```

Short form examples:
- Duration: "Shorter session today (38 min) — energy 1.5pts higher after short sessions."
- Recovery: "Recovery is Yellow — holding last session's load."
- Progression: "Energy has been 7.4/10 for 3 sessions — progressing row to 12 reps today."
- Baseline: "No pattern data yet — recommendation from profile and recovery state."

Full form includes specific session dates, specific energy scores, specific observation counts.

#### 5.2 — Explanation Rendering

A `memWhy()` function that the user can trigger via a "?" button next to any recommendation. Opens a small explanation panel showing the full form explanation.

UI placement: the existing coaching response in chat is the primary recommendation surface. A discreet "Why this?" link under memory-influenced responses opens the panel.

**Implementation note:** The panel reads from `localStorage.apexLastExplanation` — set by `_memBuildContext()` every time memory context is built. The explanation panel does not require a new API call.

#### 5.3 — System Prompt Explainability Directive

In the system prompt (app.py SYSTEM_INSTRUCTIONS), add a rule requiring the AI to surface its reasoning when recommendations are influenced by memory:

```
EXPLAINABILITY RULE:
When your recommendation is influenced by the COACHING MEMORY section:
- State the specific memory source in one sentence before the recommendation.
- Example: "Energy post-workout has averaged 5.1/10 over your last 3 sessions — today is maintenance, not progress."
- Never say "according to your memory" or "the data shows" — speak as a coach who remembers, not a system that reads.
```

#### 5.4 — "Why?" Entry Point in UI

A subtle "Защо? / Why?" text link appears below AI responses that were memory-influenced. Clicking it:
1. Reads `localStorage.apexLastExplanation.fullForm`
2. Inserts it as a system message in the chat (visually distinct from AI responses — lighter styling)
3. Does not send to the AI (client-side only)

Memory-influenced responses are identified by the presence of `[MEMORY_INFLUENCED]` marker in the SSE stream (added server-side when `profile.memoryContext` was non-empty).

### Exit Criteria

- For a user with DURATION_PREFERENCE insight active, clicking "Why?" displays a full-form explanation citing specific session dates and energy scores.
- For a new user with no memory data, clicking "Why?" displays: "This recommendation is from your profile and current recovery state — there isn't enough session history yet to tailor it further."
- Short form explanation is always ≤ 120 characters.
- Full form explanation always cites at least one specific data point (date, number, or observation count).
- All existing features work identically. Zero regressions.

### Technical risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `[MEMORY_INFLUENCED]` marker leaks into the visible chat text | Medium | Strip marker from stream before rendering in `readChatStream()`. Add to existing marker-stripping logic. |
| `apexLastExplanation` is stale when user asks "Why?" after multiple responses | Low | `apexLastExplanation` is overwritten on every response send. "Why?" button is tied to the last response only — previous responses do not have a "Why?" link. |

### Rollback strategy

Remove the "Why?" link from response rendering. Remove the `EXPLAINABILITY RULE` from SYSTEM_INSTRUCTIONS. Remove `[MEMORY_INFLUENCED]` marker injection. Memory context continues to function (Sprint 4 is unaffected). Explainability is purely additive.

---

## SPRINT 6 — VALIDATION

### Goal
Full regression testing across all plans, languages, user states, and device types. No new code. Verification only.

### Validation Matrix

#### Plan Coverage

| Plan | Memory initialized | Sessions logged | Insights active | Expected behavior |
|---|---|---|---|---|
| FREE | ✅ | ✅ | ✅ | Memory context not sent (FREE has no workout mode) — verify graceful no-op |
| CORE | ✅ | ✅ | ✅ | Full memory pipeline active; gpt-4o-mini receives memory context |
| PRO | ✅ | ✅ | ✅ | Full memory pipeline active; gpt-4o receives memory context |
| MASTER | ✅ | ✅ | ✅ | Identical to PRO behavior |

**FREE plan note:** FREE users currently have no Workout Mode access. They have no `apexWorkoutLog` entries. `_memBuildContext()` must return empty string for FREE users, not null. Verify the empty string does not produce a malformed profile block.

#### Language Coverage

| Scenario | Verify |
|---|---|
| BG user with insights | `_memBuildContext('bg')` returns Bulgarian claim strings |
| EN user with insights | `_memBuildContext('en')` returns English claim strings |
| User switches BG → EN mid-session | Memory context updates on next send (uses current `lang` at send time) |
| BG recovery state directive | System prompt recovery section in Bulgarian |
| EN recovery state directive | System prompt recovery section in English |

#### Device Coverage

| Device | Verify |
|---|---|
| Desktop (Chrome) | Full pipeline. localStorage writes/reads correctly. |
| Desktop (Firefox) | Full pipeline. localStorage behavior identical. |
| Mobile (Chrome, 375px) | `_memBuildContext()` produces same content. No UI layout breaks from "Why?" link addition. |
| Mobile (Safari, iOS) | localStorage persistence across tab close/reopen. |
| Incognito / Private | Memory initializes fresh. No errors from missing keys. New user behavior identical to Day 1 experience. |

#### User State Coverage

| User state | Scenario | Expected behavior |
|---|---|---|
| Fresh user | No sessions, no insights | `_memGetRecoveryState()` returns `{state:'yellow'}`. Context block is empty. Coaching is baseline only. |
| 5-session user | Some adaptive data, no active insights | Adaptive summary present in context. No insight-driven recommendations. |
| 30-day user | Active DURATION_PREFERENCE insight | Session design reflects duration cap. "Why?" link present. |
| 90-day user, Phase 2 | Multiple active insights | Full memory context. Coaching mode Balanced. |
| Long-term user, localStorage cleared | All memory reset | App recovers as new user. No errors. Profile re-entry flow works. |
| User with stress=high flag | STRESS_RECOVERY_SENSITIVITY active | Yellow/Red threshold lowered. Explanation cites stress-energy correlation. |

#### Regression Checklist

For each scenario above, verify all of the following:

```
□ Chat send works — no console errors
□ Workout mode launches — profile gate works
□ Workout completes — _woLogSave() runs without error
□ Recovery feedback saves — _woSaveRecovery() runs without error
□ _memEvaluateInsights() runs without error after workout completion
□ apexAdaptiveMemory key is valid JSON after the session
□ apexCoachingInsights key is valid JSON after the session
□ Profile (apexProfile) is unchanged after the session
□ apexWorkoutLog is unchanged by memory operations
□ Plan badge displays correctly (FREE/CORE/PRO)
□ Language toggle switches all visible text
□ "Why?" link appears only on memory-influenced responses
□ "Why?" panel content matches current user's active insights
□ Token count for /chat request does not exceed model context window
□ Stripe flow unaffected — payment modal, webhook, token verification unchanged
```

#### Acceptance Criteria

**Sprint 6 is complete when:**

1. All items in the regression checklist pass for all 4 plans in both BG and EN on both desktop and mobile.
2. A fresh user (no sessions) produces no console errors and receives baseline coaching.
3. A 90-day user with 3 active insights receives memory-influenced recommendations with correct explanations.
4. Token budget of 800 for `_memBuildContext()` is confirmed by manual measurement across plan types.
5. No new localStorage keys have been introduced that are not in the COACHING_MEMORY_ARCHITECTURE schema.
6. `_memValidate()` returns `{valid: true}` for all tested user states.

---

## CROSS-SPRINT RULES

### The Invariants

These rules apply in every sprint, at every commit.

**Rule 1 — Never overwrite profile data.**
`apexProfile` is sacred (GUARDRAILS §3). No memory operation writes to `apexProfile`. Memory reads from it, never writes.

**Rule 2 — Null safety everywhere.**
Every memory function must handle null localStorage gracefully. New users, cleared storage, and partial profiles are valid states — not error conditions.

**Rule 3 — No insight influences a recommendation until confidence ≥ 0.50.**
The confidence model exists to prevent premature personalization. Do not shortcut it.

**Rule 4 — Safety overrides all memory.**
A pain note in session memory stops the session design and triggers safety escalation. No insight delays or suppresses this.

**Rule 5 — Every sprint ends with a working product.**
Partially integrated memory that produces undefined behavior is not acceptable. If a sprint cannot be completed cleanly, roll back and complete the prerequisite work first.

### The localStorage Contract

At the end of the Intelligence Phase, the following keys exist in localStorage:

| Key | Owner | Written by | Read by |
|---|---|---|---|
| `apexProfile` | User | Profile save only | Memory (read-only), AI context |
| `apexWorkoutLog` | System | `_woLogSave()`, `_woSaveRecovery()` | Session Memory service |
| `apexAdaptiveMemory` | System | Sprint 2 observers | Sprint 3 evaluators, Sprint 4 context builder |
| `apexCoachingInsights` | System | Sprint 3 evaluators | Sprint 4 context builder, Sprint 5 explainability |
| `apexLastExplanation` | System | Sprint 5 context builder | Sprint 5 "Why?" panel |
| `apexHistory` | System | `saveToHistory()` | Existing chat context (unchanged) |

No other keys are introduced. No existing keys are modified in schema.

---

## DEPENDENCY MAP

```
Sprint 1 (Foundation)
  └── Sprint 2 (Adaptive Memory) depends on: _memInit(), _memGetAdaptive(), _memSaveAdaptive()
        └── Sprint 3 (Insights) depends on: adaptive memory fields, _memEvaluateInsights hook points
              └── Sprint 4 (Integration) depends on: _memGetActiveInsights(), _memBuildContext()
                    └── Sprint 5 (Explainability) depends on: _memBuildContext(), [MEMORY_INFLUENCED] marker
                          └── Sprint 6 (Validation) depends on: all sprints complete
```

No sprint may begin before its predecessor is complete and regression-tested.

---

## IMPLEMENTATION NOTES FOR THE DEVELOPER

These are not requirements. They are observations that will save time.

**On `app.html` size:** The file is already 1700+ lines. The Intelligence Phase adds roughly 400–600 lines of new JS. Consider extracting the memory service functions into a `<script src="/static/apex-memory.js">` before Sprint 3, to keep the single file manageable. This is optional but reduces cognitive load.

**On the AI context token budget:** The current profile block is approximately 600–900 tokens depending on profile completeness. Adding a 800-token memory context brings the total to 1400–1700 tokens before the conversation history. PRO users get 30 messages of history. At ~150 tokens per message, that's 4500 more tokens. Total context for a PRO user: ~6200 tokens before the user's current message. GPT-4o has a 128K context window — no risk. GPT-4o-mini has a 128K context window as well. No constraint.

**On the recovery feedback gap:** Currently, recovery feedback is optional. If a user completes workouts without submitting recovery feedback, `rec.energy` and `rec.motivation` will be null for those sessions. All memory functions must handle this gracefully — sessions without recovery data contribute to `weeklyAdherence` and `sessionDuration` but not to `recoverySensitivity`. Do not assume recovery data exists.

**On the existing `_woGetSummary()` function:** This function already produces a coaching summary of workout history. In Sprint 4, `_memBuildContext()` wraps it — do not replace it. The two functions serve different purposes: `_woGetSummary()` surfaces raw session data (what happened), `_memBuildContext()` surfaces interpreted patterns (what it means). Both are valuable. Send both.

---

*This roadmap is the production implementation guide for the Apex Intelligence Phase.*
*Architecture decisions belong in COACHING_MEMORY_ARCHITECTURE.md.*
*This document covers execution sequence, technical risks, rollback strategies, and acceptance criteria.*
*No implementation may begin without reading both documents in full.*

*Version 1.0 — 2026-06-27*
