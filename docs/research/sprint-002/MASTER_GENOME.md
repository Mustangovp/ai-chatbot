# SPRINT-002 — MASTER GENOME

The reasoning conserved across the seven expert lineages. A pattern is a **CALLED gene** only if
≥K=3 *independent* lineages reason it, its expression is **bounded** (there exist situations where
it must not fire), and it is **mechanistically grounded** (not stylistic coincidence). 13 genes met
the bar (see [COMPARISON_MATRIX](COMPARISON_MATRIX.md)). Two remain CANDIDATE (2 lineages) and are
listed but **not** part of the called genome.

Gene fields follow the Decision Genome spec (§2): id · name · statement · expression (fires / must-not) ·
alleles · conservation · tier · provenance · maps_to_principle · safety_flag · status.

> **Honesty note on single-lineage domains.** Nutrition (ARG) and Performance Psychology (GRV) each
> contributed **one** lineage in this sprint. Their *domain-specific* rules therefore cannot be
> "called genes" (which require ≥3 independent lineages). Below, the **Nutrition** and **Psychological**
> categories list (a) the universal genes that govern them and (b) **domain invariants** graded by
> underlying evidence, explicitly flagged as *pending additional lineages* — not conserved genes.

---

## Category 1 — Universal reasoning

**DG-U-01 · Leverage-first**
- *Statement:* identify the current highest-leverage factor and spend the scarce budget there before
  anything downstream.
- *Expression:* fires on any plan/plateau with limited time/energy. Must-not: when the limiter is
  genuinely a low-tier detail (rare, expert edge).
- *Alleles:* limiting-factor (GLP) · training priority-stack (HLM) · nutrition hierarchy (ARG).
- *Conservation:* 3 independent lineages · strength high · Tier B · Provenance KC-GLP-002/HLM-002/ARG-001.
- *maps_to_principle:* APX-PHI-030. *safety_flag:* false. *Status:* **CALLED**.

**DG-U-02 · Individualize-and-verify (N-of-1)**
- *Statement:* treat the plan as a hypothesis about *this* person; verify and adjust from their response.
- *Expression:* fires whenever ≥1 individual data point exists. Must-not: no data yet → use population priors.
- *Alleles:* responder-variability (GLP/HLM) · individual movement fit (MCG) · preference/context (ARG) · learner fit (WNK).
- *Conservation:* 5 lineages · strength very high · Tier A/B · Provenance KC-GLP-011/HLM-009/MCG-003/ARG-009/WNK-011.
- *maps_to_principle:* APX-PHI-031. *safety_flag:* false. *Status:* **CALLED**.

**DG-U-13 · Evidence-weighting**
- *Statement:* weight any claim by evidence quality × applicability to this person × effect size — act
  decisively on large, transferable effects; discount trivial or non-transferable ones.
- *Expression:* fires when evaluating a claim/intervention. Must-not: emergency where action can't wait for appraisal.
- *Alleles:* test-don't-guess empiricism (GLP) · applicability-weighting (HLM) · effect-size realism/debunking (ARG).
- *Conservation:* 3 lineages · Tier B · Provenance KC-GLP-009/HLM-008/ARG-004.
- *maps_to_principle:* APX-PHI-032. *safety_flag:* false. *Status:* **CALLED**.

## Category 2 — Common diagnostic patterns

**DG-U-03 · Diagnose-cause-before-acting**
- *Statement:* when progress stalls or a symptom appears, diagnose the *cause* before adding load,
  effort, or intervention.
- *Expression:* fires on any stall/symptom/fault. Must-not: when the cause is already known and verified.
- *Alleles:* recovery/technique/stimulus triage (GLP) · priority-tier triage (HLM) · provocation triage (MCG).
- *Conservation:* 3 lineages · Tier B · Provenance KC-GLP-022/HLM-002/MCG-001.
- *maps_to_principle:* APX-DIA-010. *safety_flag:* false. *Status:* **CALLED**.
- *Shared diagnostic axes across coaches:* current limiter · recoverable/tolerable ceiling · individual
  response data · quality-under-fatigue · red-flag screen (routes out).

## Category 3 — Common safety rules

**DG-U-10 · Safety-is-a-constraint / refer-out** — **safety_flag: true**
- *Statement:* safety is a hard constraint, not a tunable variable. When a load/behavior provokes injury
  or a medical red flag appears, no benefit outranks stopping and routing the person to appropriate care.
- *Expression:* fires on injury-provoking load, neurological/systemic red flags, or clinical
  eating/metabolic signals. Must-not-weaken: this gene may only *support* APX-SAF principles; nothing
  overrides it.
