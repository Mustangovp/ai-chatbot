# THE APEX BRAIN — Implementation Roadmap (engineering)

**Status:** Engineering plan. Creates no philosophy, no organs, no canon. It defines
*exactly* how the frozen Deliberation Architecture (S0–S6,
`docs/APEX_BRAIN_ARCHITECTURE.md`) — with the three verified refinements from
`docs/APEX_BRAIN_VERIFICATION.md` — becomes production code, starting from **today's
codebase**, without a big-bang rewrite and without a breaking change. Every milestone
ends with a deployable, working production system. The `docs/APEX_VALIDATION_CORPUS.md`
(140 cases) becomes the automated acceptance gate that authorizes each promotion.

---

## 0. Engineering principles (the safety envelope of the rollout itself)

1. **Shadow before enforce.** Every organ is first deployed as a *pure, side-effect-free
   computation* that runs on live traffic, writes its decision to an append-only ledger,
   and **changes nothing the user sees**. Only after its shadow output matches the corpus
   in production is it promoted to authoritative. This is how a safety-critical decision
   layer ships without risk.
2. **Two feature flags, both default-off:** `BRAIN_SHADOW` (compute + log) and
   `BRAIN_ENFORCE` (act on the decision). Rollout is flag flips, each instantly
   reversible. `BRAIN_ENFORCE` is itself staged (safety-front first, full gate later).
3. **Failure-isolated, fail-open to the legacy path.** The entire cascade runs inside a
   `try/except` in `/chat`; any exception logs and **falls back to today's exact
   behaviour** (the current `personality_block + profile_block + SYSTEM_INSTRUCTIONS`
   generation). The Brain can never 500 the chat. This mirrors the existing defensive
   style around `personality.compose`, `build_memory_context`, and `list_workouts`
   ([app.py:1434](app.py:1434), [app.py:1403](app.py:1403), [app.py:1410](app.py:1410)).
4. **Additive, idempotent migrations only.** New tables and columns are appended to
   `db.py`'s versioned `_MIGRATIONS` list ([db.py:188](db.py:188)); `metadata.create_all`
   is safe on existing DBs; no applied step is ever edited; no column is dropped or
   renamed. Runs identically on Postgres (prod) and SQLite (dev).
5. **Backward-compatible API.** `/chat` keeps its request/response contract; new fields
   are additive and optional. The frontend (`templates/apex.html`) needs **zero** changes
   to keep working; it opts into richer rendering later.
6. **The corpus is the gate.** No promotion (shadow→enforce, or a widened enforce scope)
   ships unless the 140-case suite passes with **zero Critical-Fail** and no diagnosis
   leak, exactly as `APEX_BRAIN_VERIFICATION.md` requires.
7. **One source of truth.** The Athlete Model (`athlete_model.py`) is the state every
   organ reads; nothing re-derives what lives there. `personality.py`'s regex
   re-derivation is *retired* into the model in the final milestone, not duplicated.

---

## 1. Current-state map (what we build on — all real, all today)

| Concern | Where it lives now | Role in the target |
|---|---|---|
| HTTP + streaming chat | `app.py` `/chat` [app.py:1356](app.py:1356) | host of the cascade; generation becomes S6 |
| System-prompt assembly | [app.py:1442–1445](app.py:1442) | replaced by `cascade.render_system_prompt(...)` |
| Generation call | [app.py:1499](app.py:1499) `client.chat.completions.create` | **S6**, reached only when the gate clears |
| Fixed safety text | `SYSTEM_INSTRUCTIONS` [app.py:150](app.py:150) | folded behind G1 Constitution Gate |
| Profile → prompt | `_build_profile_block` [app.py:450](app.py:450) | feeds S1 (constraints) instead of raw text |
| Voice / tone | `personality.py` `compose()` [personality.py:325](personality.py:325) | **F Expression layer** (already proto-F) |
| Behavioural signals | `personality.analyze()` regex [personality.py:174](personality.py:174) | retired into Athlete Model `coach_signals` |
| State substrate | `athlete_model.py` (built, **unwired**) | the state every organ reads |
| Persistence | `db.py` SQLAlchemy Core + versioned migrations | gains 2 additive tables |
| Account timeline | `workout_history`, `nutrition_history`, `coach_memory`, `conversations` | evidence sources for `observe()` |
| Memory block | `build_memory_context` [db.py:513](db.py:513) | complements the Athlete Model prompt block |

**The single structural change** the whole roadmap delivers: today generation is the
entry point (`messages → create()`); at the end, **a decision is the entry point**, and
generation is one gated terminal of it.

