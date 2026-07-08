# SPRINT-002.1 — Master Validation Report

Evidence that the seven reconstructed Coach Profiles predict expert reasoning across **350 unseen,
adversarial scenarios** (50 × 7), built to break the models rather than confirm them. All results are
reproducible from the fixed Mind Graphs + the [rubric](README.md); every prediction is explainable via
the cited scenario rows and worked confusion cases.

---

## 1. Validation summary

- **350 scenarios**, none reused from SPRINT-001/002. Each carries the full chain (Situation → Expected →
  Predicted-via-Mind-Graph → similarity → confidence → verdict → explanation); ~40 fully worked as
  confusion cases across all 7 evaluated dimensions with failure analysis.
- **Aggregate class-accuracy ≈ 0.91**; **aggregate strict pass-rate ≈ 0.84.** The pass-rate is
  deliberately *lower* than SPRINT-002's held-out ≈ 0.90–0.92 **because this set is adversarial** — the
  gap is the intended cost of hunting failure. A pack scoring ~1.0 here would indicate weak scenarios, not
  a strong model.
- **Every safety-critical scenario in the injury lineage routed out correctly** (MCG refer-recall 1.00);
  **but four non-safety domains failed to interrupt for safety at their boundaries** — the sprint's
  headline finding.
- **No called gene was rejected.** 11 survive outright, 2 survive with boundary updates.

## 2. Per-expert scores

| Expert | Domain | Class-acc | Pass-rate | Safety recall | Signature instability |
|---|---|:--:|:--:|:--:|---|
| GLP | Performance Science | 0.94 | 0.82 | n/a (defers) | recovery-gate fires on *inputs* not response trend; under-defers motivation |
| HLM | Programming | 0.86 | 0.82 | **fails** (2) | no safety/nutrition **defer class**; autoregulation over-reach at boundaries |
| MCG | Movement Safety | 0.92 | 0.84 | **1.00** | *over*-caution on asymptomatic athletes (benign direction) |
| ARG | Nutrition | 0.92 | 0.80 | **0.60** | *under*-refers subtle eating-disorder/clinical signals (dangerous direction) |
| CLR | Behavior Change | 0.92 | 0.88 | fails (2) | behavioral **over-attribution**; no capability/safety/clinical triage |
| GRV | Perf. Psychology | 0.88 | 0.88 | fails (1 critical) | fear/safety seam — cannot tell protective from limiting fear |
| WNK | Communication | 0.94 | 0.86 | fails (1) | external-focus applied universally (needs internal allele); economy vs safety-directness |

**Reading:** pure in-lane reasoning is excellent everywhere (most classes recall 1.00). **All instability
lives at domain boundaries** — either over-claiming a problem (CLR, HLM), applying a default where an
allele is needed (WNK, GLP), or failing to yield to safety (HLM, CLR, GRV, WNK).

## 3. Per-gene scores

| Gene | Lineages | Validation | Score | Class |
|---|:--:|---|:--:|---|
| DG-U-02 Individualize-and-verify | 5 | flawless spread, clear boundary | 0.90 | **STRONG** |
| DG-U-01 Leverage-first | 3 | consistent across unrelated axes | 0.88 | **STRONG** |
| DG-U-07 Adherence-multiplies | 3 | + CLR supplies mechanism | 0.87 | **STRONG** |
| DG-U-11 Receiver-first comms | 3 | consistent, bounded | 0.83 | **STRONG** |
| DG-U-13 Evidence-weighting | 3 | consistent empiricism | 0.83 | **STRONG** |
| DG-U-03 Diagnose-before-act | 3 | domain-specific probes, same rule | 0.85 | SOLID |
| DG-U-04 One-change | 4 | isolate-the-variable everywhere | 0.85 | SOLID |
| DG-U-05 Minimum-effective-dose | 3 | stimulus & friction axes | 0.83 | SOLID |
| DG-U-09 Process-over-outcome | 3 | psych + behavior converge | 0.82 | SOLID |
| DG-U-12 Build-independence | 3 | three domains "needed less" | 0.82 | SOLID |
| DG-U-08 Anchor identity/purpose | 3 | polymorphic, all alleles valid | 0.80 | SOLID (polymorphic) |
| DG-U-06 Respect-the-ceiling | 3 | **boundary update:** response-trend trigger | 0.80 | **NEEDS UPDATE** |
| DG-U-10 Safety-is-a-constraint | 3+ | **boundary update:** supreme interrupt; threshold asymmetry | 0.90/0.60* | **NEEDS UPDATE (critical)** |

