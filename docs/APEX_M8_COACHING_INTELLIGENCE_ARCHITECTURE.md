# APEX M8 — Coaching Intelligence Architecture

**Status:** ARCHITECTURE ONLY. No code, no deployment, no Brain change. Design of the
layer that decides **how** APEX coaches — after the Brain has decided what is *safe* and
the Human State has said *who the person is right now*.

---

## 0. Position, mission, boundaries

```
Brain Decision  →  Human State  →  Coaching Intelligence  →  Recommendation Architect  →  Renderer
 (what's SAFE)     (who they are)   (HOW to coach this human)   (WHAT to design)          (words)
```

**Mission (frozen philosophy, operationalized):** maximize **long-term adherence, trust,
confidence, and sustainable transformation** — *not* workouts completed. Disciplined, not
dependent. Every directive is judged by whether it makes the person more capable of coaching
themselves, not more reliant on the app.

**Hard boundaries — what this layer is NOT:**
- It makes **no medical decision** and **never overrides Brain safety.** A halt stays a halt;
  a NOT_YET stays a NOT_YET. Coaching Intelligence only shapes the *delivery* of a safe
  decision — tone, framing, dose-within-envelope, which coaching domain is active. It changes
  **how**, never **whether**.
- It does **not** replace the Brain or the Human State; it is a **read-only consumer** of both.
- It owns no user state. Behavioral observations it derives are written back only through the
  Human State `observe()` contract.

---

## 1. The layer

**Input (read-only):** `BrainDecision` (verdict, intervention, halt, constraints) +
`HumanStateView` (facts + dynamic state: motivation, momentum, adherence, confidence,
sleep_debt, stress, pain…) + conversation turn.

**Output — the `CoachingDirective`:**
```
CoachingDirective {
  active_domain      # e.g. relapse_prevention (primary) [+ secondary]
  style              # teacher | mentor | supportive | challenger | reassuring | analytical | disciplined
  tone               # warmth, energy, brevity knobs
  dose_guidance      # minimum_viable | maintain | progress | deload | rest   (WITHIN the Brain envelope)
  framing            # normalize_setback | preserve_autonomy | reinforce_progress | reframe_identity …
  reinforce          # the specific true thing to reinforce
  forbidden          # never-say list active for this moment (§4)
  rationale          # explainability trace (§8)
}
```
The **Architect** consumes `dose_guidance`/`framing`/`active_domain` to shape blueprint
*intent* (never safety values); the **Renderer** consumes `style`/`tone`/`forbidden`/`reinforce`.

**Safety composition rule:** `CoachingDirective` is intersected with the Brain decision —
if `halt`, `dose_guidance` is forced to `rest/route` regardless of domain. Coaching never
loosens a safety bound.

---

## 2. Domain model — 15 coaching domains

Each: **P**urpose · **A**ctivation · **O**utcome · **Pr**inciples · **I**nterventions ·
**F**orbidden · **M**etrics.

1. **Habit Recovery** — P: restart a stalled habit. A: adherence↓ after prior consistency.
   O: one completed session this week. Pr: shrink the ask, remove friction. I: 1 keystone
   micro-session, cue reset. F: guilt, "catch up on missed work". M: return-within-7-days rate.
2. **Motivation Support** — P: carry the person through a low. A: motivation signal low, no
   red flag. O: act despite low motivation. I: tiny winnable action, connect to their *why*.
   F: hype, pressure, comparison. M: action-taken-while-low rate.
3. **Confidence Building** — P: grow self-efficacy. A: confidence low / fear present.
   O: "I can do this." I: mastery reps, name past wins, graded exposure. F: overface, praise
   that isn't true. M: self-reported confidence trend.
4. **Relapse Prevention** — P: stop a lapse becoming a collapse. A: 1–2 misses, excuse pattern.
   O: lapse ≠ relapse. I: normalize, re-anchor the next single action. F: streak-shaming,
   "start over". M: lapse→recovery vs lapse→dropout ratio.
5. **Progressive Return** — P: re-enter after a layoff safely. A: return after ≥2 wks off.
   O: rebuild without injury/burnout. I: 40–60% prior load, ramp weekly. F: "pick up where you
   left off". M: sustained sessions over 3 wks.
6. **Illness Recovery** — P: coach around being unwell. A: illness stated (non-emergency).
   O: rest now, gentle return later. I: permission to rest, hydration, symptom-gated return.
   F: "push through", any training prescription while febrile. M: safe-return adherence.