---

## 2. Target module layout (new `brain/` package — additive, nothing moved)

```
brain/
  __init__.py
  cascade.py          # orchestrator: decide(ctx) -> Decision ; render_system_prompt(...)
  context.py          # BrainContext dataclass (the read-only inputs to the cascade)
  types.py            # Decision, ConstraintSet, CapacityEnvelope, RedFlag, NeedVector, enums
  s0_framing.py       # S0: request-as-signal + mandate check (verification GAP-γ)
  s1_constraints.py   # S1: Somatic Constraint Model
  s2_sentinel.py      # S2: Readiness + Red-Flag Sentinel (urgency-typed; crisis class)
  s3_needs.py         # S3: Need Vector (E1 Stakes)
  s4_gate.py          # S4: Appropriateness Gate (GO/MODIFY/NOT YET/NO TRAIN)
  s5_selector.py      # S5: Intervention Selector (full library)
  s6_generate.py      # S6: constrained system-prompt builder for training generation
  libraries/
    constraint_library.py   # curated condition/med → movement-constraint map (data)
    redflag_library.py      # curated symptom → {urgency, class, route target} (data)
    intervention_library.py # the 10 interventions + their rationale templates (data)
  ledger.py           # append-only decision record → brain_decisions table
athlete_store.py       # NEW thin persistence for athlete_model (load/integrate/observe/save)
tests/brain/
  corpus_cases.jsonl  # 140 cases distilled from the Validation Corpus (the gate)
  test_corpus.py      # runs the cascade over corpus_cases; asserts verdict/urgency/no-dx
  test_s1..s6_*.py    # per-organ unit tests
```

- `brain/` is **pure decision logic** (no Flask, no DB, no OpenAI) — trivially testable,
  exactly like `athlete_model.py` today. It takes a `BrainContext` and returns a
  `Decision`. I/O (loading state, logging, generating) stays in `app.py`/`athlete_store.py`.
- `libraries/*` are **curated data** (dicts/tables), human-reviewed, never LLM-authored —
  the Constraint Library / Red-Flag Library the Brain doc mandates.

### The core datatypes (`brain/types.py`)

```python
from dataclasses import dataclass, field
from enum import Enum

class Verdict(str, Enum):
    GO = "GO"; MODIFY = "MODIFY"; NOT_YET = "NOT_YET"; NO_TRAIN = "NO_TRAIN"

class Urgency(str, Enum):                     # verification GAP-α
    EMERGENCY = "EMERGENCY_now"
    URGENT = "URGENT_soon"
    ROUTINE = "ROUTINE_mention"

class ConstraintTier(str, Enum):
    ABSOLUTE = "absolute"; RELATIVE = "relative"; MONITOR = "monitor"

@dataclass(frozen=True)
class Constraint:
    movement: str            # e.g. "valsalva", "high_impact", "loaded_spinal_flexion"
    tier: ConstraintTier
    reason_key: str          # points to a coach-safe explanation (never a diagnosis)

@dataclass
class ConstraintSet:
    items: list[Constraint] = field(default_factory=list)
    def forbids(self, movement: str) -> bool: ...

@dataclass
class CapacityEnvelope:
    intensity_ceiling: float   # 0..1
    complexity_ceiling: float
    volume_ceiling: float
    supported: bool            # balance-supported required
    confidence: float

@dataclass
class RedFlag:
    class_key: str             # "exertional_chest", "fast_stroke", "psych_crisis", ...
    urgency: Urgency
    route_target: str          # "emergency_services" | "clinician_prompt" | "gp_soft" | "crisis_support"
    message_key: str

@dataclass
class Intervention:            # S5 output
    kind: str                  # training|walk|breathing|sleep|mobility|nutrition|recovery|conversation|medical_followup|crisis_support
    rationale_key: str

@dataclass
class Decision:
    verdict: Verdict
    intervention: Intervention
    red_flags: list[RedFlag]
    constraints: ConstraintSet
    envelope: CapacityEnvelope
    need_vector: list[tuple[str, float]]
    confidence: float
    generate_training: bool    # True only when verdict in {GO,MODIFY} and intervention.kind == "training"
    trace: dict                # per-station reasoning, for the ledger (never user-facing)
    out_of_mandate: bool       # S0 mandate-check (GAP-γ): dangerous non-training request
```

### The read-only input (`brain/context.py`)

```python
@dataclass
class BrainContext:
    message: str
    lang: str
    profile: dict              # db.get_profile(uid) or client profile
    athlete_state: dict        # athlete_model state dict (or fresh_state())
    physiology: dict           # athlete_model.project_physiology(state)
    coach_signals: dict        # athlete_model.coach_signals(state)
    recent_workouts: list      # db.list_workouts(uid)
    now: datetime
```

