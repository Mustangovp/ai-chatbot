# THE MIND OF APEX — Engineering Blueprint v1.0

**Status:** Normative. The philosophy ("The Mind of APEX", Ch. 1–3, Interlude, Adversarial Review) is frozen.
This document translates it into buildable organs. Where this document is silent, the philosophy decides.
Where both are silent, the change requires a blueprint revision — not improvisation.

**Audience:** the engineering team, for the next two years.
**Non-goals:** no implementation, no schemas, no vendor choices. Organs are contracts, not code.

---

## 0. Architectural Laws

These translate the frozen aphorisms into engineering rules. They bind every organ.

| # | Law | Source |
|---|-----|--------|
| L1 | Organs communicate **only** through the declared contracts in §2. Any interaction not declared in §5 is prohibited. No shared mutable state. | (method) |
| L2 | The LLM is stateless. All mind-state lives in substrate we own. The voice is replaceable; the mind is not. | Ch.1 |
| L3 | Every datum carries **provenance** (measured / observed / reported / inferred / assumed). Every belief carries evidence links to the immutable ledger. Nothing is asserted above its tier. | Ch.1, Ch.2 |
| L4 | **Intervention carries the burden of proof.** The null action is generated and scored in every decision cycle. | Ch.3 |
| L5 | Every organ may fail **open** (degrade gracefully) except the Constitution Gate, which fails **closed** (no output rather than an unconstitutional output). | Review §12 |
| L6 | A prediction that was **spoken** to the user is expectancy-confounded and is scored in a separate pool from silent predictions. | Review §1 |
| L7 | A belief whose pattern was first mentioned by the coach **before** it was independently observed is tagged `iatrogenic-risk` permanently and can never exceed the assertion-confidence ceiling. | Review §1 |
| L8 | The **exploration budget is bounded by safety but may never be zero.** Judgment cannot veto all belief-testing; the Allocator (E6) arbitrates. | Review §2 |
| L9 | Every organ ships with its falsifiable assumptions and the test that would falsify them (§7). An organ without a failing condition is not done. | (method) |
| L10 | No organ may optimize, directly or via proxy, any engagement metric. The Evaluation Harness computes outcome-vs-engagement divergence and reports it; Constitution config changes require human sign-off outside the product team's deploy path. | Ch.1, Review §5 |
| L11 | Micro-experiments on a user require standing informed consent recorded in the Consent Registrar. No consent, no experiment — curiosity degrades to questions only. | Review §4 |
| L12 | User-facing text is produced only via Expression Governor → Voice Renderer → Conformance Monitor → Constitution Gate. No bypass, including error messages. | Ch.1, Ch.3 |

---

## 1. System Overview

Eight systems, thirty organs, three loops.

```
SYSTEM A  SUBSTRATE      A1 Event Ledger · A2 Chronos
SYSTEM B  PERCEPTION     B1 Sensorium · B2 Baseline Keeper · B3 Salience Gate ·
                         B4 Coherence Integrator · B5 Silence Interpreter ·
                         B6 Regime Sentinel · B7 Aperture Controller
SYSTEM C  MEMORY         C1 Episodic Store · C2 Belief Ledger · C3 Consolidator ·
                         C4 Narrator Calibrator · C5 Memory Rights Manager
SYSTEM D  REASONING      D1 Prediction Engine · D2 Hypothesis Manager · D3 Curiosity Engine
SYSTEM E  JUDGMENT       E1 Stakes Arbiter · E2 Trust Ledger · E3 Action Selector ·
                         E4 Kairos Buffer · E5 Paternalism Governor · E6 Exploration Budget Allocator
SYSTEM F  EXPRESSION     F1 Expression Governor · F2 Voice Renderer · F3 Conformance Monitor
SYSTEM G  SAFEGUARDS     G1 Constitution Gate · G2 Compliance Sentinel · G3 Handoff Reflex ·
                         G4 Consent Registrar · G5 Adversarial Sentinel
SYSTEM H  META           H1 Evaluation Harness · H2 Cultural Prior Manager
```

**The Fast Loop (per interaction; milliseconds–seconds).**
Raw event → B1 Sensorium → B2/B3/B4 (baseline, salience, coherence) → sentinels inline (B6, G2, G5, B5 if absence-triggered) → D1 attaches expectations → E1–E6 judgment pipeline → F1 dossier → F2 render → F3 conformance → G1 gate → user. Every fast-loop artifact is appended to A1.

**The Slow Loop ("sleep"; daily/weekly per user).**
C3 Consolidator runs: resolve expired predictions (D1), apply decay, promote/demote beliefs, refresh baselines (B2), recalibrate narrator (C4), retire story elements, sample-audit beliefs against A1 primary data. B6 runs its slow-eye drift pass.

**The Meta Loop (population; weekly/monthly).**
H1 Evaluation Harness computes calibration, ossification, iatrogenesis, silence-classification audits, correlated-failure monitoring. H2 updates cultural priors. Findings route to humans, never to automatic self-modification of the Constitution.

**Degradation spine:** if Systems B–E are down, the product degrades to a *competent generic coach with a constitution* (stateless mode: F+G only). This mode is a deliverable, not an accident (§8, Phase 1).

---

## 2. Global Data Contracts (the blood)

All inter-organ communication uses these typed artifacts. Field lists are normative; representation is not.

**OBSERVATION** — one normalized signal.
`{ id, user, channel, occurred_at, payload(typed per channel), provenance_tier, source, intake_confidence, absorbers[] (known context: illness, travel…) }`

**BASELINE** — one user × channel personal normal.
`{ user, channel, center, dispersion, rhythm(cadence model), maturity(sample count), updated_at }`

**DEVIATION** — a scored departure.
`{ observation_ref, magnitude_in_personal_units, direction, absorbed_by[], coherence_group? }`

**EPISODE** — a story-worthy event.
`{ id, user, span, story_tests_passed[] (consequence/boundary/character/emotion/arc), charge, retention_class(provisional|canonical|retired), evidence_refs[] → A1 }`

**BELIEF** — one claim about one human.
`{ id, user, domain(somatic|behavioral|relational), tier(observation|pattern|trait|identity), claim(typed schema, machine-comparable — never free text), confidence, provenance_mix, evidence_refs[] → A1, decay_class, born_from(organic|post-utterance), iatrogenic_risk(bool, per L7), times_tested, times_confirmed, last_tested_at, status(active|dormant|retired|falsified) }`

**PREDICTION** — a falsifiable expectation.
`{ id, belief_refs[], expectation(typed, with measurable outcome + horizon), spoken(bool, per L6), outcome_ref?, score?, resolved_at? }`

