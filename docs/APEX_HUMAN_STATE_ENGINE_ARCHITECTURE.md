# APEX — Human State Engine (HSE) Architecture · P0.5

**Status:** ARCHITECTURE ONLY. No implementation, no code, no deployment, no Brain
change. Supersedes the Human Model design by adding **dynamic, time-decaying state**
alongside slow **facts**.

---

## 0. The one hard problem, resolved up front

Some dynamic variables (**recovery, fatigue, stress**, and the athlete model's
estimate-confidence) are **already owned and read by the Brain** via `athlete_model`
(M0 substrate). The HSE must NOT take these over, or the Brain would gain a new
dependency. Resolution, enforced throughout this document:

- **The Brain keeps reading `athlete_model` exactly as today** — it never reads the HSE.
- **The HSE is the unified read surface** for the Recommendation Architect. For the
  somatic subset it holds a **read-only projection** of `athlete_model`; it *owns* all
  other facts and dynamic state.
- **Sensors feed the HSE.** A sensor that should also move the Brain's readiness
  (e.g. Whoop recovery) contributes to `athlete_model` **only through the existing
  `athlete_store.observe()` substrate contract** (M0) — not a new Brain dependency; the
  Brain's read path is unchanged. This is an *evolution* item (§6), not a P0.5 change.

> **Naming caution:** `athlete_model.confidence` is the *confidence of the readiness
> estimate* (meta). The Dynamic-State "confidence" below is *user self-efficacy* — a
> different variable, HSE-owned. They are never merged.

---

## 1. Domain model

### 1.1 Two tiers
- **Facts** — slow, high-confidence, long/no TTL: `identity, preferences, equipment,
  medical_profile, schedule, budget, goals`.
- **Dynamic State** — fast, decaying, fused from sensors/observations: `energy,
  recovery, pain, motivation, stress, sleep_debt, confidence, consistency, adherence,
  momentum, fatigue`.

### 1.2 The `StateVariable` (every dynamic value is this shape)
```
StateVariable {
  key            # e.g. "recovery"
  value          # normalized 0..1 (or typed)
  owner          # HSE | brain.athlete_model (projected) | derived
  source         # sensor id | checkin | coach_obs | derivation
  confidence     # 0..1 — trust in THIS value right now (source × freshness)
  observed_at    # timestamp of the underlying reading
  ttl_seconds    # freshness horizon before it goes STALE
  update_rule    # latest_wins | ewma | decay | accumulate | fuse | computed
  visibility     # who may read (see §5)
  lifecycle      # UNKNOWN | ESTIMATED | OBSERVED | STALE | EXPIRED (§2)
}
```
A **Fact** is the degenerate case: `ttl=∞`, `update_rule=latest_wins`, `confidence≈1`.

### 1.3 Sensor port (pluggable, future)
A `Sensor` is an adapter that normalizes raw device data into `Reading{key, value,
confidence, observed_at, source}` and pushes it through the single ingest contract.
One port, many adapters:
```
Apple Health · Google Fit · Garmin · Whoop · Oura · Manual check-in · Coach observation
        └──────────────────── normalize ────────────────────┘
                              ↓  ingest(reading)
                         HSE fusion + store
```
Adding a sensor = adding an adapter. No core change. Multiple sensors for one key are
**fused** (confidence × recency weighted).

---

## 2. State machine (per dynamic variable)

```
                 ingest(direct, high-conf)
   UNKNOWN ───────────────────────────────► OBSERVED
      ▲  │ ingest(inferred/low-conf)            │  ▲
      │  └────────────► ESTIMATED ──────────────┘  │ new reading (fuse / refresh)
      │                    │  higher-conf reading   │
      │                    └────────────────────────┘
      │                                             │ age > ttl
      │            conf < floor  ┌──────── STALE ◄──┘
      └──── EXPIRED ◄────────────┘   │
            (revert to default)      └── age ≫ ttl / conf < floor ──► EXPIRED
```

