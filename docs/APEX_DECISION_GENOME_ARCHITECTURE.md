# APEX — The Decision Genome (architectural redesign)

**Status:** ARCHITECTURE ONLY. No code, no implementation. Introduced **before Sprint 002**
because Sprint 002 is the first real test of the idea.

**Mission:** identify **universal coaching genes** — reasoning patterns that appear
**independently across multiple elite experts.** Knowledge Cards remain; the Genome is the
higher abstraction *above* them.

---

## 0. Why this, why now

Sprint 001 reconstructed one coach and produced candidate principles. But a pattern from **one**
mind is that person's *style*, not a universal truth — adopting it would make APEX an imitation,
the exact failure M11 forbids. The Genome raises the bar: **a single sprint may only *propose*; a
reasoning pattern is only *called* a gene when multiple experts arrive at it independently.** This
turns "synthesize, never imitate" from an aspiration into a mechanism.

**Immediate consequence:** every Sprint-001 candidate principle is retroactively **UNCALLED** —
a single-expert observation awaiting corroboration. Sprint 002 is the first independence test.

---

## 1. Genome Architecture

### 1.1 The abstraction stack (redesigned)
```
 Source ─► Knowledge Card (M10)     one insight, one source
        ─► Coach Pattern (M11)       a reasoning pattern within ONE mind (TP/DP/CP/DXP)
        ─► DECISION GENE (this)      a pattern recurring INDEPENDENTLY across ≥K minds  ◄── new layer
        ─► GENOME                    the full set of genes = APEX's synthesized reasoning
        ─► Constitution Principle(M9) a governed, adopted rule (a validated gene, reviewed)
```
Cards and Coach Patterns are **evidence**; genes are **hypotheses of universality** tested against
that evidence; the Genome is the organism; the Constitution is what APEX is held to.

### 1.2 The biological model (precise, not decorative)
| Term | Meaning in APEX | Purpose |
|---|---|---|
| **Gene** | a reasoning pattern independently recurring across experts | the unit of universal coaching reasoning |
| **Allele** | a variant of a gene (same gene, different resolution) | preserves genuine expert disagreement *within* a shared gene |
| **Expression** | the conditions under which the gene fires | the "when valid / when it fails" boundary |
| **Dominance** | which allele wins in a given context | context-selection, not forced consensus |
| **Conservation** | how many independent experts share it, how strongly | evidence of universality → maps to evidence tier |
| **Mutation** | a novel pattern in one expert, not yet corroborated | stays profile-local; **not** a gene |
| **Phenotype** | the coaching behavior the genome produces in a situation | what the runtime ultimately expresses |

**Anti-imitation is now structural:** a gene *requires* ≥K independent experts, so no single coach
can inject a principle. Idiosyncrasy is quarantined as a mutation.

---

## 2. Gene Specification

```
DecisionGene {
  id                 # DG-<DOMAIN>-<NNN>
  name               # APEX-neutral reasoning pattern (never a branded term)
  statement          # the reasoning rule, in APEX language
  domain             # D1..D7 (M9)
  expression         # activation conditions (when it fires) + boundary (when it must not)
  alleles[]          # variants: { id, variant_statement, supporting_experts[], context_valid, evidence }
  dominance_rules    # which allele expresses in which context (maps to M9 conflict context-map)
  conservation       # { independent_expert_count, lineage_independence, strength }
  evidence_tier      # A|B|C — derived from conservation × underlying evidence
  provenance         # links to Coach Patterns (M11) + Cards (M10) across coaches
  maps_to_principle  # candidate APX-* id (if/when adopted, M9)
  safety_flag        # true → Medical Reviewer required; may only SUPPORT APX-SAF, never weaken
  status             # UNCALLED | CANDIDATE | CALLED | POLYMORPHIC | CONTESTED | RETIRED
}
```
**Calling rule:** a gene reaches **CALLED** only with ≥K (default **K=3**, minimum 2) *independent*
supporting experts, a bounded expression, and grounding beyond stylistic coincidence. Fewer → CANDIDATE;
one → UNCALLED (mutation).

---

## 3. Discovery Workflow