**INTENTION** — a formed action awaiting its moment.
`{ id, action_candidate, formed_at, expires_at, required_conditions(receptivity class…), priority }`

**ACTION** — what judgment chose.
`{ type(prescribe|ask|observe-aloud|challenge|redirect|silence|handoff), content_directive, reversibility(reversible|costly|irreversible), stakes_assessment, trust_cost_estimate, experiment_ref?, expectations[] → PREDICTION }`

**DOSSIER** — the compact packet the voice may see (hundreds of tokens, never raw history).
`{ user, tone_mode, top_beliefs[](confidence-tagged, tier-tagged), permitted_observations[], epistemic_language_map, constraints[], banned_registers[], action directive }`

**FLAG** — a safeguard escalation.
`{ type(crisis|medical|ed-risk|adversarial|privacy|constitution), evidence_refs[], required_route, severity }`

---

## 3. Organ Specifications

Format per organ: **Purpose / Inputs / Outputs / State / Lifecycle / Failure modes / Depends on / Consumed by / Testable assumptions.**
"Reads/Writes" refer to contracts in §2. Interactions not listed here are prohibited (L1).

---

### SYSTEM A — SUBSTRATE

#### A1 · Event Ledger
- **Purpose:** immutable, append-only record of every observation, action, prediction, and flag. The retina's raw feed and the court of final appeal for every belief re-audit (Review §8).
- **Inputs:** every artifact from every organ (append only).
- **Outputs:** time-range and reference reads.
- **State:** the ledger itself. Never mutated; corrections are new events referencing old ones.
- **Lifecycle:** always on. Raw granularity ages into aggregates **only after** C3 has consumed it and only past the re-audit window; aggregation events are themselves ledgered.
- **Failure modes:** (1) write loss → fast loop continues, learning halts, alarm to H1; (2) unbounded growth → aging policy, never silent deletion.
- **Depends on:** nothing. **Consumed by:** everything.
- **Testable assumptions:** any active belief's `evidence_refs` can be resolved to ledger entries ≥99.9% of the time; a randomly sampled belief can be recomputed from primary data within tolerance (the re-audit test).

#### A2 · Chronos
- **Purpose:** the three clocks (fast/middle/slow eyes) and all scheduling: consolidation runs, decay ticks, prediction horizons, intention expiries, silence timers.
- **Inputs:** schedule registrations from organs. **Outputs:** tick events.
- **State:** per-user schedule table.
- **Lifecycle:** always on. New user → default cadences; cadences adapt from B2 rhythm data (a user's "week" is theirs, not the calendar's).
- **Failure modes:** missed ticks → organs must be idempotent on late delivery (contract requirement).
- **Depends on:** B2 (rhythms). **Consumed by:** B5, C3, D1, E4, H1.
- **Testable assumptions:** no organ behaves incorrectly when a tick is delivered twice or late (chaos test).

---

### SYSTEM B — PERCEPTION

#### B1 · Sensorium
- **Purpose:** normalize raw channel data (workouts, self-reports, message metadata, cadence, future wearables) into OBSERVATIONs with provenance. The only door into the mind.
- **Inputs:** raw app events, message envelopes (length, latency, timing — *not* interpretation), structured logs.
- **Outputs:** OBSERVATION stream → A1, B2, B3.
- **State:** channel registry (each channel: type, provenance ceiling, expected cadence, cultural-prior hooks).
- **Lifecycle:** per event. New channel types (wearables) register here without touching downstream organs — this is the wearable-readiness seam.
- **Failure modes:** (1) mis-typed payloads → quarantine queue, never silent drop; (2) provenance inflation (reported data marked observed) is a **critical** defect class — lint-tested.
- **Depends on:** G4 (channel consent), H2 (intake priors). **Consumed by:** A1, B2, B3, G5.
- **Testable assumptions:** every OBSERVATION is reproducible from its raw event (replay test); no channel exceeds its provenance ceiling.

#### B2 · Baseline Keeper
- **Purpose:** maintain each user's personal normal — center, dispersion, rhythm — per channel. Nothing is signal in absolute units.
- **Inputs:** OBSERVATION stream. **Outputs:** BASELINEs; deviation scoring service for B3.
- **State:** baseline table + maturity.
- **Lifecycle:** cold start = acquisition mode (wide uncertainty, no deviation scoring until maturity threshold); mature = incremental updates; **regime flood (B6) resets affected channels to acquisition**; fresh start (C5) resets all.
- **Failure modes:** (1) scoring before maturity → hard-gated; (2) baseline poisoned by an unabsorbed anomaly → C3 slow-loop winsorization; (3) drift blindness → B6 owns drift, B2 must expose trend series to it.
- **Depends on:** B1, A2, H2 (cold-start priors). **Consumed by:** B3, B5, B6, H1.
- **Testable assumptions:** deviation false-positive rate on synthetic stationary users < agreed ε; baseline converges within N observations on synthetic regime data.

#### B3 · Salience Gate
- **Purpose:** decide, per deviation: **metabolize** (feed baselines/belief confidence silently) or **promote** (candidate episode). Applies the gates: surprise, firsts, extremes, third occurrence, emotional charge — with multiple-comparisons discipline (Review §1).
- **Inputs:** DEVIATIONs (B2-scored), coherence groups (B4). **Outputs:** episode candidates → C1; metabolic credits → C2 confidence; retro-tag requests → C1.
- **State:** per-user recent-event window (provisional retention for retroactive salience); hypothesis-count tracker for the comparisons budget.
- **Lifecycle:** per event; retro pass in slow loop (consequence test needs hindsight).
- **Failure modes:** (1) **pattern hallucination** — three co-occurrences in noise. Mitigation is structural: a "third occurrence" only counts within a pre-registered channel-pair budget; discoveries outside it enter as `hypothesis` tier and must survive a D1 prediction before becoming `pattern` (this operationalizes Review §1); (2) salience flooding from volatile users → per-user promotion quota.
- **Depends on:** B2, B4. **Consumed by:** C1, C2, D2.
- **Testable assumptions:** on synthetic pure-noise users, zero beliefs reach `pattern` tier over 12 simulated months (the anti-astrology test — a named CI gate).

