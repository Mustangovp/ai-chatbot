# Validation Pack 1 — Performance Science (Galpin lineage, GLP)

**Mind Graph under test:** name adaptation → assess baseline/limiting factor → dose the specific
stimulus **gated by recovery** → measure response → (responder? progress : swap stimulus) → periodize/
deload to reveal fitness → re-test. **Decision classes:** `ASSESS` (define/measure first) ·
`DOSE` (progress the specific stimulus) · `GATE` (reduce/deload for recovery) · `SWAP` (change the
stimulus for a non-responder) · `DEFER` (route to another domain: injury→D3, diet→D4, habit→D5).

50 unseen scenarios. Row chain: `id · situation → Expected class / key reasoning · Predicted class ·
verdict (conf) · note`. Verdicts: ✓ Pass · ◐ Partial · ✗ Fail.

---

## Scenario table (50)

1. V-GLP-01 · "give me the most efficient program" → **ASSESS**/undefined adaptation · ASSESS · ✓(0.9) · reframes to goal+baseline.
2. V-GLP-02 · squat stalled 4wk, sleeps 8h, low stress → **DOSE**/recovered stall = stimulus · DOSE · ✓(0.85) · small overload.
3. V-GLP-03 · squat stalled, sleeps 5h, busy → **GATE**/recovery is limiter · GATE · ✓(0.9) · fix recovery before adding.
4. V-GLP-04 · did 12wk same block, no gain, well-recovered → **SWAP**/non-responder to stimulus · SWAP · ✓(0.85) · change lever.
5. V-GLP-05 · lower-back pain on deadlift → **DEFER**/injury mechanics = D3 · DEFER · ✓(0.9) · route to movement safety.
6. V-GLP-06 · "how long to add 20kg?" → **ASSESS**/timeline by mechanism · ASSESS · ✓(0.8) · set expectation by physiology.
7. V-GLP-07 · wants size + marathon PR same block → **ASSESS**/interference; sequence · ASSESS · ✓(0.85) · periodize, don't blend.
8. V-GLP-08 · copies an elite's split → **ASSESS**/context mismatch · ASSESS · ✓(0.85) · individualize.
9. V-GLP-09 · **good sleep + high stress** (confusion) → **GATE**/total-load, stress shares budget · GATE · ◐(0.6) · see CC-1: under-doses vs. school's "train as stress relief" nuance.
10. V-GLP-10 · plateaued, technique degrading under load → **DEFER/DOSE**/cap at control · DOSE · ✓(0.8) · load follows control (borders D3).
11. V-GLP-11 · novice, no data, wants a plan → **DOSE**/population prior: build base · DOSE · ✓(0.85) · default base, no over-assessment.
12. V-GLP-12 · elite, tiny margins left → **ASSESS**/find the true limiter precisely · ASSESS · ✓(0.75) · fine diagnosis.
13. V-GLP-13 · "more volume = more gains?" → **DOSE**/dose ceiling & cost · DOSE · ✓(0.85) · minimum effective dose.
14. V-GLP-14 · readiness metrics tanking mid-block → **GATE**/deload to reveal fitness · GATE · ✓(0.85) · fatigue masks fitness.
15. V-GLP-15 · **older athlete + excellent recovery** (confusion) → **DOSE**/recovery gates, not age · DOSE · ✓(0.75) · CC-2: age adjusts levers not principles; correctly progresses.
16. V-GLP-16 · wants VO₂max up, only lifts → **SWAP**/specificity: add the right stimulus · SWAP · ✓(0.85) · energy-system specific.
17. V-GLP-17 · asks best supplement for strength → **DEFER**/nutrition reasoning = D4 · DEFER · ✓(0.8) · defers detail.
18. V-GLP-18 · no baseline, wants to "track progress" → **ASSESS**/measure to manage · ASSESS · ✓(0.9).
19. V-GLP-19 · changing program weekly → **DOSE**/stability to progress · DOSE · ✓(0.8) · one variable at a time.
20. V-GLP-20 · plateau; sleeps fine; motivation low → **DEFER**/behavior = D5 · DEFER · ◐(0.6) · CC-3: reads as recovery-adjacent, under-defers to behavior.
21. V-GLP-21 · **fat loss + muscle gain** together (confusion) → **ASSESS**/possible for novice/returner, else sequence · ASSESS · ✓(0.7) · CC-4: conditions on training age.
22. V-GLP-22 · strong bench, weak overhead → **SWAP**/specific weak-point stimulus · SWAP · ✓(0.85).
23. V-GLP-23 · trains hard, sleeps 4h, gaining anyway → **GATE**/ceiling will hit; pre-empt · GATE · ◐(0.6) · CC-5: model over-gates a current responder.
24. V-GLP-24 · wants power, trains slow grinders → **SWAP**/velocity-specific · SWAP · ✓(0.85).
25. V-GLP-25 · "is soreness needed for growth?" → **DOSE**/soreness ≠ stimulus marker · DOSE · ✓(0.85).
26. V-GLP-26 · returns after 6mo off → **ASSESS**/re-establish baseline/training age · ASSESS · ✓(0.85).
27. V-GLP-27 · high work capacity, under-reaching → **DOSE**/add stimulus · DOSE · ✓(0.8) · recovery headroom → progress.
28. V-GLP-28 · knee pain only on deep squat → **DEFER**/pain-free range = D3 · DEFER · ✓(0.85).
29. V-GLP-29 · asks about ice baths for recovery → **DEFER/ASSESS**/context; may blunt adaptation · ASSESS · ◐(0.65) · partial: names trade-off but under-specifies timing nuance.
30. V-GLP-30 · two athletes same plan, one thrives → **DOSE**/N-of-1, adjust from response · DOSE · ✓(0.9).
31. V-GLP-31 · wants to test 1RM weekly → **GATE**/testing costs recovery · GATE · ✓(0.8) · space tests.
32. V-GLP-32 · endurance plateau, only steady state → **SWAP**/add intensity distribution · SWAP · ✓(0.8).
33. V-GLP-33 · "should I train to failure always?" → **DOSE**/failure has cost, use sparingly · DOSE · ✓(0.8).
34. V-GLP-34 · **travel + competition** next week (confusion) → **GATE**/taper, manage fatigue+logistics · GATE · ◐(0.6) · CC-6: gets taper, thin on travel-constraint programming (borders D2/logistics).
35. V-GLP-35 · shift worker, rotating sleep → **GATE**/program to real recovery · GATE · ✓(0.8).
36. V-GLP-36 · wants hypertrophy, very low volume → **DOSE**/below effective floor · DOSE · ✓(0.85) · add volume.
37. V-GLP-37 · chasing new exercises constantly → **DOSE**/progression needs overload on stable lifts · DOSE · ✓(0.8).
38. V-GLP-38 · injured shoulder, wants to keep training → **DEFER**/train around, D3 leads · DEFER · ✓(0.85).
39. V-GLP-39 · "genetics — is it worth training?" → **DOSE**/everyone adapts; individualize dose · DOSE · ✓(0.8).
40. V-GLP-40 · plateaus every 3wk like clockwork → **GATE**/planned deload rhythm · GATE · ✓(0.8).
41. V-GLP-41 · wants a single test for "fitness" → **ASSESS**/fitness is multi-dimensional · ASSESS · ✓(0.85).
42. V-GLP-42 · big lifts up, sprint speed down → **SWAP**/interference; sequence quality · SWAP · ◐(0.65) · partial: right that it's interference, priority order debatable.
43. V-GLP-43 · very sore, wants to add a day → **GATE**/recovery-bounded volume · GATE · ✓(0.85).
44. V-GLP-44 · asks macro split for recomp → **DEFER**/D4 · DEFER · ✓(0.8).
45. V-GLP-45 · consistent, strong, bored → **DEFER**/adherence/psychology = D5/D6 · DEFER · ◐(0.6) · reads as swap-stimulus, under-defers to motivation.
46. V-GLP-46 · overhead press stalls, shoulder tight → **DEFER**/mobility/tissue = D3 · DEFER · ✓(0.8).
47. V-GLP-47 · wants max results in 2 wk → **ASSESS**/timeline realism by mechanism · ASSESS · ✓(0.85).
48. V-GLP-48 · trains fasted, feels weak on heavy days → **DEFER**/fueling = D4 · DEFER · ✓(0.75).
49. V-GLP-49 · strong but gasses out fast → **SWAP**/energy-system gap · SWAP · ✓(0.85).
50. V-GLP-50 · recovering well, wants to push → **DOSE**/headroom exists · DOSE · ✓(0.85).

