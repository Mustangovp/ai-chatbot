# APEX 1.0 — Release Notes

*A living AI biological operating system — a personal performance coach that reads your physiology and adapts every plan to you.*

## Highlights

**Living AI coach, one identity.** APEX is a calm, direct, elite performance coach — not a generic chatbot. Its personality is stable across every reply and every month: confident, honest ("never invents"), accountable without shame, and it explains *why*. Tone adapts to you by data (disciplined / inconsistent / frustrated / exhausted / in-workout), never at random.

**The living organism.** A full-viewport volumetric plasma core that breathes and drifts continuously — cinematic, calm, and now visibly alive (≈10 s breath cycle). It reacts to your recovery, fatigue and stress in real time.

**Your data is permanent.** Server-side accounts (passwordless email magic-link, email as identity) on PostgreSQL. Profile, workout history, nutrition history, coach memory, conversations, subscription and free-usage all belong to your account — not the browser. Clearing cache, cookies or localStorage never loses anything; sign in on any device and everything loads automatically.

**Personalized, never generic.** Hydration, calories, protein, recovery and training are calculated from your own signals (age, sex, height, weight, goal, activity, sleep, stress, recovery, training load, injuries). Missing a signal? It's ignored — never replaced with a generic number.

**Real coaching flow.** Premium chat with beautiful rendering — workout plans become Exercise Cards, nutrition becomes Nutrition Cards, full markdown renders natively. A full workout protocol (sets, reps, rest timer, progress, summary, history logging). Full EN / BG localization.

**Payments & compliance.** Stripe checkout, server-verified subscription state, one-continuous-path purchase, and an EU-compliant, never-hidden cancellation.

## 1.0 quality hardening (this release)
- Chat streaming now has a 75 s inactivity timeout — a stalled connection releases the UI immediately with *"Connection interrupted. Please try again."* and one-tap retry.
- Accessibility: every profile field is programmatically labelled; the chat input has an aria-label.
- Security: the tracking-opt-out redirect only accepts internal routes (no open redirect).
- Reliability (earlier in 1.0): the free-limit counter is race-safe (no 500 on a first concurrent request); subscription lookup degrades to FREE if the database is briefly unavailable.

## Known limitations
- Anonymous (signed-out) usage is per-device; only a signed-in account survives a full cookie wipe.
- Cross-browser rendering verified on Chromium; a manual Safari / iOS / Android pass is recommended before wide launch.
- The live magic-link login and Stripe test-payment smoke tests remain to be witnessed on production before an unqualified paid-launch GO.

## Requires (operations)
`DATABASE_URL` (Postgres), `RESEND_API_KEY` (magic-link email), `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET`, `APP_URL` (https, for Secure cookies), `OPENAI_API_KEY`, `APEX_SECRET`.
