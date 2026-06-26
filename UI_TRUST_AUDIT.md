# UI Trust Audit — APEX PULSE PRO
**Date:** 2026-06-23  
**Method:** Full code review of templates/app.html as a first-time user. Every visible element audited.  
**Rule:** A missing feature is better than a broken feature. Trust is more important than feature count.

---

## Classification

| Grade | Meaning |
|---|---|
| A | Keep — does not damage trust, visually solid |
| B | Improve — noticeable quality gap, fix before next release |
| C | Remove immediately — actively damages trust or has a live bug |

---

## CRITICAL: Known Bug (ship-blocking)

### C-1 — Exercise notes break the workout layout

**File:** `templates/app.html:1690`  
**Code:**
```javascript
${ex.note?`<div class="wo-ex-note">${ex.note}<\div>`:''}
```

**Problem:** `<\div>` is not `</div>`. In JavaScript template literals, `\d` is an undefined escape sequence — in non-strict mode the backslash is silently discarded, producing `<div>`. The "closing" tag is actually another **opening** div.

When an AI-generated workout table contains a "Бележка" / "Note" column (which it frequently does), all subsequent workout elements — the set counter, rep count, Done button, Pulse button — render nested inside the unclosed note div. They inherit the note's `font-size: 12px; color: var(--muted)` styles. The entire exercise screen is visually broken.

**Fix:**
```javascript
${ex.note?`<div class="wo-ex-note">${ex.note}</div>`:''}
```

**Impact:** Any workout generated with a notes column. Common case.

---

## Camera Pulse Measurement

### C-2 — rPPG camera measurement is unreliable and must be removed from the primary flow

**Location:** `_woRunHr()`, `_woCalcBpm()` — `app.html:1892–1971`  
**Currently visible as:** "❤️ Измери пулса" button on every exercise screen.

**The algorithm:**
- 4×4 pixel video capture at 5 FPS
- Green channel average
- Zero-crossing counter to estimate frequency
- Result: BPM = (crossings / elapsed_seconds) × 60

**Why it fails:** Clinical rPPG requires:
- High frame rate (30+ FPS)
- Larger pixel sample with artifact rejection
- Multiple color channels + Fourier analysis
- Motion artifact filtering

At 5 FPS with 16 pixels and zero-crossing, the algorithm cannot distinguish heartbeat signal from noise, lighting variation, or micro-movements. In dim gym lighting — the most common use environment — readings will be random or consistently wrong.

A user who does a hard set, taps "Measure pulse", waits 15 seconds, and sees "BPM: 143" when their actual HR is 85 will immediately lose confidence in the entire app. If the number is close to right by coincidence, they will trust it — and potentially train in the wrong zone based on a bad reading.

**The fallback is excellent.** The manual BPM entry (`_woShowHrFallback`) is well-designed: clear instructions, Brave browser–specific guidance, validated input (40–220 range), correct zone classification. This should be the primary UX.

**Decision:**

Remove the "❤️ Измери пулса" camera button from the exercise screen entirely.  
Replace with the manual entry as an optional, explicitly opt-in feature labeled "Измери пулса ръчно."  
If camera rPPG is reintroduced in a future version, it must be validated against a reference device before display.

**Status: C — remove the camera button from exercise screen immediately.**

---

## Exercise Stick Figures

### B-1 — SVG figure mapping is semantically wrong for 3 of 5 movement patterns

**File:** `_woSvg()`, `app.html:1183–1191`

```javascript
if(/клек|squat|мъртва|deadlift|преса|press|набир/.test(n)) return _WO_SVG.squat;
```

| Exercise (BG) | Shown figure | Correct? |
|---|---|---|
| Клек | Squat | ✅ |
| Мъртва тяга | Squat | ⚠️ Close enough (hip hinge) |
| Набиране | Squat | ❌ Pull-up has nothing in common with squat |
| Горна преса | Squat | ❌ Overhead press is standing, vertical push |
| Лицев лег (bench) | Pushup | ⚠️ Acceptable |

