# APEX PULSE PRO — PROJECT STATE
## Persistent Development Memory

---

> **Purpose:** This file eliminates repeated codebase analysis at the start of each session.
> Read this first. Update this last.
> Last updated: June 2026 — Apex 1.5 Steps 1–3 complete

---

## QUICK REFERENCE

| Item | Value |
|---|---|
| App URL | `/app` route via Flask |
| Primary language | Bulgarian (BG), with EN toggle |
| Backend | Python / Flask, `app.py` (~1246 lines) |
| Frontend | Single-file, `templates/app.html` (~1700+ lines) |
| Landing pages | `templates/landing.html`, `templates/landing_en.html` |
| AI model (PRO) | `gpt-4o` |
| AI model (FREE/CORE) | `gpt-4o-mini` |
| Payments | Stripe Checkout + Webhook |
| Storage | Client-side `localStorage` only — no database |
| Auth | HMAC-signed tokens: `base64(expiry.plan.hmac_sha256[:32])` |
| Deployment | Flask server (production details not in scope here) |

---

## CURRENT ARCHITECTURE

### Backend (`app.py`)

```
Flask app
├── GET  /              → landing.html
├── GET  /en            → landing_en.html
├── GET  /app           → app.html
├── POST /chat          → SSE streaming AI response
├── POST /create-checkout-session → Stripe checkout URL
├── GET  /app/success   → redirect with ?pending_session=
├── POST /webhook       → Stripe webhook → issues HMAC token
├── GET  /poll-token    → frontend polls until webhook fires
├── POST /verify-token  → validates token, returns plan
├── POST /withdraw      → 7-day refund or waiver (EU Directive 2023/2673)
├── POST /save-lead     → email capture → +5 free messages
└── POST /feedback      → user feedback collection
```

**Plans:**
```python
PLANS = {
  "core": {"name": "APEX PULSE CORE - 30 Days", "amount": 999,  "memory": 10},
  "pro":  {"name": "APEX PULSE PRO - 30 Days",  "amount": 1499, "memory": 30},
}
```

**Memory caps (localStorage rolling window):**
- FREE: 12 messages (last 6 sent to backend via `getFreeMemory()`)
- CORE: 10 messages context
- PRO: 30 messages context (60 stored locally, 30 sent)

**Model selection:**
```python
model = "gpt-4o" if is_pro else "gpt-4o-mini"
max_tokens = 4000 if is_pro else 1500
```

**System prompt rules (SYSTEM_INSTRUCTIONS, lines 105–223 of app.py):**
- Bulgarian-first coaching persona
- Metric system only
- Full column names in tables: Протеин / Въглехидрати / Мазнини
- Explain WHY for every recommendation
- Direct coaching voice — no filler ("Excellent question!")
- Bulgarian local brands only (Kaufland / Lidl / Fantastico)
- End every response with: `🔱 **ELITE STATUS: ACTIVE**`

### Frontend (`templates/app.html`)

Single-file SPA. No framework. Vanilla JS.

```
Key JS objects / functions:
├── _WO_SVG{}           → 6 exercise SVG animations (squat/pushup/lunge/crunch/plank/generic)
├── _woSvg(name)        → routes exercise name → SVG via regex
├── _woParse(msgEl)     → parses workout table from AI message DOM
├── startWorkout(exs)   → launches workout overlay (requires profile gate)
├── _woRender()         → renders current workout phase
├── _woRenderEx(b)      → exercise card (SVG + set/rep display)
├── _woRenderFb(b)      → RPE feedback screen (easy/medium/hard)
├── _woRenderRest(b)    → smart rest timer with countdown bar
├── _woRenderHr(b)      → rPPG heart rate measurement
├── _woRenderDone(b)    → completion screen
├── _woFb(fb)           → processes RPE feedback, adapts repDelta, routes to rest
├── _woRestSecs(name)   → calculates rest time from profile + exercise type
├── _woCalcBpm(samples) → zero-crossing BPM from rPPG green channel
├── send()              → main chat function (SSE streaming)
├── readChatStream()    → reads SSE stream, renders markdown live
├── getChatHistory()    → reads localStorage apexHistory (last 30)
├── saveToHistory()     → writes to localStorage apexHistory
├── checkAccess()       → verifies token on load, routes post-Stripe flow
├── activateElite()     → unlocks PRO/CORE features after token verification
├── pollForToken()      → polls /poll-token after Stripe redirect
├── updatePlanBadge()   → FREE (white) / CORE (green) / PRO (red) badge
├── showDailyLimit()    → FREE limit screen with upgrade offer
├── updateGoalBar()     → renders persistent goal strip from apexProfile (Step 3)
├── _gbCoachFocus(p)    → derives coaching focus label from sleep/stress/goal
└── T{}                 → translation object (BG/EN strings)
```