`cascade.decide(ctx: BrainContext) -> Decision` runs S0→S5 in order, each station able to
halt/reroute, returning the `Decision`. `cascade.render_system_prompt(decision, ctx,
personality_block, athlete_prompt_block) -> str` builds S6's constrained prompt (or the
non-training intervention prompt). Both are pure.

---

## 3. The substrate: wiring `athlete_model.py` into persistence & events

The Athlete Model exists but is unwired. Before any organ, it must (a) persist per user
and (b) be fed by real events. This is the foundation every station reads.

### 3.1 New persistence (`athlete_store.py`) — pure DB glue over `athlete_model`

```python
# athlete_store.py
import db as store, athlete_model as am
def load(uid) -> dict:                 # returns integrated state (or fresh_state)
    row = store.get_athlete_state(uid)          # new db fn (§7)
    st = row or am.fresh_state()
    return am.integrate(st)                      # lazy decay on read
def observe(uid, fact, payload):       # load → observe → save; failure-isolated
    st = load(uid)
    am.observe(st, fact, payload)
    store.save_athlete_state(uid, st)            # new db fn (§7)
    return st
def prompt_block(uid, lang): return am.prompt_block(load(uid), lang)
def physiology(uid): return am.project_physiology(load(uid))
def signals(uid): return am.coach_signals(load(uid))
```

- **Inputs/outputs:** all JSON-serializable state; no OpenAI, no Flask.
- **Dependencies:** `db.py` (2 new functions §7.1), `athlete_model.py` (unchanged).

### 3.2 Event wiring (where `observe()` gets called — additive, wrapped)

| Fact (athlete_model vocab) | Call site today | Wiring |
|---|---|---|
| `workout_completed` | `db.log_workout` [db.py:447](db.py:447) via `/api/workout` [app.py:1276](app.py:1276) | after log, `athlete_store.observe(uid,"workout_completed",session)` |
| `self_report` | profile save [app.py:1261](app.py:1261) when sleep/stress/recovery present | on PUT `/api/profile`, observe the self-report fields |
| `exchange` | `/chat` per user message [app.py:1454](app.py:1454) | in `_persist_reply` [app.py:1482](app.py:1482), observe `exchange` |
| `nutrition_plan_issued` | `db.save_nutrition` [db.py:463](db.py:463) | after save, observe `nutrition_plan_issued` |

Each call is wrapped `try/except` and never blocks the request (same pattern as existing
persistence). **This is M0 and changes nothing user-facing** — the model simply begins to
learn and its `prompt_block` can be *appended* to the system prompt in shadow (logged,
not yet trusted).

---

## 4. Per-organ engineering specification (S0–S6)

Each organ below is a pure function `f(BrainContext, upstream results) -> station result`,
living in its own module, unit-tested against corpus cases, and composed by `cascade.py`.
The **dependencies are one-directional and declared** (matching the Brain doc's interaction
map): S0→S1→S2→S3→S4→S5→S6, each reading only upstream outputs + the Athlete Model.

---

### S0 · Framing — `brain/s0_framing.py`

- **Purpose:** treat the request as a signal; classify it. Includes the verification's
  **mandate-check (GAP-γ)**: dangerous/out-of-mandate *non-training* requests (PED-dosing
  optimization, diuretic dehydration, crash weight-cut, unsupervised med changes,
  fasting-on-glucose-meds) route straight to bounded refusal.
- **Class/interface:**
  ```python
  @dataclass
  class Framing: intent: str; out_of_mandate: bool; mandate_reason_key: str | None
  def frame(ctx: BrainContext) -> Framing
  ```
- **Inputs:** `ctx.message`, `ctx.lang`.
- **Outputs:** `Framing`. If `out_of_mandate`, the cascade short-circuits to a
  refuse+redirect `Decision` (verdict `NO_TRAIN`, intervention `conversation`, via E5/G1).
- **Dependencies:** `libraries/` mandate keyword table (curated); no state needed.
- **Tests:** `test_s0_mandate.py` — V-050/056/057/093/100 → `out_of_mandate=True`;
  ordinary requests → `False`. Assert no false positives on the 130 in-scope cases.

---

### S1 · Somatic Constraint Model — `brain/s1_constraints.py`

- **Purpose:** convert who-this-human-is into a `ConstraintSet` + `CapacityEnvelope`.
- **Class/interface:**
  ```python
  def build(ctx: BrainContext) -> tuple[ConstraintSet, CapacityEnvelope]
  ```