**Effect:** A user doing pull-ups or overhead press sees a squatting animation. They register the mismatch. It signals that the app doesn't know what these exercises look like.

**Recommended fix:** Separate `набир` from the squat regex and assign the `generic` figure. Add `набир|pull.?up|подтягивания` as a separate pattern returning a new `pullup` figure, or use `generic`. Separate `преса на рамо|overhead|OHP` similarly.

**Priority:** B — doesn't break functionality but lowers perceived quality.

### B-2 — Generic fallback figure (walking) is contextually wrong

**File:** `_WO_SVG.generic` — `app.html:1181`

The generic fallback is an animated walking stick figure with swinging arms. It appears for every exercise that doesn't match the 5 named patterns: bicep curls, rows, lateral raises, cable exercises, any machine work.

A user doing a bicep curl sees a figure walking. The animation communicates "this app doesn't know what you're doing." A static neutral pose (standing upright, arms relaxed) would communicate "visual unavailable" rather than "wrong movement."

**Recommended fix:** Replace the walking animation with a static or gently breathing standing figure. No arm swing.

**Priority:** B.

---

## Visual Hierarchy and Empty States

### A-1 — Chat empty state is handled by the greeting

When the app loads, `showGreeting()` runs immediately and fills the chat box. The empty chat state is never visible to a new user. No issue.

### A-2 — Goal bar hides correctly when no profile exists

`updateGoalBar()` calls `bar.style.display='none'` when `!p.weight`. Users with no profile don't see a broken bar with `—` values. Correctly handled.

### B-3 — Goal bar hidden columns expose placeholder values in DOM

**Location:** `app.html:478–489`

Three columns (`gb-progress-col`, `gb-score-col`, `gb-recovery-col`) are in the DOM with class `gb-hide` (display:none). Their values are `—`. If any future JS code, a CSS specificity bug, or a browser extension accidentally shows them, users see unexplained `—` placeholders for "ПРОГРЕС", "APEX SCORE", "RECOVERY."

**Recommended fix:** Remove these columns from the DOM entirely. Reintroduce them only when the feature is live and the value is populated. An empty slot is less trustworthy than a missing slot.

**Priority:** B — low probability, but the blast radius is a broken nav bar visible on every message.

---

## Paywall and Conversion

### B-4 — Trust signals are in English on a Bulgarian-first app

**Location:** `app.html:578–581`

```html
<div class="row">🔒 <span><strong>Stripe</strong> · used by Amazon, Google, Shopify</span></div>
<div class="row">🏦 <span>Card data never touches our servers</span></div>
```

The rest of the paywall is Bulgarian. At the critical conversion moment, the trust signals switch to English. For a user who has no reason to read English confidently, the switch signals that these lines are copy-pasted from somewhere — they're not written for this user.

**Recommended fix:**
```
🔒 Stripe · използван от Amazon, Google, Shopify
🏦 Данните на картата ти не достигат до нашите сървъри
```

**Priority:** B.

### A-3 — Payment logos (Visa, Mastercard, Apple Pay, Google Pay, Revolut, Stripe)

Real SVG files, properly displayed. No placeholder images. Correct trust signal. Keep.

### A-4 — Disclaimer modal

Required by law. Well-presented with a required checkbox before confirmation. Correct implementation. Keep.

### A-5 — 7-day cancellation modal

Clear language, correct legal framing ("без автоматично подновяване"). Keep.

---

## Mobile Responsiveness

### B-5 — Cancel subscription button collapses to `✕` at 480px

**Location:** `app.html:102`

```css
@media(max-width:480px){.cancel-sub-btn .cs-text{display:none;}}
```

At mobile widths, the cancel button shows only `✕` with no label. The `title` attribute says "Cancel subscription" (English only). On mobile, `title` tooltips are not shown on tap.

`✕` is visually identical to a generic close button. A user who wants to cancel their subscription may not recognize this button. A user who accidentally taps it expects something to close, not a cancellation flow.

