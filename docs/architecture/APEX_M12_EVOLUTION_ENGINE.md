# APEX M12 — Evolution Engine

**Chapter VI.** **Status:** ARCHITECTURE ONLY. No code, no deployment.

**Mission:** design how the Decision Genome **evolves**. Genes are hypotheses; **real-world
outcomes** decide which grow stronger. This operationalizes the Constitution's "Continuous
Learning" section using the Observatory (M5) — a closed loop from principle → decision → outcome
→ evidence → fitness → governed Constitution update.

---

## 0. Two locks that govern everything (read first)

1. **Mission-lock.** A gene's fitness is measured **only against the Constitution's mission** —
   long-term adherence, trust, confidence, sustainable transformation. **Engagement is never an
   objective.** Session counts / DAU are *guardrails* (watched for dark-pattern drift), and any
   gene that raises engagement while lowering transformation/trust is penalized, not promoted.
2. **Safety-lock.** Safety and Values genes are **PROTECTED** — **exempt from selection.** Outcome
   data can *strengthen or clarify* them but can **never demote or retire** them. The loop can
   never "learn" to weaken a safety check to improve any metric. Any change to a safety gene needs
   Medical Reviewer sign-off + an explicit constitutional amendment — not a fitness update.

Everything below is bounded by these two locks.

---

## 1. Evolution Architecture

A gene now carries evidence on **two independent axes** — never conflated:
- **Convergence** (from the Genome): how universal across independent experts.
- **Efficacy** (from the Observatory): whether it actually helps real humans, on mission metrics.

```
   Genome (convergence) ─┐
                         ▼
              ADOPTED gene = Constitution principle
                         │ produces
                         ▼
        runtime coaching decision  ──tagged with principle→gene IDs (M8/M9 rationale)──┐
                         │                                                              │
                         ▼                                                              │
     Observatory (M5) + HSE longitudinal + user feedback  ── outcome signals ──────────┘
                         │ attribution (probabilistic, confound-aware)
                         ▼
             Evidence Ledger (convergence + efficacy)
                         │ fitness estimate (per context, with uncertainty)
                         ▼
        Lifecycle Controller → PROPOSED transition (promote/demote/retire)
                         │ Safety Sentinel gate + human review + canary
                         ▼
             versioned Constitution / Genome release
```
**The engine only proposes.** No user-facing change ships without safety clearance, human review,
a canary, and a versioned release (the M4/M8 rollout discipline). It never edits live coaching
behavior directly — it writes proposed fitness/confidence.

**Components:** Outcome Signal Collector · Attribution Engine (uses the explainability trace) ·
Evidence Ledger · Fitness Estimator · Lifecycle Controller · Safety Sentinel · Review Board.

---

## 2. Gene Lifecycle

```
  HYPOTHESIS ─(cross-expert independence, Genome)─► CALLED ─(review + canary)─► ADOPTED
      ▲                                                                          │ outcomes accrue
      │ new evidence                                                             ▼
   (mutation stays profile-local)                        REINFORCED ◄─ strong convergence + efficacy
                                                              │  sustained under-performance / contradicted
                                                              ▼
                                                          WEAKENING ─► DEPRECATED ─► RETIRED (archived)

   PROTECTED (Safety/Values) ── exempt: may only strengthen/clarify, never WEAKENING/RETIRED
```
| State | Meaning | Enter when |
|---|---|---|
| HYPOTHESIS | expert-proposed, unproven | Genome candidate |
| CALLED | independent convergence met | ≥K independent experts (Genome) |
| ADOPTED | published as principle; generating outcomes | review + canary pass |
| REINFORCED | convergence **and** efficacy strong | sustained mission-positive evidence |
| WEAKENING | efficacy under-performs / context-limited | sustained mission-negative (non-safety) |
| DEPRECATED | superseded by a fitter gene/allele | a better allele/gene wins |
| RETIRED | contradicted; archived w/ rationale | higher-tier evidence overturns it |
| **PROTECTED** | safety/values, immovable | any safety_flag gene |

Every transition is a **proposal** requiring the §7 gate; PROTECTED genes bypass the down-side entirely.

---

## 3. Fitness Model

Fitness is a **Constitution-aligned**, **per-context**, **uncertainty-bearing** score — with safety
as a hard gate, not a term:

```
if safety != PASS:  fitness = DISQUALIFIED
else:
  fitness(gene, context) =
        w_c · Convergence            # expert universality (Genome)
      + w_e · Efficacy(context)      # mission outcomes (Observatory) — adherence/trust/confidence/transformation
      + w_r · Robustness             # holds across segments/contexts
      − Penalty(mission_misalignment)# engagement-up while transformation/trust-down → penalized
  , reported with a confidence interval (from sample size + attribution certainty)
```
- **Mission metrics only:** long-term behavior retention, trust proxies (retention, low complaint/
  refund/withdrawal), self-efficacy/confidence trend (HSE), durable progress. **Not** workouts, not DAU.
