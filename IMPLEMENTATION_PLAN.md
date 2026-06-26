# APEX 1.5 — IMPLEMENTATION PLAN
## Execution Roadmap

---

> **Source documents:** APEX_VISION.md · COACHING_ENGINE.md · PROJECT_STATE.md
> **Scope constraint:** No relational database. No user accounts. No infrastructure changes.
> All persistence is `localStorage` or minimal Flask endpoint additions.
> **Design principle:** Every step must deliver observable user value. No invisible groundwork.

---

## THE CORE PROBLEM THIS RELEASE SOLVES

Currently, Apex forgets everything between sessions.

A user can train for three weeks, log their workouts, struggle with lunges, improve their plank — and Apex knows none of it. The next conversation starts from zero. The AI is coaching a stranger.

Apex 1.5 closes this gap without a database. Every feature in this plan uses the memory infrastructure that already exists — `localStorage`, the system prompt context block, and the existing `/chat` endpoint — and extends it to hold more of the user's reality.

The user's experience after 1.5: **"This thing remembers me."**

---

## RELEASE OVERVIEW

**5 Feature Areas. 15 Steps. 4 Sessions.**

```
Session 1 — Identity (Steps 1–4)
  Step 1: Profile redesign — multi-step onboarding
  Step 2: Complete all 18 profile fields
  Step 3: Edit Profile, persistent goal display
  Step 4: Profile context upgrade in system prompt

Session 2 — Assessment + Memory (Steps 5–8)
  Step 5: Fitness test flow (push-up, plank, squat)
  Step 6: Workout log schema in localStorage
  Step 7: Workout done screen — save session data
  Step 8: Inject workout history into AI context

Session 3 — Recovery + Dashboard Foundations (Steps 9–12)
  Step 9: Daily recovery check-in (3 inputs, 10 seconds)
  Step 10: Recovery score calculation
  Step 11: Recovery state injected into AI context
  Step 12: Progress panel — weight check-ins + streak

Session 4 — Dashboard Visuals + Polish (Steps 13–15)
  Step 13: Weight trend chart (SVG, no library dependency)
  Step 14: Workout history display (last 7 sessions)
  Step 15: Workout mode translation + completion screen upgrade
```

---

## SESSION 1 — FITNESS IDENTITY PROFILE

### Why this is first

The profile is the foundation of personalized coaching. Every recommendation Apex makes is only as good as what it knows about the person. Currently, 7 fields are collected. 11 critical fields are missing. Adding them requires no backend, no infrastructure, and zero risk — but the payoff is immediate. Every AI response becomes more relevant from the moment the additional fields are saved.

It also sets the right psychological expectation for the user. A multi-step onboarding that asks thoughtful questions signals that this is a serious coaching tool, not a chatbot.

---

### Step 1: Redesign Profile as Multi-Step Onboarding

**Current state:**
Profile is a single modal that interrupts the first session. It appears once, can be dismissed, and disappears forever. No indication it can be updated.

**What changes:**
The profile becomes a 3-step onboarding flow with a progress indicator.

```
Step A — The Basics (currently collected, reorganized)
  Name
  Age
  Sex
  Height
  Current weight
  Body fat % (optional, with explanation of why it matters)

Step B — Your Situation
  Daily activity level (5 options: desk job / light active / moderately active / very active / athlete)
  Sleep quality (3 options: poor / average / good — last 2 weeks)
  Stress level (3 options: low / moderate / high — current)
  Medical conditions (free text, optional)
  Medications (free text, optional, with note: "affects training recommendations")
  Injuries (existing field, moved here)

Step C — Your Goal
  Primary goal (dropdown: fat loss / muscle gain / strength / endurance / general health / sport performance)
  Goal detail (free text: "what does success look like in 3 months?")
  Training experience level (existing field)
  Available equipment (existing field)
  Food preferences (checkboxes: omnivore / vegetarian / vegan / dairy-free / gluten-free / no preference)
  Allergies (free text: "e.g. nuts, shellfish, lactose")
```

**Design rules:**
- Each step fits on one screen without scrolling on mobile
- Step B and C are optional but clearly recommended ("Takes 45 seconds. Improves every recommendation.")
- A progress indicator shows "Step 1 of 3" at the top
- Back button between steps — no data lost if user goes back
- Each step saves to `localStorage` independently on Next — user keeps data even if they abandon midway
- Skip button on Steps B and C (not on Step A — basics are required)