- **Inputs:** `ctx.profile` (age, sex, stated conditions, meds, injuries, equipment),
  `ctx.athlete_state` traits (recovery_capacity, adaptation, adherence), `ctx.recent_workouts`.
- **Outputs:** typed `ConstraintSet` (absolute/relative/monitor as **movements**, never
  diagnoses) + `CapacityEnvelope` (intensity/complexity/volume ceilings + `supported` +
  `confidence`). Sparse profile → low envelope confidence → conservative downstream
  (this is the “most cautious when it knows least” law).
- **Dependencies:** `libraries/constraint_library.py` — the curated map, e.g.
  `{"hypertension": [Constraint("valsalva",ABSOLUTE,...), Constraint("heavy_isometric",RELATIVE,...)],
    "stroke_history": [Constraint("maximal_exertion",ABSOLUTE,...), Constraint("unsupported_balance",RELATIVE,...)],
    "osteoporosis":[Constraint("loaded_spinal_flexion",ABSOLUTE,...)], ...}`. Conservative
  default on unknown conditions/meds; human-reviewed; **never LLM-generated**.
- **DB/API:** none new (reads existing profile).
- **Tests:** `test_s1_constraints.py` from the corpus — P-035 → {valsalva, maximal,
  unsupported_balance, loaded_flexion} absolute/relative + narrow envelope; P-036/P-079 →
  **wide envelope, empty constraint set** (the over-caution / “invent no constraints”
  guard from the CONCERN ledger); P-040 → loaded_spinal_flexion forbidden.

---

### S2 · Readiness + Red-Flag Sentinel — `brain/s2_sentinel.py`  *(carries the two verified fixes)*

- **Purpose:** trait vs state; scan for signals that outrank the training question.
  Implements **GAP-α (urgency tiering)** and **GAP-β (psychological-crisis class)** from
  the verification, from day one.
- **Class/interface:**
  ```python
  @dataclass
  class State: readiness: float; readiness_conf: float; red_flags: list[RedFlag]
  def assess(ctx: BrainContext) -> State
  ```
- **Inputs:** `ctx.message` (symptom scan), `ctx.physiology` (readiness = f(fatigue, sleep,
  recovery)), `ctx.athlete_state`, `ctx.profile`, self-report.
- **Outputs:** `readiness` (+confidence) and **urgency-typed** `RedFlag`s. Each red flag
  carries `urgency ∈ {EMERGENCY, URGENT, ROUTINE}` and a `route_target`; the cascade halts
  toward the matching handoff.
- **Dependencies:** `libraries/redflag_library.py` — curated symptom → flag, e.g.:
  ```python
  {"fast_stroke":      RedFlag("fast_stroke", EMERGENCY, "emergency_services", ...),
   "cauda_equina":     RedFlag("cauda_equina", EMERGENCY, "emergency_services", ...),
   "autonomic_dysreflexia": RedFlag(..., EMERGENCY, "emergency_services", ...),
   "rhabdo":           RedFlag(..., EMERGENCY, "emergency_services", ...),
   "acute_hypo":       RedFlag(..., EMERGENCY, "stop_and_treat", ...),
   "psych_crisis":     RedFlag("psych_crisis", EMERGENCY, "crisis_support", ...),  # GAP-β
   "exertional_chest": RedFlag(..., URGENT, "clinician_prompt", ...),
   "unilateral_calf":  RedFlag(..., URGENT, "clinician_prompt", ...),
   "persistent_low_mood": RedFlag(..., ROUTINE, "gp_soft", ...)}
  ```
  The scan is a curated matcher over **symptom clusters** (the CONCERN-ledger requirement:
  fire on patterns, not only single classic tokens), reviewed by a professional.
- **DB/API:** none new.
- **Tests:** `test_s2_sentinel.py` = the **Critical-Fail Index**. P-083 → EMERGENCY /
  emergency_services (not a soft route — the GAP-α regression test); P-116 → psych_crisis /
  EMERGENCY / crisis_support (GAP-β regression test); P-015/P-063 → URGENT; P-022/P-125 →
  ROUTINE soft route (cluster-sensitivity). Assert: no marked red flag is ever downgraded
  below its corpus urgency.

---

### S3 · Need Vector — `brain/s3_needs.py`  *(frozen E1 Stakes, verbatim)*

- **Purpose:** compute what matters most today, before deciding to train.
- **Interface:** `def rank(ctx, s1, s2) -> list[tuple[str, float]]` — ranked need vector
  over `{medical_followup, sleep, stress_reduction, recovery, gentle_movement, nutrition,
  conversation, training}` using the frozen stakes order (safety > relationship > habit >
  adaptation > today) and feed-the-scarcer-account.
