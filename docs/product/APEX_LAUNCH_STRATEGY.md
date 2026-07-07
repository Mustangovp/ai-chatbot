# APEX — PUBLIC BETA LAUNCH STRATEGY

**Owner:** Founding exec team (CPO / CGO / Launch Strategist).
**Objective:** first **1,000 users → first 100 paying** in 30 days, on the frozen Brain.
**Doc type:** business strategy. No Brain features, no architecture change, `BRAIN_ENFORCE` stays OFF until § Phase 5 canary readiness.

---

## The one thing that makes this winnable — positioning

APEX is not "another AI fitness chatbot." Every competitor optimizes for **engagement**
(more messages = more dopamine = more retention). APEX is the only one whose core
intelligence — **the Brain** — will **refuse to give you a workout when training is the
wrong answer**, route you to care on a red flag, and adapt to your real constraints.

> **Category:** the safe, honest AI coach.
> **One-liner:** *"The AI coach with a conscience — it knows your limits, and when not to push."*
> **Contrarian wedge:** transformation over engagement. We make users **disciplined, not
> dependent** — and we say so out loud. That is the story press, Product Hunt, and Reddit reward.

**Beachhead:** Bulgaria first (home market, native BG, low CAC, near-zero AI-coach
competition), then English/global. The product is already bilingual — this is a
distribution advantage, not a build task.

**Three proof pillars for every channel:** (1) *Safety* — it won't hurt you.
(2) *Personalization* — it remembers you and adapts. (3) *Honesty* — no dark patterns,
24-hour refund, safety never paywalled.

---

# PHASE 1 — PRODUCT

### First-time user experience (FTUE)
- **No signup wall.** Anonymous visitors can talk to the coach immediately (free daily
  limit already enforced server-side). The landing CTA is *"Talk to your coach now,"* not
  *"Sign up."*
- **Aha in <60s:** first message → the coach acknowledges the goal by name and returns one
  real, personalized action. The "first 30 seconds" experience is the entire conversion.
- **Safety as a visible feature, not a disclaimer:** when the Brain (post-enforce) adapts or
  routes, that moment is the product's magic — surface it as care, never as a refusal.

### Onboarding — conversational, progressive, never a form wall
- Capture the profile **through the conversation**, not a 12-field form: goal → level →
  one health input, asked naturally by the coach.
- Magic-link account is requested **only when there's something to save** ("Want me to
  remember this across your devices?") — passwordless, one tap.
- A lightweight **profile-completeness meter** framed as coaching value: *"The more I know,
  the safer and sharper your plan."* (The Brain literally rewards completeness with a wider,
  more confident envelope — honest incentive.)

### Activation flow
- **Activation = first personalized plan received + a return session within 48h.**
- Nudges: end every first session with a concrete next step + an opt-in reminder email.
- Instrument the funnel: visit → first message → first plan → account created → return.

### Profile completion
- Target: **≥60%** of activated users add a goal + level + ≥1 health note in week 1.
- Mechanism: the coach asks one profile question per early session (never all at once);
  completeness unlocks visibly "smarter" plans.

### Subscription flow
- Freemium: FREE daily message limit → on limit, a **contextual upgrade card** (not a
  hard wall): *"You've used today's free coaching. Go unlimited?"*
- Stripe Checkout (already wired), server-authoritative plan, magic-link account required
  to pay. Post-purchase: instant unlock, receipt email, welcome-to-Premium sequence.

### Pricing strategy (decisions, in EUR)
| Tier | Price | What you get | Model |
|---|---|---|---|
| **FREE** | €0 | ~10 coached messages/day, safety Brain **always on**, single-device | gpt-4o-mini |
| **CORE** | **€9.99/mo · €99/yr** | Unlimited coaching, cross-device persistent memory | gpt-4o-mini |
| **PRO** | **€19.99/mo · €199/yr** | Smartest model, longest memory, priority, advanced multi-week plans | gpt-4o |

