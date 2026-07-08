# SPRINT-002.1 — Master Coach Validation

**Type:** Knowledge engineering only. No runtime, no Brain, no Coaching, no Human State, no
Recommendation, no deployment, no feature flags, no Constitution update. This sprint produces
**evidence**, not documentation: it tests whether each reconstructed Coach Profile (SPRINT-002)
predicts how that expert's school would reason across **unseen** situations, and it deliberately
tries to **break** each model.

SPRINT-002's genome is **not accepted** until this validation stands.

---

## 0. What "validation" means here (honesty contract)

- We do **not** measure the real person. We measure the **faithfulness of the reconstruction**:
  applied blind to a new situation, does the extracted Mind Graph reach the same *reasoning
  direction* the school is on public record reasoning toward?
- "Expected reasoning" is the analyst's best faithful reconstruction of the school's decision
  structure for that situation, fixed **before** running the Mind Graph (no back-fitting).
- We compare **reasoning, not wording or style** (per the sprint rule). Similarity is scored on the
  seven evaluated dimensions below, never on phrasing.
- We **search for failure.** A pack with no Partials/Fails is treated as a *defective* pack (the
  scenarios weren't hard enough), not a success. Every pack includes confusion cases built to break it.

## 1. The seven evaluated dimensions (per scenario)

Every scenario is scored on whether Predicted matches Expected across:

1. **Diagnostic sequence** — what is assessed, and in what order.
2. **Priority ordering** — which factor is solved first.
3. **Risk assessment** — what danger is flagged (esp. safety/medical).
4. **Trade-offs** — what is knowingly sacrificed for what.
5. **Constraint handling** — how hard constraints (time, injury, equipment, medical) are treated.
6. **Decision path** — the actual decision reached.
7. **Communication intent** — what the message is *for* (not how it's worded).

## 2. Verdict rubric (deterministic → reproducible)

- **Pass (✓)** — Predicted matches Expected on **decision path + priority ordering + risk**, and ≥5/7
  dimensions overall.
- **Partial (◐)** — matches decision path **or** priority but misses one decisive dimension (a
  trade-off, a constraint, a communication intent), 3–4/7 dimensions.
- **Fail (✗)** — wrong decision path, **or** wrong priority order, **or** a missed safety/medical
  risk (a missed safety risk is an automatic Fail regardless of other dimensions).

Because the Mind Graph and this rubric are explicit, the same scenario scored by the same procedure
yields the same verdict → **reproducible**. Each scenario records its dimension hits so the score can
be re-derived.

## 3. Decision-class taxonomy (per expert) → confusion matrix

Each expert has a small set of mutually-exclusive **decision classes** (its Decision Graph outputs).
Each scenario has one Expected class and one Predicted class; the **confusion matrix** is
Predicted (rows) × Expected (cols) over the 50 scenarios. From it: **accuracy** (diagonal / total),
and per-class **precision** (diagonal / predicted-row-sum) and **recall** (diagonal / expected-col-sum).

## 4. Scenario rules

- **≥50 unseen scenarios per expert**, none reused from SPRINT-001/002 validation sets.
- Each carries the full chain: *Situation → Expected reasoning → Predicted reasoning (via the Mind
  Graph) → similarity → confidence → Pass/Partial/Fail → explanation.* Compact rows carry this in
  columns; **adversarial/confusion cases are fully worked** across all 7 dimensions with failure analysis.
- **Confusion cases** (built to break): conflicting signals such as *good sleep + high stress*,
  *pain + high motivation*, *fat loss + muscle gain*, *travel + competition*, *older athlete +
  excellent recovery*, plus domain-specific traps.

## 5. Failure protocol

Every Partial/Fail produces a **Failure Analysis**: *why the prediction failed · the missing pattern ·
the wrong assumption · a candidate update* (to the Mind Graph, an allele, or a boundary). Candidate
updates are recorded, **not** applied to SPRINT-002 (no back-fitting; changes are proposals for a
future extraction pass).

## 6. Index

- Per-expert packs: [D1](pack-1-galpin.md) · [D2](pack-2-helms.md) · [D3](pack-3-mcgill.md) ·
  [D4](pack-4-aragon.md) · [D5](pack-5-clear.md) · [D6](pack-6-gervais.md) · [D7](pack-7-winkelman.md)
- [GENOME_VALIDATION.md](GENOME_VALIDATION.md) — each called gene: supporting experts, per-expert
  reasoning evidence, expression boundaries, exceptions, counter-examples, confidence, why-a-gene,
  why-not-coincidence. Plus allele and mutation validation.
- [MASTER_REPORT.md](MASTER_REPORT.md) — validation summary, per-expert & per-gene scores, and the
  strong / weak / questionable / needs-more-experts / rejected gene classification.

**Acceptance:** no claimed gene survives without explicit independent-expert evidence; every result is
reproducible from the stated rubric; every prediction is explainable. The sprint is OPEN until all
seven packs + genome validation + master report exist. Committed once as `SPRINT-002.1 Master Coach
Validation`.