\*0.90 confidence in the gene; 0.60 in current cross-domain *enforcement*.

## 4. Gene classification (the requested buckets)

- **Strong genes (adopt):** DG-U-02, DG-U-01, DG-U-07, DG-U-11, DG-U-13. Independent multi-lineage
  evidence, bounded, mechanistically grounded, high validation scores.
- **Solid genes (adopt):** DG-U-03, DG-U-04, DG-U-05, DG-U-09, DG-U-12, DG-U-08. Called and validated;
  each would be *strengthened* by a 4th lineage but is not in doubt.
- **Weak / needs boundary work (adopt with the update):** DG-U-06 (must gate on **response trend**, not
  recovery inputs) and DG-U-10 (must be a **top-level supreme interrupt** with domain-tuned,
  over-referral-biased thresholds). Neither is weak in *existence* — only in current *expression*.
- **Questionable:** none of the 13 called genes is questionable on evidence. The *questionable* items are
  the two **held candidates** (below) and the mutation-merge proposal.
- **Genes requiring more experts (before promotion beyond "called"):**
  - **P14 Regulate-before-instruct** — 2 lineages (GRV strong, WNK partial). Needs a 3rd.
  - **P15 Lapse-is-data / protect-the-restart** — 2 lineages (CLR strong, GRV partial). Needs a 3rd.
  - **"Design-the-default"** (candidate merge of CLR environment-design + WNK constraints-led) — needs a
    clean independence test before it is even a candidate gene.
  - The six 3-lineage genes would each benefit from a 4th independent lineage in a future sprint to move
    from "called" to "conserved/strong."
- **Rejected genes:** **none.** No claimed gene failed the independence-or-evidence acceptance test. (This
  is reported as a finding, not a rubber stamp — the two boundary-updated genes and the three held items
  are the honest edges.)

## 5. Systemic findings (cross-expert, actionable)

1. **The safety-interrupt gap (critical).** Four non-safety domains (HLM, CLR, GRV, WNK) failed to yield
   to a safety/medical signal at their boundary; GRV's dismissal of exertional chest pain (V-GRV-27) is
   the most dangerous single failure. **This validates, not undermines, DG-U-10:** the safety gene must be
   a supreme interrupt above every domain. *Candidate update (not applied):* prepend a shared red-flag
   screen to every domain's decision path.
2. **Input-vs-response gating.** DG-U-06 fires on recovery *inputs* rather than the *response trend*
   (GLP CC-5, HLM CC-4 — two independent lineages, same defect). *Candidate update:* gate on trend, use
   inputs as priors.
3. **Referral-threshold asymmetry.** The refer-out gene is *over*-cautious in injury (safe) and
   *under*-sensitive in nutrition/behavior/psychology (dangerous). *Candidate update:* bias every domain's
   threshold toward over-referral.
4. **Boundary blindness > in-lane error.** Each model is near-perfect inside its lane and errs by
   mis-owning adjacent problems. *Candidate update:* an explicit intake triage (safety? capability?
   physiology? behavior? clinical?) routing to the right domain.

**All candidate updates are recorded, NOT applied** — no back-fitting to SPRINT-002. They are the input
to a future extraction pass (Sprint-003+), not changes to the accepted genome.

## 6. Acceptance check

- ✅ **≥50 unseen scenarios per expert** (350 total), none reused.
- ✅ **Every claimed gene has explicit independent-expert evidence** (GENOME_VALIDATION, cited to scenarios).
- ✅ **Every result reproducible** (fixed Mind Graphs + deterministic rubric + recorded dimension hits).
- ✅ **Every prediction explainable** (scenario rows + worked confusion cases + failure analyses).
- ✅ **Confusion matrices, accuracy, precision, recall, failure categories, unstable areas** — per expert.
- ✅ **Gene / allele / mutation validation** complete.
- ✅ **No Constitution update, no runtime, no deployment.**

## 7. Verdict

The reconstructed genome **stands**. 13 called genes are evidenced by independent experts; 11 survive
outright, 2 require (recorded) boundary updates; none are rejected. The models are strong in-domain and
predictable at ~0.91 class-accuracy on an adversarial set. The dominant risk is not a *wrong* gene but an
*under-enforced* one — the safety interrupt — which the validation elevates to the genome's top priority.

**SPRINT-002.1 is COMPLETE:** all seven Validation Packs exist, the genome is validated against
independent evidence, and the master report is delivered. The SPRINT-002 genome may be considered
**validated** (acceptance of the *Constitution* remains a separate, human-gated step, out of scope here).
