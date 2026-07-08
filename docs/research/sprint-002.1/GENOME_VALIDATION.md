# SPRINT-002.1 — Genome Validation

Each called gene from the [MASTER_GENOME](../sprint-002/MASTER_GENOME.md) is put to the acceptance
test: **no gene survives without explicit evidence from independent experts.** For every gene:
supporting experts · per-expert reasoning evidence (cited to validation scenarios) · expression
boundaries · exceptions · counter-examples · confidence · why-a-gene · why-not-coincidence.

Cross-cutting result feeding this section: the packs surfaced two systemic findings that *sharpen*
(not weaken) the genome — a **safety-interrupt gap** (domain models under-enforce the safety gene at
their boundaries) and an **input-vs-response gating** flaw (the recovery-ceiling gene fires on inputs,
not response trend). Both are recorded as gene **boundary updates**, not gene rejections.

Legend: **✓ SURVIVES** · **⚠ SURVIVES-with-boundary-update** · **↓ DOWNGRADE** · **✗ REJECT**.

---

## DG-U-01 · Leverage-first ✓
- **Supporting experts (independent):** GLP, HLM, ARG (+ implicit in D5/D6/D7 sequencing).
- **Evidence:** GLP limiting-factor (V-GLP-01,12,41) · HLM priority-stack (V-HLM-16,42) · ARG hierarchy
  (V-ARG-04,05,13).
- **Boundaries:** fires on any resource-limited plan/plateau. **Exception:** an elite whose only margin
  is a low tier. **Counter-example:** V-HLM-27 (details matter for an optimized elite).
- **Confidence:** 0.88. **Why a gene:** three unrelated domains independently order effort by leverage.
  **Not coincidence:** the *axes* differ (physiology / training stress / nutrition) but the *structure*
  (solve the binding constraint first) is identical — convergent, not inherited.

## DG-U-02 · Individualize-and-verify (N-of-1) ✓ (strongest gene)
- **Supporting experts:** GLP, HLM, MCG, ARG, WNK (5 lineages).
- **Evidence:** GLP responder variability (V-GLP-30) · HLM individual response (V-HLM-30) · MCG no
  universal best exercise (V-MCG-03,30,40) · ARG preference/response (V-ARG-30) · WNK learner-fit
  (V-WNK-05,12,30).
- **Boundaries:** fires once ≥1 data point exists. **Exception:** no data → population priors
  (V-GLP-11). **Counter-example:** a true novice with no history.
- **Confidence:** 0.90. **Why a gene:** five independent domains reason "the individual is the unit."
  **Not coincidence:** appears in a physiologist, a programmer, a spine mechanic, a nutritionist, and a
  motor-learning coach — maximal lineage spread; a shared-teacher artifact is implausible.

## DG-U-03 · Diagnose-cause-before-acting ✓
- **Supporting experts:** GLP, HLM, MCG.
- **Evidence:** GLP diagnose stall (V-GLP-02,03,04) · HLM tier-triage (V-HLM-16) · MCG provocation
  triage (V-MCG-01,21,43).
- **Boundaries:** fires on any stall/symptom/fault. **Exception:** cause already known & verified.
  **Counter-example:** V-GLP-11 (obvious beginner default, no diagnosis needed).
- **Confidence:** 0.85. **Why a gene:** three domains refuse to prescribe before diagnosing.
  **Not coincidence:** the diagnostic *indices* differ (recovery/technique/stimulus vs priority-tier vs
  provocation) — same rule, domain-specific probes.

## DG-U-04 · One-change-at-a-time ✓
- **Supporting experts:** GLP, HLM, WNK, CLR (4).
- **Evidence:** GLP one-variable (V-GLP-19) · HLM stability to progress (V-HLM-24) · WNK one cue
  (V-WNK-02,22) · CLR smallest action (V-CLR-06,35).
- **Boundaries:** any adjustment. **Exception:** urgent safety correction (V-WNK-09,44). **Counter:**
  a safety fault needing multiple immediate fixes.
- **Confidence:** 0.85. **Not coincidence:** isolate-the-variable logic recurs in training, cueing, and
  habit design independently — a control-of-confounds principle, not a stylistic tic.

## DG-U-05 · Minimum-effective-dose ✓
- **Supporting experts:** GLP, HLM, CLR.
- **Evidence:** GLP dose ceiling (V-GLP-13,36) · HLM MED volume (V-HLM-25) · CLR smallest repeatable
  (V-CLR-01,26,48).
- **Boundaries:** setting volume/friction/ask. **Exception:** under the effective floor → add
  (V-GLP-36, V-HLM-06 reversed). **Counter:** a novice who needs *more* structure, not less.
- **Confidence:** 0.83. **Not coincidence:** dose-with-a-cost logic appears in stimulus dosing and in
  behavioral friction independently.

## DG-U-06 · Respect-the-ceiling ⚠ (SURVIVES with boundary update)
- **Supporting experts:** GLP, HLM, MCG (polymorphic).
- **Evidence:** GLP recovery gate (V-GLP-03,14,43) · HLM recoverable ceiling / RIR (V-HLM-03,13,18) ·
  MCG tissue tolerance (V-MCG-04,14,26).