**User value:**
The first impression becomes intentional. The user understands they are being onboarded into a system that will use this information. The process communicates: "We take your situation seriously."

---

### Step 2: Add All 18 Profile Fields

**What changes:**
The `apexProfile` object in `localStorage` expands from 7 keys to 18. The `_build_profile_block()` function in `app.py` expands to serialize all 18 fields into the system prompt.

**New profile object shape:**
```
{
  name, age, sex, height, weight, bodyFat,       ← Basics
  activityLevel, sleepQuality, stressLevel,
  medicalConditions, medications, injuries,       ← Situation
  goal, goalDetail, level, equipment,
  foodPreferences, allergies                      ← Goal
}
```

**System prompt additions** (what the AI gains):
- Greeting by name in the first message of each session
- Food preferences applied to every nutrition recommendation
- Allergies as a hard constraint ("never recommend X")
- Activity level used in TDEE calculation
- Sleep quality affects recovery recommendations
- Stress level triggers the recovery-first priority from COACHING_ENGINE.md
- Medical conditions trigger conservative intensity defaults

**Coaching logic triggered by new fields:**
- `stressLevel === 'high'` → AI leads with stress management before training intensity
- `sleepQuality === 'poor'` → AI addresses sleep before adding training volume
- `medicalConditions` not empty → AI defaults to conservative recommendations and recommends medical clearance for high-intensity work
- `activityLevel === 'desk job'` → TDEE adjustment, sedentary multiplier applied in caloric recommendations

**User value:**
Immediate. From the next message after profile completion, the AI addresses the user by name, avoids their allergens, and references their life context. The shift is noticeable.

---

### Step 3: Persistent Goal Display + Edit Profile

**What changes:**

**Goal display:**
The user's primary goal and goalDetail appear as a small persistent element at the top of the chat interface — not intrusive, but always visible. Format: `● Цел: [goal] — [goalDetail]`. Tappable on mobile to open the edit profile flow.

This serves two functions. First, it reminds the user that Apex is oriented around their specific goal, not a generic program. Second, it signals to the AI (which also receives this in the profile block) that this goal is the north star.

**Edit Profile button:**
A settings icon or "Profile" link in the header opens the same multi-step flow, pre-populated with saved values. All fields are editable. On save, `localStorage.apexProfile` is updated. The AI receives the updated profile on the next message — no refresh required.

**What this closes:**
The current UX has no edit path. If a user loses 5kg, there is no way to update their weight. If their goal changes, they cannot update it. If they realize they forgot an allergy, it is gone. This is a trust-breaking gap.

**User value:**
Users who see their goal displayed feel seen. Users who can update their profile feel in control. Both are prerequisites for long-term engagement.

---

### Step 4: System Prompt Context Upgrade

**What changes:**
`_build_profile_block()` in `app.py` is rewritten to produce a richer, more coaching-relevant context block.

**Current output format (approximate):**
```
Профил: мъж, 32г., 85кг, 178см, средно ниво, фитнес зала, наранявания: няма
```

**New output format:**
```
═══ ПОТРЕБИТЕЛСКИ ПРОФИЛ ═══
Име: Иван
Цел: Покачване на мускулна маса | „Искам да кача 5кг мускули за 6 месеца"
Ниво: Средно (3г. опит)
Физически показатели: Мъж, 32г., 85кг, 178см, телесни мазнини: ~18%
Дневна активност: Заседнала работа (офис)
Сън: Среден (6-7 ч./нощ) ← ВАЖНО: адаптирай обема на тренировките
Стрес: Умерен
Оборудване: Фитнес зала
Хранителни предпочитания: Всеядна. Без алергии.
Медицински бележки: Лека болка в дясното коляно при натоварване
══════════════════════════

КОУЧИНГ ПРИОРИТЕТ ЗА ТАЗИ СЕСИЯ:
Сън е под оптималното. Препоръките за обем трябва да са умерени.
Колянът изисква модифицирани вариации на клек.
```

The coaching priority block is generated dynamically based on profile values — not hardcoded. The logic: if sleep is poor, add the sleep note. If stress is high, add the stress note. If medical conditions exist, add the caution note. This is a priority signal to the AI before the conversation begins.