**localStorage keys:**
| Key | Content |
|---|---|
| `apexToken` | HMAC token (plan + expiry) |
| `apexPlan` | "core" or "pro" |
| `apexSessionId` | Stripe session ID (for /withdraw) |
| `apexProfile` | JSON profile object (14 fields: name, gender, age, weight, height, activityLevel, level, sleepQuality, stressLevel, healthNotes, goal, goalDetail, equipment, foodPreferences, allergies) |
| `apexHistory` | Last 30 messages (paid users) |
| `apexFreeUsage` | `{count, windowStart}` — daily limit tracking |
| `apexFreeMemory` | Last 6 messages (free users) |
| `apexLeadBonus` | "true" if email submitted (+5 messages) |
| `apexWo` | Current workout session state (resume on reload) |
| `apexPendingPlan` | Last AI plan HTML (restored after Stripe redirect) |
| `apexDisclaimerAccepted` | "true" after disclaimer gate |
| `apexCount` | Internal message counter (−999999 = elite/paid) |

### CSS SVG Exercise Animations

All use CSS `d:path()` morphing for limb paths + SMIL `<animate>` for joint circles.

| Exercise | ViewBox | Duration | ID Prefix | Status |
|---|---|---|---|---|
| Squat | 0 0 100 130 | 2.2s | `sq-` | ✅ Committed |
| Push-up | 0 0 170 90 | 1.8s | `pu-` | ✅ Committed |
| Plank | 0 0 170 90 | 2.4s | `pl-` | ✅ Committed |
| Lunge | 0 0 160 130 | 2.0s | `ln-` | ✅ Committed |
| Crunch | 0 0 170 82 | 1.6s | `cr-` | ✅ Committed |
| Generic | 0 0 80 128 | 1.15s | `wf` | ✅ (arm swing, no prefix conflict) |

`_woSvg()` routing regex (current):
```javascript
/клек|squat|мъртва|deadlift|преса|press|набир/  → squat
/лицев|push.*up|bench|лег/                       → pushup
/кранч|коремни|sit.?up|crunch/                   → crunch
/планк|plank/                                    → plank
/изпад|lunge/                                    → lunge
// default                                        → generic
```

---

## IMPLEMENTED FEATURES ✅

### Access & Monetization
- [x] Stripe Checkout + Webhook token issuance
- [x] HMAC-signed token — plan encoded server-side, cannot be upgraded by client
- [x] Token verification on every `/chat` request
- [x] EU Directive 2023/2673 withdrawal — 7-day refund vs. waiver logic
- [x] Founding price cutover (`SHOW_FOUNDING_PRICE` flag)
- [x] FREE daily limit: 10 msg/24h window
- [x] Lead bonus: +5 messages for email capture via `/save-lead`
- [x] `apexPendingPlan` — restores last AI plan after Stripe redirect
- [x] Plan badge: FREE (white) / CORE (green) / PRO (red)
- [x] Copy + PDF export (locked for FREE users)

### Chat Engine
- [x] Flask SSE streaming (`stream_with_context`)
- [x] Live markdown rendering during stream (marked.js)
- [x] Table decoration (wraps in `.table-wrap` for horizontal scroll)
- [x] Input lock during AI response (prevents double-send)
- [x] Input focus restore after response (desktop only, `preventScroll:true`)
- [x] Typing indicator ("ПРЕСМЯТАМ" / "CALIBRATING")
- [x] Error handling with user-visible message
- [x] Stream disconnect recovery (partial response preserved)

### Profile System (Steps 1–3 ✅)
- [x] 3-step onboarding modal: 14 fields across Basics / Situation / Goal panes
- [x] Per-step localStorage persistence (partial abandonment preserves data)
- [x] `_pfPopulate()` — pre-fills all fields on re-open (Edit Profile flow)
- [x] `_build_profile_block()` — structured 6-section coaching context with TDEE + protein targets
- [x] Priority coaching flags (stress/sleep/health → behavioral AI directives)
- [x] Profile gate on Workout Mode (requires at least weight field)
- [x] `maybeShowProfile()` — appears once after disclaimer accepted
- [x] **Goal Bar** — persistent strip below nav showing: Primary Goal / Current Weight / Coaching Focus
- [x] **Edit Profile button** in goal bar — reopens all steps with pre-populated fields
- [x] `updateGoalBar()` — called on load, language switch, profile save, profile skip
- [x] Coaching focus derived from sleep+stress state (recovery-first logic per COACHING_ENGINE §2)
- [x] 4 future DOM slots pre-wired (Progress %, Apex Score, Recovery, Weight trend) — hidden, awaiting later steps