- **Annual = ~2 months free** (anchor to it everywhere; it wins on LTV, cashflow, churn).
- **Safety is never paywalled** — red-flag routing and constraint-aware plans exist on FREE.
  This is both ethically required and the strongest trust/marketing asset.
- **BG localization:** display BGN alongside EUR; consider a purchasing-power-adjusted BG
  annual promo for the beachhead. Keep one global price ladder to avoid arbitrage.

### Free vs Premium experience
- **FREE** = a real taste, not crippled: genuine coaching, safety, ~10 msgs/day.
- **CORE** = *"your coach never forgets you"* — unlimited + persistent cross-device memory.
- **PRO** = *"the smartest version of your coach"* — gpt-4o, deepest memory, complex plans.
- The upgrade story is **more coach, not less harm** — you never pay for safety.

### User retention strategy
- **The memory moat:** the coach remembers your history, constraints, and progress —
  leaving means losing your coach. This is the healthiest possible lock-in.
- **Anti-dark-pattern retention** (on-brand): celebrate **discipline and consistency**, not
  streak-anxiety. Weekly reflection ("here's the week you built"), proactive check-ins,
  gentle re-engagement — never manipulative FOMO.
- **Lifecycle email:** value reminders, progress recaps, win-back for lapsed users.

---

# PHASE 2 — GROWTH

### Landing page (`templates/landing_en.html` + BG)
- Hero: the one-liner + *"Talk to your coach now"* (anonymous CTA, no email gate).
- Sections: the 60-second demo, the three proof pillars, the Brain safety story
  ("it knows when *not* to give you a workout"), pricing, testimonials, honest FAQ
  (refund, safety, data). Conversion target: **≥8%** visit→first-message.

### Waitlist (pre-PH scarcity)
- A **beta invite** waitlist to manufacture scarcity + collect emails before Product Hunt.
- Referral positions (skip-the-line for shares) = built-in viral loop. Target 500 waitlist
  before launch day.

### Email sequence (bilingual, lifecycle)
1. **Welcome** (instant) — one tip + "reply with your goal."
2. **First value** (Day 1) — a coaching win + invite back.
3. **Education** (Day 3) — the safety story (why a coach that says "not today" is better).
4. **Social proof** (Day 5) — a transformation testimonial.
5. **Upgrade nudge** (Day 7) — contextual, value-led (annual anchor).
6. **Win-back** (Day 14 inactive) — "your coach kept your progress."

### Product Hunt launch
- **Angle that wins PH:** *"An AI coach that refuses to hurt you."* Makers-story = the Brain
  + transformation philosophy. Assets ready (OG images, screenshots already produced).
- Playbook: line up a strong hunter, 20+ genuine supporters primed, launch 00:01 PT, maker
  first-comment tells the safety story, respond to every comment all day. **Goal: Top 5.**

### Reddit strategy (value-first, rules-respecting)
- Subs: r/fitness, r/bodyweightfitness, r/loseit, r/artificial, + Bulgarian communities.
- Lead with **usefulness, never a link drop**: answer "can I train with high blood
  pressure?" style questions with genuine value; the safety angle is native to these subs.
- A founder AMA ("I built an AI coach that refuses unsafe workouts — AMA") once there's proof.

### TikTok strategy
- Hooks: *"I asked an AI coach for a workout and it said no — here's why that's good,"*
  myth-busting, "coach reacts to dangerous fitness advice," 30-day transformation diaries.
- BG + EN creators; 1 post/day cadence in launch month; repurpose to Reels/Shorts.

### Instagram strategy
- Reels (same hooks as TikTok), educational carousels (the safety pillar), coach-voice
  quote cards, stories with the beta countdown. Assets/highlight covers already produced.

### LinkedIn strategy
- Founder-led build-in-public + the **engineering-ethics** story (a safety cascade that can
  refuse generation). Seeds credibility, press, and a future **corporate-wellness** B2B lane.

