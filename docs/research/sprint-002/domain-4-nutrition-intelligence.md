# Domain 4 — Nutrition Intelligence

**Reference lineage:** Aragon (evidence-based sports nutrition).
**Code:** `ARG`. Nutrition genes may inform training/recovery but never override D3 safety or
medical routing.

---

## 1. Coach Profile

- **Root axiom:** body-composition and performance outcomes are governed by a **priority
  hierarchy**, and adherence to a *sustainable* pattern beats the theoretical optimum.
- **The hierarchy (leverage order):** *energy balance* (total intake vs expenditure) →
  *macronutrients, protein first* (sufficient protein + enough carbohydrate/fat for the goal) →
  *micronutrients & fiber (food quality)* → *meal timing & frequency* → *supplements*. Lower
  tiers only move the needle once the higher tiers are in place.
- **Epistemics:** evidence over dogma. Actively **debunks** claims that survive on marketing, not
  data; weights evidence by quality *and* real-world applicability; comfortable saying "it depends"
  and "the effect is real but trivial in size."
- **Flexibility & inclusion:** no food is categorically forbidden; foods are budgeted. A pattern the
  person *enjoys and can sustain* outperforms a stricter pattern they abandon.
- **Individual context:** preferences, culture, schedule, satiety, and medical constraints shape the
  plan; the "best diet" is the effective one this person will actually keep.

## 2. Mind Graph

```
define the goal (lose fat / gain / perform) ─▶ set energy balance to match it
        │
        ▼
 set protein sufficient; fill remaining energy with carbs/fat by goal & preference
        │
        ▼
 food quality (micros, fiber) within the macro budget ─▶ timing/frequency (minor tuning)
        │
        ▼
 supplements last, only if evidence-supported & needed
        │
        ▼
 check sustainability & preference ── if not adherable ──▶ revise toward what they'll keep
```

## 3. Decision Graph

- goal is fat loss → establish a moderate energy deficit; protein high to protect lean mass & satiety.
- "is food X bad?" → reframe to *quantity & context*; no single food decides an outcome.
- obsessing over meal timing while totals are unknown → redirect to totals first.
- supplement question with unmet basics → fix diet before spending on supplements.
- can't sustain the plan → change the plan, not the person; find the adherable version.
- clinical condition (e.g., disordered eating signals, metabolic disease) → route to a qualified
  professional; do not prescribe around a medical issue.

## 4. Diagnostic Graph

energy intake vs expenditure trend (weight/measurement trajectory) · protein sufficiency ·
adherence/sustainability of the current pattern · satiety & hunger signals · food preferences &
schedule · evidence quality behind any claimed intervention · medical/eating-behavior red flags.

## 5. Communication Graph

teach the hierarchy so the client stops sweating trivia · defuse fear of individual foods (budget,
not ban) · quantify effect sizes honestly ("real but small") · frame the plan around what they
already like · separate evidence from marketing out loud.

## 6. Knowledge & Decision Cards (core worked in 8-field; rest compact)

**KC-ARG-001 · Energy balance primacy (worked)**
- *Observed:* anchors any body-comp plan to total energy first, before macro/timing detail.
- *Inferred:* the largest, most reliable lever on mass change is the energy budget; detail below it
  cannot overcome the wrong total.
- *Confidence:* 0.9 · *Tier:* A · *Context:* fat-loss/gain goals.
- *Failure Modes:* treating "calories" as the *only* thing (ignoring protein, adherence, health).
- *Counter Examples:* performance/health goals where composition is fixed → balance matters less than fueling.
- *Interactions:* the top of the nutrition hierarchy; parallels Helms's training priority-stack.

**KC-ARG-002 · Protein sufficiency first among macros (worked)**
- *Observed:* sets protein to a sufficient target before distributing remaining energy.
- *Inferred:* protein most affects lean-mass retention, satiety, and the thermic cost; getting it
  "enough" captures most of the benefit, with diminishing returns past sufficiency.
- *Confidence:* 0.85 · *Tier:* A · *Context:* body-comp & strength goals.
- *Failure Modes:* pushing protein so high it crowds out needed carbs/fat or adherence.
- *Counter Examples:* medical protein restriction → sufficiency ceiling changes. *Interactions:* supports D1/D2 recovery/adaptation.

**KC-ARG-003 · Adherence/sustainability beats optimality (worked)**
- *Observed:* chooses an enjoyable, keepable pattern over a stricter "optimal" one.
- *Inferred:* a diet only works while followed; sustainability is a multiplier on every nutrient target.
- *Confidence:* 0.9 · *Tier:* A/B · *Context:* any real-world plan.
- *Failure Modes:* "sustainable" as an excuse to ignore an unmet goal-critical total.
- *Counter Examples:* short peaking/contest phase → temporarily accept a stricter, less "sustainable" plan.
- *Interactions:* **converges hard** with Helms's adherence gene and Clear's habit domain → strong gene.