**User value:**
Invisible to the user. Immediate improvement in response quality and specificity. The AI will reference the user's name, goal, and physical context from the first message of every session.

---

## SESSION 2 — ASSESSMENT ENGINE + WORKOUT MEMORY

### Why these belong together

The Assessment Engine produces a verified fitness level. The Workout Memory System stores what the user does with that level. Together they give Apex the two things a human coach has in the first month: a baseline and a history.

Without assessment, the coaching starts from a guess. Without memory, the coaching starts over every session.

---

### Step 5: Fitness Assessment Flow

**Current state:**
User self-selects beginner / intermediate / advanced. There is no verification. Users almost always underestimate or overestimate their level.

**What changes:**
A guided 3-test flow that measures actual performance before the first training plan is generated.

This flow is triggered:
- During onboarding after profile Step C completion
- At any time via "Run Fitness Test" in the profile/settings area
- On demand when a user asks "what level am I at?"

---

**Test 1 — Push-up Test**

Purpose: Upper body and core strength-endurance. Reliable predictor of overall fitness across all ages and sexes.

Flow:
1. Screen shows instructions: "Perform as many push-ups as possible without stopping. Modified (knees) or standard — choose one and stick with it."
2. User taps Start. A stopwatch appears. No time limit — the test ends when the user stops.
3. User taps Done and enters their count.
4. Optional: note whether they used modified (knees) or standard form.

Scoring against age-adjusted norms:

| Age | Beginner (M/F) | Intermediate (M/F) | Advanced (M/F) |
|---|---|---|---|
| 18-29 | <15 / <8 | 15-29 / 8-19 | 30+ / 20+ |
| 30-39 | <13 / <7 | 13-24 / 7-14 | 25+ / 15+ |
| 40-49 | <11 / <5 | 11-20 / 5-12 | 21+ / 13+ |
| 50+ | <9 / <3 | 9-17 / 3-9 | 18+ / 10+ |

---

**Test 2 — Plank Hold Test**

Purpose: Core stability and endurance. Correlates with injury resilience and posterior chain development.

Flow:
1. Instructions screen: standard forearm plank position, illustrated by the existing `pl-` CSS SVG animation.
2. User taps Start. A visible stopwatch counts up. Animated figure holds plank (the animation is already built — reuse it here).
3. User taps Stop when form breaks.
4. Time recorded in seconds.

Scoring:
| Level | Time |
|---|---|
| Beginner | <30 seconds |
| Intermediate | 30-90 seconds |
| Advanced | 90+ seconds |

---

**Test 3 — Squat Endurance Test**

Purpose: Lower body strength-endurance. Assesses hip mobility and bilateral leg strength without equipment.

Flow:
1. Instructions: "Perform as many bodyweight squats as possible with correct form — thighs parallel to floor or below."
2. User taps Start. Stopwatch visible. Existing `sq-` CSS SVG animation plays for form reference.
3. User taps Done and enters count.

Scoring:
| Level | Count |
|---|---|
| Beginner | <20 |
| Intermediate | 20-40 |
| Advanced | 41+ |

---

**Composite Score Logic:**

Each test produces a level (beginner / intermediate / advanced). The composite level is the median of the three results. If results are mixed (e.g., intermediate / beginner / advanced), the system defaults to the lower of the top two.

This score automatically sets `profile.level` and overwrites the self-reported value.

**Stored in `localStorage.apexProfile`:**
```
assessmentDate: "2026-06-23"
assessmentResults: {
  pushups: { count: 18, form: "standard", level: "intermediate" },
  plank: { seconds: 52, level: "intermediate" },
  squats: { count: 34, level: "intermediate" }
}
compositeLevel: "intermediate"
```

**Assessment expiry:**
After 30 days, a soft prompt appears: "Your last assessment was 30 days ago. Want to re-test? Results improve recommendations." Re-testing is voluntary but encouraged.

**User value:**
The user receives an objective answer to "what level am I actually at?" — something most people genuinely do not know. The result is shown with context: "Intermediate — your push-up score is strong, your plank hold is approaching advanced. Your squat endurance has the most room to grow." This is coaching feedback, not just a label.

---