**Recommended fix:** Use abbreviated text even on mobile:
```css
@media(max-width:480px){.cancel-sub-btn .cs-text{font-size:11px;} /* keep visible */}
```
Or: "Откажи" (8 chars) instead of hiding completely.

**Priority:** B — consumer rights requirement; the button must be recognizable.

### A-6 — Navigation layout at standard mobile widths

At 768px breakpoint: padding and font sizes reduce correctly. Nav-right has feedback icon + lang button (cancel button hidden for non-paying users). Layout holds. No issue.

### A-7 — Chat messages `max-width: 88%`

Readable on all tested viewport sizes. User messages align right, AI messages align left. Clear distinction. Keep.

### A-8 — Input bar sticky bottom

`position:sticky; bottom:0` with a gradient fade ensures the input is always accessible without covering the last message. Well implemented. Keep.

### A-9 — Profile modal `max-height: 90dvh`

Uses `dvh` (dynamic viewport height) which accounts for browser chrome on mobile (address bar show/hide). Step 3 is the longest pane; scrolls within the modal card. No content clipping. Keep.

---

## Full Element Status Table

| Element | Grade | Reason |
|---|---|---|
| Exercise note `<\div>` bug | **C** | Live layout bug — breaks workout screen when notes present |
| Camera HR measurement button | **C** | Unreliable algorithm, betrays trust on first use |
| SVG figure mapping (набир, преса) | **B** | Wrong movement shown for pull-ups and overhead press |
| Generic walking SVG fallback | **B** | Walking animation for non-walking exercises is confusing |
| Goal bar hidden columns in DOM | **B** | Could show `—` placeholders if shown accidentally |
| Paywall trust signals in English | **B** | Language switch at conversion moment erodes trust |
| Cancel button collapses on mobile | **B** | `✕` icon is ambiguous — consumer rights concern |
| Navigation | **A** | Clean, sticky, responsive, correct |
| Chat interface | **A** | Markdown rendering, message styles, typing indicator — all professional |
| Typing indicator label | **A** | "ПРЕСМЯТАМ / CALIBRATING" on-brand |
| Quick reply chips | **A** | Well-styled, appropriately sized touch targets |
| Goal bar (when profile exists) | **A** | Useful context, hides cleanly when empty |
| Profile modal (3 steps) | **A** | Clear progress indicator, correct defaults |
| Workout mode structure | **A** | Progress bar, set tracking, rest timer — solid |
| Rest timer with skip | **A** | Countdown + progress bar + coach bubble = clear UX |
| Recovery check-in scales | **A** | Energy/motivation/difficulty sliders are well-designed |
| HR fallback (manual entry) | **A** | Well-designed, Brave browser-specific, properly validated |
| HR zone classification | **A** | Standard 220-age formula, clear zone feedback |
| Feedback modal | **A** | Clear 4-option structure, character counter, email optional |
| Payment logos (SVG) | **A** | Real logos, properly displayed |
| Disclaimer modal | **A** | Required by law, required checkbox |
| Cancellation modal | **A** | Clear language, correct legal framing |
| Paywall 2-plan layout | **A** | Clear pricing, correct feature lists |
| Input bar | **A** | Focus states, sticky positioning, clean |
| Toast notifications | **A** | Visible, well-timed, dismisses automatically |
| Message animations | **A** | Subtle, `prefers-reduced-motion` respected |
| Footer legal links | **A** | All required links present |
| Workout trigger button | **A** | Appears after AI generates a table — correct |

---

## Priority Order for Fixes

1. **Fix `<\div>` → `</div>`** (`app.html:1690`) — 1-character fix, live bug.
2. **Remove camera HR button from exercise screen** — Replace with manual-only entry.
3. **Translate paywall trust signals to Bulgarian** — 2 strings.
4. **Fix cancel button mobile label** — CSS change.
5. **Remove hidden goal bar columns from DOM** — HTML cleanup.
6. **Fix SVG figure mapping** — Separate `набир` from squat regex.
7. **Replace generic walking SVG** — Static standing pose.
