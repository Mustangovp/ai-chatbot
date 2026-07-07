# SPRINT-002 — Cross-Coach Comparison Matrix

Every reconstructed reasoning pattern compared against every coach. Classification rule:
**identical reasoning structure → candidate gene** · **partially different → allele** ·
**unique to one lineage → mutation**. Convergence is judged on *decision structure*
(inputs read + why), **not vocabulary**, and down-weighted for shared lineage (independence test).

Legend per cell: ● expresses the pattern natively · ◐ expresses a context-valid **allele** ·
○ compatible but not a primary driver · — not in this coach's domain.

Codes: GLP Galpin · HLM Helms · MCG McGill · ARG Aragon · CLR Clear · GRV Gervais · WNK Winkelman.

---

## 1. Convergence matrix (patterns × coaches)

| # | Reasoning pattern (APEX-neutral) | GLP | HLM | MCG | ARG | CLR | GRV | WNK | Independent experts | Call |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| P1 | Solve the highest-leverage factor first | ● | ● | ○ | ● | ○ | ○ | ○ | 3 (GLP,HLM,ARG) | **CALLED** |
| P2 | Adherence/consistency multiplies everything | ○ | ● | ○ | ● | ● | ◐ | — | 3–4 | **CALLED** |
| P3 | Individualize & verify on the person (N-of-1) | ● | ● | ● | ● | ○ | ○ | ● | 5 | **CALLED** |
| P4 | Respect the ceiling (recovery / tissue tolerance) | ● | ● | ● | ○ | — | — | — | 3 | **CALLED / POLYMORPHIC** |
| P5 | Diagnose the cause before adding load/effort | ● | ● | ● | ○ | ○ | ○ | ○ | 3 | **CALLED** |
| P6 | Minimum effective dose / smallest sufficient change | ● | ● | — | ◐ | ● | — | ◐ | 3–4 | **CALLED** |
| P7 | Change one variable at a time | ● | ● | — | — | ● | — | ● | 4 | **CALLED** |
| P8 | Safety is a hard constraint; route medical out | ○ | ○ | ● | ● | — | ◐ | ○ | 3 | **CALLED (safety_flag)** |
| P9 | Anchor drive to identity / purpose / why | ● | ○ | — | ○ | ● | ● | — | 3 | **CALLED / POLYMORPHIC** |
| P10 | Process/systems over outcome/goals | ● | ○ | — | ○ | ● | ● | ○ | 3 | **CALLED** |
| P11 | Communicate for the receiver's action | ● | ○ | ○ | ● | ○ | ● | ● | 3–4 | **CALLED** |
| P12 | Weight evidence by quality × applicability × effect size | ● | ● | ○ | ● | ○ | — | ○ | 3 | **CALLED** |
| P13 | Build learner independence / autonomy support | ○ | ○ | — | ○ | ● | ● | ● | 3 | **CALLED** |
| P14 | Regulate state before instruction/execution | ○ | ○ | ○ | — | ○ | ● | ◐ | 2 | **CANDIDATE** |
| P15 | A lapse is data, not a verdict; protect the restart | ○ | ○ | ○ | ○ | ● | ◐ | — | 2 | **CANDIDATE** |

## 2. Alleles (shared gene, context-selected variants)

| Gene | Allele A | Allele B | Allele C | Dominance (context) |
|---|---|---|---|---|
| P4 Ceiling | *recoverable load* (GLP/HLM, whole-organism) | *tissue tolerance* (MCG, injured/at-risk tissue) | *set-level RIR* (HLM, per-set) | tissue-tolerance dominates in symptomatic/injury context; recovery-load otherwise |
| P6/P7 Dose/Change | *stimulus dose* (GLP/HLM) | *behavioral friction dose* (CLR) | *cue count* (WNK) | select by whether limiter is physiology, behavior, or skill |
| P9 Anchor | *goal-value* (GLP) | *identity/self-image* (CLR) | *purpose/values* (GRV) | identity/purpose for long-term drive; goal-value for a defined training block |
| P11 Receiver-comm | *reframe/explain-why* (GLP) | *teach the hierarchy* (ARG) | *external cue economy* (WNK) | external-cue for motor skill; explanation for conceptual buy-in |
| P12 Attentional focus | *external* (WNK, default) | *brief internal* (MCG rehab/activation) | — | internal only for rehab activation; external otherwise |
| P8 Refer-out | *injury/neuro* (MCG) | *eating/metabolic* (ARG) | *acute danger* (GRV bound) | same gene, red-flag set differs by domain |

## 3. Mutations (single-lineage; stay profile-local unless independently re-derived)

| Mutation | Lineage | Note / merge-watch |
|---|---|---|
| Autoregulation by proximity-to-failure | HLM | watch for independent set-level effort-titration elsewhere |
| Proximal stiffness → distal mobility | MCG | motor-control specific; possible D7 convergence |
| 24-hour cumulative load | MCG | partial overlap with GLP total-stress → candidate merge |
| Budget-not-ban (no forbidden foods) | ARG | partial overlap with CLR "design the default" |
| Environment/friction over willpower | CLR | possible merge with ARG satiety-design → "design the default" gene |
| Immediate reinforcement of delayed-reward behavior | CLR | behavior-specific |
| Change the *relationship* with fear | GRV | bounded by P8 safety (fear signaling real danger is heeded) |
| External-over-internal focus | WNK | polymorphic (internal allele exists) → not universal |
| Constraint-led (task replaces cue) | WNK | possible merge with CLR environment design |

## 4. Reading of the matrix

- **13 patterns reach CALLED** (≥3 independent lineages, bounded, mechanistically grounded). These
  become the Master Genome.
- **2 patterns are CANDIDATE** (2 lineages) — held for a future expert to confirm or drop; not adopted
  into the genome yet (P14 regulate-first, P15 lapse-handling — though P15 already exists as an APEX
  *coaching* rule, it is not yet a *called gene*).
- **Convergence is strongest** on: individualize-and-verify (P3, 5 lineages), one-change/min-dose
  (P6/P7, 4), adherence (P2, 3–4), receiver-communication (P11, 3–4).
- **No forced agreement:** genuine domain-specific reasoning (autoregulation, external focus, fear
  relationship) is preserved as mutations/alleles, never averaged into the genome.
- **Independence check:** the strongest convergences arise across *unrelated* lineages (physiology ∥
  nutrition ∥ motor learning ∥ behavior), which is the signal that a gene is real reasoning, not a
  shared-teacher artifact.