### Workout Mode
- [x] AI table parsing → `🏋️ Режим Тренировка` button
- [x] Exercise card with SVG animation
- [x] Set/rep counter
- [x] RPE feedback: easy (+2 reps) / medium (no change) / hard (−1 rep), capped ±8/−4
- [x] Smart rest timer (level + compound bonus + age + goal modifiers)
- [x] Personalized rest reason text
- [x] Coach voice comments during rest (3 pools, randomized)
- [x] Skip rest button
- [x] Progress bar across full workout
- [x] rPPG heart rate: 15s capture via rear camera, green channel, zero-crossing BPM
- [x] HR zone classification (60%/<60%/>80% of max HR)
- [x] Manual HR fallback (wrist pulse method with calculation instruction)
- [x] Camera error: Brave browser detection with specific instructions
- [x] Workout session resume via `localStorage` (`apexWo`)
- [x] 5 exercise CSS SVG animations (all committed)

### UX
- [x] Landing → app goal routing (`?goal=`, `?q=`)
- [x] Plan param routing (`?plan=core/pro` opens paywall on correct plan)
- [x] BG/EN language toggle (T translation object)
- [x] Disclaimer gate
- [x] 4 goal chips on greeting screen
- [x] Paywall founding vs. 3-plan layout (date-gated)
- [x] Toast notifications
- [x] Withdraw modal (EU cancellation)

---

## PARTIALLY IMPLEMENTED FEATURES ⚠️

### Profile System (14/18 fields — UI + backend complete as of Steps 1–2)
**What works:** 3-step onboarding collects 14 fields. `_build_profile_block()` in app.py now produces a structured coaching context with 6 sections + dynamic priority flags. TDEE and protein targets are calculated server-side from weight/height/age/activity/goal. Fully backward compatible with old 7-field profiles.
**What's missing:** name field (collected but not a profile requirement for APEX_VISION's 18); body fat % (dropped from Step 1 to keep mobile-friendly — add in future pass); formal assessment (Step 5).
**AI receives per session:** Identity · Goal + numeric targets · Training capacity · Recovery indicators · Health constraints · Nutrition constraints · Priority behavioral flags.

### Memory System (client-side only)
**What works:** Conversation history (30 paid / 6 free messages) reaches backend and AI uses it contextually.
**What's missing:** Server-side storage. Device change, browser clear, or incognito wipes everything. No structured history of weight, workouts, nutrition, HR, sleep. No long-term memory.
**Impact:** Apex cannot remember anything across devices or after localStorage is cleared. The "adaptive coach" vision is impossible without server-side storage.

### Progress Intelligence (session only)
**What works:** RPE → `repDelta` adapts reps live within the current workout session.
**What's missing:** After `closeWorkout()`, all data is discarded. No workout log. No performance trends. No accumulated data the AI can reference.
**Impact:** The AI cannot say "last week you struggled with lunges" because it never recorded that.

### Heart Rate (isolated measurement)
**What works:** Single post-set rPPG measurement + zone classification + rest advice.
**What's missing:** Pre-workout resting HR, HR stored across sessions, HR trend in recovery analysis.
**Impact:** HR data is disposable. Cannot contribute to the recovery intelligence described in COACHING_ENGINE.md.

### Adaptive Training (in-session only)
**What works:** RPE adaptation within a single workout session.
**What's missing:** Cross-session adaptation. Week 3 data does not affect Week 4 plan generation.
**Impact:** Every plan is generated from the static profile only — not from actual performance history.

### Workout Mode Detection (fragile)
**What works:** Parses BG/EN column headers for упражнение/sets/reps.
**What's missing:** Only triggers when AI generates an exact table format the regex matches. List format, prose, or unexpected column names silently skip workout mode.
**Impact:** Users occasionally get a workout plan with no `🏋️` button.

---

## MISSING FEATURES ❌

### No Database / No User Identity
No server-side storage of any kind. No user accounts. Tokens are plan+expiry only, not user identity. If localStorage is cleared, the user loses everything except their paid access (token can be re-entered).
**Blocks:** Memory system, progress dashboard, cross-session adaptation, workout logs, all of APEX 2.0.

### No Assessment Engine
Self-reported level (beginner/intermediate/advanced) instead of measured fitness tests.
APEX_VISION requires: push-up test, plank hold, squat test, mobility assessment → auto-set level.

