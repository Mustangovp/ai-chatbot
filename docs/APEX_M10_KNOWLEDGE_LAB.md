# APEX M10 — Knowledge Lab

**Chapter III — Build the Knowledge.**
**Status:** ARCHITECTURE ONLY. No code, no runtime, no deployment, no Brain / Human State /
Coaching implementation. The Knowledge Lab is **internal research infrastructure**, not part
of the product runtime.

**Mission:** the permanent research framework that builds APEX's knowledge for the next
decade — transforming world-class expertise into **structured, reviewed, versioned** APEX
knowledge. The objective is not to *collect* information; it is to *transform* it into
principles the product can be held accountable to.

---

## 0. Position (how the Lab relates to M9)

M9 defined the **destination** (the Constitution, principle spec, evidence tiers, conflict
rules, governance). M10 is the **factory** that fills it, at scale, with an audit trail.

```
   ┌──────────────────────── KNOWLEDGE LAB (offline research) ─────────────────────────┐
   │  Expert Source → Extraction → Knowledge Cards → (graph + consensus) → Principles → │
   │  Evidence Review → Conflict Resolution → PUBLISH                                    │
   └────────────────────────────────────┬───────────────────────────────────────────────┘
                                         │ versioned principle release (read-only)
                                         ▼
                         M9 CONSTITUTION  →  M8 Coaching Intelligence  →  runtime
```

**Hard separation:** the Lab never runs in production. Its only output crossing the boundary
is a **versioned, human-approved principle set** that the Constitution ingests. No runtime
component reads Knowledge Cards directly.

---

## 1. Knowledge Lab Architecture

**Components:**
- **Source Registry** — every source catalogued with type + metadata + reliability class (§2).
- **Extraction Workbench** — turns a source into Knowledge Cards (§3) using M9's ExtractionRecord.
- **Card Store** — the atomic unit of research knowledge; versioned, immutable-on-publish.
- **Knowledge Graph** — typed relationships between cards (§4).
- **Consensus Engine** — computes agreement across cards on a topic (§5).
- **Review System** — evidence + medical + coaching review, status lifecycle (§6).
- **Synthesis** — clusters of cards → candidate Constitution principles (M9 §4).
- **Publication Gate** — only human-approved, reviewed knowledge is published to the Constitution.

**Data flow contract:** `Source → Card(s) → graph edges → consensus → candidate Principle →
review → publish`. Each hop is logged; nothing skips review.

---

## 2. Knowledge Sources

| Source type | Typical reliability class | Notes |
|---|---|---|
| Scientific papers (systematic reviews/RCTs) | high → Tier A/B | study design determines tier |
| Clinical guidelines / consensus statements | high → Tier A | authoritative for Safety |
| Books (textbooks / practitioner) | medium | separate textbook vs opinion |
| Conference presentations | medium | often Tier B/C |
| Expert interviews | medium (expert consensus) | Tier B at best; single-source |
| Podcasts / public lectures / educational videos | low–medium | claims must trace to primary evidence |
| Case studies | low–medium (context-bound) | Tier C unless aggregated |
| Elite coaching material | medium (real-world practice) | Tier B when convergent across coaches |

**Source metadata (registry):** id, type, author/credentials, title, date, medium, access,
language, reliability_class, ingestion_date, licensing note (respect copyright — extract
*insights and decision rules*, never reproduce substantial text).

---

## 3. Knowledge Card Specification

One extracted insight = one Card (atomic). Cards aggregate into Constitution principles.

```
KnowledgeCard {
  id                       # KC-<DOMAIN>-<NNNN>
  domain                   # D1..D7 (M9)
  source_type              # §2
  source_metadata          # ref into Source Registry
  summary                  # the insight in APEX-neutral language (no reproduced text)
  decision_pattern         # the "if X then Y" the expert applies
  mental_model             # the frame they reason with
  coaching_principle       # the actionable coaching takeaway
  contraindications        # where it must NOT be applied
  exceptions               # where the rule breaks
  communication_pattern    # how it should be delivered
  behavior_pattern         # habit/motivation mechanism, if any
  evidence_tier            # A | B | C (provisional until review)
  confidence               # 0..1 extractor confidence
  open_questions           # what remains unresolved
  related_cards            # graph edges (§4)
  potential_constitution_principle  # candidate APX-* id/title this card may support
  # review fields (§6): review_status, confidence_score, last_review_date, reviewer_notes
}
```

Cards are **immutable once published**; a change creates a new version linked to the prior.

---

## 4. Knowledge Graph Design

Typed, directed relationships between cards. The graph is how synthesis, conflict detection,
and coverage analysis happen.

| Edge | Meaning | Used for |
|---|---|---|
| `depends_on` | B only holds if A holds | ordering; invalidation cascades |
| `contradicts` | B disagrees with A | feeds Consensus Engine → conflict |
| `supports` | B reinforces A | strengthens a candidate principle |
| `extends` | B adds nuance/scope to A | principle refinement |
| `special_case_of` | B is A under narrower context | context maps (M9 §6) |
| `alternative_to` | B is a different valid approach | option sets, autoregulation |

**Uses:** cluster cards into a candidate principle (`supports`/`extends`); surface disagreement
(`contradicts`/`alternative_to` → Consensus Engine); detect **coverage gaps** (domains/topics
with few high-tier cards) to drive what to research next; propagate invalidation when a
`depends_on` parent is deprecated.

---

## 5. Expert Consensus Engine

Aggregates the cards on a topic and their edges into a consensus verdict — **never forcing
artificial agreement.**