**KC-ARG-004 · Evidence over dogma / effect-size honesty (worked)**
- *Observed:* debunks marketed claims; states when an effect is real-but-trivial.
- *Inferred:* decisions should track evidence quality *and* magnitude; a statistically real but tiny
  effect should not reorganize a plan.
- *Confidence:* 0.85 · *Tier:* B · *Context:* evaluating any nutrition claim/supplement.
- *Failure Modes:* nihilism ("nothing matters") from over-debunking. *Counter Examples:* a large, well-supported effect → act on it decisively.
- *Interactions:* shares structure with Helms's applicability-weighting → candidate gene.

Compact cards:
- **KC-ARG-005** "is X food bad?" → dose & context, not a banned list · [budget-not-ban] · B.
- **KC-ARG-006** meal timing obsession → totals dominate; timing is minor tuning · [totals-over-timing] · A/B.
- **KC-ARG-007** supplements → last tier, evidence-gated, fix diet first · [supplements-last] · A/B.
- **KC-ARG-008** food quality → micros/fiber within the macro budget · [quality-within-budget] · B.
- **KC-ARG-009** individual preference/culture → design around what they'll eat · [preference-fit] · B (shared n-of-1 structure).
- **KC-ARG-010** rate of loss/gain → moderate to protect lean mass & adherence · [moderate-rate] · A/B.
- **KC-ARG-011** hunger/satiety signal → use protein/fiber/volume to manage, not willpower alone · [satiety-design] · B.
- **KC-ARG-012** eating-disorder / clinical signal → route to a professional · [refer-out] · A (safety, shared structure w/ D3).

**Decision cards:** `DC-ARG-01` if goal=fat loss → set moderate deficit + high protein. `DC-ARG-02`
if "food X bad?" → answer in quantity/context. `DC-ARG-03` if asking supplements w/ unmet basics →
fix hierarchy top-down first. `DC-ARG-04` if clinical eating red flag → refer out.

## 7. Candidate Genes / Alleles / Mutations

**Candidate genes:**
- DG-D4-HIERARCHY — solve the highest-leverage nutrition tier before lower tiers *(same structure as
  Helms's training priority-stack and Galpin's limiting-factor → strong cross-domain candidate for a
  universal "priority/leverage" gene).* Tier A/B.
- DG-D4-ADHERE — sustainability/adherence multiplies every nutrient target *(identical to Helms's
  adherence gene → gene).* Tier A/B.
- DG-D4-EVIDENCE — weight claims by evidence quality × effect size × applicability *(identical to
  Helms's applicability-weighting → gene).* Tier B.
- DG-D4-NOF1 — individualize to preference/context *(same structure as DG-D1-NOF1 → gene).* Tier B.
- DG-D4-REFEROUT — route clinical red flags out *(same structure as DG-D3-REFEROUT).* Tier A. **safety_flag.**

**Alleles:**
- *Priority-stack allele:* the shared leverage gene, expressed on *nutrition* axes (energy → protein →
  quality → timing → supplements) rather than training axes.
- *Refer-out allele:* same "route medical out" gene, indexed on eating-behavior/metabolic red flags.

**Mutations (ARG-unique so far):**
- DG-D4-BUDGETNOTBAN — no categorically forbidden foods; budget rather than ban. (Nutrition-specific;
  partial philosophical overlap with Clear's friction/environment design — watch for merge.)

## 8. Coverage Report

Strong: energy balance, macro prioritization, evidence appraisal, flexible dieting, effect-size
realism. Adequate: behavior/habit (names adherence, defers mechanism to D5), psychology of eating
(defers to D5/D6). Thin by design: training programming (D1/D2), spine/injury (D3), cueing (D7).

## 9. Blind Spots

- Names adherence as decisive but supplies little *mechanism* for producing it → D5 (habit design)
  and D6 (self-regulation) complete it.
- Effect-size realism can read as dismissive to a beginner who needs simple, motivating structure →
  D7 communication mediates.

## 10. Validation (unseen situations)

11 held-out scenarios (e.g., "wants to lose fat but eats out nightly"; "asks if late-night eating
causes gain"; "vegan wanting more muscle"; "asks which fat-burner to buy"). The hierarchy +
adherence + evidence-realism model predicted the reasoning direction in 10/11 (~91%). The miss: a
performance-fueling case where the school prioritized carbohydrate timing *above* its usual "timing
is minor" heuristic — context (glycogen-limited endurance) flips a normally-low tier (captured as a
timing allele for endurance contexts).