- *Alleles:* injury/neuro red flags (MCG) · eating/metabolic red flags (ARG) · fear-that-signals-real-
  danger (GRV, bounded).
- *Conservation:* 3 lineages · Tier A/B · Provenance KC-MCG-006/010 · ARG-012 · GRV-002(bound).
- *maps_to_principle:* APX-SAF-030 / APX-SAF-031. *Status:* **CALLED (safety)**.
- *Corollary safety invariants (from D3):* remove the provocation before loading; progress within
  tolerance by graded exposure; spare the spine, load the hips; calm before build.

## Category 4 — Common communication rules

**DG-U-11 · Receiver-first communication**
- *Statement:* the measure of any instruction is the understanding/action it produces in the receiver,
  not its completeness in the coach's head; encode for *their* level and language.
- *Expression:* fires on every explanation/cue. Must-not: dumb down past the accuracy an expert receiver wants.
- *Alleles:* reframe/explain-by-mechanism (GLP) · teach-the-hierarchy (ARG) · external cue economy (WNK).
- *Conservation:* 3–4 lineages · Tier B · Provenance KC-WNK-001/GLP-006/ARG(comm).
- *maps_to_principle:* APX-COM-030. *safety_flag:* false. *Status:* **CALLED**.
- *Called sub-rules (WNK-anchored, corroborated):* one cue at a time; external-focus default (internal
  allele for rehab); vivid analogy over mechanical description; re-encode don't repeat.

**DG-U-12 · Build-independence / autonomy-support**
- *Statement:* coach toward the person needing you less — fade feedback as competence grows, support
  autonomy and choice, transfer ownership.
- *Expression:* fires as competence/consistency rises. Must-not: fade too early on unsafe/unstable patterns.
- *Alleles:* fade feedback / constraints-led (WNK) · autonomy & safety (GRV) · habit independence (CLR).
- *Conservation:* 3 lineages · Tier B · Provenance KC-WNK-004/GRV-004/CLR-003.
- *maps_to_principle:* APX-COM-031 / APX-PSY-032. *safety_flag:* false. *Status:* **CALLED**.

## Category 5 — Common progression rules

**DG-U-04 · One-change-at-a-time**
- *Statement:* change a single variable at a time so cause is isolable and the system can adapt/solve.
- *Expression:* fires on any adjustment. Must-not: an urgent safety correction may require an immediate direct change.
- *Alleles:* one training variable (GLP/HLM) · one cue (WNK) · smallest behavior (CLR).
- *Conservation:* 4 lineages · Tier B · Provenance KC-GLP-028/HLM(auto)/WNK-003/CLR-002.
- *maps_to_principle:* APX-STR-030. *safety_flag:* false. *Status:* **CALLED**.

**DG-U-05 · Minimum-effective-dose**
- *Statement:* use the least stimulus/friction that produces the adaptation; dose has a ceiling and a cost.
- *Expression:* fires when setting volume/intensity/ask-size. Must-not: when clearly under the effective floor (add).
- *Alleles:* minimum effective training dose (GLP/HLM) · smallest repeatable action (CLR).
- *Conservation:* 3–4 lineages · Tier A/B · Provenance KC-GLP-018/HLM-012/CLR-002.
- *maps_to_principle:* APX-STR-031. *safety_flag:* false. *Status:* **CALLED**.

**DG-U-06 · Respect-the-ceiling** — **POLYMORPHIC**
- *Statement:* progress up to, but not through, the ceiling that gates adaptation.
- *Expression:* fires on every dosing decision. Must-not: when well under the ceiling (progress freely).
- *Alleles:* recoverable-load ceiling (GLP/HLM, whole-organism) · tissue-tolerance ceiling (MCG, injury) ·
  set-level RIR ceiling (HLM). *Dominance:* tissue-tolerance dominates in symptomatic context; recovery-load otherwise.
- *Conservation:* 3 lineages · Tier A · Provenance KC-GLP-063/HLM-004/MCG-002.
- *maps_to_principle:* APX-REC-030. *safety_flag:* partial (tissue allele supports APX-SAF). *Status:* **CALLED / POLYMORPHIC**.

## Category 6 — Common behavioral rules

**DG-U-07 · Adherence-multiplies**
- *Statement:* consistency of a sustainable action multiplies every other variable; diagnose and fix
  adherence before optimizing details.
