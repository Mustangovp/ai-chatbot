# APEX EXPERIENCE BACKLOG

---

## Purpose

This document captures every future experience idea without permitting immediate implementation.

No entry in this backlog may enter production without:

1. A formal design session (storyboard + copy + visual hierarchy)
2. Implementation plan approved before any code is written
3. Regression test matrix defined before any code is committed

The backlog protects production from feature creep.
It is not a to-do list. It is a holding space for good ideas that are not ready yet.

---

## Rules for New Entries

Every proposal must include all five fields:

- **Problem** — what friction or gap the user currently experiences
- **Expected benefit** — what the user feels after the change
- **Implementation cost** — engineering effort estimate (hours/days)
- **Engineering risk** — what could break
- **Validation method** — how success will be confirmed

Proposals missing any field are not accepted into the backlog.

---

## PENDING STEPS (locked implementation order)

These are not backlog items. They are frozen implementation steps from SCENE_1_FINAL that have not yet been built.

| Step | Description | Depends on |
|---|---|---|
| Step 4 | M3 — Replace profile modal with full-screen single-question flow | Steps 1–3 ✅ |
| Step 5 | M3 — Answer transitions, received moment, coaching context lines per question | Step 4 |
| Step 7 | M2 — Skip behavior for returning users (bypass greeting for users with complete profile) | Step 6 ✅ |
| Step 8 | M1 — Landing dissolve transition (page-to-app cross-dissolve, no hard navigation) | Step 7 |

These steps are not backlog items. They are production work. They execute in order.

---

## BACKLOG

---

### EXP-001 — Number Reveal Animation in Transformation Moment

**Problem:** The TDEE, protein, and target numbers appear instantly — they arrive as complete values. The user does not feel the numbers being computed.

**Expected benefit:** If numbers count up from 0 over 300ms (e.g., 0 → 2,465), the user watches their specific number emerge rather than reading a static result. Increases the sense that the coach is doing real work for them specifically.

**Implementation cost:** Medium (2–3 hours). Requires a `countUp(el, target, duration)` helper that increments a number using `requestAnimationFrame` and a linear/ease-out curve. Must handle comma-formatting locale correctly for BG/EN.

**Engineering risk:** Low. Self-contained visual enhancement. Does not touch the calculation logic or the timing chain. Risk: if the count-up duration is miscalibrated, it extends the total sequence past the 2.5s ceiling. Must be capped at 280ms per number maximum.

**Validation method:** Fire `_pfShowTransformation()` in browser, observe each number counting up from 0. Confirm total sequence ends within 2.3s with count-up included. Test BG locale (space-separated thousands: "2 465") vs EN (comma-separated: "2,465").

---

### EXP-002 — Returning User Greeting (Post-Profile, Pre-Day-0)

**Problem:** Currently `showGreeting()` displays the two-line coaching intro and single chip for every user, including users who already have a complete profile and have been through Day 0. The first-visit experience and the returning-visit experience are identical.

**Expected benefit:** A returning user who opens the app should not see "Your first session starts here." That is someone else's moment. The returning user should feel recognized. A short two-line returning greeting ("Welcome back, Alex. / Where are we today?") is more honest than repeating first-visit language.

**Implementation cost:** Low (1–2 hours). `showGreeting()` detects `_pfLoad()` — if a complete profile exists and `apexHistory` has entries, render alternate greeting copy. No structural changes required.

**Engineering risk:** Low. The chip array may need to differ for returning users (no "Build my plan" — perhaps "Continue where we left off" or a workout chip). Edge case: user has profile but no history — treat as new user.

**Validation method:** Load app with complete profile + 2+ history entries. Confirm alternate copy renders. Load app with no profile — confirm original greeting renders. BG + EN.

---

### EXP-003 — Directive Coaching Rationale Variation (Anti-Repetition)

**Problem:** The Step 3 directive rationale sentence is static. Every `muscle_gain` user, regardless of whether it is their first week or their fourth, reads "Week 1 tests your baseline lifts. We build from real numbers." After the first time, this sentence loses its coaching weight.