- **Per-context:** a gene/allele may be fit in one context and unfit in another → refine
  **expression/dominance (alleles)**, not a blanket global demotion.
- **Uncertainty-first:** small sample / weak attribution → wide interval → **no consequential action.**
- **Anti-Goodhart:** the fitness *function itself* is versioned and governed — you cannot silently
  change what "good" means. Metrics are audited proxies; the mission is the north star.

---

## 4. Evidence Aggregation

Two ledgers, merged, never conflated:

- **Convergence evidence** (Genome): independent expert count, lineage-independence, evidence tier.
- **Efficacy evidence** (Observatory + HSE + feedback): outcomes **attributed** to the gene via the
  M8/M9 rationale trace (decision → principle IDs → gene IDs).

**Confidence update (Bayesian-style, conservative):** prior from convergence + evidence tier;
posterior updated by accruing outcome evidence with **recency weighting** and **sample gating**.
A Tier-A / conserved gene has a **strong prior** — it takes substantial, replicated contrary
evidence to move it. A Tier-C / single-context gene moves faster.

**Causal honesty (mandatory):** observational outcomes are confounded. The engine **flags
correlation, never asserts causation**; prefers cohort/canary comparisons; stratifies by segment;
and treats attribution as probabilistic. Confounds (seasonality, selection, population shift) are
checked before any transition. This guards the four named failure modes: *attribution error,
confounded efficacy, small-sample noise, metric gaming.*

---

## 5. Promotion Rules

A gene advances only when **all** hold, and a human approves:
1. **Convergence gate** (for CALLED): ≥K independent experts (Genome).
2. **Efficacy gate** (for ADOPTED→REINFORCED): mission-positive outcomes, replicated across
   ≥2 contexts, CI excludes "no effect / harm."
3. **Safety gate:** Safety Sentinel = PASS (safety_flag genes always require Medical Reviewer).
4. **Mission gate:** no engagement-for-transformation trade-off.
5. **Canary:** user-facing adoption is rolled out to a cohort first (M4/M8 pattern) and measured
   before full adoption; instant rollback available.
6. **Human sign-off:** the engine proposes; the Review Board disposes. **No auto-promotion to
   user-facing behavior.**

---

## 6. Retirement Rules

Demote / retire only when, **and** confirmed by review as not an artifact:
1. **Sustained mission under-performance** across contexts (not one segment; not one noisy window), **or**
2. **Contradicted** by higher-tier evidence (Genome or external), **or**
3. **Superseded** by a fitter gene/allele.

Then: `WEAKENING → DEPRECATED → RETIRED`. **RETIRED = archived** with rationale + full provenance,
**never deleted**; capabilities citing it are flagged; the change ships as a versioned release and
is **reversible**.

**Hard exemption:** PROTECTED (Safety/Values) genes are **never** demoted or retired by outcomes.
"This safety check lowers engagement" is *not* a retirement reason — the loop cannot trade safety
for metrics. Safety changes go through amendment + Medical Reviewer, never through fitness.

---

## 7. Governance

| Role | In the loop |
|---|---|
| Researcher / Reviewer | evidence quality, attribution sanity |
| **Medical Reviewer** | mandatory on any safety_flag gene; can veto |
| Coaching Reviewer | mission-alignment of outcomes and framing |
| Data/Evidence steward | confound checks, sample adequacy, metric integrity |
| **Safety Sentinel** | blocks any safety demotion; gate on every transition |
| Chief Architect | approves lifecycle transitions + versioned releases |

**Rules of the loop:**
- The engine is a **proposal system**; nothing user-facing changes without safety clearance + human
  review + canary + versioned release.
- The **fitness function and mission metrics are themselves versioned and reviewed** — no silent
  redefinition of "good."
- **AI may** aggregate, estimate fitness, flag confounds, propose transitions; **AI may never**
  approve a transition, retire a gene, or touch safety. AI proposes, humans dispose.
- **Ethical bounds:** never experiment toward harm; canaries are safety-bounded; **no
  experimentation on users in distress/illness/vulnerable states** beyond the conservative default.
- **Full auditability + reversibility:** every fitness update and transition is logged, attributed,
  and rollback-able like a deploy.

---

## 8. Invariants
- Fitness is measured against the mission (adherence/trust/confidence/transformation) — **never engagement.**
- Safety/Values genes are PROTECTED: strengthen-only, never demoted/retired by outcomes.
- Convergence (expert) and Efficacy (real-world) are distinct axes, merged conservatively.
- Correlation is flagged, causation never asserted; uncertainty gates all consequential action.
- The engine proposes; humans (with a Safety Sentinel) dispose; changes are canaried, versioned, reversible.
- No implementation — architecture only.