### YouTube strategy
- Long-form: *"I let an AI coach train me for 30 days,"* a Brain explainer ("how it decides
  not to hurt you"), and founder build-in-public. SEO-durable, funds Shorts.

### SEO roadmap (90 days)
- **Unique content moat = the safety corpus.** Programmatic + editorial pages for
  *"is it safe to exercise with [condition]?"* — a question set almost no competitor answers
  responsibly, and one APEX is uniquely credible on.
- BG-language fitness terms = low competition, high home-market intent.
- 0–30d: 10 cornerstone safety articles + on-page basics. 30–60d: programmatic condition
  pages + internal linking. 60–90d: backlinks from the PH/press moment, refresh, expand.

---

# PHASE 3 — REVENUE

- **Model:** freemium → subscription. FREE is the top of funnel and the always-on trial.
- **Annual vs monthly:** default the pricing UI to **annual** (2 months free). Monthly for
  the hesitant. Annual is the churn and cashflow winner — push it in the upgrade card and email.
- **Trial:** the free tier *is* the no-card trial; **additionally** grant new accounts a
  **7-day PRO taste** so they feel the smartest model before choosing a tier.
- **Upgrade triggers:** (1) hitting the daily free limit, (2) wanting cross-device memory,
  (3) wanting the smarter model / a complex multi-week plan, (4) a genuine moment-of-need
  where the Brain gives a safe modification and the full plan is one tap away.
- **Churn reduction:** the **memory moat** (leaving loses your coach), **pause instead of
  cancel**, annual lock-in, proactive value recaps, and the existing **24-hour refund** as a
  trust signal (low-friction refund *reduces* pre-purchase hesitation and chargebacks).

**Target unit economics for beta:** free→paid **≥5%**, blended ARPU **~€12/mo**, gross
churn **<8%/mo**, LTV:CAC **>3:1** by day 30 on organic-led channels.

---

# PHASE 4 — ANALYTICS

### North Star Metric
**Weekly Activated Coached Users (WACU):** users who received ≥1 personalized plan **and**
returned for a follow-up session that week. It captures *real value delivered*, not vanity
engagement — fully aligned with transformation-over-engagement.

### The metric tree
| Layer | Metric | Beta target |
|---|---|---|
| **Acquisition** | visits, visit→first-message, waitlist signups, CAC by channel | ≥8% visit→message |
| **Activation** | % new users → first plan + return in 48h | **≥40%** |
| **Retention** | W1 / W4 return rate; WACU cohort curve | W4 **≥25%** |
| **Revenue** | MRR, ARPU, free→paid %, annual mix, LTV, LTV:CAC | free→paid **≥5%** |
| **Churn** | gross monthly churn, refund rate | **<8%** / refunds <5% |
| **Product health (Brain)** | shadow decision mix, halt rate, zero EMERGENCY misses | per rollout handbook |

### Dashboard specification
1. **Acquisition funnel** — source → visit → first message → account → paid.
2. **Activation** — first-plan rate, 48h return, profile completion.
3. **Retention cohorts** — weekly WACU curves by signup cohort.
4. **Revenue** — MRR, ARPU, tier + annual mix, conversion, churn/refunds.
5. **Brain shadow telemetry** — reuse `docs/APEX_BRAIN_PRODUCTION_ROLLOUT.md` § 3 queries
   (verdict/halt distribution, zero-EMERGENCY-miss) as a product-health panel.

---

# PHASE 5 — 30-DAY BETA EXECUTION PLAN

**Structure:** Week 1 Foundation (private alpha) → Week 2 Closed beta → Week 3 Open-beta ramp
→ Week 4 Public launch (Product Hunt). Every day lists **Eng / Product / Marketing / Launch /
Success criteria**. **Engineering = launch infrastructure only — no Brain features** (analytics,
Stripe/pricing, landing, onboarding, email, and the shadow-soak from the rollout handbook).

### WEEK 1 — Foundation & private alpha (Days 1–7)

**Day 1 — Instrumentation stand-up**
- Eng: add product analytics (events: visit, first_message, first_plan, account_created,
  upgrade_viewed, subscribed) — no Brain change.
- Product: finalize the activation event definitions.
- Marketing: lock positioning + one-liner; reserve handles.
- Launch: assemble the alpha list (~20 friendlies).
- ✅ Success: events firing to the dashboard end-to-end.

**Day 2 — Pricing & billing finalize**
- Eng: wire the €9.99/€19.99 monthly + €99/€199 annual price IDs in Stripe; 7-day PRO trial.
- Product: build the contextual upgrade card at the free-limit boundary.
- Marketing: draft pricing page copy (annual-default).
- Launch: alpha invites drafted.
- ✅ Success: a test purchase (monthly + annual) unlocks the tier; refund path verified.

**Day 3 — Landing conversion pass**
- Eng: landing hero CTA "Talk to your coach now" (anonymous), analytics on CTA.
- Product: 60-second demo section + three proof pillars.
- Marketing: safety-story block + FAQ (refund/safety/data).
- Launch: alpha goes live to 20 users.
- ✅ Success: visit→first-message ≥8% on alpha traffic.

**Day 4 — Onboarding flow**
- Eng: conversational profile capture + completeness meter + magic-link "save" prompt.
- Product: define activation nudge + reminder email trigger.
- Marketing: 5 cornerstone SEO safety articles outlined.
- Launch: collect alpha feedback (calls).
- ✅ Success: ≥60% of alpha users complete goal+level+1 health note.

**Day 5 — Enable the shadow-soak (rollout handbook § 1)**
- Eng: set `BRAIN_SHADOW=1` in prod (ENFORCE/DEBUG off); run the smoke queries.
- Product: confirm UX byte-identical (golden OFF-path holds).
- Marketing: build the beta waitlist page + referral positions.
- Launch: waitlist opens; seed to personal networks.
- ✅ Success: `brain_decisions` filling; 0 shadow errors; UX unchanged.

**Day 6 — Email automation**
- Eng: wire the 6-step lifecycle sequence (bilingual) to signup/inactivity triggers.
- Product: welcome + first-value emails finalized.
- Marketing: 100 waitlist signups; first TikTok/Reel filmed.
- Launch: alpha bug-fix pass.
- ✅ Success: welcome email delivers on account creation; 100 waitlist.

**Day 7 — Alpha review & instrument the metric tree**
- Eng: retention/cohort + revenue panels live on the dashboard.
- Product: pick fixes from alpha; freeze the beta scope.
- Marketing: schedule week-2 content calendar.
- Launch: go/no-go for closed beta.
- ✅ Success: full metric tree visible; alpha activation ≥30% (baseline).

### WEEK 2 — Closed beta (Days 8–14)

**Day 8** — Eng: fix top-3 activation drop-offs. Product: refine upgrade card copy from data.
Marketing: invite first 100 waitlisters. Launch: closed beta live. ✅ 100 activated sessions.
**Day 9** — Eng: annual-default pricing UI + trial countdown. Product: profile-completion nudge
tuning. Marketing: 2 Reddit value posts (no links). ✅ First 5 paid conversions.
**Day 10** — Eng: dashboard alerting on activation dip. Product: first win-back email live.
Marketing: LinkedIn build-in-public post #1. Launch: monitor shadow telemetry (verdict mix sane).
✅ W1 retention ≥30% on Day-8 cohort.
**Day 11** — Eng: perf pass on `/chat` under load. Product: pricing A/B (monthly-first vs
annual-first). Marketing: 3 TikToks live. ✅ p95 latency stable with shadow on.
**Day 12** — Eng: referral tracking. Product: testimonial capture in-app. Marketing: collect
5 testimonials. Launch: invite next 100. ✅ 200 total users.
**Day 13** — Eng: SEO on-page (meta, sitemap, condition-page template). Product: FAQ from real
questions. Marketing: publish 2 cornerstone articles. ✅ Google indexing started.
**Day 14** — Review: cohort retention, conversion, shadow distribution vs corpus. Decide PH date.
✅ free→paid ≥4%; zero EMERGENCY misses on probe set.

### WEEK 3 — Open-beta ramp (Days 15–21)

**Day 15** — Eng: open self-serve signup (remove invite gate). Marketing: announce open beta to
waitlist. Launch: referral loop live. ✅ Signups > invites (organic > seeded).
**Day 16** — Eng: harden email deliverability (SPF/DKIM). Marketing: Instagram carousel series.
✅ Email open ≥35%.
**Day 17** — Eng: PH assets integration (embed, badge). Marketing: line up PH hunter + 20
supporters. ✅ PH page drafted.
**Day 18** — Eng: annual-plan LTV report. Product: pause-instead-of-cancel flow. Marketing:
YouTube "30 days with an AI coach" filming. ✅ Churn path shows pause option.
**Day 19** — Marketing: Reddit AMA ("I built a coach that refuses unsafe workouts"). Product:
upgrade-trigger tuning from data. ✅ AMA > 50 genuine comments.
**Day 20** — Eng: load-test for launch spike. Marketing: press/creator outreach (safety angle).
✅ System holds 5× current load.
**Day 21** — Full pre-launch rehearsal + go/no-go. ✅ 500+ users, ≥25 paying, metric tree healthy.

### WEEK 4 — Public launch (Days 22–30)

**Day 22** — Eng: freeze non-critical deploys; monitoring on high alert. Marketing: tease launch.
Launch: final PH assets + first-comment written. ✅ Launch-day runbook signed off.
**Day 23** — Buffer/fix day. ✅ Zero open P1 bugs.
**Day 24 — PRODUCT HUNT LAUNCH DAY** — All hands: 00:01 PT go-live, maker safety-story
first-comment, respond to every comment, coordinated TikTok/IG/LinkedIn/Reddit push, email
blast to waitlist. ✅ **Top 5 of the day; traffic spike converts ≥8%.**
**Day 25** — Eng: hotfix from launch traffic. Marketing: capitalize on PH momentum (press replies,
"we launched" posts). ✅ Signup spike retained (48h return tracking).
**Day 26** — Product: convert launch traffic (limited annual launch offer). Marketing: creator
collabs go live. ✅ Paid conversions accelerate.
**Day 27** — Eng: analyze funnel drop-offs from the spike; ship UX fixes (non-Brain). ✅
Activation ≥40% on launch cohort.
**Day 28** — Marketing: publish transformation testimonials + YouTube video. ✅ Social proof live.
**Day 29** — Review: shadow-soak week complete — check verdict/halt distribution vs corpus,
zero EMERGENCY misses, latency/error flat. Assess **BRAIN_ENFORCE canary readiness** per the
rollout handbook (do **not** flip — decision only). ✅ Shadow acceptance § 2.6 evaluated.
**Day 30 — Milestone review.** Metrics vs targets; retro; next-30 plan.
✅ **1,000 users, ≥100 paying, WACU trending up, LTV:CAC > 3:1** — and a documented
go/no-go on the enforcement canary.

### 30-day success criteria (the scoreboard)
- **1,000 total users**, **≥100 paying** (≥5% conversion).
- **Activation ≥40%**, **W4 retention ≥25%**, **WACU** rising week over week.
- **MRR ≥ €1,200**, gross churn **<8%**, refunds **<5%**, LTV:CAC **>3:1**.
- **Product Hunt Top 5**; ≥500 organic (non-seeded) signups.
- **Shadow-soak clean** — decision distribution sane, **zero EMERGENCY misses**, UX unchanged —
  giving a real, data-backed decision on the `BRAIN_ENFORCE` canary.

---

## Guardrails honored
- No Brain features added; architecture frozen; `BRAIN_ENFORCE` stays OFF (the only Brain
  action in this plan is enabling the **shadow** soak — logging only — per the rollout handbook).
- The shadow-soak is deliberately scheduled inside the beta so that, by Day 30, the enforcement
  go-live is a **data-backed operational decision**, not an engineering task.
```
