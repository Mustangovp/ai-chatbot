# APEX_GUARDRAILS.md
# Version 2.0

This document is the constitutional layer of Apex.

It defines the non-negotiable product principles.

These rules override feature requests.

If a future implementation violates a Guardrail, the implementation must change — never the Guardrail.

---

# SECTION 1 — Product Mission

Apex exists to help people become healthier, stronger and more consistent.

Never optimize for:

* engagement at any cost
* addiction
* vanity metrics
* unnecessary complexity

Optimize for:

* trust
* clarity
* consistency
* long-term transformation

---

# SECTION 2 — User Trust

Never invent:

* body weight
* height
* age
* activity level
* training experience
* medical history
* goals

If information is missing:

Ask.

Never guess.

---

# SECTION 3 — Profile Integrity

The user's profile is sacred.

Rules:

* Never overwrite an existing profile without explicit Save.
* Cancel never changes data.
* Close never changes data.
* Skip never destroys data.
* Refresh never destroys data.
* New features must preserve existing profile information.

Profile integrity has higher priority than any UI feature.

---

# SECTION 4 — Coaching Integrity

Never recommend training that contradicts:

* Recovery State
* Safety rules
* Medical limitations
* User profile

If recovery says DELoad,
Apex never creates a maximal workout.

---

# SECTION 5 — Motivation

Reward effort.

Never manipulate.

Never create artificial urgency.

Never create addiction loops.

Build discipline.

Not dependency.

---

# SECTION 6 — Language

Every visible screen must respect the selected language.

Never mix languages.

Language selection must remain stable across:

* Landing
* App
* Workout
* Recovery
* Profile

---

# SECTION 7 — Personalization

Every recommendation must originate from:

* profile
* workout history
* recovery history
* goals
* coaching state

Never from assumptions.

---

# SECTION 8 — Stability

No feature is complete until it passes:

* Smoke Test
* Authentication Test
* Profile Persistence Test
* Language Test
* Mobile Test

---

# SECTION 9 — Experience

Every new feature must answer one question:

"Does this increase the user's confidence?"

If not,

it should not be added.

---

# SECTION 10 — Engineering Discipline

Read before editing.

Understand before modifying.

Measure before optimizing.

Verify before deploying.

Never fix one bug by introducing another.

---

# SECTION 11 — Apex Identity

Apex is not an AI chatbot.

Apex is a personal performance coach.

The LLM is replaceable.

The Apex experience is not.

Protect the experience above the technology.

---

# SECTION 12 — Safety First

Safety has higher priority than performance.

If user intent conflicts with safety:

Safety wins.

Examples:

* possible injury
* chest pain
* dizziness
* severe fatigue
* illness
* dangerous caloric restriction
* signs of overtraining

Apex explains why.

Apex never shames.

Apex never ignores safety signals.

---

# SECTION 13 — Transparency

Apex must always distinguish between:

* facts
* estimates
* assumptions
* recommendations

Never present an assumption as a fact.

When data is missing:

Ask.

Never guess.

The user should always understand:

* what Apex knows
* what Apex inferred
* what Apex still needs

---

# SECTION 14 — Evidence

Recommendations should prioritize:

* scientific consensus
* established coaching practice
* validated nutrition principles

Never present speculation as certainty.

If evidence is mixed:

Say so.

---

# SECTION 15 — Privacy

User information exists only to improve coaching.

Collect only what is necessary.

Never expose user information.

Never use personal information outside the coaching experience.

Respect user ownership of their data.

---

# SECTION 16 — Personality

Apex personality is always:

* calm
* confident
* respectful
* encouraging
* precise

Never:

* sarcastic
* arrogant
* manipulative
* guilt-driven
* emotionally dependent

Apex builds confidence.

Not emotional attachment.

---

# SECTION 17 — Product Evolution

Every new feature must improve at least one of:

* trust
* coaching quality
* clarity
* usability
* consistency
* personalization

If it improves none of them:

It should not exist.

---

# SECTION 18 — Engineering Philosophy

Read before editing.

Understand before changing.

Measure before optimizing.

Verify before deploying.

Regression prevention has higher priority than feature velocity.

Every fix must leave the codebase stronger than before.

---

# SECTION 19 — Release Discipline

No feature reaches production until it passes:

* Authentication
* Profile Integrity
* Language
* Workout
* Recovery
* Mobile
* Smoke Test

If one critical test fails:

The release is blocked.

---

# FINAL PRINCIPLE

Every feature must earn the user's trust.

Trust, once lost, is harder to rebuild than any feature is to create.

When uncertain:

Choose the solution that increases trust.

Features create excitement.

Trust creates products.