| Verdict | Condition (illustrative) | Result |
|---|---|---|
| **Consensus** | many `supports`, no material `contradicts`, high tier | strong candidate principle |
| **Minor disagreement** | agreement + bounded `alternative_to`/`special_case_of` edge cases | principle + documented exceptions |
| **Major disagreement** | genuine `contradicts` at comparable tier | open ConflictRecord (M9 §6); context map, no forced middle |
| **Unknown** | too few / low-tier cards | flagged coverage gap; defaults conservative |

The engine outputs a **consensus report** per topic (verdict, participating cards, edges,
tier distribution) that becomes the evidence packet for review. Disagreements are preserved
verbatim, not averaged.

---

## 6. Evidence Review Workflow

Every card must receive review before it can inform a published principle.

**Per-card review fields:** `evidence_tier` (confirmed), `confidence_score`, `review_status`,
`last_review_date`, `reviewer_notes`.

**Status lifecycle:**
```
DRAFT → EXTRACTED → NORMALIZED → IN_REVIEW
                                   ├─► APPROVED ─► MERGED ─► PUBLISHED ─► (DEPRECATED)
                                   ├─► NEEDS_WORK ─► (back to NORMALIZED)
                                   └─► REJECTED (kept with rationale, never deleted)
```
**Review gates:** a card in the **Medical Safety** domain, or with any `contraindications`,
**requires Medical Reviewer sign-off**; a coaching/behavior/communication card requires
**Coaching Reviewer** sign-off; evidence tier is confirmed by the **Reviewer**; final
constitutional merge is the **Chief Architect's**. Re-review is scheduled by tier (A slow,
C fast) so knowledge cannot silently go stale.

---

## 7. Research Workflow (Capture → Publish)

| Stage | Input → Output | Owner | Gate |
|---|---|---|---|
| **Capture** | source → Source Registry entry | Researcher | licensing/reliability logged |
| **Extract** | source → draft Cards (M9 template) | Researcher (+AI assist §9) | one insight per card |
| **Normalize** | draft → APEX-neutral, de-identified Cards | Researcher | no reproduced text; synthesis not quotation |
| **Review** | Cards → tier + status + notes | Reviewer / Medical / Coaching | domain sign-offs |
| **Merge** | approved Cards → candidate Principle | Researcher + Chief Architect | consensus report attached |
| **Approve** | candidate → constitutional acceptance | Chief Architect | safety + values alignment (M9 §7) |
| **Version** | principle set → semver release | Chief Architect | changelog, deprecations |
| **Publish** | release → Constitution ingests (read-only) | Chief Architect | immutable release tag |

Nothing is published that has not passed review; rejected knowledge is retained with rationale
for traceability.

---

## 8. Governance Model

| Role | Owns | Cannot |
|---|---|---|
| **Researcher** | capture, extraction, normalization, link proposals | approve or publish |
| **Reviewer** | evidence tier, confidence, general QC | override a medical/coaching veto |
| **Medical Reviewer** (clinical) | sign-off on Safety + any contraindication card | be bypassed for safety content |
| **Coaching Reviewer** (behavior/comms) | sign-off on coaching/behavior/communication cards | set evidence tier alone |
| **Chief Architect** | constitutional merge, versioning, publication | approve safety content without Medical sign-off |

**Separation of duties:** extraction ≠ approval; the person who wrote a card cannot be its sole
approver; safety always requires the Medical Reviewer. **Only reviewed knowledge enters the
Constitution.** Every action is attributed and timestamped.

---

## 9. Future AI Support (assistant, never authority)

AI accelerates research; humans remain the authority.

**AI MAY:** summarize sources, cluster cards, compare positions, **highlight conflicts**,
suggest graph links, draft candidate cards, flag coverage gaps, propose tiers *as suggestions*.
**AI MAY NEVER:** approve a card, set a review status to APPROVED/PUBLISHED, assign a final
evidence tier, resolve a conflict, or merge into the Constitution.

**Guardrails:** every AI-produced artifact enters as **DRAFT** and is labelled AI-assisted;
a human review step is mandatory before any status advance; AI actions are logged for audit;
AI never touches the Safety immovable core without Medical Reviewer confirmation. The authority
gradient is fixed: **AI proposes, humans dispose.**

---

## 10. Future Expansion Strategy (10-year)

- **Throughput:** scale from single-source manual extraction (E1) → assisted batch extraction
  (E2, AI-drafted, human-reviewed) → continuous ingestion with coverage-driven prioritization (E3).
- **Coverage-driven research:** the graph's gap analysis (§4) sets the research agenda — under-
  covered domains/topics with low-tier support are prioritized, not whatever is newest/loudest.
- **Re-review cadence:** scheduled tier re-validation; Tier-C cards must earn Tier-B within a
  window or be retired; guideline updates trigger targeted re-review of dependent cards.
- **Versioned releases:** the Constitution ships as periodic, changelogged semver releases the
  runtime pins to — knowledge changes are deliberate, auditable events, never silent drift.
- **Traceability to product:** the Observatory (M5) can tag live coaching decisions with the
  principle IDs (and, transitively, the cards) behind them — closing the loop from source →
  card → principle → decision.
- **Multilingual / cultural:** sources and delivery in BG/EN first; the extraction is
  language-agnostic (insights, not text), so knowledge is reusable across locales.

---

## 11. Invariants
- The Lab is offline research infrastructure; it never runs in the product runtime.
- One insight per card; synthesis, not reproduction (copyright-respecting).
- Only human-reviewed, versioned knowledge is published to the Constitution.
- Safety content always requires Medical Reviewer sign-off; AI never approves anything.
- Disagreements are recorded and preserved, never forced into false consensus.
- APEX always knows *why* — every card carries evidence, confidence, and provenance.