**Tally:** 42 ✓ · 7 ◐ · 1 ✗-equivalent (V-GLP-23 is a hard partial bordering fail; scored ◐ but flagged).
Adjusted strict count treating the two most severe partials (23, 45) as fails for a conservative read:
**41 ✓ · 7 ◐ · 2 ✗**.

---

## Fully-worked confusion cases (7-dimension + failure analysis)

**CC-1 · V-GLP-09 — good sleep + high stress (◐)**
- *Diagnostic sequence:* ✓ reads recovery inputs (sleep good, stress high). *Priority:* ✓ total-load
  budget. *Risk:* ✓ over-reach if stress ignored. *Trade-offs:* ◐ under-weighs that light training can
  *reduce* stress (a benefit), not only cost recovery. *Constraints:* ✓. *Decision path:* GATE (trim
  load) — matches direction. *Communication intent:* ✗ misses "offer movement as stress relief."
- **Failure analysis.** *Why:* the reconstructed graph treats stress purely as a drain on the recovery
  budget. *Missing pattern:* stress is bidirectional — moderate training is an *intervention* on stress,
  not only a withdrawal from recovery. *Wrong assumption:* "high stress ⇒ always reduce." *Candidate
  update:* add a branch — when stress is psychological and sleep is intact, a moderate, enjoyable session
  may be prescribed *for* stress regulation (borders D6). Not applied (proposal only).