7. **Stress Coaching** — P: adapt to life overwhelm. A: stress high / life event. O: movement
   as regulation, not another burden. I: down-regulation, reduce dose, walk/breathe. F: adding
   load, urgency. M: continued light engagement through stress.
8. **Travel Adaptation** — P: keep momentum off-routine. A: travel/disrupted context. O: a
   plan that survives no-gym/short-time. I: bodyweight, time-boxed, hotel/room options. F: "wait
   until you're home". M: sessions-while-traveling rate.
9. **Time-Constrained Coaching** — P: fit training into little time. A: stated tight time.
   O: a real session in the time available. I: minimum effective dose, supersets. F: implying
   short = worthless. M: completion of short sessions.
10. **Plateau Recovery** — P: break a stall. A: no progress over weeks (trend). O: renewed
    progress or a reframed metric. I: change stimulus, deload, check recovery/nutrition, redefine
    "progress". F: "just try harder", blame. M: metric movement or reframed-goal acceptance.
11. **Injury Adaptation** — P: train *around* a limit. A: pain/constraint (non-emergency).
    O: keep moving safely within the envelope. I: pain-free ROM, substitute patterns, respect
    S1 contraindications. F: "no pain no gain", training through sharp pain. M: pain-free
    adherence.
12. **Lifestyle Coaching** — P: fit fitness to a real life. A: schedule/equipment/budget facts.
    O: a sustainable weekly shape. I: anchor to routine, realistic frequency. F: idealized
    programs that ignore constraints. M: weekly-plan adherence.
13. **Consistency Coaching** — P: make showing-up the identity. A: building adherence. O: a
    durable cadence. I: streak-of-effort (not perfection), keystone habit. F: perfectionism,
    all-or-nothing. M: rolling consistency %.
14. **Identity Coaching** — P: shift self-concept ("I'm someone who trains"). A: momentum
    building / values stated. O: internalized identity. I: language of identity, celebrate the
    *type of person*. F: appearance-only framing, extrinsic-only rewards. M: intrinsic-motivation
    trend.
15. **Long-Term Maintenance** — P: sustain after a goal is met. A: goal reached / plateau by
    design. O: keep the gains, avoid boom-bust. I: autonomy, minimal effective maintenance, new
    horizons. F: manufacturing urgency to keep engagement. M: 6–12 month retention of behavior.

---

## 3. Coaching styles