**Expected benefit:** On second and subsequent profile submissions (or when the profile is updated), the directive produces a different rationale sentence — one that references change rather than baseline. "Your targets have been recalculated. The new baseline replaces the old one."

**Implementation cost:** Medium (2–3 hours). Requires checking whether `apexWorkoutLog` has entries (returning user) or not (first time). If returning, swap the rationale pool to "update" variants rather than "baseline" variants.

**Engineering risk:** Low-medium. The detection logic is simple but the copy matrix doubles (first-time + returning, per goal, BG+EN). Risk of copy drift between the two sets.

**Validation method:** Submit profile with existing workout log entries. Confirm "update" variant rationale renders. Submit profile with empty workout log. Confirm "baseline" variant renders. BG + EN.

---

### EXP-004 — Transformation Moment: Goal-Specific Opening Sentence

**Problem:** "Here is what your profile requires." is universal — the same sentence for a sedentary fat-loss beginner and a very-active strength advanced athlete. The bridge sentence is accurate but not personalized.

**Expected benefit:** The bridge sentence acknowledges the user's specific goal before the numbers appear. Fat loss: "Here is what consistent fat loss requires from your body." Muscle gain: "Here is what your muscle gain target demands." This makes the sentence feel like the coach has already read the profile before the numbers land.

**Implementation cost:** Low (1 hour). Replace the single string with a `OPENER` object keyed by `p.goal`, same pattern as the rest of `_pfShowTransformation()`.

**Engineering risk:** Minimal. Isolated string substitution. No timing or structural changes.

**Validation method:** Fire transformation for each of the 5 goals in BG and EN. Confirm correct opener renders per goal. Confirm "Here is what your profile requires." is fully replaced — no fallback leaking.

---

### EXP-005 — Day 0 Card: Micro-Pause Before Directive Section

**Problem:** The directive section (`d0-directive`) currently renders simultaneously with the Day 0 card via the `day0-fadein` animation. Both the verdict paragraph and the "Your Week 1 plan is ready" line arrive together. The user has not finished reading the verdict before the next coaching action appears.

**Expected benefit:** If the directive section fades in 600ms after the Day 0 card arrives (a separate animation, not part of the card), the user reads the assessment first. The directive then arrives as a second beat — the coach waited for the user to absorb, then spoke again. This pacing communicates patience, not urgency.

**Implementation cost:** Low-medium (2 hours). Split the `day0-fadein` class so only `.day0-card` fades in immediately. The `.d0-directive` wrapper starts at `opacity: 0` and gets a separate class (e.g., `d0-directive-in`) added via `setTimeout` 600ms after the card appears.

**Engineering risk:** Low. CSS-only timing change. Risk: the 600ms gap may feel too long on mobile (shorter attention, higher intent). Should be tested on actual mobile device, not just resized viewport.

**Validation method:** Load Day 0 card. Confirm `.day0-card` fades in immediately. Confirm `.d0-directive` is invisible for exactly 600ms, then fades in. BG + EN. Mobile device test (not viewport resize).

---

### EXP-006 — CTA Button: Haptic Feedback on Mobile

**Problem:** The `BEGIN YOUR FIRST SESSION →` CTA is the most important tap in the first 60 seconds. On mobile, it receives no haptic feedback — the same physical response as tapping anything else.

**Expected benefit:** A single short vibration pulse (20–30ms) on tap signals to the user that something real started. The coach's plan has been activated. The tap has consequence.

**Implementation cost:** Very low (30 minutes). `navigator.vibrate(25)` in the CTA's `onclick` handler. Guard with `if (navigator.vibrate)` for browser compatibility.

**Engineering risk:** Minimal. Vibration API is opt-in, widely supported on Android, absent on iOS (iOS silently ignores it — no error). No effect on desktop.

**Validation method:** Tap CTA on Android device (physical, not emulated). Confirm single short pulse. Confirm no vibration on desktop. Confirm iOS does not error.

---

*Last updated: 2026-06-26*
*All entries require formal design session before implementation.*
*No entry may be implemented directly from this file.*