- **UNKNOWN** — no usable value; consumers use the safe default/prior.
- **ESTIMATED** — inferred/derived, low confidence.
- **OBSERVED** — a direct reading within TTL; highest confidence.
- **STALE** — past TTL; confidence decaying, still usable but flagged.
- **EXPIRED** — decayed below the confidence floor; reverts to UNKNOWN/default.

**Decay:** `confidence(t) = confidence₀ · f(age / ttl)` (monotonic ↓).
**Fusion:** on a new reading, `value = Σ(cᵢ·wᵢ·valueᵢ)/Σ(cᵢ·wᵢ)` over live sources
(`w` = recency). **Read gating:** below the confidence floor a variable reads as
UNKNOWN → the consumer falls back to the conservative default (mirrors the Brain's
"unknown → conservative" stance).

---

## 3. Lifecycle diagram (ingest → fuse → decay → expire)

```
  sensor / check-in / coach obs
             │ Reading{key,value,conf,ts,source}
             ▼
      ┌─────────────┐   validate + normalize
      │  ingest()   │───────────────┐
      └─────────────┘               ▼
                            ┌────────────────┐  fuse with live sources
                            │  FUSION        │  (conf × recency)
                            └───────┬────────┘
                                    ▼
                            ┌────────────────┐  store {value,conf,ttl,ts,source,lifecycle}
                            │  STATE STORE   │
                            └───────┬────────┘
                clock ticks         │  decay confidence; TTL check
                                    ▼
                        OBSERVED → STALE → EXPIRED → (default)
                                    │
                                    ▼  view() = freshness-adjusted snapshot
                        Recommendation Architect (read-only consumer)
```

Writes happen only at `ingest()`; time advances lifecycle automatically; reads are a
freshness-adjusted snapshot.

---

## 4. Ownership matrix

Confidence = typical at fresh reading. TTL = freshness horizon. **Brain-owned rows are a
read-only projection inside the HSE; the Brain reads them from `athlete_model` only.**

### Facts
| Variable | Owner | Source | Conf | TTL | Update rule | Visibility |
|---|---|---|---|---|---|---|
| identity | HSE | onboarding/profile | 1.0 | ∞ | latest_wins | Architect, user |
| preferences | HSE | conversation (explicit) | 0.9 | ∞ | merge/conflict-resolve | Architect, user |
| equipment | HSE | profile/conversation | 0.9 | ∞ | latest_wins | Architect |
| medical_profile | **Brain (S1 constraints)** | Brain, clinical sign-off | per sign-off | persistent (Addendum 02) | **Brain only** | Architect (read-only) |
| schedule | HSE | conversation/calendar* | 0.8 | ~weeks | latest_wins | Architect |
| budget | HSE | conversation | 0.8 | ∞ | latest_wins | Architect |
| goals | HSE (mirror of profile) | onboarding/conversation | 0.9 | ∞ | latest_wins | Architect; Brain via profile |

### Dynamic State
| Variable | Owner | Source | Conf | TTL | Update rule | Visibility |
|---|---|---|---|---|---|---|
| energy | HSE (derived) | recovery+sleep+fatigue | 0.6 | ~12h | ewma+decay | Architect, user |
| **recovery** | **Brain athlete_model** (projected) | Whoop/Oura/athlete_store | 0.5–0.9 | 24h | fuse → observe() | Architect (RO), Brain |
| pain | HSE | check-in/coach_obs | 0.7 | hours–days | latest+decay | Architect |
| motivation | HSE | check-in/behavioral | 0.6 | ~days | ewma | Architect, user |
| **stress** | **Brain athlete_model** (projected) | check-in/HRV | 0.5–0.9 | 24h | fuse → observe() | Architect (RO), Brain |
| sleep_debt | HSE | sleep sensor/check-in | 0.6–0.9 | rolling 7–14d | accumulate+decay | Architect, user |
| confidence (self-efficacy) | HSE | behavioral/check-in | 0.6 | ~days | ewma | Architect, user |
| consistency | HSE (computed) | workout_history | 0.9 | rolling window | computed | Architect, user |
| adherence | HSE (computed) | recommendation vs completion | 0.9 | rolling window | computed | Architect, user |
| momentum | HSE (derived) | trend(consistency, adherence) | 0.6 | rolling window | computed trend | Architect, user |
| **fatigue** | **Brain athlete_model** (projected) | training load/sensors | 0.5–0.9 | 24–48h | fuse → observe() | Architect (RO), Brain |