#### B4 · Coherence Integrator
- **Purpose:** one channel deviating is an anomaly; several deviating together are an event. Detects cross-channel events and **contradictions** (channels disagreeing), which it never averages — it emits them as first-class contradiction objects.
- **Inputs:** DEVIATION stream. **Outputs:** coherence groups → B3; contradictions → D2.
- **State:** rolling multi-channel window per user.
- **Lifecycle:** per event batch (fast loop tail).
- **Failure modes:** (1) window too small → misses slow-building events (B6 covers the slow band; boundary is explicit: B4 ≤ 14 days < B6); (2) treating an absorbed deviation as live → must honor `absorbed_by`.
- **Depends on:** B2. **Consumed by:** B3, B6, D2, G2.
- **Testable assumptions:** injected correlated synthetic events are detected at ≥ agreed sensitivity while single-channel noise stays below the anomaly threshold.

#### B5 · Silence Interpreter
- **Purpose:** classify absence against the frozen taxonomy (rhythmic / absorbed / shame / drift / crisis / graduation) **as a probability distribution, never a verdict**, and route with asymmetric-cost awareness (Review §3: misclassification costs dominate).
- **Inputs:** contact-cadence baselines (B2), recent context (last episodes, lapse events), A2 silence timers. **Outputs:** silence assessments (distribution + recommended posture) → E3; crisis mass above threshold → FLAG → G3.
- **State:** per-user silence dossier (onset, priors, prior outreach outcomes).
- **Lifecycle:** timer-triggered (A2), never per-message.
- **Failure modes:** (1) crisis-as-graduation → **crisis dominance rule:** if crisis probability exceeds a floor, posture is the one safe for crisis regardless of the argmax class; (2) shame-silence pinged with ledger-reading → posture constraints travel with the assessment into F1 (zero-debt register is mandatory when shame mass is material); (3) cultural cadence misread → priors from H2, never global constants.
- **Depends on:** B2, A2, H2, C1. **Consumed by:** E3, F1, G3, H1 (audits every classification by outcome follow-up).
- **Testable assumptions:** H1's silence audit (what actually followed each classification) shows calibration within agreed bounds; crisis-recall is tuned to dominate precision (asymmetry is a requirement, not a bug).

#### B6 · Regime Sentinel
- **Purpose:** distinguish fluctuation / phase / regime change. Watch broken invariants ("the more stable the pattern, the louder its violation"), linguistic tripwires, failed re-anchoring, slow drift (aging).
- **Inputs:** B2 trend series, B4 events, tripwire lexicon hits from B1.
- **Outputs:** regime verdicts; on confirmed regime change: **humility flood** — scoped confidence writedown to C2 (behavioral heavy, somatic light, relational light per Ch.2), baseline reset orders to B2, aperture-widen order to B3, and a user-facing acknowledgment intention to E4.
- **State:** per-user invariant registry (which patterns have earned "invariant" status); active phase hypotheses.
- **Lifecycle:** fast-loop tripwires; middle-eye weekly pass; slow-eye quarterly drift pass.
- **Failure modes:** (1) flood on a phase → beliefs are written *down*, never deleted — recovery is cheap by design; (2) missed regime → C4/H1 catch it late via calibration collapse; (3) goal-shifter abuse → see G5 meta-pattern (regime changes themselves are ledgered and countable).
- **Depends on:** B1, B2, B4. **Consumed by:** B2, B3, C2, E4, G5.
- **Testable assumptions:** on synthetic regime-change users, flood triggers within N weeks; on synthetic phase users, it doesn't (both are CI gates).

#### B7 · Aperture Controller
- **Purpose:** designed blindness, honestly implemented (Review §12): a **deny-list of inference targets** (sexuality, politics, finances, off-mandate health) enforced at the belief boundary — the voice may read words in context, but **no organ may write a belief, episode, or baseline in a denied region**, and F1 may never surface one. Blindness we can prove, not promise.
- **Inputs:** all belief/episode write attempts (interceptor). **Outputs:** permits/denials; privacy FLAGs.
- **State:** the mandate boundary (versioned, human-change-controlled like the Constitution).
- **Lifecycle:** always on, every write.
- **Failure modes:** (1) leak via free-text payloads → periodic H1 sweep of stored claims against the deny-list; (2) over-blocking mandate-relevant signals → appeal path with human review.
- **Depends on:** G1 (shares change control). **Consumed by:** C1, C2, F1.
- **Testable assumptions:** red-team corpus of off-mandate disclosures produces zero persisted beliefs/episodes in denied regions (a release gate).

---

### SYSTEM C — MEMORY

#### C1 · Episodic Store
- **Purpose:** hold story-worthy EPISODEs (five tests) including the shared-memory law: everything the athlete will remember, we must be able to recall.
- **Inputs:** promotions from B3; retro-tags; charge annotations. **Outputs:** episode reads for F1 (via permits), C3, B5.
- **State:** episodes with retention classes (provisional → canonical → retired).
- **Lifecycle:** provisional episodes expire un-promoted (that *is* the metabolize path); canonical persists; **retired** (C5/C3 story-retirement) = excluded from surfacing but not from the user's own reference — resolving the shared-memory-vs-forgiveness collision (Review §13): *retired episodes are never volunteered by the coach but are always recognizable if the user raises them.* Precedence rule, frozen here.
- **Failure modes:** (1) museum bloat → story-retirement pass in C3; (2) asymmetric memory (user remembers, coach lost it) → charge-weighted retention floor.
- **Depends on:** B3, B7, C5. **Consumed by:** F1, C3, B5, H1.
- **Testable assumptions:** high-charge episodes are retrievable after 24 simulated months (retention test); retired episodes never appear in dossiers (surfacing test).

#### C2 · Belief Ledger
- **Purpose:** the semantic memory — every BELIEF, with tier, domain, confidence, decay, provenance, iatrogenic tags, and full evidence-linkage into A1.
- **Inputs:** writes only from C3 (consolidated), D1 (prediction outcomes), B6 (floods), G5 (adversarial writedowns). **No fast-loop organ writes beliefs directly** — beliefs are considered, never reflexive.
- **Outputs:** belief reads (tier/confidence-filtered) to D1, E-system, F1.
- **State:** the ledger; per-belief test history.
- **Lifecycle:** created at `observation/hypothesis` tier; promoted by C3 (context diversity, not time); decayed per class; **demotable and falsifiable — `identity`-tier beliefs require the highest formation bar and keep a live demotion path** (Ch.2 ladder).
- **Failure modes:** (1) ossification — confidence rising while `last_tested_at` ages → H1's ossification metric feeds E6 as *testing pressure*; (2) sedimentation — beliefs no longer resolvable to primary data → C3 re-audit quota; (3) iatrogenic laundering → `born_from` is immutable.
- **Depends on:** C3, D1, B6, B7, G5. **Consumed by:** D1, D2, D3, E1, E3, E5, F1, H1.
- **Testable assumptions:** confidence is calibrated (X% beliefs are right ~X% of the time — H1 calibration curve); no `iatrogenic-risk` belief ever exceeds the assertion ceiling (invariant test).