- **Inputs:** S1 constraints, S2 readiness + red flags, `ctx.athlete_state`, goals.
- **Outputs:** ranked list; population differences come *only* from S1's envelope/weights
  (no branching on “patient type”).
- **Tests:** `test_s3_needs.py` — P-035 → medical_followup + gentle_movement top, training
  bottom; P-036 → training top (adaptation legitimately leads).

---

### S4 · Appropriateness Gate — `brain/s4_gate.py`

- **Purpose:** the right of refusal. Emits `Verdict ∈ {GO, MODIFY, NOT_YET, NO_TRAIN}`.
- **Interface:** `def decide(ctx, s1, s2, s3) -> tuple[Verdict, float]`.
- **Decision rule (uncertainty → safety):** any EMERGENCY/URGENT red flag → `NOT_YET`
  (temporal defer) or `NO_TRAIN` (categorical); state below floor → `NOT_YET`; absolute
  contraindication w/ no safe modification → `NO_TRAIN`; low confidence → conservative;
  else `MODIFY` if a tightened envelope is needed, `GO` if within envelope. The
  four-way mapping is exactly the verification's gate table (NOT_YET vs NO_TRAIN by tense).
- **Inputs/outputs:** upstream results → `(Verdict, confidence)`.
- **Dependencies:** frozen E3/E5 rules (encoded as pure predicates); no new libraries.
- **Tests:** `test_s4_gate.py` — the corpus verdict column: P-004 GO, P-001 MODIFY,
  P-015 NOT_YET, P-003 NO_TRAIN, etc. Distribution check (≈30/35/20/10/5) to catch a
  gate that collapses toward all-GO (dangerous) or all-NO (useless).

---

### S5 · Intervention Selector — `brain/s5_selector.py`

- **Purpose:** even when training is permitted, is it optimal? Select one intervention.
- **Interface:** `def select(ctx, verdict, s3) -> Intervention`.
- **Inputs:** S3 need vector, S4 verdict, `ctx` (receptivity/Kairos), red-flag route.
- **Outputs:** `Intervention(kind, rationale_key)` from the full library
  (`libraries/intervention_library.py`): training · walk · breathing · sleep · mobility ·
  stress_reduction · nutrition · conversation · medical_followup · crisis_support.
  `generate_training` on the `Decision` is set True **only** when verdict∈{GO,MODIFY} and
  kind == "training".
- **Tests:** `test_s5_selector.py` — P-035 → medical_followup + gentle walking/breathing;
  P-116 → crisis_support; P-067 → training. Assert training is never selected when S4 is
  NOT_YET/NO_TRAIN.

---

### S6 · Constrained Generation — `brain/s6_generate.py` + `app.py` `/chat`

- **Purpose:** the gated terminal. Reached only when `decision.generate_training`.
- **Interface:** `def training_system_prompt(decision, ctx, personality_block,
  athlete_prompt_block) -> str` — assembles the system prompt from the **Decision**: the
  `ConstraintSet` and `CapacityEnvelope` become **hard prompt constraints** (“Do not
  program: Valsalva, maximal isometrics, unsupported balance. Intensity ceiling: low.
  Movements must be pain-free ROM.”), plus the frozen `SYSTEM_INSTRUCTIONS` (behind G1) and
  the personality/voice block. For **non-training** interventions, a sibling
  `intervention_system_prompt(decision, ctx, ...)` renders the chosen intervention
  (walk/breathe/route) in APEX's voice — this is the frozen null/redirect action made real.
- **Integration:** replaces the manual assembly at [app.py:1442–1445](app.py:1442). Today:
  ```python
  base = (profile_block + "\n\n" + SYSTEM_INSTRUCTIONS) if profile_block else SYSTEM_INSTRUCTIONS
  system_content = (personality_block + "\n\n" + base) if personality_block else base
  ```
  Target (only when enforcing): `system_content = cascade.render_system_prompt(decision,
  ctx, personality_block, athlete_prompt_block)`. The generation call at
  [app.py:1499](app.py:1499) is **unchanged** — same model, same streaming, same cost.
  What changed is the *prompt it receives* and *whether it is reached at all*.
- **G1 Constitution Gate:** unchanged. It remains the final filter (no clinical labels).
  S2/S5 produce routes and constraints; G1 guarantees no diagnosis reaches the user — the
  verification's structural line.
