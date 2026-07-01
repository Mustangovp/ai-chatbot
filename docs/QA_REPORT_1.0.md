# APEX 1.0 — QA Report (post-fix)

**Date:** 2026-07-01 · **Commit:** `2598cf4` · **Scope:** production quality audit + approved fixes (M-1, M-2, L-1). No redesign, refactor, or feature work.

Method: static inspection (`app.py`, `db.py`, `personality.py`, `templates/apex.html`), backend behaviour tests (curl + Flask test client), live DOM/geometry checks in Chromium at forced 320 px.

---

## Fixes applied and verified

| ID | Severity | Fix | Verification |
|----|----------|-----|--------------|
| **M-1** | Medium | Chat streaming now uses an `AbortController` with a **75 s inactivity watchdog** (reset on every token). A stall aborts, releases the UI, shows *"Connection interrupted. Please try again."*, and restores the message for one-tap retry. | Live: normal stream still renders Exercise cards; network error → message shown, input restored (`retry me`), `sending` released, input never disabled. |
| **M-2** | Medium | All **22** profile-wizard `<label>` elements now carry `for="pf-*"`; the chat input has a localized `aria-label`. | `grep`: 22/22 labels associated, 0 unlabeled; ids match fields. |
| **L-1** | Low | `/owner-mode?next=` passes through `_safe_next()` — internal routes only; absolute / scheme-relative / scheme / backslash targets fall back to `/`. | `_safe_next` unit cases pass; `/owner-mode?next=https://evil.com` → `/`. |

**Regression suite: PASS — zero regressions** (schema · magic-link once-only · cross-device load · account gating · free-limit 10-then-block · personality engine · RV-1 free_usage race · RV-3 subscription degrade-to-FREE). Zero console errors.

---

## Deferred findings (not in approved scope — logged for APEX 2.0)

| ID | Sev | Finding | Location | Est |
|----|-----|---------|----------|-----|
| L-2 | Low | Dead import `import secrets as _secrets` (unused) | `app.py:33` | 5 m |
| L-3 | Low | Icon-only buttons `✕` (drawer close) and `➤` (send) lack `aria-label` | `apex.html` | 15 m |
| L-4 | Low | Touch targets 36 px (menu button, top-bar pills) — meets WCAG 2.5.8 AA (24 px), below 2.5.5 AAA (44 px) | `apex.html` CSS | 30 m |
| L-5 | Low | No in-progress spinner on `goCheckout` / `sendFeedback` / `doWithdraw` (login & chat have one) | `apex.html` | ~30 m ea |
| L-6 | Low | Anonymous free-limit resets on a full **cookie** wipe (by design; accounts are wipe-proof) | server | n/a |

---

## Areas checked → No issue found
- **Chat (highest priority):** streaming completes and renders cards; **no duplicated tokens**; **no flashing**; **input never frozen**; scroll ownership correct (position held through streaming); "Jump to latest" shows/snaps/hides correctly.
- **Console:** zero errors and zero warnings on load.
- **Code hygiene:** no duplicate function definitions/handlers; no `TODO/FIXME/HACK`.
- **Mobile @ 320 px:** no horizontal scroll (`scrollW == clientW == 320`); overview, top-bar, metrics, CTA row, and the 3-step profile wizard (incl. 3-column + lifestyle cards) fit with no overflow/clipping.
- **Dark theme / brand:** consistent; brand red = `#F5212D`.
- **Backend error handling:** invalid token → `/app?auth=invalid`; forged session → `authenticated:false` + 401; DB unavailable → subscription FREE (RV-3); chat network fail → graceful message.

## Could not fully verify (stated honestly; not counted pass/fail)
- **Cross-browser** (Safari / Firefox / real iOS / Android): only Chromium testable here; UI uses `backdrop-filter` widely. Recommend a manual device pass before paid launch.
- **Live visual screenshots:** the preview rasterizer wedges on the animated canvas; layout verified via DOM geometry instead.
- **FPS / memory profiling:** no profiler available; code review shows throttled (~45 fps) render with fixed buffers and no growing per-frame allocations — not profiled.
- **Authenticated + Stripe live E2E:** still gated on a magic-link token + test-mode payment.

## Recommendation
Not a blocker for a **free / soft launch**. For **paid** launch, the shipped M-1/M-2/L-1 fixes plus a manual cross-browser device pass are advised. Remaining items are polish (APEX 2.0 backlog).