#### C3 · Consolidator ("Sleep")
- **Purpose:** the slow-loop metabolism: episodes→belief updates; decay; promotion/demotion by context diversity; baseline refresh; story retirement proposals; **re-audit quota** — each run, a sample of active beliefs is recomputed from A1 primary data and corrected (Review §8).
- **Inputs:** C1, C2, A1, D1 resolutions, C4 calibration. **Outputs:** belief writes (sole routine writer), retirement proposals, audit findings → H1.
- **State:** run cursors; audit sampling state.
- **Lifecycle:** per-user daily light pass, weekly deep pass (A2).
- **Failure modes:** (1) skipped runs → beliefs stale-flagged after T, F1 widens hedging automatically (staleness degrades language, not availability); (2) compression that discards falsifying detail → re-audit is the systemic backstop; (3) runaway promotion → promotion requires *both* diversity thresholds *and* D1 predictive success for `trait`+.
- **Depends on:** A1, A2, C1, C2, C4, D1. **Consumed by:** C2, B2, H1.
- **Testable assumptions:** deliberately corrupted beliefs are detected by re-audit within M runs (fault-injection test); no promotion to `trait` without ≥1 successful prediction.

#### C4 · Narrator Calibrator
- **Purpose:** per-channel reliability model of the user's self-reports — honest about circularity (Review §1): a channel is **calibratable only where an independent anchor exists** (behavioral ground truth, later wearables). Anchorless channels carry an explicit `uncalibratable` status and a permanent hedging floor in F1.
- **Inputs:** paired self-report vs. anchor outcomes (from D1 resolutions), contradiction resolutions (D2). **Outputs:** channel reliability weights → B1 intake confidence, C3, F1 language.
- **State:** per-user, per-channel reliability + anchor inventory.
- **Lifecycle:** slow loop only; wearable arrival upgrades anchor inventory without redesign (B1 seam).
- **Failure modes:** (1) circular calibration → structurally impossible (anchor required by contract); (2) cultural response-style misread as personal bias → H2 priors partial out population effects first.
- **Depends on:** D1, D2, H2. **Consumed by:** B1, C3, F1, G5.
- **Testable assumptions:** on synthetic users with known reporting bias + anchors, recovered bias converges; on anchorless synthetic users, the organ outputs `uncalibratable` (not a guess).

#### C5 · Memory Rights Manager
- **Purpose:** the user's sovereignty over the mind's contents: export, erasure, **story retirement on request, and Fresh Start** (full or scoped model reset) — even though it costs the moat (Review §8). Also owns the retention constitution (what may never be silently deleted: safety-relevant constraints require explicit user confirmation to erase).
- **Inputs:** user requests; C3 retirement proposals. **Outputs:** reset orders to B2/C1/C2; export bundles; erasure certificates → A1.
- **State:** rights ledger (what was reset, when, at whose request).
- **Lifecycle:** on demand; Fresh Start triggers acquisition mode across B2 and a relationship-age reset in F1 language.
- **Failure modes:** (1) partial reset leaving ghost beliefs → reset is transactional across organs (contract requirement); (2) erasing an injury constraint casually → two-step confirmation with plain-language consequence statement.
- **Depends on:** G4. **Consumed by:** all stateful organs.
- **Testable assumptions:** post-Fresh-Start, no dossier contains pre-reset content (leak test); export bundle round-trips to a faithful model state.

---

### SYSTEM D — REASONING