### No Progress Dashboard
No graphs, charts, or visual tracking of any kind. No weight trend. No workout consistency view. No strength progress. No recovery status. No goal progress indicator.

### ✅ Goal as Profile Field (Step 3 complete)
Goal is now a dedicated field in `apexProfile` (step C of onboarding). It persists in localStorage, is visible at all times in the Goal Bar, and is the first input into `_gbCoachFocus()`. The AI receives goal + TDEE + protein targets in every `/chat` request via `_build_profile_block()`.

### No Recovery Intelligence
No sleep tracking. No energy level input. No fatigue detection. No overtraining risk detection. No volume auto-adjustment based on recovery state. Recovery score (defined in COACHING_ENGINE.md) not yet calculated.

### No Hydration Tracking
System prompt has hydration formula rules. No UI for logging water intake, no daily target display, no reminders.

### No Apex Fitness Score
Defined in COACHING_ENGINE.md (5 components, 100-point scale). Not calculated or displayed anywhere.

### No Cross-Device Sync
Everything is local. Phone and laptop are completely independent.

### Workout Mode — Language Lock
Workout overlay is always in Bulgarian regardless of `lang` setting. English users see Bulgarian labels.

### No Workout Completion Data
The "done" screen shows total exercises and sets but discards all session data (no reps completed, no HR readings, no adaptation log).

---

## TECHNICAL DEBT 🔧

### High Priority
- **No database:** The entire vision requires server-side storage. SQLite as minimum viable first step.
- **`app.html` is 1700+ lines:** One file is becoming unmaintainable. JS functions are mixed with HTML template. No separation of concerns. No build system.
- **System prompt in `app.py` at line 105:** The coaching persona is hardcoded as a string in Python. It is not versioned or configurable. Changing coaching behavior requires a code deploy.

### Medium Priority
- **`localStorage` is the only persistence layer:** This is a single point of failure. Any browser data clear destroys user history, profile, and workout state permanently. There is no recovery path.
- **Free message counting drifts:** `apexCount` (client-side, controls `isElite`) and `apexFreeUsage` (client-side, controls daily limit) are independent counters. The server has its own counter that resets on restart unless persisted. Three counters for one concept.
- **`_woParse()` is fragile:** Column header matching via string includes is brittle. AI response format variation silently breaks workout mode.
- **No input sanitization on profile fields:** `pf-injuries` is a free-text field that goes directly into the system prompt. A malicious input could attempt prompt injection via the profile.

### Low Priority
- **`SHOW_FOUNDING_PRICE` is a hardcoded date comparison:** This will need to be toggled manually or made configurable.
- **`generic` SVG animation uses CSS `transform: rotate()` instead of `d:path()`:** Inconsistent with the other 5 animations. Fine for now, but will look different if the animation style evolves.
- **`T{}` translation object has gaps:** Some UI strings exist in BG only (workout overlay labels, camera instructions). English users see Bulgarian text in workout mode.

---

## UX ISSUES 🎨

| Issue | Location | Severity |
|---|---|---|
| ~~No way to edit profile after initial setup~~ | ✅ Fixed Step 3 — Edit Profile button in goal bar | ~~High~~ |
| ~~No "Edit Profile" button in UI~~ | ✅ Fixed Step 3 — button opens pre-populated onboarding | ~~High~~ |
| Profile completeness not shown to user | Anywhere | Medium |
| Workout mode button missing when AI formats differently | Chat | Medium |
| Workout completion shows no useful data | Done screen | Medium |
| Workout overlay always in Bulgarian | Workout overlay | Medium |
| No goal field in profile | Profile modal | High |
| FREE users lose all value on localStorage clear | Everywhere | High |
| No visual progress indicator anywhere in app | App | High |
| Profile modal appears as interruption, not onboarding | First visit | Medium |
| No way for user to know their free message count | Chat | Low |

---

## COACHING GAPS (vs. COACHING_ENGINE.md) 🎯

| Gap | Description |
|---|---|
| No foundation check | Apex never checks if sleep, hydration, or stress is broken before adding training |
| No single-variable rule | Apex may give multiple simultaneous recommendations |
| No RPE history | Cannot detect "consistently easy" or "consistently hard" patterns across sessions |
| No cross-session adaptation | Plan does not evolve based on previous session performance |
| No assessment before plan generation | Self-reported level is the only fitness input |
| No proactive recovery detection | Apex never flags fatigue, overtraining risk, or deload need |
| No goal beneath the goal | Apex addresses stated goal, not underlying motivation |
| No retrospective at milestones | No month-1, month-3, or month-6 summary or acknowledgment |
| No plateau detection | Cannot identify stalled progress across sessions |
| No deload scheduling | Deloads are never recommended proactively |