### Step 6: Workout Log Schema in localStorage

**What changes:**
Define the data structure for workout history before building anything that reads or writes it. This step is design, not implementation.

**Schema:**
```
localStorage key: "apexWorkoutLog"
Value: Array of session objects, capped at last 30 sessions.

Each session object:
{
  date: ISO timestamp,
  duration: seconds,
  exercises: [
    {
      name: string,
      sets: [
        {
          reps: number,          ← actual reps completed (baseReps + repDelta)
          rpe: "easy"|"medium"|"hard",
          hr: number|null        ← BPM if measured, null if not
        }
      ]
    }
  ],
  sessionRpe: "easy"|"medium"|"hard"|null,  ← overall session difficulty
  hrMeasurements: [number],                 ← all HR readings in session
  recoveryAtStart: number|null              ← recovery score if check-in done
}
```

**Why cap at 30 sessions:**
localStorage has a 5MB limit. 30 sessions with full set-level data is approximately 15-50KB depending on workout length — well within budget. Beyond 30, the oldest session is dropped.

**Why this step is separate:**
The schema must be agreed before Step 7 (writing) and Step 8 (reading) are built. A poorly designed schema discovered mid-build requires refactoring both ends.

---

### Step 7: Workout Done Screen — Save Session Data

**Current state:**
`_woRenderDone()` displays a completion message and discards all session data on `closeWorkout()`.

**What changes:**
Before displaying the done screen, all session data is assembled from the `_wo` state object and written to `localStorage.apexWorkoutLog`.

**Done screen upgrade:**
The completion screen changes from a generic message to a session summary:

```
🔱 ТРЕНИРОВКАТА ЗАВЪРШИ

5 упражнения · 16 сета · 38 минути

Адаптации тази сесия:
  Клек              → +2 повт. (беше лесно)
  Набирания         → –1 повт. (беше трудно)
  Лицеви            → без промяна

Пулс: 142 уд/мин → Оптимална зона (78% от макс.)

[Затвори]    [Сподели прогреса →]
```

The adaptation summary (which exercises got easier / harder) is the most valuable coaching feedback in the entire workout experience. It is currently discarded. After this step, the user sees it and it is preserved.

**User value:**
The completion screen becomes a coaching moment, not just a dismissal. The user learns something about themselves from every session. The data also persists for the AI to reference.

---

### Step 8: Inject Workout History into AI Context

**What changes:**
The profile context block sent to `/chat` gains a new section: recent workout history.

**Format injected into system prompt:**
```
═══ ПОСЛЕДНИ ТРЕНИРОВКИ ═══
[2026-06-22] Тренировка A — 5 упр. / 16 сета / средна трудност / пулс 138
  Клек 4×12 (лесно), Набирания 3×6 (трудно), Лицеви 3×10 (средно)
[2026-06-20] Тренировка B — 4 упр. / 14 сета / средна трудност
  Мъртва 3×8 (средно), Планк 3×45с (лесно)
[2026-06-18] Тренировка A — 5 упр. / 16 сета / трудна / пулс 156
  Клек 4×10 (трудно), Лицеви 3×9 (средно)
══════════════════════════
Модел: Набиранията са последователно трудни. Клекът се стабилизира след 1 трудна сесия.
```

The "Model" line at the bottom is generated from the workout log — not by the AI, but by a small local analysis function. It detects patterns: which exercises are consistently easy, consistently hard, or improving. This distilled insight goes to the AI as context.

**Pattern detection logic:**
- If the same exercise has been rated "easy" in 2+ of last 3 sessions: flag as "consistently easy → ready for progression"
- If "hard" in 2+ of last 3: flag as "consistently hard → consider modification or volume reduction"
- If RPE improving across 3 sessions (hard → medium → easy): flag as "progressing well"

**User value:**
The AI can now say "You've been finding pull-ups hard in the last two sessions — I'm going to reduce your volume there and add some assistance work." That sentence was impossible before Step 8. After Step 8, it is available in every conversation.

---

## SESSION 3 — RECOVERY FEEDBACK LOOP + DASHBOARD FOUNDATION

### Why recovery comes before the visual dashboard

A dashboard that shows only weight and workout frequency is interesting but not actionable. A dashboard that shows recovery state alongside performance data tells the user *why* their numbers are moving the way they are.