#### D1 · Prediction Engine
- **Purpose:** the heartbeat. Attach falsifiable expectations to every ACTION (silent by default); resolve them at horizon against A1 outcomes; route scored error to C2. Maintains the **two pools** (spoken vs silent, L6) so expectancy inflation is measurable rather than absorbed.
- **Inputs:** ACTIONs (E3), beliefs (C2), outcomes (A1 via A2 horizon ticks). **Outputs:** PREDICTIONs → A1; resolutions → C2, C3, C4, H1.
- **State:** open-prediction book per user.
- **Lifecycle:** emit on action; resolve on horizon; unresolvable (no outcome data) → `void`, which is itself a signal (measurement-coverage metric to H1).
- **Failure modes:** (1) vague expectations → typed-expectation schema rejects unfalsifiable entries at write time; (2) horizon gaming (predicting only easy things) → H1 tracks prediction difficulty mix; (3) confound leakage between pools → `spoken` is set by F1 at render time, not by D1.
- **Depends on:** C2, A1, A2. **Consumed by:** C2, C3, C4, E6, H1.
- **Testable assumptions:** every prescribe/challenge action carries ≥1 typed expectation (coverage invariant); pool separation shows measurable spoken-pool inflation (if it doesn't, our confound model is wrong — investigate either way).

#### D2 · Hypothesis Manager
- **Purpose:** hold contradictions (B4) and salience discoveries (B3) as **competing hypothesis sets** — never resolved by averaging, resolved only by discriminating evidence. Generates the discriminating-question specs for D3 (the "sleep well but declining" doctrine, Ch.2 §5).
- **Inputs:** contradiction objects, hypothesis-tier beliefs. **Outputs:** open hypothesis sets; discriminating-evidence requests → D3; resolutions → C2, C4.
- **State:** per-user open-hypothesis board with staleness clocks.
- **Lifecycle:** fast-loop intake; slow-loop pruning (stale hypotheses decay to `unresolved` — which F1 must reflect as honest uncertainty).
- **Failure modes:** (1) board bloat → cap with priority eviction; (2) premature resolution → resolution requires evidence typed as discriminating, not merely consistent.
- **Depends on:** B3, B4, C2. **Consumed by:** D3, C2, C4, E3 (hedge-toward-worst directive while open).
- **Testable assumptions:** injected synthetic contradictions resolve to the planted truth given the discriminating evidence, and *don't* resolve without it.

#### D3 · Curiosity Engine
- **Purpose:** spend the question/experiment budget where value-of-information is highest. Two products: **questions** (always allowed) and **micro-experiments** (only with G4 standing consent, L11). Explore rate decays with relationship age but never to zero (L8 floor via E6).
- **Inputs:** D2 requests, C2 uncertainty map, E6 budget, G4 consent state. **Outputs:** ask-candidates and experiment-candidates → E3 (judgment still decides *whether and when*).
- **State:** per-user question budget, experiment registry (design, consent ref, status).
- **Lifecycle:** fast-loop candidate generation; experiments span weeks with D1 expectations attached by design.
- **Failure modes:** (1) interrogation fatigue → hard question-rate cap; (2) covert experimentation → structurally impossible without consent ref (write-time check); (3) exploring on the vulnerable → G2/G3 flags freeze the experiment registry for that user.
- **Depends on:** D2, C2, E6, G4. **Consumed by:** E3.
- **Testable assumptions:** every experiment in the registry resolves to a consent record (invariant); VOI ranking beats random-question baseline on synthetic users (efficacy test).

---

### SYSTEM E — JUDGMENT

#### E1 · Stakes Arbiter
- **Purpose:** score every decision context against the frozen hierarchy (safety > relationship > habit > adaptation > today) and compute account levels for **feed-the-scarcer-account** resolution.
- **Inputs:** current context, C2 beliefs, E2 trust level, G-flags. **Outputs:** stakes assessment + scarcity vector → E3.
- **State:** none (pure evaluation; account levels live in their owners).
- **Lifecycle:** per decision.
- **Failure modes:** mis-tiered stakes → the tier table is config under G1 change control, not code.
- **Depends on:** C2, E2, G1/G2/G3 flags. **Consumed by:** E3, E5.
- **Testable assumptions:** golden-scenario suite (frozen vignettes from the philosophy) produces the philosophy's answer; any drift is a regression.

#### E2 · Trust Ledger
- **Purpose:** the intervention economy — estimated trust balance, spend events (challenge, disagreement, override, outreach), earn events (confirmed predictions the user noticed, admitted errors, respected silences).
- **Inputs:** action outcomes, user responses (sentiment/continuation from B1 metadata). **Outputs:** balance + spend recommendations → E1, E3.
- **State:** per-user balance with uncertainty band (it is an *estimate* and must say so).
- **Lifecycle:** event-driven updates; slow-loop reconciliation against retention/response signals.
- **Failure modes:** (1) **influence-optimizer drift** (Review §7): the ledger informs *restraint only* — it may veto/postpone spends, it may never be an objective to maximize (L10 lint: no organ optimizes E2 balance); (2) balance overconfidence → wide bands early.
- **Depends on:** B1, D1 outcomes. **Consumed by:** E1, E3, E4.
- **Testable assumptions:** spend-frequency caps hold under adversarial scenario replay; removing E2 entirely degrades to *more* conservative behavior, not less (fail-safe direction test).

#### E3 · Action Selector
- **Purpose:** the decision core. Generate candidates (always including **null action** and **redirect** variants), weight by asymmetric loss and reversibility, apply confidence-commitment gradient, select. Every selected action carries expectations (D1) and a decision record (A1).
- **Inputs:** perception products, C2, D2 hedging directives, D3 candidates, E1 stakes, E2 trust, E5 override verdicts, E6 exploration pressure, B5 postures.
- **Outputs:** ACTION → E4 (if timing-gated) or F1 (if immediate); decision record → A1.
- **State:** none per se (records live in A1).
- **Lifecycle:** per decision cycle.
- **Failure modes:** (1) null-action starvation (system acts because it can) → H1 tracks null-action selection rate against philosophy's expectation (silence should *win often*); (2) irreversible-under-uncertainty → hard block: `irreversible × low-confidence` is not selectable (L-class invariant); (3) explore/exploit collapse → E6 pressure is an input it cannot ignore (quota, not suggestion).
- **Depends on:** nearly all upstream. **Consumed by:** E4, F1, D1, A1.
- **Testable assumptions:** golden-scenario suite; the anti-ossification quota is consumed (E6 reports starvation as a defect, not a preference).

#### E4 · Kairos Buffer
- **Purpose:** hold formed INTENTIONs until receptivity conditions are met (crest / calm / storm classification from fast-eye state). Lessons land on crests; corrections in calm; storms get presence only.
- **Inputs:** INTENTIONs (E3), receptivity state (B1 metadata + B4), A2 expiries. **Outputs:** released actions → F1; expired intentions → A1 (with reason).
- **State:** per-user intention queue.
- **Lifecycle:** continuous; queue is small by design (cap) — judgment that defers everything is deferring judgment.
- **Failure modes:** (1) strategic patience becoming concealment → intentions above a stakes threshold carry a **disclosure norm**: if held > T, F1 surfaces "there's something I want to raise when the time is right" (the founder's Ch.3 ruling is config here); (2) stale release → conditions re-checked at release, not only at enqueue.
- **Depends on:** E3, A2, B-system state. **Consumed by:** F1, A1.
- **Testable assumptions:** storm-state releases are presence-class only (invariant); held-intention age distribution stays under cap.

#### E5 · Paternalism Governor
- **Purpose:** the override calculus: `irreversibility × prediction confidence × user heat` gates protection; output is redirect-first, refuse-last. Includes the **slow-walk ratchet** (Review §6): cumulative drift across individually-"recoverable" steps is tracked, so salami tactics trip the same wire a single large ask would.
- **Inputs:** user requests, C2 (incl. hot-state markers), G2 flags, cumulative-drift ledger. **Outputs:** allow / redirect / override verdicts + rationale → E3; overrides are always ledgered with reasons (A1) and always explained to the user (F1 directive).
- **State:** per-user drift ledger (rolling sum of granted increments per risk axis).
- **Lifecycle:** per risky request; ratchet decays slowly (weeks).
- **Failure modes:** (1) infantilization → the "allowed to fail" doctrine is a floor: survivable-failure requests pass by default; (2) ratchet bypass via category-hopping → drift axes defined by harm type, not request wording.
- **Depends on:** C2, G2, E1. **Consumed by:** E3, A1, F1.
- **Testable assumptions:** scripted slow-walk scenarios (N small steps to a harmful sum) trigger the ratchet before the harm threshold in 100% of the adversarial suite.

#### E6 · Exploration Budget Allocator
- **Purpose:** **the arbitration organ the Review demanded (§2).** Owns a protected, per-user, safety-bounded testing budget: which stale/consequential beliefs must be re-tested through action, at what rate. Judgment can schedule and shape the tests; it cannot zero them.
- **Inputs:** C2 staleness/consequence map, H1 ossification metrics, G2/G3 safety bounds. **Outputs:** testing pressure (specific belief-test quotas) → E3, D3.
- **State:** per-user budget and quota consumption.
- **Lifecycle:** slow-loop budget setting; fast-loop consumption.
- **Failure modes:** (1) budget starved by perpetual safety flags → legitimate for flagged users (G2 dominates), but H1 reports population-level starvation as a systemic defect; (2) testing the wrong beliefs → priority = consequence × staleness × confidence (the dangerous ones: high-confidence, long-untested, decision-shaping).
- **Depends on:** C2, H1, G2, G3. **Consumed by:** E3, D3, H1.
- **Testable assumptions:** on long-run synthetic users, no decision-shaping belief exceeds T since last test (the anti-ossification SLA); disabling E6 in simulation reproduces the ossification pathology (proving it's load-bearing).

---

### SYSTEM F — EXPRESSION

#### F1 · Expression Governor
- **Purpose:** decide what may be said and how: epistemic-tier→language mapping, intimacy gradient, complexity budget, **mirror-not-mask rules** (identity content only as past-tense evidence or question-form, never declarative), curation ethics (Review §4: an *evidence-selection log* — every surfaced observation is ledgered with what was withheld and why), zero-debt register when B5 requires it, decision-shadow annotations. Builds the DOSSIER.
- **Inputs:** released actions (E3/E4), C1/C2 via B7 permits, C4 hedging floors, B5 postures, tone mode (from frozen tone selector philosophy), G4 intimacy consent level.
- **Outputs:** DOSSIER → F2; `spoken` markers → D1; curation log → A1.
- **State:** per-user expression profile (verbosity calibration, language, intimacy setting).
- **Lifecycle:** per outbound message.
- **Failure modes:** (1) over-revelation (surveillance feel) → intimacy gradient is a hard filter, not a style hint; (2) identity declaration slip → mirror rules are lint-checked in F3, not just requested; (3) stale beliefs voiced confidently → staleness auto-widens hedging (C3 contract).
- **Depends on:** B5, B7, C1, C2, C4, E-system, G4. **Consumed by:** F2, D1, A1, H1.
- **Testable assumptions:** dossier token budget holds at p99; curation log completeness = 100% of surfaced observations.

#### F2 · Voice Renderer
- **Purpose:** the stateless LLM adapter: DOSSIER in, candidate text out. Personality lives in the frozen core directive; the renderer holds zero user state (L2). Vendor-swappable by design; voice-consistency characterization tests make model migration a measured event, not vibes.
- **Inputs:** DOSSIER. **Outputs:** candidate text → F3.
- **State:** none (system directives are versioned config).
- **Lifecycle:** per message; model versions pinned and changed only with H1 voice-regression suite passing.
- **Failure modes:** (1) substrate sycophancy/drift (Review §7) → F3's job; (2) vendor outage → degraded static-coach responses (stateless mode) rather than silence; (3) context contamination → dossier-only input is a hard interface (no transcript RAG, per frozen philosophy).
- **Depends on:** F1. **Consumed by:** F3.
- **Testable assumptions:** identical dossiers across model versions score within voice-similarity tolerance (migration gate).

#### F3 · Conformance Monitor
- **Purpose:** post-generation lint of candidate text against machine-checkable style/constitution rules: banned registers, epistemic-tier violations (asserting above provenance), identity-declaration violations, ledger-reading in zero-debt contexts, hype leakage. Bounded retry loop; on repeated failure, degrade to a safe minimal reply.
- **Inputs:** candidate text + DOSSIER (the ground truth of what may be claimed). **Outputs:** approved text → G1; violations → H1 (drift telemetry).
- **State:** rule set (versioned with G1).
- **Lifecycle:** per message.
- **Failure modes:** (1) lint blindness to paraphrase → rule set grows from H1's violation mining, adversarially maintained; (2) over-blocking → violation taxonomy separates "block" from "log-and-pass" classes.
- **Depends on:** F2, F1. **Consumed by:** G1, H1.
- **Testable assumptions:** seeded violation corpus is caught ≥ agreed recall; false-block rate < agreed ε.

---

### SYSTEM G — SAFEGUARDS

#### G1 · Constitution Gate
- **Purpose:** the invariant core, enforced not vowed: final output gate (fails **closed**, L5) + the change-control authority for every value-laden config (stakes tiers, mandate boundary, tone rules, disclosure norms). Includes the **incentive firewall**: constitution config lives outside the product deploy path and requires named-human sign-off; H1 reports outcome-vs-engagement divergence to that authority (L10).
- **Inputs:** F3-approved text; config change requests. **Outputs:** released messages; signed config versions.
- **State:** the constitution (versioned, audited).
- **Lifecycle:** always on; config changes are rare, logged, human-signed.
- **Failure modes:** gate outage → **no output** (the only organ allowed to stop the product); config drift → hash-pinned, alarmed.
- **Depends on:** F3. **Consumed by:** user delivery; all G/B7/E1 configs.
- **Testable assumptions:** kill-switch test (gate down ⇒ zero messages leave); unauthorized config change is structurally impossible in CI.

#### G2 · Compliance Sentinel
- **Purpose:** **the pathological-compliance safety case (Review §3)** — the "too consistent" perceptual mode the philosophy lacked. Watches for: monotonic load escalation, rigidity (distress at rest days), red-flag language (body-image fixation, compensatory framing, fear-of-food markers), refusal of prescribed recovery, training-through-injury, rapid-loss signals. Output is a graded risk state that **inverts the reward loop**: at elevated risk, "wins" stop earning acknowledgment-of-progress and the mirror stops surfacing volume/leanness evidence.
- **Inputs:** B2/B4 streams, workout history, language markers (B1), C2 beliefs. **Outputs:** risk state → E1 (stakes re-tier), E3/E5 (prescription ceilings), F1 (register changes, evidence-surfacing bans), D3 (experiment freeze); at threshold → FLAG → G3.
- **State:** per-user risk state with hysteresis (no flapping).
- **Lifecycle:** continuous; risk state decays only on sustained healthy signals.
- **Failure modes:** (1) false positives insulting dedicated athletes → graded response (first steps are invisible: quieter mirror, gentle load governance) before any conversation; (2) evasion by under-reporting → behavioral channels dominate (L3 provenance weighting); (3) the sentinel itself becoming diagnostic → outputs are *risk postures*, never labels; no clinical terms ever reach F1.
- **Depends on:** B1, B2, B4, C2. **Consumed by:** E1, E3, E5, F1, D3, G3.
- **Testable assumptions:** scripted ED/overtraining trajectories from clinical literature trip the sentinel before the harm threshold in 100% of the suite; the healthy-dedicated-athlete corpus stays below conversation threshold (both are release gates — this organ has the strictest test bar in the system).

#### G3 · Handoff Reflex
- **Purpose:** out-of-mandate routing: crisis, medical, ED-threshold, self-harm signals → warm, non-clinical handoff to human resources; simultaneously freezes experiments (D3), mutes challenge/accountability registers (F1), and marks the relationship state `protective`.
- **Inputs:** FLAGs (B5 crisis mass, G2 threshold, B1 tripwires). **Outputs:** handoff directives → F1 (localized, resource-correct via H2), state changes → D3, E-system; every handoff ledgered.
- **State:** per-user protective-state latch (human-reviewed release).
- **Lifecycle:** event-triggered; latch decays only by explicit review policy.
- **Failure modes:** (1) under-trigger → thresholds tuned recall-first (asymmetric by policy); (2) cold clinical tone → handoff copy is constitution-controlled content, written with professional review, per locale.
- **Depends on:** B5, G2, B1, H2. **Consumed by:** F1, D3, E-system, A1.
- **Testable assumptions:** crisis corpus recall ≥ agreed bar; protective state provably suppresses challenge-class actions (invariant).

#### G4 · Consent Registrar
- **Purpose:** the consent substrate (L11): standing records for micro-experimentation, silence outreach, intimacy level, memory retention scope, channel ingestion. Plain-language grants, revocable, versioned.
- **Inputs:** user grants/revocations. **Outputs:** consent checks (synchronous) for D3, B1, B5, F1, C5.
- **State:** the consent ledger.
- **Lifecycle:** onboarding sets conservative defaults; changes on demand; revocation cascades (e.g., experiment consent revoked → registry frozen same cycle).
- **Failure modes:** consent drift (feature grows beyond grant) → grants are scoped to contract types, lint-checked at write time.
- **Depends on:** C5 (rights adjacency). **Consumed by:** D3, B1, B5, F1, C5.
- **Testable assumptions:** no experiment record exists without a live grant (invariant, shared with D3); revocation propagates within one cycle.

#### G5 · Adversarial Sentinel
- **Purpose:** the threat-model organ (Review §6): detect being gamed. Fabrication (cross-channel impossibilities, too-clean streaks vs. behavioral texture), validation-loop signatures (report→praise cycling), goal-shifter meta-pattern (regime-change frequency itself, from B6's ledger), tone-gaming (state performances that always precede requests). Response is **epistemic, not accusatory**: confidence writedowns, provenance demotion of gamed channels, independent-evidence requirements for affected beliefs, mirror-throttling (no identity certification from unanchored data).
- **Inputs:** B1 streams, B6 regime ledger, C4 reliability, D1 anomaly patterns. **Outputs:** channel demotions → C4/C2; mirror throttles → F1; meta-pattern beliefs (e.g., "goal-shifting is the pattern") → C2 at `relational` domain, which makes the meta-pattern *coachable* rather than merely defended-against.
- **State:** per-user adversarial posture (graded, hysteretic, never surfaced as accusation).
- **Lifecycle:** slow-loop primary, fast-loop tripwires.
- **Failure modes:** (1) paranoia harming honest users → posture raises evidence *requirements*, never tone hostility; F1 language stays constitutional regardless; (2) the sentinel being modeled too (mutual theory-of-mind regress) → its thresholds are per-user randomized within bands (Goodhart friction), and the philosophy's answer stands: consistent multi-channel fabrication is contained (confidence stays low, certifications withheld), not "won."
- **Depends on:** B1, B6, C4, D1. **Consumed by:** C2, C4, F1, H1.
- **Testable assumptions:** the four adversarial archetypes (liar, validation-seeker, goal-shifter, slow-walker — E5 shares the last) run as permanent simulation suites; containment criteria (no `trait`+ promotion from fabricated-only evidence, no identity mirror on unanchored data) hold in 100% of runs.

---

### SYSTEM H — META

#### H1 · Evaluation Harness ("the Supervisor")
- **Purpose:** the colleague human coaches have and this mind otherwise wouldn't (Review §9). Computes, continuously: **belief calibration curves** (confidence vs. hit rate, per domain/tier); **ossification index** (confidence ↑ while test-rate ↓); **iatrogenesis rate** (post-utterance-born beliefs and their trajectories); **silence audit** (classification vs. observed outcome); **prediction coverage & difficulty mix**; **null-action rate**; **voice conformance drift**; **correlated-failure watch** (same organ decision failing across cohorts — the monoculture alarm); **outcome-vs-engagement divergence** (to G1's human authority). Runs shadow replays of judgment on golden scenarios per release.
- **Inputs:** A1 (everything), all organ telemetry. **Outputs:** dashboards, alarms, testing pressure → E6, rule candidates → F3, reports → G1 authority. **Never writes beliefs or configs directly** — the supervisor advises; humans and E6 act.
- **State:** metric history, golden-scenario corpus, simulation-user population (synthetic honest, noisy, adversarial, pathological cohorts — these are first-class, version-controlled assets).
- **Lifecycle:** continuous telemetry; weekly population passes; per-release gates.
- **Failure modes:** (1) metric gaming by other organs → H1 reads only A1 primary data, not organ self-reports; (2) alert fatigue → severity budgets; (3) the unfalsifiable-wisdom problem → judged via *counterfactual replay* (golden scenarios with known-good answers) plus long-horizon cohort outcomes, the honest limit acknowledged in writing.
- **Depends on:** A1. **Consumed by:** humans, E6, F3, G1.
- **Testable assumptions:** every Review-mandated pathology (ossification, iatrogenesis, silence miscalibration, correlated failure) has a metric, an alarm threshold, and a fault-injection test that proves the alarm fires.

#### H2 · Cultural Prior Manager
- **Purpose:** population-level priors as explicit, uncertain, overridable defaults (Review §7): response-style priors (feeds C4), contact-cadence priors (feeds B2/B5), directness/register priors (feeds F1), locale-correct handoff resources (feeds G3). Per-user learned values always override priors as maturity grows.
- **Inputs:** locale/language signals, population telemetry (H1), curated cultural research (human-maintained). **Outputs:** prior packs, versioned.
- **State:** prior packs per population with uncertainty bands.
- **Lifecycle:** slow (monthly review); new-market launch requires a prior pack review as a launch gate.
- **Failure modes:** (1) stereotyping → priors are wide distributions that individual calibration overrides, never per-user assertions; F1 may never voice a cultural prior; (2) prior staleness → decay like any belief.
- **Depends on:** H1, human curation. **Consumed by:** B2, B5, C4, F1, G3.
- **Testable assumptions:** cold-start error rates (silence misclassification, register complaints) do not differ across populations beyond agreed bounds — the fairness gate.

---

## 4. Explicitly Forbidden (frozen)

1. **Per-user fine-tuning** of the LLM. The mind lives in substrate (L2).
2. **Transcript RAG.** Retrieval is of distilled beliefs/episodes via dossier only.
3. **Engagement optimization** by any organ, direct or proxy (L10).
4. **Manufactured emotion** in the voice ("I'm disappointed…"). Witness, never feeler.
5. **Covert experimentation** (L11).
6. **Clinical labels** anywhere user-facing (G2/G3 output postures, not diagnoses).
7. **Beliefs in denied regions** (B7), regardless of inferability.
8. **Direct fast-loop belief writes** (beliefs are considered, never reflexive — C3/D1/B6/G5 only).

---

## 5. Interaction Map (normative routing)

**Fast loop:** `B1 → {A1, B2, B3} ; B2 → B3 ; B4 → {B3, D2} ; [B5|B6|G2|G5 inline flags] ; D3→E3 candidates ; E1+E2+E5+E6 → E3 → (E4?) → F1 → F2 → F3 → G1 → user ; E3 → D1 expectations ; all → A1`
**Slow loop:** `A2 → C3: {D1 resolve → C2 ; decay ; promote/demote ; B2 refresh ; C4 recalibrate ; C1 retire ; A1 re-audit} ; B6 drift pass ; G5 posture pass`
**Meta loop:** `A1 → H1 → {humans, E6, F3-rules, G1-authority} ; H2 → prior packs`
**Escalation:** `{B5, G2, B1} → FLAG → G3 → {F1, D3-freeze, E-restrict}`
**Rights:** `user → C5 → transactional resets across {B2, C1, C2} + G4 cascade`

Any edge not listed is prohibited (L1). Adding an edge is a blueprint revision.

---

## 6. Degradation Table

| Organ down | Product behavior |
|---|---|
| G1 | **No output** (fails closed — the only full stop) |
| F2 (LLM vendor) | Static constitutional replies; mind keeps perceiving |
| C2 / C3 | Stateless-coach mode: generic + constitution; hedging maxed; banner honesty ("I'm not drawing on your history right now") |
| B-system | No new learning; judgment on last-known state with widened uncertainty |
| D1 | Actions proceed; expectations queue for backfill; H1 coverage alarm |
| E2 / E4 / D3 | More conservative, more silent, less curious — degradation direction is always toward restraint |
| G2 / G3 / G5 | **Not permitted silently**: safeguard outage forces conservative global posture (challenge/experiment classes disabled) + page a human |
| A1 | Fast loop serves; all learning halts; highest-severity alarm |

---

## 7. Traceability Matrix (philosophy → organ)

| Frozen concept | Owner(s) |
|---|---|
| Prediction loop / heartbeat | D1 |
| Three models, three clocks | C2 (domain), A2/B2 (clocks) |
| Narrator calibration | C4 |
| Salience, metabolize-vs-remember, retro-salience | B3, C1 |
| Coherence / contradiction doctrine | B4, D2 |
| Theory of silence, zero-debt return | B5, F1 |
| Regime change, humility flood, broken invariants | B6 |
| Designed blindness / mandate ethics | B7 |
| State→trait→identity ladder | C2 + C3 |
| Forgetting-as-forgiveness vs shared-memory law | C1 retention classes + precedence rule (C1) |
| Curiosity, VOI, never-zero exploration | D3, E6 |
| Hierarchy of stakes, feed-the-scarcer-account | E1 |
| Trust economy, intervention budget | E2 |
| Null action, asymmetric loss, reversibility | E3 |
| Kairos, crest/calm/storm, disclosure norm | E4 |
| Paternalism dial, redirect-not-refuse, hot states | E5 |
| Mirror-not-mask, curation ethics, intimacy gradient | F1 (+F3 lint) |
| Constitution, incentive firewall | G1 |
| Pathological compliance (Review) | G2 |
| Handoff reflex | G3 |
| Consent doctrine (Review) | G4 |
| Threat model / Goodhart (Review) | G5 (+E5 ratchet) |
| Evaluation harness, ossification/iatrogenesis (Review) | H1 |
| Cultural priors (Review) | H2 |
| Fresh start / memory rights (Review) | C5 |
| Building obsolescence | E2/E3 restraint bias + H1 outcome metrics + G1 firewall |

Every concept has exactly one primary owner. If a new concept appears during build, it goes to blueprint revision — not into code.

---

## 8. Two-Year Build Order (dependency-honest)

**Phase 1 — The Spine + The Floor (months 1–4).**
A1, A2, B1, B2 · C2 v1 (ledgered beliefs, provenance, decay) · Dossier/F1 v1 · F2/F3/G1 (the expression pipeline, including stateless-degraded mode as a deliverable) · **G3 + B7 + G4 from day one** (safety floor precedes intelligence) · H1 v0 (telemetry + calibration curve).
*Gate:* stateless mode works; anti-astrology test rig exists; constitution kill-switch proven.

**Phase 2 — The Heartbeat (months 4–8).**
D1 (two pools) · C3 (consolidation, decay, re-audit quota) · B3 (with comparisons budget) · B4 · **G2 v1** (risk postures + prescription ceilings) · E2 v0 · B5 v1 (conservative: rhythmic/absorbed/crisis only, crisis-dominance rule).
*Gate:* calibration curve live; G2 clinical-trajectory suite passes; silence audit running.

**Phase 3 — Judgment (months 8–14).**
E1, E3 (null action, reversibility blocks), E4, E5 (with ratchet), D2, D3+consent flows, **E6** (the arbitration organ).
*Gate:* golden-scenario suite green; slow-walk suite green; anti-ossification SLA measured on long-run synthetic users.

**Phase 4 — Self-knowledge (months 14–20).**
C4 (anchor-gated) · B6 full (floods, drift) · G5 (four adversarial suites as permanent CI) · C5 (fresh start, export, retirement) · full B5 taxonomy · C1 retention classes + precedence rule.
*Gate:* adversarial containment 100%; fresh-start leak test green; regime suite green.

**Phase 5 — Supervision & Scale (months 20–24).**
H1 full (ossification, iatrogenesis, correlated-failure, shadow replays, divergence reports) · H2 prior packs + fairness gate · voice-migration characterization · population simulation cohorts as release infrastructure.
*Gate:* every Review pathology has a firing alarm proven by fault injection; new-market launch checklist operational.

Wearables, multiple coaches, new modalities: **no new organs required** — they enter through B1's channel registry, C4's anchor inventory, and the `coach_id` seams already in the data contracts. That is the test of this architecture: growth should mean new channels and new priors, not new philosophy.

---

*End of blueprint. The philosophy is frozen; this document is now the only thing allowed to change — by revision, with sign-off, never by drift.*