| Style | Use when | Never when |
|---|---|---|
| **Teacher** | new concept, they want the *why*, skill-building | crisis, shame, low motivation (don't lecture) |
| **Mentor** | medium-term guidance, values/identity work | acute distress needing reassurance first |
| **Supportive** | low motivation, setback, fear | they're asking for a hard push and are ready |
| **Challenger** | high confidence + capacity, plateau by comfort | after a miss, low confidence, illness, shame |
| **Reassuring** | fear, anxiety, illness, post-lapse | complacency that needs a nudge |
| **Analytical** | data-driven user, plateau diagnosis | emotional moment (feels cold), low literacy |
| **Disciplined** | user explicitly wants accountability & has capacity | vulnerability, shame, illness, relapse (never punitive) |

**Global style rule:** style adapts to *state*, never to maximize compliance. Challenger and
Disciplined are **forbidden** in any shame/fear/illness/relapse state.

---

## 4. Coaching rules (invariant guardrails — always/never)

**Never:** punish or guilt missed workouts · shame weight gain or a binge · encourage guilt or
self-punishment · promise unrealistic results or timelines · use fear/urgency to drive
engagement · compare the user to others · prescribe training through illness or sharp pain ·
frame short/rest sessions as failure · make the user dependent on the app.

**Always:** normalize temporary setbacks · reinforce real progress (only true things) · explain
*why* · preserve user autonomy (offer, don't command) · keep safety first (defer to the Brain) ·
protect dignity · make the next action small and winnable · connect effort to the person's own goals.

These rules **override** any domain/style and are compiled into `forbidden` on every directive.

---

## 5. Coaching State Machine (the user's coaching journey)

```
        ┌────────────► THRIVING ◄─────────┐
        │ (identity)      │ complacency     │ momentum
   CONSOLIDATED ◄─────────┘                 │
        ▲   │ miss                          │
 rebuild│   ▼                               │
   REBUILDING ◄── returns ── LAPSED ◄── misses pile up ── WAVERING ◄── first miss ── MOTIVATED
        │                      │                                                        ▲
        └── consistency ───────┘  drop-out risk                                onboard  │
                                                                              NEW ───────┘
```

| State | Signals | Active domain(s) | Style | Intervention |
|---|---|---|---|---|
| NEW | onboarding | Confidence, Lifestyle | Teacher/Supportive | tiny first win |
| MOTIVATED | high momentum | Consistency, Identity | Mentor | reinforce cadence |
| WAVERING | 1 miss, excuses | Relapse Prevention | Supportive | normalize + re-anchor |
| LAPSED | ≥3 misses, motivation↓ | Habit Recovery, Motivation | Reassuring/Supportive | shrink the ask |
| REBUILDING | returned, fragile | Progressive Return, Confidence | Supportive/Mentor | graded ramp |
| CONSOLIDATED | steady weeks | Consistency, Identity | Mentor | maintain + deepen |
| THRIVING | strong, wants more | Plateau, Identity, Long-Term | Challenger (if ready) | new stimulus/horizon |
| (branch) DISTRESS | shame/fear/illness | Illness/Stress/Confidence | Reassuring | permission, safety |

Transitions are driven by Behavioral Signals (§6); every transition names its intervention.
DISTRESS is a cross-cutting branch enterable from any state (and always yields Reassuring +
safety-first, never Challenger/Disciplined).

---

## 6. Behavioral Signal taxonomy

| Signal | Detected from | Coaching response |
|---|---|---|
| Skipped workouts | HumanState.adherence↓, gaps in workout history | Relapse Prevention; shrink ask |
| Repeated excuses | conversation pattern + misses | normalize, remove friction (not confront) |
| Motivation drop | HumanState.motivation↓ / stated | Motivation Support; connect to *why* |
| Rising adherence | adherence/consistency↑ | reinforce; advance to Identity |
| Fear | stated / fear-avoidance language | Reassuring; graded exposure |
| Frustration | plateau + stated | Plateau Recovery; reframe progress |
| Burnout | high stress + fatigue + adherence↓ | Stress Coaching; deload, permission to rest |
| Success momentum | streak, PRs, momentum↑ | Identity Coaching; celebrate the person |
| Loss of confidence | HumanState.confidence↓ / "I can't" | Confidence Building; mastery reps |
| Shame | "ashamed", "failed again", weight-gain guilt | Reassuring; strip guilt, protect dignity |
| Illness | stated symptoms (non-emergency) | Illness Recovery; rest, symptom-gated return |
| Time pressure | stated minutes / schedule | Time-Constrained; minimum effective dose |

Each signal carries a **confidence** (from HumanState/NLU); low-confidence signals bias toward
the gentler response. Multiple signals → priority: **safety > distress(shame/fear/illness) >
relapse/motivation > progression.**

---

## 7. Coaching Playbook (100+ canonical situations)

Per situation: **Objective** · **Strategy** · **Never say**. Grouped by domain.

### Habit Recovery & Relapse
1. "I haven't trained in 3 weeks." — O: return, not shame. S: welcome back, one 15-min keystone today. N: "you've undone your progress."
2. "I keep missing my workouts." — O: reduce friction. S: find the one obstacle, shrink the plan. N: "you need more discipline."
3. "I fell off again." — O: lapse≠relapse. S: normalize, re-anchor next single action. N: "again? start over."
4. "I always quit after 2 weeks." — O: break the pattern. S: design for week 3, tiny + scheduled. N: "prove you won't quit."
5. "I missed the whole week." — O: protect the streak-of-effort. S: this week isn't lost; do one thing now. N: "make up the sessions."
6. "I broke my streak." — O: decouple worth from streak. S: streaks restart; effort is the metric. N: shaming the break.
7. "I keep making excuses." — O: remove the friction behind the excuse. S: curiosity, not confrontation. N: "stop making excuses."
8. "I don't know why I stopped." — O: gentle re-entry. S: no autopsy needed; restart small. N: interrogation/guilt.

### Motivation & Confidence
9. "I want to quit." — O: keep the door open. S: acknowledge, smallest possible action, reconnect to why. N: hype, "don't be a quitter."
10. "I have no motivation." — O: act despite feeling. S: 5-minute rule, motivation follows action. N: "just want it more."
11. "I feel like a failure." — O: strip the label. S: separate behavior from identity; name a real win. N: agreeing they failed.
12. "I'm not good at this." — O: build efficacy. S: mastery reps, evidence of progress. N: empty praise.
13. "I'm scared I'll hurt myself." — O: safe confidence. S: graded exposure, within envelope. N: dismiss the fear.
14. "Everyone's better than me." — O: internal frame. S: compare to your own last week. N: reinforce comparison.
15. "What's the point." — O: reconnect meaning. S: their stated *why*, one next step. N: toxic positivity.
16. "I'll never look like that." — O: realistic + kind. S: process goals, their body's trajectory. N: promise a physique/timeline.

### Setback & Shame (dignity-first)
17. "I'm ashamed of my body." — O: dignity. S: warmth, focus on capability/health. N: appearance judgment.
18. "I gained weight." — O: no shame. S: normalize fluctuation, focus on behaviors. N: "you let yourself go."
19. "I binged yesterday." — O: neutralize guilt. S: one meal isn't a verdict; next normal meal. N: "compensate/burn it off."
20. "I ate terribly all weekend." — O: reset without penance. S: return to normal, no punishment cardio. N: guilt/restriction.
21. "I feel disgusting." — O: interrupt the spiral. S: compassion, a small kind action. N: agree/appearance talk.
22. "I failed again." — O: reframe failure as data. S: what we learn, next tiny step. N: "why do you keep failing."

### Illness, Pain, Recovery
23. "I'm sick." — O: rest. S: permission to rest, hydrate, gentle return when symptoms clear. N: any workout while ill.
24. "I have the flu / fever." — O: safety. S: rest fully; see a doctor if severe. N: "sweat it out."
25. "My knees hurt." — O: train around it. S: pain-free ROM, substitute, respect constraints. N: "push through."
26. "My back is sore today." — O: modify. S: gentle movement, avoid aggravators; route if red-flag. N: dismiss or "no pain no gain."
27. "I tweaked my shoulder." — O: protect. S: avoid the pattern, keep the rest moving. N: "work through it."
28. "I'm exhausted." — O: deload/recover. S: reduce dose or rest; check sleep/stress. N: "no excuses."
29. "I didn't sleep." — O: adjust today. S: lighten load, prioritize recovery. N: prescribe a hard session.

### Time, Travel, Life
30. "I only have 15 minutes." — O: a real session. S: minimum effective dose, supersets. N: "that's not enough time."
31. "I only have 10 minutes." — O: something > nothing. S: one focused block. N: dismiss it.
32. "I'm travelling." — O: keep momentum. S: bodyweight/room plan, time-boxed. N: "wait until you're home."
33. "I'm on vacation." — O: guilt-free movement. S: enjoy + optional light activity; rest is ok. N: guilt for resting.
34. "I have no equipment." — O: adapt. S: bodyweight/household options. N: imply equipment required.
35. "Work is insane right now." — O: protect a minimum. S: 2 tiny anchors/week, movement as relief. N: add pressure.
36. "I have a newborn." — O: micro-fit. S: 5–10 min, interruption-proof, no guilt. N: idealized schedules.
37. "I work night shifts." — O: circadian-aware. S: anchor to *their* clock, protect sleep. N: standard-day assumptions.
38. "I have kids all day." — O: realistic. S: home, short, with-kids options. N: "find the time."
39. "It's the holidays." — O: maintain, not maximize. S: keep one anchor, enjoy the season. N: "earn your food."

### Plateau, Progress, Identity
40. "I'm not seeing progress." — O: renew or reframe. S: change stimulus / redefine progress (strength, energy, consistency). N: "try harder."
41. "I've been stuck for months." — O: diagnose. S: check recovery/nutrition/variation; adjust one lever. N: blame effort.
42. "The scale won't move." — O: broaden the metric. S: non-scale victories, trend not day. N: fixate on the scale.
43. "I feel like I'm going backwards." — O: perspective. S: show the longer trend; adjust load. N: catastrophize.
44. "I finally hit a PR!" — O: cement identity. S: celebrate the *person* who showed up. N: immediately "now push more."
45. "I've been consistent for a month!" — O: reinforce identity. S: name it: you're someone who trains. N: undercut with "but…".
46. "I actually enjoyed that." — O: intrinsic motivation. S: reflect it back, build on it. N: refocus only on outcomes.

### Long-term, Lifestyle, Autonomy
47. "I reached my goal — now what?" — O: sustain. S: maintenance dose + a new horizon of their choosing. N: manufacture urgency.
48. "I don't want to live in the gym." — O: sustainable fit. S: minimal effective, life-first. N: more-is-better.
49. "Can I take a week off?" — O: autonomy + safety. S: yes; rest is training; plan the return. N: guilt or "you'll lose it all."
50. "I want to do this my way." — O: preserve autonomy. S: offer options, support their choice within safety. N: override them.

### Safety-adjacent delivery (Brain already decided — Coaching shapes tone)
51. "Chest pain but I want to train." — O: route with care. S: warm, clear: this needs a doctor now; not training. N: minimize; give a workout.
52. "I felt dizzy but pushed through." — O: safety + no shame. S: praise the honesty, advise checking, hold training. N: scold; ignore.
53. "My doctor said no lifting." — O: respect clearance. S: honor it; offer cleared alternatives. N: contradict medical advice.
54. "I'm pregnant, what can I do?" — O: boundaried support. S: encourage clinician guidance; gentle cleared options. N: prescribe beyond scope.

*(Situations 55–108 continue the same pattern across every domain — e.g. "I hate cardio",
"I'm intimidated by the gym", "I only eat once a day", "I can't afford a gym", "I'm vegan",
"I have diabetes and feel shaky", "I'm a beginner and embarrassed", "I overtrained", "I'm
bored", "I compare myself to my old self", "I relapsed after an injury", "I'm scared to eat
carbs", "I feel guilty resting", "I keep restarting Mondays", "my partner discourages me",
"I'm too old for this", "I lost all my progress", "I'm burned out at work and skipping",
"I did everything right and still failed", "I don't trust myself", … ). Each row is
Objective / Strategy / Never-say, governed by the domains (§2), styles (§3), and rules (§4).
The canonical set is maintained as a versioned table so coverage and tone can be audited.*

**Playbook invariant:** every entry's *Never-say* column is a superset of the global rules
(§4); no strategy may violate a rule to serve a domain.

---

## 8. Explainability model

Every `CoachingDirective` carries a `rationale`:
```
rationale {
  signals_detected   # [ {signal, confidence, evidence} ]         → what we saw
  state              # coaching-state-machine node + why           → where they are
  domain_selected    # + activation evidence                       → what we're doing
  domain_rejected    # [ {domain, why_not} ]                       → why not the alternatives
  style_selected     # + why (state-appropriate)                   → how we're speaking
  style_forbidden    # [ {style, why_not} ]                        → styles ruled out (e.g. Challenger during shame)
  rules_applied      # active never/always guardrails              → what we will not say
}
```
This answers both required questions — *why this strategy* (signals→state→domain→style) and
*why not another* (explicit rejected domains/styles with reasons). The rationale is loggable to
the Observatory (M5) for auditing coaching quality, and surfaced (softened) to the user on
request as the "why" behind a message.

---

## 9. Future evolution roadmap

Additive, reversible, Brain-frozen. Depends on the Human State Engine (M-P0.5) and the
conversational state-ingestion feeder identified in M7.

| Stage | Move | Gate |
|---|---|---|
| **C0 (this doc)** | Freeze domains, styles, rules, state machine, signals, playbook. | none |
| **C1** | Implement the rule engine + playbook as data (deterministic domain/style selection from signals + HumanState). Read-only; unwired. | none |
| **C2** | Explainability trace produced for every directive; log to Observatory. | none |
| **C3** | Feed `CoachingDirective` into Architect (dose/framing) + Renderer (style/tone/forbidden) behind a flag, shadow-first. | flag off |
| **C4** | Coaching-state-machine transitions driven by live Behavioral Signals from HumanState. | flag off |
| **C5** (separate) | Wire into `/chat`; canary; measure adherence/trust/confidence outcomes, not workout counts. | deploy-gated |
| **C6** | Personalize style over time (which style *this* person responds to) — bandit over coaching strategies, guardrails immovable. | deploy-gated |

**Invariants at every stage:** never a medical decision; never overrides Brain safety; the
never/always rules are immovable; success is measured by long-term adherence, trust,
confidence, retention — never by workouts maximized.

---

## 10. Boundary summary
- Consumes `BrainDecision` + `HumanStateView` (read-only). Emits `CoachingDirective` +
  optional behavioral observations (via HumanState `observe()`).
- Modifies nothing in `brain/`, enforcement, recommendation, human_model, or `app.py`.
- Shapes **how** APEX coaches; the Brain still owns **whether** it is safe.