- **Tests:** `test_s6_generate.py` — snapshot the assembled prompt for P-035 asserts
  push-ups/planks are explicitly forbidden and intensity is floored; for a GO case asserts
  the envelope is wide. (Prompt-assembly is deterministic and unit-testable; the LLM output
  is checked by the end-to-end corpus harness, §8.)

---

## 5. The incremental milestone plan (every milestone ships to production)

Each milestone is independently deployable, flag-gated, and ends with a working system.
The **enforcement of behaviour is deferred to M4** — everything before it is invisible to
users (shadow + substrate), so the risky change (refusing/rerouting generation) lands only
once the cascade has been proven on live shadow traffic against the corpus.

### M0 · Substrate & shadow harness — *no user-visible change*
- **Build:** `athlete_store.py`; wire `observe()` at the 4 event sites (§3.2); DB tables
  `athlete_models` + `brain_decisions` (§7); `brain/ledger.py`; flags `BRAIN_SHADOW`,
  `BRAIN_ENFORCE` (both off). Append the Athlete Model `prompt_block` to the system prompt
  **only when `BRAIN_SHADOW`** and log it — still no gate.
- **Deployable end state:** identical UX; the model starts learning; the ledger starts
  filling. **Rollback:** flags off / migrations are additive (no rollback needed).
- **Exit gate:** `athlete_models` rows growing; `observe()` never throws in prod logs.

### M1 · S1 Constraint Model (shadow)
- **Build:** `brain/s1_constraints.py` + `constraint_library.py`; compute S1 in `/chat`
  under `BRAIN_SHADOW`, log the `ConstraintSet`/`Envelope` to `brain_decisions`. No output
  change. **Tests:** `test_s1_constraints.py` green.
- **Exit gate:** shadow S1 on live traffic matches expected constraints on spot-checks;
  the over-caution guard cases (P-036/P-079) show wide envelopes in the ledger.

### M2 · S2 Sentinel (shadow) — *the safety detector, still only logging*
- **Build:** `brain/s2_sentinel.py` + `redflag_library.py` (urgency-typed + psych-crisis).
  Shadow-log every red flag + urgency. **Tests:** the full Critical-Fail Index passes at the
  organ level. **Exit gate:** in production shadow, every message that *should* raise a flag
  does (measured by sampling + the corpus replay), with zero EMERGENCY misses.

### M3 · S3+S4+S5 + cascade orchestration (shadow) — *the whole Brain, logging only*
- **Build:** `s3_needs.py`, `s4_gate.py`, `s5_selector.py`, `s0_framing.py`, `cascade.py`,
  `intervention_library.py`. `/chat` now computes a full `Decision` under `BRAIN_SHADOW`
  and logs it beside the legacy path (which still produces the actual reply).
- **Tests:** **`tests/brain/test_corpus.py` runs all 140** — the acceptance gate. Verdict,
  urgency, intervention sanity, no-diagnosis all asserted; zero Critical-Fail required.
- **Exit gate:** 140/140 pass in CI **and** a week of production shadow shows the
  decision distribution ≈ corpus (§ verification scoreboard) with no anomalous all-GO/all-NO
  drift. This is the go/no-go for touching user output.

### M4 · Enforce the SAFETY FRONT only — *first user-visible change; closes the live hazard*
- **Build:** flip `BRAIN_ENFORCE=safety`. In `/chat`, when the shadow `Decision` is an
  **EMERGENCY/URGENT red flag**, or `NOT_YET`/`NO_TRAIN` from a hard contraindication, the
  route/decline is rendered (via `intervention_system_prompt`, still streamed through the
  same generation call for voice) **instead of** a raw workout. `GO`/`MODIFY` requests are
  *additionally* constrained (S1 constraints injected into the prompt) but otherwise flow as
  today. Everything else is unchanged.
- **Why this scope first:** it is the smallest change that eliminates the
  push-ups-for-a-stroke-survivor hazard and its 28 Critical-Fail siblings, and it is
  instantly reversible (`BRAIN_ENFORCE=off`).
- **API:** `/chat` SSE gains an optional leading `{"decision":{"verdict","urgency","route"}}`
  event before the token stream; the frontend ignores unknown events today (backward
  compatible) and can render a routing card later.
- **Tests:** end-to-end server tests hitting `/chat` for the Critical-Fail cases assert the
  reply routes and never emits a workout; a canary % of traffic first, then 100%.
- **Deployable end state:** production now refuses correctly; capable users unaffected.

