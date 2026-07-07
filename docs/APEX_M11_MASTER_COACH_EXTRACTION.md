# APEX M11 — First Master Coach Extraction

**Chapter IV — Build the Mind.**
**Status:** KNOWLEDGE ENGINEERING ONLY. No code, no runtime, no deployment, no Brain / Human
State / Coaching-Intelligence change.

**Mission:** not to learn exercises, not to summarize books — to **reconstruct how a
world-class coach thinks**: their decision-making, not their opinions or quotes. This becomes
the first *living knowledge profile* inside APEX and, with others, the raw material APEX
synthesizes into **its own reasoning — never an imitation of any individual.**

---

## 0. The one rule that governs everything: WHY, not WHAT

M10 captured *what* is known (Knowledge Cards, a **knowledge** graph). M11 captures *how a
coach reasons* (a **mind** graph). We do **not** record what a coach says; we reconstruct the
**decision engine** that generates what they say.

Every extracted element must answer the **validity frame** (or it is not admitted):

1. **What problem is being solved?** 2. **What evidence supports it?** 3. **When is it valid?**
4. **When does it fail?** 5. **What assumptions does it rest on?**

And every element is split into **OBSERVED** (what the coach demonstrably did/said) vs
**INFERRED** (the reasoning we reconstruct) — each with its own confidence, so we never
launder an inference as a fact.

---

## 1. Master Coach Profile — architecture

A **Master Coach Profile** is a versioned, evidence-graded model of *how one coach thinks*,
built inside the Knowledge Lab (M10) and used only as **input to synthesis** — never surfaced
as "Coach X's method."

It represents ten dimensions:

| Dimension | What it captures |
|---|---|
| Decision Philosophy | the values/priorities that bias every call |
| Mental Models | the frames they reason with (§2) |
| Reasoning Process | the *sequence* from situation → decision (§5, Mind Graph §6) |
| Communication Style | how they deliver a decision (§4) |
| Prioritization | what they optimize first when things conflict |
| Risk Tolerance | how conservative/aggressive, and where |
| Adaptation Logic | how they change the plan as reality changes |
| Failure Recovery | how they handle lapses, plateaus, injuries, setbacks |
| Motivational Style | how they move a person to act |
| Long-term Philosophy | what "success" means to them over years |

**Composed of four pattern types** — Thinking (§2), Decision (§3), Communication (§4),
Diagnostic (§5) — each backed by M10 Knowledge Cards, assembled into a **Mind Graph** (§6).

**Per-coach extraction targets (14):** Core Beliefs · Decision Rules · Mental Models ·
Diagnostic Questions · Programming Philosophy · Recovery Philosophy · Nutrition Philosophy ·
Communication Patterns · Behavioral Patterns · Common Mistakes they repeatedly correct ·
Situations where they intentionally **refuse** action · Trade-offs · Exceptions · Contradictions.

**Profile schema:**
```
MasterCoachProfile {
  id                 # MCP-<NNN>
  identity           # role/domain focus, de-identified for synthesis; provenance retained internally
  domains            # D1..D7 (M9) coverage
  decision_philosophy, prioritization, risk_tolerance, long_term_philosophy   # narrative + linked rules
  thinking_patterns[]      # TP-* (§2)
  decision_patterns[]      # DP-* (§3)
  communication_patterns[] # CP-* (§4)
  diagnostic_patterns[]    # DXP-* (§5)
  refusals[]         # situations where they deliberately do nothing (and WHY)
  contradictions[]   # where the coach is internally inconsistent (recorded, not resolved)
  provenance         # source Cards (M10) + OBSERVED/INFERRED split + confidence
  version, review_status
}
```

---

## 2. Thinking Pattern Specification (mental models)

A **ThinkingPattern** is a frame the coach uses to *make sense* of a situation before deciding.

```
ThinkingPattern {
  id            # TP-<NNN>
  name          # the model, APEX-neutral (not a branded term)
  frame         # how the coach re-represents the problem
  triggers      # situations that invoke this model
  explains      # what it lets them predict/understand
  assumptions   # what must be true for it to hold
  boundary      # when it applies / when it breaks
  evidence_tier # A|B|C, + validity-frame answers
  related       # TP/DP links
}
```
*Illustrative shape (not a real coach):* "Load is information, not just stress" — reframes a
hard session's soreness as feedback about recovery capacity, triggering an adaptation decision
rather than a badge of honor. Boundary: breaks under injury/illness (safety overrides).

---

## 3. Decision Pattern Specification

A **DecisionPattern** is the reusable reasoning that turns signals into a call.

```
DecisionPattern {
  id            # DP-<NNN>
  situation     # the class of moment
  inputs_read   # the signals THIS coach actually attends to (often fewer than exist)
  rule          # if <inputs> then <decision>
  why           # the problem being solved (mandatory)
  priority      # what it optimizes; order when goals conflict
  tradeoffs     # what it knowingly sacrifices
  exceptions    # documented carve-outs
  failure_mode  # when the rule misfires, and the tell
  evidence_tier # + validity frame
  overrides / overridden_by   # relation to other DPs and to Safety (always overridden by Safety)
}
```
The point is **inputs_read + why**, not the surface advice: two coaches can give the same cue
for opposite reasons — the reason is what we extract.

---

## 4. Communication Pattern Specification