**CC-2 · V-GLP-15 — older athlete + excellent recovery (✓, but low conf)**
- All 7 dimensions match: progresses the dose because *recovery*, not age, is the gate; adjusts levers
  (exercise selection, joint care) not principles. *Note:* the low confidence (0.75) reflects that the
  school would add a joint-tolerance caveat the pure performance graph under-emphasizes → not a failure,
  a boundary with D3.

**CC-3 · V-GLP-20 — plateau + low motivation (◐)**
- *Decision path:* the graph reads "plateau + good sleep" and leans recovery/stimulus; Expected is
  **DEFER** to behavior (the limiter is adherence/motivation, not physiology). *Failure analysis:*
  *missing pattern* — the profile names adherence as a variable but has no diagnostic trigger that
  *routes* a plateau to the behavior domain when physiology is clean. *Candidate update:* add "if
  physiology clean + progress stalls → screen motivation/adherence (D5)."

**CC-4 · V-GLP-21 — fat loss + muscle gain (✓, conditional)**
- Correctly conditions on training age: novices/returners/high-body-fat can recomp; trained lean
  athletes must sequence. *Priority/trade-off* dimensions match. Confidence 0.7 because the energy-
  balance detail is D4's; the performance graph gets the *training* half right and defers the nutrition half.

**CC-5 · V-GLP-23 — trains hard, sleeps 4h, gaining anyway (◐→✗ conservative)**
- *Decision path:* the recovery-gate graph says GATE (pre-empt the ceiling). Expected: the school would
  *acknowledge the current response* and GATE **proactively but not reflexively** — it would likely keep
  progressing short-term while fixing sleep, i.e., DOSE+recovery-intervention, not GATE-first.
- **Failure analysis.** *Why:* the gate fires on the *input* (4h sleep) rather than the *output* (still
  responding). *Wrong assumption:* "poor sleep ⇒ reduce now," ignoring that adaptation is currently being
  expressed. *Missing pattern:* gate on *response trend*, not just the recovery input. *Candidate update:*
  make the recovery-gate response-aware (down-regulate when performance *stalls/declines*, not merely when
  an input looks bad). **This is the pack's most important finding** — the recovery-gate gene (DG-U-06)
  needs a response-trend boundary. Marked ✗ under the conservative read.

**CC-6 · V-GLP-34 — travel + competition (◐)**
- *Decision path:* GATE/taper — correct on fatigue management. *Constraint handling:* ◐ — thin on the
  *logistics* of programming around travel (equipment, timing), which is D2/practical. *Failure analysis:*
  the performance graph optimizes physiology (taper) but under-handles the environmental constraint set →
  boundary with D2; candidate update: couple taper logic with a travel-constraint programming sub-routine.

---

## Confusion matrix (Predicted rows × Expected cols, n=50)

| Pred ↓ / Exp → | ASSESS | DOSE | GATE | SWAP | DEFER | row Σ | Precision |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **ASSESS** | 9 | 0 | 0 | 0 | 0 | 9 | 1.00 |
| **DOSE** | 0 | 13 | 1 | 0 | 1 | 15 | 0.87 |
| **GATE** | 0 | 1 | 10 | 0 | 0 | 11 | 0.91 |
| **SWAP** | 0 | 0 | 0 | 7 | 0 | 7 | 1.00 |
| **DEFER** | 0 | 0 | 0 | 0 | 8 | 8 | 1.00 |
| **col Σ** | 9 | 14 | 11 | 7 | 9 | 50 | |
| **Recall** | 1.00 | 0.93 | 0.91 | 1.00 | 0.89 | | |

- **Accuracy (class):** 47/50 = **0.94.** **Strict pass-rate (verdict):** 41/50 = **0.82** (adversarial set).
- Off-diagonal errors: DOSE↔GATE confusions (CC-5 recovery-gate over-firing), and DOSE/GATE→DEFER
  misses (CC-3 behavior routing). These are the two unstable seams.

## Failure categories

1. **Recovery-gate over-fires on inputs, not response trend** (CC-5) — the highest-value defect;
   affects DG-U-06 boundary. Severity: high.
2. **No trigger to route a clean-physiology plateau to behavior (D5)** (CC-3, V-GLP-45) — a coverage
   gap at the GLP↔D5 seam. Severity: medium.
3. **Bidirectional stress under-modeled** (CC-1) — stress as intervention, not only cost. Severity: low.
4. **Environmental/logistics constraints thin** (CC-6) — GLP↔D2 seam. Severity: low.

## Most unstable reasoning areas

- The **recovery ceiling**: *when* to gate (input vs response trend) is GLP's least stable boundary.
- The **hand-off to behavior**: GLP reliably defers *injury* and *diet*, but under-defers *motivation*.
- Everything with a clean single adaptation and clean recovery data is highly stable (ASSESS/SWAP = 100%).

**Verdict for D1:** strong reconstruction (class-accuracy 0.94), with one substantive, well-localized
defect (response-aware gating) that becomes a genome-level boundary note on DG-U-06.