The recovery check-in is also the fastest input to build. Three taps. Ten seconds. And it feeds directly into the AI context — meaning it improves recommendations from day one.

---

### Step 9: Daily Recovery Check-In

**What changes:**
A check-in prompt appears once per day, at the start of the first chat session of the day (not as a blocker — as a brief, skippable card above the chat input).

**Check-in UI (3 inputs, no typing required):**

```
┌─────────────────────────────────────────────┐
│  ⚡ Бързо - как се чувстваш днес?           │
│                                             │
│  Сън:     [😴 Лош] [😐 Среден] [😊 Добър] │
│  Енергия: [🔋 Ниска] [⚡ Средна] [🚀 Висока]│
│  Стрес:   [😤 Висок] [😐 Среден] [😌 Нисък] │
│                                             │
│           [Запази]  [Пропусни]              │
└─────────────────────────────────────────────┘
```

No text input. Three rows of three buttons each. Total interaction time: 8-10 seconds.

**When it appears:**
- First session of the day only
- After the greeting loads
- Disappears after save or skip — does not reappear until next day
- Respects the `lang` setting (BG/EN)

**Stored in `localStorage.apexRecovery`:**
```
Array of daily entries, capped at last 90 days:
{
  date: "2026-06-23",
  sleep: "good"|"average"|"poor",
  energy: "high"|"medium"|"low",
  stress: "low"|"moderate"|"high"
}
```

Resting HR from the previous workout's post-exercise measurement (stored in workout log) contributes to the recovery score automatically — no extra input required.

**User value:**
The check-in takes less time than unlocking a phone. It is the most frictionless data input in the product. Users who complete it consistently will receive progressively better recovery recommendations — and they will feel the difference. The check-in is also a daily engagement touchpoint that builds habit.

---

### Step 10: Recovery Score Calculation