---

## HIGHEST PRIORITY TASKS

Listed in order of impact and dependency.

### 1–3. ✅ Profile onboarding + coaching context + Goal Bar (commits 512af73, 0a5616d, e395c80)
3-step modal collects 14 fields. `_build_profile_block()` produces structured 6-section coaching context with dynamic priority flags and calculated TDEE/protein targets. AI receives coaching instructions, not raw form data. Goal Bar always visible in UI with North Star context and Edit Profile access.
**Next: Step 4** — Fitness assessment flow (push-up / plank / squat tests → auto-set level).

### 2. Persist Workout Data to Backend (foundational for everything adaptive)
After `_woRenderDone()`, POST the completed session to a new `/log-workout` endpoint: exercises, sets, reps (with repDelta applied), HR readings, session RPE, timestamp.
Minimum viable backend: SQLite with `workouts` table. No user accounts needed yet — key by token hash.

### 3. Add Goal as First-Class Profile Field
Separate from the profile fields above — goal needs to be displayed in the app header at all times, updated easily, and referenced in every AI response. It is the north star of all recommendations.

### 4. Fix Workout Mode Language (quick win, high visibility)
Workout overlay labels use hardcoded Bulgarian strings. Route them through `T[lang]` translation object. Affects all English users.

### 5. Add "Edit Profile" Button
Currently profile can only be set once. Add a settings/profile icon in the header that reopens the profile modal at any time. Update `localStorage.apexProfile` on save. Required before adding more profile fields or the UX debt compounds.

### 6. Persist Workout to `localStorage` as Log (pre-backend stopgap)
Before backend storage is built, store completed workout summaries in `localStorage.apexWorkoutLog` (array, capped at last 20 sessions). Surface the last 3 sessions to the AI via the profile context block. Immediate improvement to adaptive recommendations without needing a server.

### 7. Progress Dashboard (minimum viable)
A single `/progress` page (or modal): weight check-in input + chart (Chart.js or SVG), last 7 workout sessions as a list with completion status and session difficulty. No backend needed if weight log is `localStorage`-only as a first pass.

---

## NEXT MILESTONE

### Milestone: Apex 1.5 — "The Coaching Upgrade"
**Goal:** Make Apex feel like it actually knows the user, without rebuilding the backend.
**Scope:** Frontend-only and minor backend additions. No database yet.

**Definition of done:**
- [x] Profile modal has 14 fields (goal, food prefs, allergies, activity, stress/sleep, health notes) ✅ Step 1
- [x] "Edit Profile" accessible at all times via Goal Bar button ✅ Step 3
- [x] Goal displayed in UI as persistent coaching context (Goal Bar) ✅ Step 3
- [ ] Workout log stored in `localStorage` (last 20 sessions)
- [ ] Last 3 workout sessions surfaced to AI in system context
- [ ] Workout overlay fully translated to BG/EN
- [ ] Workout done screen shows actual reps completed and HR reading if taken
- [ ] `_woParse()` made more resilient (case-insensitive partial header matching)

**Estimated sessions to complete:** 3-4 focused development sessions.

**What this unlocks:**
The AI will be able to reference previous workouts in responses. Users will have a complete profile that personalizes nutrition and recovery advice. The UX will feel like a product that remembers you, even before server-side storage exists.

---

## DOCUMENT HISTORY

| Date | What changed |
|---|---|
| June 2026 | Initial document created. Gap analysis complete. All 5 exercise animations committed. COACHING_ENGINE.md, APEX_VISION.md, IMPLEMENTATION_PLAN.md in repo. |
| June 2026 | **Apex 1.5 Step 1** — Profile modal redesigned as 3-step onboarding. New CSS (progress dots, nav row, back button). HTML restructured into 3 panes (Basics / Situation / Goal). JS rewritten with `openProfile()`, `pfNext()`, `pfBack()`, `pfSkipStep()`, `_pfPopulate()`, per-step save functions. 14 fields now visible in UI (up from 7). Commit 512af73. |
| June 2026 | **Apex 1.5 Step 2** — `_build_profile_block()` in app.py rewritten. 6-section coaching context: Identity · Goal+Targets · Capacity · Recovery · Health · Nutrition. Dynamic priority flags translate field values into behavioral AI instructions. TDEE + protein targets calculated from weight/height/age/activity/goal. Backward compatible with legacy 7-field profiles. Commit 0a5616d. |

---

*Update this file at the end of every development session.*
*The "Implemented Features" section is the source of truth — if it is not listed here, it is not confirmed to exist.*