*\*calendar = future sensor.*

---

## 5. Read / write rules

1. **Single writer:** state changes only through `ingest(reading)` (sensors, check-ins,
   coach observations) and the derivation jobs for computed variables. Nothing else writes.
2. **Immutable reads:** `view(subject)` returns a freshness-adjusted **snapshot**;
   consumers cannot mutate it.
3. **Brain isolation (hard):** the Brain reads **only** `athlete_model`; it never imports
   or reads the HSE. Brain-owned variables are *projected into* the HSE read-only — the
   HSE never writes them back except via the existing `athlete_store.observe()` contract
   (§6, future).
4. **Confidence gating:** a variable below its confidence floor (STALE→EXPIRED) reads as
   UNKNOWN; consumers must use the conservative default. No consumer may treat a low-conf
   value as certain.
5. **Architect is read-only:** `architect.design(view: HumanStateView, decision:
   BrainDecision) -> Blueprint`. It reads state + the Brain Decision; it owns no state and
   records diversity/outcomes via `ingest()` at the orchestration layer, not inside itself.
6. **Visibility tiers:** `internal` (raw readings/fusion) · `architect` (fused view) ·
   `user` (surfaced in-app) · `brain` (only the athlete_model subset, via its own path).

---

## 6. Evolution strategy

Additive, reversible, and Brain-frozen at every step.

| Stage | Move | Brain impact |
|---|---|---|
| **E0 (this doc)** | Freeze the domain model + matrix. No code. | none |
| **E1** | HSE skeleton: `StateVariable`, `view()`, `ingest()`, lifecycle/decay engine, `Sensor` port. Facts first (re-home M6 preferences + goals/equipment/schedule/budget). | none |
| **E2** | Manual check-in + coach-observation sensors (no devices yet). Populate HSE dynamic state that the Brain does **not** own (energy, pain, motivation, sleep_debt, self-efficacy, consistency, adherence, momentum). | none |
| **E3** | Read-only somatic projection: HSE surfaces recovery/fatigue/stress by **reading** `athlete_model`. Architect consumes the unified `HumanStateView`. | none (read-only) |
| **E4** | Device sensors (Apple Health, Google Fit, Garmin, Whoop, Oura) as adapters → HSE fusion. | none |
| **E5** (opt-in, deploy-gated) | Somatic contribution: device-derived recovery/sleep may inform the Brain **only** through `athlete_store.observe()` (existing M0 contract). Flag-gated. | **no new dependency** — Brain still just reads athlete_model |
| **E6** (separate) | Wire `/chat`: Brain Decision → `HumanStateView` → Architect → Renderer. Flag-gated like M4. | none |

**Sensor addition** = one adapter implementing `normalize(raw) -> Reading`; the fusion,
decay, and TTL machinery is shared. **Backward compatibility:** every stage is additive;
existing tables (`user_preferences`, `recommendation_history`, `workout_history`,
`nutrition_history`, `athlete_models`) are referenced, never dropped. **Confidence/TTL
tuning** is config, not code.

---

## 7. Invariants (must hold at every stage)
- Brain frozen; Brain reads only `athlete_model`; Brain gains no new dependency.
- One writer (`ingest`); immutable reads; Architect owns no state.
- Somatic variables are Brain-authoritative; HSE mirrors them read-only.
- Unknown/expired state → conservative default (never optimistic).
- No `/chat` wiring or deployment before an explicit, separate, flag-gated step (E6).