How a decision is *delivered* — reconstructed as pattern, never as reproduced wording.

```
CommunicationPattern {
  id             # CP-<NNN>
  intent         # what the delivery is trying to achieve (buy-in, calm, challenge…)
  sequence       # what they establish first → last (e.g. validate → reframe → prescribe)
  framing        # metaphor/framing *style* (abstracted, not quoted)
  autonomy_stance # command ↔ offer
  push_vs_soften # when they press, when they back off (state-conditioned)
  boundary       # when this style would harm (maps to M8 forbidden styles)
  evidence_tier
}
```

---

## 5. Diagnostic Pattern Specification

Before deciding, what does this coach **ask**? The diagnostic layer is where reasoning is most
visible — a great coach's questions reveal their model.

```
DiagnosticPattern {
  id            # DXP-<NNN>
  trigger       # the presenting situation
  questions[]   # the questions the coach asks (each: what it rules in / rules out)
  branch_logic  # how answers route to different DecisionPatterns
  priority      # which question they ask first and why (their information theory)
  stop_rule     # when they have enough to decide (avoids over-diagnosis)
  evidence_tier
}
```
Reasoning workflow: **DXP (ask) → TP (frame) → DP (decide) → CP (deliver).**

---

## 6. Mind Graph Architecture

The Mind Graph represents **how the coach thinks** — a traversable reasoning network, distinct
from M10's knowledge graph of facts.

**Nodes:** `belief` (core values) · `mental_model` (TP) · `diagnostic_question` (DXP) ·
`decision_rule` (DP) · `priority` · `risk_posture` · `communication_move` (CP).

**Edges:**
| Edge | Meaning |
|---|---|
| `informs` | a belief/model informs a rule |
| `triggers` | a situation/question triggers a model or rule |
| `constrains` | a priority/risk-posture constrains a decision |
| `overrides` | one rule beats another (Safety overrides all) |
| `trades_off_against` | two goals in tension |
| `applies_when` / `breaks_when` | context boundaries |

**Use:** traverse `situation → DXP → TP → DP → CP` to *reproduce the coach's reasoning*, then
**validate** the profile by checking the traversal reproduces the coach's known decisions on
held-out situations (a profile that can't predict the coach is wrong). Also used to **compare**
coaches (graph overlap = convergent reasoning) and to **synthesize** (§7).

```
        belief ─informs─► mental_model ─┐
   diagnostic_question ─triggers──────► decision_rule ─► communication_move
        priority ─constrains──────────► decision_rule
        risk_posture ─constrains──────► decision_rule
                     Safety (Brain) ─overrides──► every decision_rule
```

---

## 7. Extraction workflow (Source → … → Constitution)

```
 Source ─► Observation ─► Reasoning reconstruction ─► Knowledge Cards ─► Decision Patterns ─► (synthesis) ─► Constitution Principles
```
1. **Source** — captured in M10 Source Registry (books, papers, talks, interviews, case studies…).
2. **Observation** — record *what the coach does/says* across many situations (behaviors +
   stated reasons). Mark **OBSERVED**.
3. **Reasoning reconstruction** — infer the **WHY**: the hidden model/rule that generates the
   observation. Mark **INFERRED** + confidence; apply the validity frame.
4. **Knowledge Cards** — each reconstructed element → an M10 Card tagged to the profile.
5. **Pattern assembly** — cluster Cards into TP/DP/CP/DXP; build the Mind Graph.
6. **Review** — M10 governance (Coaching Reviewer; Medical Reviewer for any safety content).
7. **Synthesis → Constitution** — only across coaches (§8), never single-coach → principle.

**Anti-overfitting rule:** a single coach's idiosyncrasy is a *profile* fact, not an APEX
principle. Persona ≠ principle.

---

## 8. Expert Synthesis Strategy (→ APEX's own mind)

Once multiple Master Coach Profiles exist, APEX builds **its own reasoning** by comparing Mind
Graphs — it never adopts one coach.

| Pattern across coaches | APEX action |
|---|---|
| **Convergent** — several coaches independently reason the same way | strong candidate APEX principle (high confidence) |
| **Divergent** — coaches genuinely disagree | M9 ConflictRecord + context map; APEX keeps both, selects by context |
| **Idiosyncratic** — unique to one coach | recorded in that profile; **not** adopted as principle |
| **Contradicted by evidence** | evidence wins; principle graded down/rejected |

**The APEX Mind** = the merged, synthesized reasoning graph: convergent reasoning becomes
principle, divergent reasoning becomes context-selected options, idiosyncrasy stays local.
This is what makes APEX *"not the method of Coach X"* — it reasons in ways **no single coach
does**, assembled from the best-supported thinking across many.

---

## 9. Invariants / guardrails
- Extract **WHY, not WHAT**; separate OBSERVED from INFERRED; every element passes the 5-question
  validity frame.
- Reconstruct reasoning **patterns**, never reproduce a coach's words/content (copyright + it is
  the abstraction that makes synthesis possible).
- A profile is validated by its power to **predict the coach**; an unfalsifiable profile is rejected.
- No single-coach idiosyncrasy becomes a Constitution principle; synthesis is cross-coach.
- **Safety is always Brain-owned and overrides every reasoning path** in every Mind Graph.
- Profiles are internal research artifacts; APEX never presents itself as imitating any individual.