```
 Master Coach Profiles + Mind Graphs (M11)  +  Knowledge Cards (M10)
        │  1. normalize into a shared reasoning ontology (align each coach's patterns to common axes)
        ▼
   2. cluster convergent patterns across coaches
        │  3. INDEPENDENCE TEST — did they derive it separately? (down-weight shared lineage / mutual citation)
        ▼
   4. call a candidate gene  →  5. map divergences as ALLELES (not as a rejected gene)
        │  6. grade conservation × evidence → tier
        ▼
   7. validate (§4)  →  8. review gates (M10 governance)  →  9. propose to Constitution (§6)
```
- **Shared ontology** is essential: two coaches use different words for the same reasoning — alignment
  happens on *decision structure* (inputs_read + why), not vocabulary. (Two coaches saying "deload"
  for opposite reasons are **not** the same gene.)
- **AI assists** (M10 rule): AI may propose alignments/clusters/candidate genes and flag conflicts;
  **AI never calls a gene** — humans dispose.

---

## 4. Validation Strategy

A candidate gene must pass **all**:
1. **Independent recurrence** — ≥K experts, with lineage-independence weighting (shared teacher counts as partial).
2. **Predictive** — the gene predicts *multiple* coaches' decisions on held-out situations (cross-coach version of the Sprint-001 test); score consistency.
3. **Falsifiable** — there exist situations where it must *not* fire; an always-on "gene" is too vague to be real.
4. **Grounded** — supported by mechanism/evidence, not stylistic coincidence (guards against *false convergence*).
5. **Parsimonious** — not reducible to a more general gene (guards against duplicate/overlapping genes).

**Failure modes named:** *false convergence* (same surface, different reasoning), *lineage artifact*
(shared lineage ≠ independence), *overfitting* (too broad to falsify), *parameter-masquerade* (a
difference that is really an allele, mistaken for a separate gene, or vice-versa).

---

## 5. Consensus Rules (how disagreement is handled)

| Outcome | Condition | Result |
|---|---|---|
| **Conserved** | near-universal, no material dissent | strong principle candidate; high tier |
| **Polymorphic** | shared gene, ≥2 valid **alleles** by context | principle + **dominance rules** select the allele; both preserved |
| **Contested** | genuine disagreement about the **gene itself** (not just alleles) | keep **open**; conservative default; no forced middle |
| **Uncalled / mutation** | one expert only | stays profile-local; not adopted |

**Never force artificial agreement.** Disagreement is expressed *within* the model — as alleles
(context-selected) or as an open contested gene — never averaged away. This is M9 §6 conflict
resolution, now with a genetic mechanism.

---

## 6. Relationship with the Constitution

- **Direction of authority:** genes are the **primary evidence** for principles. Pipeline:
  `Coach Patterns → gene (independent convergence) → validation → review gates → Constitution principle`.
- **Not 1:1:**
  - Not every gene becomes a principle — safety review, values alignment, or contrary evidence can **veto** a gene.
  - Not every principle needs a gene — the **immovable core** (Safety, Values) is axiomatic, owned by the frozen Brain / M9, and does not require cross-expert discovery.
- **Safety supremacy:** a `safety_flag` gene requires Medical Reviewer sign-off and may only **support**
  `APX-SAF-*`, never weaken it. No gene overrides the Brain.
- **Traceability (full chain):** `Principle ← Gene ← Alleles ← Coach Patterns ← Cards ← Sources`, and
  forward: the Observatory (M5) can tag a live decision with the principle → gene → supporting experts.
- **Versioning:** the Genome is versioned alongside the Constitution. Each new Sprint (00N) can:
  strengthen a gene's conservation, add an allele, call a new gene, or move a CANDIDATE → CALLED. A
  gene contradicted by accumulating evidence is **RETIRED** (never silently deleted).

---

## 7. What changes for the roadmap
- **Sprint 001 output is re-labelled UNCALLED** (single-expert). Its ~candidate `APX-*` principles are
  now *gene candidates awaiting independence*, not adopted principles.
- **Sprint 002 gains a purpose beyond extraction:** it is the **first independence test** — where
  Coach-2's patterns are aligned against Coach-1's to *call* the first genes (or reveal false convergence).
- **Sprints continue** until conserved genes accumulate into a genome robust enough that the Constitution
  is built from cross-expert reasoning — APEX's own mind, provably **not** any individual's.

## 8. Invariants
- A gene requires **independent** cross-expert recurrence (K≥2, default 3); one expert = mutation.
- Alignment is on decision structure (inputs_read + why), never vocabulary.
- Disagreement is preserved as alleles or open contested genes — never forced consensus.
- Safety is Brain-owned and supreme; genes may only support it.
- AI proposes genes; humans call them. Full provenance from source to principle.
- No implementation — architecture only.