**What changes:**
A local function calculates today's recovery score (0-100) using the COACHING_ENGINE.md formula, sourcing data from:
- `apexRecovery` (today's sleep, energy, stress)
- `apexWorkoutLog` (resting HR from last measurement, vs. personal baseline)
- `apexWorkoutLog` (session completion rate: last 14 days)

**Calculation (per COACHING_ENGINE.md Section 6):**

```
Sleep Score (0-25):
  good → 25, average → 20, poor → 12, no data → 15

Energy Score (0-25):
  high → 25, medium → 18, low → 10, no data → 15

Stress Score (0-25):
  low → 25, moderate → 18, high → 10, no data → 15

Training Load Score (0-25):
  ≥75% sessions completed last 14d, avg RPE ≤7 → 25
  ≥75% sessions, avg RPE >7 → 15
  <75% sessions → 8
  no data → 15

Total: sum of four components (0-100)
```

**Score interpretation:**
```
85-100 → Optimal (green)
65-84  → Good (light green)
45-64  → Moderate (yellow)
25-44  → Poor (orange)
<25    → Critical (red)
```

The score is calculated each time the app loads and cached in session memory — not in `localStorage` (it is derived, not raw data).

---

### Step 11: Recovery State Injected into AI Context

**What changes:**
The profile context block gains a recovery section.

**Format:**
```
═══ ВЪЗСТАНОВЯВАНЕ ДНЕС ═══
Резултат: 58/100 — Умерено
Сън: Среден · Енергия: Ниска · Стрес: Висок
Последен пулс в покой: 74 уд/мин (базова линия: 68)

⚠️ КОУЧИНГ ПРИОРИТЕТ:
Стресът е висок, а енергията е ниска. Ако потребителят иска тренировка днес,
препоръчай намален обем (−25%) или активно възстановяване.
Не препоръчвай максимално усилие при тези показатели.
══════════════════════════
```

The coaching priority line at the bottom is the most important part. It translates the raw score into a behavioral instruction for the AI. The AI does not need to calculate — it receives the conclusion and the reasoning.

**Coaching priority logic:**
- Score ≥85: "Optimal recovery. Proceeding as planned is appropriate. User can attempt peak effort today."
- Score 65-84: No special instruction. Proceed as normal.
- Score 45-64: "Moderate recovery. Reduce session intensity by 15-20% if training today."
- Score 25-44: "Poor recovery. Recommend active recovery or rest. If user insists on training, reduce volume by 40%."
- Score <25: "Critical recovery state. Strongly recommend full rest. Ask what has changed this week."

**User value:**
The AI starts proactively managing recovery without the user asking. A user who opens the app feeling exhausted and types "I want to train today" receives: "Your recovery score is 52 today — your stress is high and energy is low. I can give you a training session, but I'd recommend a lighter version today. Here's why..." That response is currently impossible. After Step 11, it is automatic.

---

### Step 12: Progress Panel — Weight Check-Ins + Streak

**What changes:**
A new panel is accessible from the header. Not a separate page — a sliding drawer or modal that opens over the chat interface.

**Panel structure (minimal viable first version):**

```
┌─────────────────────────────────────────────┐
│  ПРОГРЕС                              [×]   │
│                                             │
│  Цел: Покачване на мускулна маса            │
│  Старт: 82кг  →  Сега: 84.5кг  (+2.5кг)   │
│                                             │
│  ┌─ Тегло (последни 30 дни) ──────────────┐ │
│  │  [chart area — Step 13]                │ │
│  └─────────────────────────────────────────┘ │
│                                             │
│  Тренировки тази седмица: ████░ 4/5        │
│  Серия без прекъсване: 12 дни 🔥           │
│  Тренировки общо: 23                        │
│                                             │
│  Последни 7 сесии: [Step 14]               │
│                                             │
│  + Въведи тегло днес: [___] кг  [Запази]   │
└─────────────────────────────────────────────┘
```

**Weight check-in:**
Input field + save button. Writes to `localStorage.apexWeightLog`:
```
Array of { date, weight } entries, uncapped (typical user: 1-2/week × 52 weeks = 100 entries max)
```

**Streak calculation:**
A training "streak" is defined as consecutive days with at least one workout OR an intentional rest day (rest days must be logged to count). Logic:
- Check workout log for each of the last N days
- Count consecutive days from today backward where a session exists
- Break the streak on any day with no session and no rest log

For MVP: streak counts consecutive days with at least one workout session. Rest day logging is a 2.0 feature.

**User value:**
Streak is the most motivating number in the product. Many users will open the app specifically to maintain it. The weight trend provides the longitudinal view that chat history cannot — the user sees their arc at a glance.

---

## SESSION 4 — DASHBOARD VISUALS + POLISH

### Step 13: Weight Trend Chart

**What changes:**
A weight trend visualization in the progress panel. Built with SVG path drawing — no external library required.

**Chart design:**
- Line chart: X axis = dates (last 30 days), Y axis = weight (kg)
- Each recorded weigh-in is a data point (dot + connected line)
- A trend line (7-day rolling average) drawn in a lighter color to reduce noise
- Goal weight shown as a horizontal dashed reference line (if goal is weight-related)
- Color coding: trend moving toward goal = green, away from goal = red/amber

**Edge cases to handle:**
- Fewer than 3 data points: show the dots without a line, with a prompt to "check in more often for trend analysis"
- Non-weight goals (strength, endurance): show the chart but with a note: "Weight is secondary to your strength goal — use it as context, not as the primary metric"
- Weight fluctuations of ±1kg day-to-day: expected, normal. The trend line handles this visually.

**Companion AI note:**
When a user opens the progress panel and their weight trend is flat despite a fat loss goal, Apex should be able to reference this. The AI context block should include: "Weight trend: 30-day change: −0.2kg. User is in a fat loss phase. Progress is slower than expected."

**User value:**
The chart makes progress (or the lack of it) undeniable. Users who do not track weight often believe they are not progressing. The chart frequently reveals they are. The reverse is also true — and that honest feedback is the trigger for the "investigate before adjusting" conversation described in COACHING_ENGINE.md.

---

### Step 14: Workout History Display

**What changes:**
The last 7 workout sessions are displayed in the progress panel as a compact list.

**Format per session:**

```
● 22 юни — 5 упр. / 16 сета / Средна
  Клек ↑  Лицеви → Набирания ↓

● 20 юни — 4 упр. / 14 сета / Лесна
  Мъртва → Планк ↑

● 18 юни — 5 упр. / 16 сета / Трудна
  Клек ↓  Лицеви →
```

Arrow icons:
- ↑ = exercise got easier (repDelta positive or RPE improved vs. previous session)
- → = exercise unchanged
- ↓ = exercise got harder (repDelta negative or RPE worsened)

Tapping a session expands it to show full exercise detail.

**Consistency view:**
Above the session list: a 4-week dot-grid calendar. Each day is a dot. Trained = filled red dot. Rest = empty dot. Today = highlighted.

```
Юни  Mo Tu We Th Fr Sa Su
w1   ●  ○  ●  ○  ●  ○  ○
w2   ●  ○  ●  ○  ○  ●  ○
w3   ●  ○  ●  ○  ●  ○  ○
w4   ●  ○  ◉  ← today
```

**User value:**
Seeing the workout history laid out forces the user to confront the reality of their consistency. Four weeks of dots is harder to rationalize than a vague memory of "I've been training pretty regularly." It also creates pride when the pattern is good — social reinforcement through visible evidence.

---

### Step 15: Workout Mode Translation + Completion Upgrade

**What changes:**

**Translation:**
All hardcoded Bulgarian strings in the workout overlay are routed through `T[lang]`. Affected strings:
- Phase labels: "Сет X от Y" / "Почивка" / "Измери пулса"
- Button labels: "✓ Готово" / "Пропусни →" / "Отказ"
- Coach comments pool: `_WO_CMT` currently has only Bulgarian entries — add EN equivalents
- Done screen: "ТРЕНИРОВКАТА ЗАВЪРШИ" and stats line
- Feedback labels: "Лесно" / "Средно" / "Трудно"
- Rest reason text: `_woRestReason()` output
- HR measurement instructions

**`_woParse()` resilience upgrade:**
Column header matching is currently exact-string `includes()`. Replace with a scoring function:
- Header matches if it contains any keyword from an expanded synonym list
- Matching is case-insensitive and diacritic-tolerant
- Column detection succeeds if ≥2 of 3 required columns (exercise, sets, reps) are found
- Fallback: if reps column not found, default to 10 reps (better than silently skipping workout mode)

New synonym lists:
```
Exercise column: упражнение, exercise, движение, movement, ex
Sets column: серии, sets, сет, сетове, series
Reps column: повторения, reps, repetitions, повт, брой
Rest column: почивка, rest, пауза, pause, recovery
```

**Completion screen upgrade (extension of Step 7):**
The done screen built in Step 7 also includes:
- Recovery recommendation: "Хидратирай се — поне 500мл вода в следващите 30 минути."
- Post-workout nutrition window reminder if > 45 minutes have passed
- Prompt to record today's weight if they have not done so in 48+ hours

**User value:**
English users can finally use workout mode without switching languages mid-session. The `_woParse()` fix stops the silent failure that has prevented some users from entering workout mode at all. The completion screen additions make the post-workout window actionable.

---

## DEPENDENCY MAP

```
Step 1 (Profile redesign)
  └── Step 2 (18 fields) — requires Step 1 UI complete
        └── Step 4 (system prompt) — requires Step 2 schema
              └── Step 11 (recovery in context) — requires Step 4 and Step 10

Step 5 (Assessment flow) — independent, can run parallel to Steps 1-4
  └── Writes to profile object from Step 2

Step 6 (Workout log schema) — design step, no dependencies
  └── Step 7 (Save session) — requires Step 6 schema
        └── Step 8 (History in context) — requires Step 7 data
        └── Step 14 (History display) — requires Step 7 data
        └── Step 12 (Progress panel) — requires Step 7 for session count/streak

Step 9 (Recovery check-in) — independent after Step 2 (needs profile for context)
  └── Step 10 (Recovery score) — requires Step 9 data
        └── Step 11 (Recovery in context) — requires Step 10

Step 12 (Progress panel) — requires Step 7 (workout count) and Step 9 (weight check-in)
  └── Step 13 (Weight chart) — requires Step 12 panel structure
  └── Step 14 (Workout history display) — requires Step 12 panel and Step 7 data

Step 15 (Translation + parser fix) — independent of all above
```

**Parallel tracks possible in Session 2:**
Steps 5 (Assessment) and 6 (Schema design) are independent and can be worked simultaneously. Step 5 is UI-heavy. Step 6 is design-only.

**Critical path:**
`1 → 2 → 4 → 11` is the longest dependency chain. Everything feeding the AI context must be complete before the payoff of improved recommendations is visible.

---

## RISKS AND MITIGATIONS

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| localStorage quota exceeded | Low | High | Cap all arrays explicitly. Workout log: 30. Recovery log: 90. Weight log: uncapped but small. Monitor combined size. |
| `_woParse()` still misses some AI formats | Medium | Medium | Resilience upgrade in Step 15 closes most cases. Accept that edge cases remain until Step 8 makes workout mode less critical (AI can reference history even without the button firing). |
| Assessment flow creates friction and kills onboarding | Medium | High | Assessment is optional during onboarding. Can be triggered at any time. Never block a new user from chatting. |
| Weight chart on small screens | Low | Low | Use horizontal scroll inside chart container. Never clip data. SVG viewBox handles responsive scaling. |
| Recovery check-in daily prompt becomes annoying | Medium | Medium | Make it skippable in one tap. Remember skip per day (not per session). Never show it mid-conversation. |
| Multi-step profile onboarding feels too long | Medium | High | Steps B and C are clearly optional and skippable. Include time estimate ("45 seconds"). Users who skip still get Step A data — that alone is better than the current 7 fields. |

---

## WHAT APEX 1.5 DOES NOT INCLUDE

These are explicitly out of scope. Not because they are unimportant — because they require a database, user accounts, or significant backend work that belongs in Apex 2.0.

- **Cross-device sync** — all data stays in `localStorage`. Device switch loses history.
- **Server-side workout log** — log exists only in the browser.
- **User accounts / login** — no authentication layer.
- **Apex Fitness Score** — depends on server-side data for trajectory component.
- **Adaptive programming automation** — the AI adapts based on context injected in Step 8, but there is no automated plan generation. The user still asks for a plan.
- **Progress sharing / social features**
- **Push notifications / hydration reminders**
- **Nutrition logging**
- **Full periodization engine**

---

## DEFINITION OF DONE FOR APEX 1.5

Apex 1.5 is complete when:

- [ ] Profile modal collects all 18 fields across 3 steps
- [ ] Profile is editable at any time from the header
- [ ] User's goal is displayed persistently in the UI
- [ ] Fitness assessment flow runs through 3 tests and sets level automatically
- [ ] Assessment can be retaken at any time
- [ ] Workout sessions are saved to `localStorage` with full set-level data
- [ ] Workout done screen shows per-exercise adaptation summary
- [ ] Last 3 workouts are included in AI context on every chat request
- [ ] Daily recovery check-in appears once per day (skippable)
- [ ] Recovery score is calculated and injected into AI context
- [ ] AI proactively modifies recommendations when recovery score is below 65
- [ ] Progress panel shows weight trend chart, consistency calendar, last 7 sessions
- [ ] Weight check-in is available in progress panel
- [ ] Workout overlay is fully translated to BG/EN
- [ ] `_woParse()` handles synonym variation and case differences

---

## EXPECTED USER EXPERIENCE AFTER 1.5

**Day 1 (new user):**
User completes 3-step onboarding in ~2 minutes. Takes the 3 fitness tests and receives their level with coaching feedback. Opens chat. AI greets them by name, references their goal, acknowledges their fitness level came from an actual test. First recommendation is personalized to their equipment, goal, allergies, and sleep quality.

**Week 2 (returning user):**
User opens app. Recovery check-in appears. Three taps. Chat opens. AI says: "Your recovery score is 71 — good. Your resting HR is slightly elevated versus your baseline. Let's keep today's session at planned intensity but skip the extra heavy set at the end." User did not ask for this. Apex offered it because it had the data.

**Week 6 (engaged user):**
User opens progress panel. Sees 18kg lost over 6 weeks (fat loss goal). Consistency calendar shows 4 of 5 planned sessions per week, consistently. The workout history shows lunges getting progressively easier (↑ markers three sessions in a row). AI references this: "Your lunge performance has improved consistently — you're ready to add a third working set." The user did not tell the AI this. The workout log did.

That is the Apex 1.5 experience.

---

*Document version: 1.0 — June 2026*
*Next review: after Session 1 implementation is complete*
*Author notes: Update dependency map if implementation order changes. Update Definition of Done as features are checked off.*