- **Boundary update (from validation):** the gene currently fires on **recovery *inputs*** (e.g., "slept
  4h → gate") rather than the **response trend**. Galpin CC-5 (V-GLP-23) and Helms CC-4 (V-HLM-22) both
  fail here: an athlete still *responding* should be gated on declining performance, not on a bad-looking
  input. **Update:** gate on response trend, using inputs as priors, not triggers.
- **Exception:** well under the ceiling → progress freely. **Counter:** V-GLP-27 (headroom → add).
- **Confidence:** 0.80 (down from 0.85 pending the boundary fix). **Why still a gene:** the *existence*
  of a ceiling is unanimous; only its *trigger* needs refinement. **Not coincidence:** recovery-limited
  and tissue-limited ceilings are mechanistically distinct yet structurally identical → genuine polymorphism.

## DG-U-07 · Adherence-multiplies ✓
- **Supporting experts:** HLM, ARG, CLR (mechanism).
- **Evidence:** HLM fix consistency first (V-HLM-01,10,39) · ARG sustainability (V-ARG-07,14,21,48) ·
  CLR the *how* — shrink/cue/friction/reinforce (V-CLR-01,03,05,08).
- **Boundaries:** fires when completion < target. **Exception:** not a licence to never progress an
  adherent person (V-HLM-11). **Counter:** an already-consistent athlete → move to dose/physiology.
- **Confidence:** 0.87. **Not coincidence:** a programmer, a nutritionist, and a behavioral scientist
  each make consistency the master multiplier — and CLR supplies the mechanism the other two only name.

## DG-U-08 · Anchor-to-identity/purpose ✓ (polymorphic)
- **Supporting experts:** GLP (goal-value), CLR (identity), GRV (purpose).
- **Evidence:** GLP anchor to why (V-GLP-20 family) · CLR identity votes (V-CLR-04,14,21,43) · GRV
  purpose (V-GRV-05,14,35,46).
- **Boundaries:** long-horizon motivation & relapse. **Exception:** a one-off acute task with no identity
  stake. **Counter:** V-CLR-40 (identity needs an action to be more than talk).
- **Confidence:** 0.80. **Not coincidence:** three lineages independently anchor durable drive to
  self-concept; the *flavor* differs (goal / identity / purpose) → three context-selected alleles.

## DG-U-09 · Process-over-outcome ✓
- **Supporting experts:** GRV, CLR, GLP.
- **Evidence:** GRV control-the-controllables (V-GRV-02,09,12,29,31) · CLR systems-over-goals
  (V-CLR-12,21) · GLP process-by-mechanism (expectation setting).
- **Boundaries:** pressure, plateaus, outcome-fixation. **Exception:** when outcome data must inform
  strategy (V-GRV competition-strategy edge). **Counter:** a decision that genuinely hinges on the result.
- **Confidence:** 0.82. **Not coincidence:** psychology and behavior science reach the same attentional
  rule from different starting points.

## DG-U-10 · Safety-is-a-constraint / refer-out ⚠ (SURVIVES; most important finding)
- **Supporting experts:** MCG, ARG, GRV (bounded) — and, by *omission*, every other lineage.
- **Evidence FOR the gene:** MCG red-flag routing is flawless (V-MCG-02,07,18,38,45 → recall **1.00**);
  MCG refuses to load through pain (V-MCG-06,44).
- **The systemic finding:** the gene is **under-enforced at other domains' boundaries.** Helms
  (V-HLM-28,48), Clear (V-CLR-11), Gervais (V-GRV-07,27), and Winkelman (V-WNK-25) each **failed** to
  interrupt for a safety/medical signal — Gervais CC-4 (dismissing exertional chest pain as anxiety) is
  the single most dangerous failure in the sprint. **This does not reject the gene — it proves the gene
  must be SUPREME across all domains**, exactly as its `safety_flag` demands.
- **The asymmetry:** referral sensitivity is **polymorphic and uneven** — MCG *over*-refers (safe
  direction, recall 1.00), ARG *under*-refers subtle eating-disorder signals (dangerous direction, recall
  **0.60**, V-ARG-08,25,38). The refer-out threshold must be domain-tuned, biased toward over-referral.
- **Boundary update:** promote DG-U-10 to a **top-level interrupt** that pre-empts every other domain's
  reasoning; require the ARG/CLR/GRV/WNK models to consult it *before* their own decision path.
- **Confidence:** 0.90 (in the gene) / 0.6 (in current cross-domain enforcement). **Why a gene / not
  coincidence:** injury, nutrition, and psychology lineages independently subordinate benefit to a hard
  safety stop; the *content* of the red flags differs by domain, the *supremacy rule* is identical.

## DG-U-11 · Receiver-first communication ✓
- **Supporting experts:** WNK, GLP, ARG.
- **Evidence:** WNK coach-for-their-action (V-WNK-01,03,11,20) · GLP reframe/explain (V-GLP-01,06) · ARG
  teach-the-hierarchy (V-ARG-04,10,32).
- **Boundaries:** every explanation/cue. **Exception:** an expert who wants the full model (V-WNK-05,35).
  **Counter:** dumbing down past needed accuracy.
- **Confidence:** 0.83. **Not coincidence:** a motor-learning coach, a physiologist, and a nutritionist
  each judge a message by the receiver's resulting action, not its completeness.

## DG-U-12 · Build-independence / autonomy-support ✓
- **Supporting experts:** WNK, GRV, CLR.
- **Evidence:** WNK fade feedback / constraints (V-WNK-04,14,19,40,45,49) · GRV autonomy & safety
  (V-GRV-06,20,28) · CLR habit independence (V-CLR-16,49).
- **Boundaries:** as competence/consistency rises. **Exception:** unsafe/unstable pattern → keep feedback
  dense (V-WNK-42). **Counter:** an early novice.
- **Confidence:** 0.82. **Not coincidence:** three domains independently aim to make the coach needed less.

## DG-U-13 · Evidence-weighting ✓
- **Supporting experts:** HLM, ARG, GLP.
- **Evidence:** HLM applicability > tier (V-HLM-09,37) · ARG effect-size realism / debunking
  (V-ARG-02,05,20,29,34,43,47) · GLP test-don't-guess (V-GLP-18).
- **Boundaries:** evaluating any claim. **Exception:** emergency where action can't wait. **Counter:** a
  large, well-supported, transferable effect → act decisively.
- **Confidence:** 0.83. **Not coincidence:** appraise-by-quality-×-applicability-×-magnitude recurs across
  three empirical lineages.

---

## Allele validation (why experts disagree · context · when each is superior)

- **DG-U-06 ceiling — recovery-load vs tissue-tolerance vs set-RIR.** *Why disagree:* different binding
  constraints (systemic recovery vs local tissue vs daily readiness). *When each superior:* tissue-tolerance
  dominates in a symptomatic/injured athlete (MCG); recovery-load for a healthy trainee (GLP/HLM); set-RIR
  for in-session titration. Validation: the tissue allele is *necessary* (McGill pack) and the recovery
  allele's trigger needs the response-trend fix.
- **DG-U-08 anchor — goal-value vs identity vs purpose.** *Why disagree:* time-horizon and self-concept
  depth. *When superior:* identity/purpose for long-term drive and relapse (CLR/GRV); goal-value for a
  defined training block (GLP). All three validated within their lane.
- **DG-U-11 focus (comm) — external vs internal (rehab).** *Why disagree:* motor-learning default vs
  rehab activation need. *When superior:* external for skill acquisition/execution (default); brief
  internal for rehab/activation (V-WNK-06) and some expert proprioception (V-WNK-47). Validation confirms
  the internal allele is under-fired → **the allele is real and required**, not a rejected variant.
- **DG-U-10 refer-out — injury vs eating/metabolic vs acute-danger red-flag sets.** *Why disagree:* the
  red flags are domain-specific. *When superior:* each domain owns its red-flag list, but all defer to the
  supreme stop. Validation exposed the **threshold asymmetry** (MCG over- vs ARG under-referral).

## Mutation validation (why local · why not universal)

- **Autoregulation by proximity-to-failure (HLM).** *Local:* requires an interoceptive RIR skill and a
  resistance-training context; no other lineage independently reasons set-level effort titration. *Not
  universal:* novices mis-rate RIR (V-HLM-08); peaking uses absolute load. Remains a mutation until a
  second lineage converges.
- **Proximal-stiffness → distal-mobility (MCG).** *Local:* motor-control/spine-specific. *Not universal:*
  no independent derivation elsewhere; over-bracing can harm tasks needing spinal mobility.
- **Budget-not-ban (ARG).** *Local:* nutrition framing. *Not universal:* partial overlap with CLR
  environment design, but not independently derived as the same rule.
- **Change-the-relationship-with-fear (GRV).** *Local:* psychology-specific; **bounded hard by DG-U-10** —
  validation CC-1/CC-4 show why: fear that encodes real danger must be heeded, not coached through. Stays
  local *and* explicitly safety-subordinated.
- **External-focus (WNK).** Reclassified: **polymorphic gene component**, not a free-standing mutation —
  it is the default allele of DG-U-11's focus dimension, with a validated internal allele.
- **Constraint-led (WNK) / Environment-design (CLR).** Both propose "design the context over instruct/
  exhort." Validation supports a **candidate merge** into a future "design-the-default" gene — but with only
  loose independence today, they remain mutations pending a cleaner independence test.

---

## Genome-validation verdict

- **11 of 13 genes SURVIVE outright** with independent multi-expert evidence.
- **2 SURVIVE with boundary updates** (DG-U-06 response-trend trigger; DG-U-10 promoted to a supreme
  top-level interrupt with domain-tuned, over-referral-biased thresholds).
- **0 genes rejected.** No gene was found to be a coincidence artifact; the strongest (DG-U-02) spans five
  unrelated lineages.
- **Systemic defect (not a gene flaw):** every non-safety domain under-enforces DG-U-10 at its boundary —
  the validation's most important actionable finding, and precisely why the safety gene carries `safety_flag`.