### M5 · Full gate — generation becomes S6
- **Build:** `BRAIN_ENFORCE=full`. All requests route through `cascade.decide`; the system
  prompt is always `cascade.render_system_prompt(...)`; generation is reached only when
  `decision.generate_training`. Non-training interventions (walk/breathe/sleep/route) are
  rendered by S5. `_build_profile_block` is now *consumed by S1* rather than dumped raw.
- **Tests:** the 140-corpus end-to-end suite runs against the enforced path in CI and as a
  production canary; zero Critical-Fail to widen past canary.
- **Deployable end state:** the final architecture — a decision is the entry point,
  generation a gated terminal.

### M6 · Consolidation & de-duplication — *one source of truth*
- **Build:** retire `personality.analyze()`'s regex re-derivation → `personality.compose`
  reads `athlete_model.coach_signals` (the model becomes the sole signal source; no
  duplicated logic). Remove `BRAIN_SHADOW` (now always on the enforced path). Add
  observability dashboards over `brain_decisions` (verdict mix, red-flag rates, override
  rate). Fold the CONCERN-ledger tuning contract (§9) into config with alarms.
- **Deployable end state:** clean, observable, single-source-of-truth Brain. `personality.py`
  is now purely the F Expression layer; `athlete_model.py` is the sole state.

> Every milestone above ends green in production. If any exit gate fails, the flag stays at
> the prior stage; nothing regresses.

---

## 6. Rollback matrix

| Milestone | User-visible? | Rollback |
|---|---|---|
| M0–M3 | No (shadow) | flags off; tables are additive, left in place harmlessly |
| M4 | Yes (safety front) | `BRAIN_ENFORCE=off` → instant return to legacy generation |
| M5 | Yes (full gate) | `BRAIN_ENFORCE=safety` (partial) or `off` (full) |
| M6 | No (cleanup) | revert the personality/signal swap commit; model untouched |

---

## 7. Database schema changes (all additive, via `db.py` `_MIGRATIONS`)

Append to the versioned list at [db.py:188](db.py:188) — `create_all` builds new tables,
each numbered step recorded in `schema_version`, never editing an applied step:

### 7.1 `athlete_models` (v2)
```python
athlete_models = Table("athlete_models", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
           nullable=False, unique=True),
    Column("schema", String(32), nullable=False),   # "athlete-model-v1"
    Column("state", JSON, nullable=False),           # the athlete_model state dict
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)
# db functions:
def get_athlete_state(user_id) -> dict|None
def save_athlete_state(user_id, state: dict)   # upsert by user_id (same pattern as save_profile)
```

### 7.2 `brain_decisions` (v3) — the append-only decision ledger (Event Ledger)
```python
brain_decisions = Table("brain_decisions", metadata,
    _uuid_col(),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")),  # nullable: anon
    Column("verdict", String(16)),               # GO|MODIFY|NOT_YET|NO_TRAIN
    Column("intervention", String(32)),
    Column("urgency", String(16)),               # EMERGENCY_now|URGENT_soon|ROUTINE_mention|null
    Column("enforced", Boolean, default=False),  # shadow vs authoritative
    Column("out_of_mandate", Boolean, default=False),
    Column("trace", JSON),                        # per-station reasoning (never user-facing)
    Column("message_hash", String(64)),           # sha256 of the message (privacy: no raw text)
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Index("ix_brain_user_created", "user_id", "created_at"),
)
def log_decision(user_id, decision, enforced: bool)  # brain/ledger.py calls this
```

- **Migration strategy:** add both `Table` definitions to `metadata`; append
  `(2, lambda c: None)` and `(3, lambda c: None)` to `_MIGRATIONS` (base tables are created
  by `create_all`; the no-op steps just record the version). Zero-downtime, forward-only,
  identical on SQLite/Postgres. No existing table is touched.
- **Privacy:** the ledger stores a message **hash**, not raw text (raw transcript already
  lives, account-owned, in `conversations`). Trace holds reason-keys, never diagnoses.

---

## 8. Testing strategy (the corpus is the gate)

Three layers, all in CI, ordered cheap→expensive:

1. **Per-organ unit tests** (`tests/brain/test_s0..s6_*.py`) — pure functions, no I/O, fast.
   Each asserts the corpus behaviour for its station (constraint mapping, urgency tier,
   verdict). These are the regression tests for the two verified FAILs: `test_s2_sentinel.py`
   permanently pins P-083→EMERGENCY and P-116→psych_crisis/EMERGENCY.
