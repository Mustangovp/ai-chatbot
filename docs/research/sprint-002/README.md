# SPRINT-002 — Master Coach Genome Generation

**Type:** Knowledge engineering only. No runtime, no Brain, no Coaching, no Human State,
no Recommendation, no deployment, no feature flags, no production change. This sprint
produces *reconstructed reasoning* and its synthesis into a candidate genome.

**Governing rule (from M11):** extract **WHY**, not WHAT. We do not copy coaches — we
reconstruct how elite experts *reason*, then express every pattern in APEX-neutral language.

---

## 0. Copyright & imitation guardrail (binding on every file in this sprint)

- **No quotes.** Nothing is reproduced from any book, video, article, or post.
- **No copyrighted wording.** Every sentence is original APEX phrasing.
- **No branded systems.** Trademarked program names, proprietary method names, and
  signature acronyms are *not* reproduced as such. Where an expert is associated with a
  named framework, we reconstruct the underlying, non-proprietary reasoning (which rests on
  public physiology/psychology/motor-learning science) in neutral terms.
- **No imitation** of voice, personality, or catchphrase.
- What we extract are **ideas and decision structures** (not protectable) rendered in our
  own expression — a synthesis, not a reproduction.

If a pattern cannot be stated without borrowing protected expression, it is dropped.

---

## 1. The seven domains and expert lineages

| # | Domain | Reference lineage | Code | Extraction file |
|---|---|---|---|---|
| 1 | Performance Science | Galpin | GLP | [domain-1](domain-1-performance-science.md) (+ Sprint-001) |
| 2 | Programming Intelligence | Helms | HLM | [domain-2](domain-2-programming-intelligence.md) |
| 3 | Movement Safety | McGill | MCG | [domain-3](domain-3-movement-safety.md) |
| 4 | Nutrition Intelligence | Aragon | ARG | [domain-4](domain-4-nutrition-intelligence.md) |
| 5 | Behavior Change | Clear | CLR | [domain-5](domain-5-behavior-change.md) |
| 6 | Performance Psychology | Gervais | GRV | [domain-6](domain-6-performance-psychology.md) |
| 7 | Coaching Communication | Winkelman | WNK | [domain-7](domain-7-coaching-communication.md) |

"Reference lineage" means: the school of reasoning this expert is a public exponent of. The
extraction targets the *reasoning of that school*, not the individual's protected material.

---

## 2. Per-pattern schema (every extracted pattern carries these 8 fields)

- **Observed** — the reasoning behavior visible in the public body of work (what they do/decide).
- **Inferred** — the underlying decision structure we reconstruct (the WHY behind the WHAT).
- **Confidence** — 0–1, our certainty the *inference* is faithful.
- **Evidence Tier** — `A` (strong mechanistic/experimental grounding) · `B` (inferred from
  consistent expert reasoning) · `C` (weak / stylistic / single-context).
- **Context** — where the pattern validly applies.
- **Failure Modes** — how the pattern goes wrong if misapplied.
- **Counter Examples** — situations where the expert would *not* apply it (falsifiability).
- **Interactions** — which other patterns/genes it reinforces or trades against.

Core patterns per domain are **fully worked** with all 8 fields; supporting cards are compact
but distinct decision units (same method as Sprint-001). Extraction continues per domain
**until the reasoning framework is stable** — new sources stop producing new structure.

---

## 3. Card / gene / principle vocabulary (inherited, unchanged)

- **Knowledge Card** `KC-<CODE>-###` — a single reasoning/decision unit.
- **Decision Card** `DC-<CODE>-###` — an explicit if/then decision rule.
- **Gene** `DG-<DOMAIN>-###` — a reasoning pattern tested for cross-coach conservation.
  Status ∈ {UNCALLED, CANDIDATE, CALLED, POLYMORPHIC, CONTESTED}. **Called** needs ≥K=3
  *independent* experts, a bounded expression, and mechanistic grounding (Decision Genome §2–4).
- **Allele** — a context-valid variant of a shared gene.
- **Mutation** — a single-expert pattern (stays profile-local; not adopted).
- **Candidate Constitution Principle** `APX-<AREA>-###` — proposed only *after* the genome,
  only from CALLED/POLYMORPHIC genes. AI proposes; humans dispose (M10 governance).

**Comparison rule per pattern:** identical reasoning across coaches → **candidate gene**;
partially different → **allele**; unique → **mutation**.

---

## 4. Validation protocol (prediction-consistency target 90%)

For each expert, a reconstructed profile is tested against **unseen situations** (held-out
scenarios not used to build the profile). We score whether the profile predicts the *direction*
of the expert's reasoning (not exact words). Per-domain validation sections report the score.
The genome-level validation additionally requires each **called gene** to predict *multiple*
coaches' decisions on cross-coach held-out cases.

> Reported prediction-consistency is an **analyst estimate** of faithfulness of the reconstruction,
> not an experimental measurement of the person. It answers: "does this reasoning model, applied
> blind, reach the same decision the school would?" Targets met per domain are recorded honestly,
> including where a domain fell short and why.

---

## 5. Deliverables (index)

Per expert (files above): Coach Profile · Mind Graph · Decision Graph · Diagnostic Graph ·
Communication Graph · Knowledge Cards · Decision Cards · Candidate Genes · Mutations · Alleles ·
Comparison notes · Coverage Report · Blind Spots.

Synthesis:
- [COMPARISON_MATRIX.md](COMPARISON_MATRIX.md) — every pattern vs every previous coach.
- [MASTER_GENOME.md](MASTER_GENOME.md) — called genes in 8 categories (universal reasoning,
  diagnostic, safety, communication, progression, behavioral, nutrition, psychological).
- [CANDIDATE_CONSTITUTION.md](CANDIDATE_CONSTITUTION.md) — candidate `APX-*` principles.

**Sprint status:** OPEN until all seven domains are extracted, compared, validated, and
synthesized. Committed once, whole, as `SPRINT-002 Master Coach Genome Generation`.