- *Expression:* fires when completion/consistency is below target. Must-not: as an excuse to never progress an adherent person.
- *Alleles:* training adherence (HLM) · dietary sustainability (ARG) · habit mechanism — shrink/cue/friction/reinforce (CLR).
- *Conservation:* 3–4 lineages · Tier A/B · Provenance KC-HLM-001/ARG-003/CLR-001…004.
- *maps_to_principle:* APX-PSY-030. *safety_flag:* false. *Status:* **CALLED**.
- *Called sub-mechanism (CLR-anchored):* shrink the ask · make the cue obvious · reduce friction ·
  reinforce immediately · a lapse is data — protect the restart.

**DG-U-08 · Anchor-to-identity/purpose** — **POLYMORPHIC**
- *Statement:* anchor durable motivation to who the person is / what they value, not to a distant number.
- *Expression:* fires for long-horizon motivation & relapse recovery. Must-not: a one-off acute task with no identity stake.
- *Alleles:* goal-value (GLP) · identity/self-image votes (CLR) · purpose/values (GRV).
- *Conservation:* 3 lineages · Tier B · Provenance KC-GLP-020/CLR-001/GRV-009.
- *maps_to_principle:* APX-PSY-031. *safety_flag:* false. *Status:* **CALLED / POLYMORPHIC**.

## Category 7 — Common nutrition rules *(one lineage — domain invariants, not yet genes)*

Governing universal genes here: **DG-U-01** (leverage), **DG-U-07** (adherence), **DG-U-13**
(evidence), **DG-U-02** (individualize), **DG-U-10** (clinical refer-out).

Domain invariants (ARG, graded by evidence; **pending additional nutrition lineages** to be called):
- **NUT-INV-1** Energy balance is the primary lever for mass change. (Tier A)
- **NUT-INV-2** Protein sufficiency first among macros; diminishing returns past sufficiency. (Tier A)
- **NUT-INV-3** Totals dominate timing/frequency; supplements are last and evidence-gated. (Tier A/B)
- **NUT-INV-4** Budget, don't ban; food quality within the macro budget. (Tier B, mutation-status)
- *→ These map to candidate APX-NUT principles but are flagged "single-lineage — corroborate before adoption."*

## Category 8 — Common psychological rules *(one lineage — universal genes + domain invariants)*

Governing universal genes here: **DG-U-09** (below), **DG-U-08** (identity/purpose), **DG-U-07**
(adherence mechanism), **DG-U-12** (autonomy).

**DG-U-09 · Process-over-outcome**
- *Statement:* direct attention and self-review to the controllable process/system rather than the
  uncontrollable outcome or comparison.
- *Expression:* fires under pressure, plateaus, outcome-fixation. Must-not: when outcome data must inform strategy.
- *Alleles:* systems-over-goals (CLR) · control-the-controllables (GRV) · process-by-mechanism (GLP).
- *Conservation:* 3 lineages · Tier B · Provenance KC-GRV-001/CLR-007/GLP(process).
- *maps_to_principle:* APX-PSY-033. *safety_flag:* false. *Status:* **CALLED**.

Domain invariants (GRV, **pending additional psychology lineages**):
- **PSY-INV-1** Regulate state (arousal/self-talk) before instruction or execution. (Tier A/B — also CANDIDATE gene P14)
- **PSY-INV-2** Establish psychological safety before pushing truth/performance. (Tier B)
- **PSY-INV-3** Change the *relationship* with fear rather than eliminate it — bounded by DG-U-10 safety. (Tier B, mutation)

---

## CANDIDATE genes (2 lineages — held, NOT in the called genome)

- **P14 · Regulate-before-instruct** (GRV strong, WNK partial). Promote when a third lineage independently
  sequences state-regulation ahead of instruction.
- **P15 · Lapse-is-data / protect-the-restart** (CLR strong, GRV partial). *Note:* already live as an APEX
  coaching rule ("a lapse is not a relapse"), but not yet a *called* cross-coach gene — corroborate before
  elevating from coaching-rule to genome-principle.

---

## Genome summary

| Category | Called genes |
|---|---|
| Universal reasoning | DG-U-01, DG-U-02, DG-U-13 |
| Diagnostic | DG-U-03 |
| Safety | DG-U-10 (safety_flag) |
| Communication | DG-U-11, DG-U-12 |
| Progression | DG-U-04, DG-U-05, DG-U-06 (polymorphic) |
| Behavioral | DG-U-07, DG-U-08 (polymorphic) |
| Nutrition | governed by universals; 4 domain invariants pending lineages |
| Psychological | DG-U-09 (+ DG-U-08); 3 domain invariants pending lineages |

**13 CALLED genes · 3 polymorphic · 1 safety-flagged · 2 candidates held · mutations preserved.**
No forced agreement; disagreement expressed as alleles or held candidates, never averaged away.