2. **The 140-case acceptance suite** (`tests/brain/test_corpus.py` over
   `corpus_cases.jsonl`) — runs `cascade.decide` on every persona's message+profile and
   asserts: verdict match · red-flag routing/urgency · intervention within the acceptable
   set · **no diagnosis** (a G1 lint over the rendered prompt/route text). **Any
   Critical-Fail fails the build.** This file is generated once by distilling each corpus
   entry's evaluation block into `{id, message, profile, expect:{verdict, urgency,
   intervention_in, no_dx:true}}`, then frozen as canon (append-only, verdicts never
   weakened — §change-control of the corpus).
3. **End-to-end + production shadow** — server tests hit `/chat` (safety-front cases) and
   assert the streamed reply routes, never a workout; in production, `brain_decisions`
   shadow logs are diffed against the corpus distribution weekly. Shadow is the real-world
   acceptance test before each enforce-widening.

**CI gate for any promotion:** unit + 140-corpus green, zero Critical-Fail, zero diagnosis
leak. Mirrors `APEX_BRAIN_VERIFICATION.md` §5 exactly.

---

## 9. The CONCERN-ledger tuning contract → configuration (`brain/config.py`)

The verification's CONCERN ledger becomes explicit, alarmed config — the build-time
contract the implementation must honor:

- **Envelope width:** `ENVELOPE_WIDE_WHEN_UNCONSTRAINED = True` — absence of constraints
  yields a *wide* envelope (the anti-infantilization guard; P-036/P-055/P-073/P-079). A
  monitor asserts the ledger's GO-rate for constraint-empty profiles stays high.
- **Soft-flag sensitivity:** the Sentinel fires on **clusters** (`REDFLAG_CLUSTER_MODE`),
  not single tokens (P-022/P-111/P-125/P-138).
- **Provenance tie-break:** `BEHAVIOUR_OUTRANKS_SELFREPORT = True` — conflicting
  self-report vs measured behaviour resolves conservatively (P-030/P-053/P-137), reading
  `athlete_model` provenance tiers directly.
- **Mandate-check on:** `S0_MANDATE_CHECK = True` (P-050/056/057/093/100).

Each is a named flag with a production alarm, so a mis-tuning is caught as a metric drift,
not a user harm.

---

## 10. What does NOT change (guarding the frozen canon during engineering)

- **Philosophy, Brain Architecture, Corpus, Verification** — untouched; consumed, not edited.
- **No new organs.** `brain/` modules are the S0–S6 organs already specified; the two
  verified fixes are an `urgency` field, a catalogue class, and an S0 predicate — all inside
  existing organs.
- **G1 Constitution Gate** — unchanged; still the final no-clinical-labels filter.
- **`SYSTEM_INSTRUCTIONS`, Stripe/token/auth/free-limit, streaming, model selection** — all
  untouched; the cascade sits *in front of* generation, not around billing or identity.
- **Frontend `templates/apex.html`** — needs no change to keep working; richer rendering of
  routing cards is optional and additive.

---

## 11. Risk register

| Risk | Mitigation |
|---|---|
| Cascade bug breaks `/chat` | failure-isolated try/except → fall back to legacy generation; flags |
| Over-caution (infantilization) at enforce | shadow distribution check + envelope-wide config + P-036/P-079 tests before widening |
| Red-flag under-trigger | Critical-Fail unit tests pinned; cluster-mode; weekly shadow audit; EMERGENCY misses page on-call |
| Constraint/red-flag library gaps | conservative defaults on unknowns; human review; library is data, hot-fixable without code deploy |
| Latency (S1–S5 are cheap reads; only S6 calls the LLM) | most requests are *faster* (refusals skip generation); measure p95 in shadow first |
| Athlete Model state corruption | bounded steps already prevent jumps; state is per-user JSON; a bad row degrades to `fresh_state()` |
| Migration failure | additive/idempotent; `create_all` safe; tested on SQLite + a Postgres staging clone before prod |

---

## 12. One-screen summary

```
today:   message ──────────────────────────────► generate ──► stream
                       (personality + profile + SYSTEM_INSTRUCTIONS)

M0–M3:   message ──► [cascade in SHADOW → ledger] ──► generate ──► stream   (UX identical)

M4:      message ──► cascade ──► red flag / NO-TRAIN? ──► route/decline ──► stream
                                └─ else ─► generate (S1-constrained) ──► stream

M5+:     message ──► S0─S1─S2─S3─S4─S5 ──► S6 generate (only if earned) ──► G1 ──► stream
                                          └─ or non-training intervention ─► G1 ──► stream
```

**From "generate a workout, then render" to "decide what this human needs, and a workout is
one gated answer" — shipped in six reversible, always-deployable steps, gated by 140 humans.**

*End of the APEX Brain Implementation Roadmap.*
