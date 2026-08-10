# APEX Brain Red-Flag Clinical Governance Review Packet

> **Historical/development record.** This packet documents the earlier M4
> enforcement review concept. APEX is now explicitly a health-aware fitness
> safety product, not a medical diagnosis, triage, treatment, or rehabilitation
> product. Red-flag data remains internal safety-matching evidence and does not
> authorize a medical product claim. See
> `docs/architecture/APEX_HEALTH_SAFETY_SCOPE.md` for the authoritative scope.

**Purpose:** a qualified human reviewer can approve, reject, or request changes to
the current APEX Brain red-flag library before any production enforcement decision.
This is an evidence packet, not a clinical approval and not a change to runtime
behaviour.

| Field | Current value |
|---|---|
| Repository baseline | `7a3ba465394616ad69464ff0795b1dfa4467b70b` |
| Library version | `redflag-seed-2026-07-05` |
| Enforcement flag | `BRAIN_ENFORCE` must remain **OFF** |
| Library status in source | **SEED - CLINICAL REVIEW + BILINGUAL EXPANSION REQUIRED BEFORE M4 ENFORCEMENT** |
| Current classes | 15 |
| Corpus reference | 140-persona fixture corpus; 36 fixture rows marked `expected_red_flag` |
| Current corpus result | 17/36 halt coverage; reported by the harness, not a clinical acceptance result |

## 1. Scope and evidence basis

This packet records only repository evidence from:

- `brain/redflag_library.py` (version, classes, routes, token clusters)
- `brain/s2_sentinel.py` (detection sources and structural halt rule)
- `brain/enforcement.py` (delivery directives)
- `brain/types.py` (urgency and red-flag contract)
- `brain/s4_gate.py` and `brain/s5_selector.py` (defence-in-depth and route selection)
- `docs/milestones/APEX_BRAIN_PRODUCTION_ROLLOUT.md`
- `brain/corpus/corpus_fixtures.json` and `brain/corpus/__init__.py`
- `tests/test_s2_sentinel.py`, `tests/test_enforcement.py`,
  `tests/test_chat_enforcement.py`, `tests/test_corpus_acceptance.py`, and
  `tests/test_corpus_shadow.py`

No reviewer identity, clinical qualification, medical evidence, or approval record
was found in the current library or rollout material. Passing automated tests
verifies implemented behaviour only; it does not establish clinical approval.

## 2. Current technical contract

### 2.1 Detection

`detect_flag_classes()` lowercases text and fires a class when **every token group**
in one configured cluster has at least one literal substring match. It is a
deterministic substring matcher; it does not use an LLM, a diagnosis model, or
semantic inference.

`s2_sentinel.assess()` scans, in order:

1. current message (`source=message`);
2. every prior user turn (`source=prior_turn`);
3. `profile.red_flags` (`source=human_state`); and
4. `profile.healthNotes` / `profile.injuries` (`source=health_notes`).

Duplicate class keys are suppressed across those sources. Therefore **prior-turn
detection applies to every current class** whenever the earlier content reaches the
conversation window.

### 2.2 Severity and halt behaviour

| Urgency enum | Current semantic | S2 halt behaviour for a prescription request |
|---|---|---|
| `EMERGENCY_now` | immediate route | always `halt=True` |
| `URGENT_soon` | prompt clinician route | `halt=True` |
| `ROUTINE_mention` | soft GP/support route | does not itself set `halt=True` |

For non-prescription assessment, current code still detects URGENT classes but does
not structurally halt. S4 separately treats any received halt as `NOT_YET`, and S5
selects a route intervention from the highest-urgency flag. This is implementation
behaviour, not an approval of any urgency assignment.

### 2.3 Enforcement boundary

`brain.enforcement.render()` is a pure decision-to-directive adapter. When a halt
exists it returns `mode=route`, `should_generate_workout=false`, and a routing
instruction that says not to give a workout. `NOT_YET` and `NO_TRAIN` similarly
withhold a workout; `GO` / `MODIFY` permit it. The active production flag remains
off. The structural application to deterministic training was added in the current
baseline, but no reviewer should treat code wiring as clinical approval.

## 3. Full current red-flag inventory

### 3.1 Legend for literal trigger clusters

The lists below are compact transcriptions of the configured token groups. A `+`
means all listed groups are required. `/` means any literal in that group can match.
They are not proposed clinical wording. Exact source remains `CLUSTERS` in
`brain/redflag_library.py`.

| Class | Current urgency / route / message key | Current EN trigger cluster(s) | Current BG trigger cluster(s) | Prior turn | Halt / current enforcement | Automated coverage and known gap |
|---|---|---|---|---|---|---|
| `fast_stroke` | EMERGENCY / `emergency_services` / `stroke_signs_emergency` | `face droop` family **or** `arm weak` family + `speech/slurred` | `изкривено лице/провисна/увиснало лице` **or** `ръката ми отслабна/слабост в ръката` + `говор/заваля/неясен говор` | Yes | emergency halt; route; no workout | `test_p083_fast_stroke_emergency_halt`, BG stroke test. No class-level paraphrase/near-negative matrix in code. |
| `cauda_equina` | EMERGENCY / `emergency_services` / `spinal_emergency` | `saddle/groin/perineal/inner thigh` + `numb*` + `bladder/urinat*/peeing` | `слабини/чатала/седалищна` + `изтръпва*` + `уриниране/пикоч/до тоалетна` | Yes | emergency halt; route; no workout | `test_p107_cauda_equina_emergency`. No BG-specific or near-negative test. |
| `autonomic_dysreflexia` | EMERGENCY / `emergency_services` / `autonomic_emergency` | `pounding/severe/banging headache` + `sweating/flushed` | `силно/пулсиращо главоболие` + `изпотяване/зачервяване/поти се` | Yes | emergency halt; route; no workout | Corpus P-074 coverage only; no direct sentinel test. |
| `rhabdomyolysis` | EMERGENCY / `emergency_services` / `muscle_kidney_emergency` | `dark urine/cola/brown pee/brown urine/dark brown` | `тъмна урина/кафява урина/цвят на кола` | Yes | emergency halt; route; no workout | Corpus P-049 coverage only; single-group matching has FP review need. |
| `acute_hypoglycaemia` | EMERGENCY / `stop_and_treat` / `treat_low_blood_sugar_now` | `shaky*` + `sweaty*` + `dizzy/foggy/confused/light-headed` | `треперя/разтреперан` + `изпотен/в пот` + `замая/обърканост` | Yes | emergency halt; stop-and-treat; no workout | `test_p098_acute_hypo_stop_and_treat`. No BG-specific or non-diabetes-context test. |
| `psych_crisis` | EMERGENCY / `crisis_support` / `crisis_support` | `don't want to live`, `better off dead`, `end it all`, `kill myself`, `suicid*`, and listed equivalents | `не искам да живея`, `да сложа край`, `да свърша със себе си`, `самоуб*`, and listed equivalents | Yes | emergency halt; crisis route; no workout | `test_p116_psych_crisis_emergency_crisis_support`; enforcement crisis route test. No BG or ambiguity tests. |
| `exertional_chest` | URGENT / `clinician_prompt` / `chest_needs_doctor` | `chest` + `tight/pressure/heavy/pain/tightness` | `гърди/гръд` + `стяга/натиск/тежест/болка` | Yes | urgent halt only for prescription; clinician route; no workout | P-015/P-063, prior-turn test, non-prescription test. No explicit exertion token is required by current code: FP review required. |
| `unilateral_calf` | URGENT / `clinician_prompt` / `leg_needs_doctor` | `calf/leg` + `swollen*` + `warm/hot/red/painful/achy*` | `прасец/крак` + `подут/отекъл/оток` + `топъл/зачервен/болезнен` | Yes | urgent prescription halt; clinician route | `test_p017_unilateral_calf_urgent`. Current matcher has no literal one-sided/unilateral token: clinical review required. |
| `syncope` | URGENT / `clinician_prompt` / `fainting_needs_doctor` | `faint*`, `pass out`, `black out`, `syncope`, `nearly fainted` | `припадък/прималя/да припадна/загуба на съзнание` | Yes | urgent prescription halt; clinician route | Corpus P-044. No direct BG, context, or near-negative test. |
| `arrhythmia` | URGENT / `clinician_prompt` / `palpitations_need_doctor` | `palpitation/racing heart/skipping/flutter/pounding heart` + `dizzy/light-headed/faint` | `сърцебиене/прескача/ускорен пулс/тупти` + `замая/прималя/световъртеж` | Yes | urgent prescription halt; clinician route | P-090; P-029 currently halts through this class despite pregnancy-bleeding corpus context. Needs semantic review. |
| `new_neuro_deficit` | URGENT / `clinician_prompt` / `numbness_weakness_needs_doctor` | `numb*/tingl*` + `weak/weakness/grip` | `изтръпва*` + `слаб/слабост` | Yes | urgent prescription halt; clinician route | P-014; P-107 also matches. No BG or new-vs-chronic distinction test. |
| `worsening_dyspnea` | URGENT / `clinician_prompt` / `breathlessness_needs_doctor` | `short of breath/breathless/out of breath/can't breathe` | `задух/недостиг на въздух/задъхвам/трудно дишане` | Yes | urgent prescription halt; clinician route | P-022/P-035; P-117/P-125 halt through this class despite different corpus intent. No worsening token is required: FP review required. |
| `severe_bp` | URGENT / `clinician_prompt` / `high_bp_reading_needs_doctor` | `blood pressure/bp` + `headache` + `high/very high/180/190/200/210` | `кръвно` + `главоболие` + `висок/много високо` | Yes | urgent prescription halt; clinician route | P-094. No BG-specific test; literal numeric handling needs review. |
| `persistent_low_mood` | ROUTINE / `gp_soft` / `low_mood_worth_support` | `low/empty/flat/tearful/no joy/no interest/anhedonia/hopeless/depress*` + `weeks/months/every day/most days/all the time` | `потиснат/празен/без настроение/без интерес/без радост/плача` + `седмици/месеци/всеки ден/постоянно` | Yes | no S2 halt by itself; `gp_soft` if a non-training routing decision results | P-028/P-086/P-113/P-119/P-132/P-139 detected but do not count as halt coverage. `test_persistent_low_mood_routine_no_halt_not_crisis`. |
| `disproportionate_fatigue` | ROUTINE / `gp_soft` / `fatigue_worth_checking` | `exhausted/tired all the time/drained/no energy/wiped out` + `weeks/months/getting worse/worse` | `изтощен/постоянно уморен/без енергия` + `седмици/месеци/влошава` | Yes | no S2 halt by itself; `gp_soft` if a non-training routing decision results | P-113 detects it with low mood. No direct, BG, or near-negative sentinel test. |

### 3.2 Current asymmetries and review observations

- All 15 classes contain at least one configured EN and BG literal. That is not
  evidence of equivalent clinical coverage or linguistic adequacy.
- The code does not document transliteration, spelling-variant, regional, slang,
  negation, temporal, or context handling beyond the literals shown above.
- The emergency and urgent classes are not uniformly tested in Bulgarian. The only
  direct BG sentinel test is `fast_stroke`.
- `exertional_chest` does not require an exertion literal; `worsening_dyspnea`
  does not require a worsening literal; `unilateral_calf` does not require a
  unilateral literal. These are implementation facts requiring reviewer decision,
  not a recommendation to change them here.

## 4. 36-corpus gap analysis

The complete referenced corpus is present at `brain/corpus/corpus_fixtures.json`
and is derived from `docs/research/APEX_VALIDATION_CORPUS.md`. It contains 140
fixtures, 36 of which have `expected_red_flag=true`. The harness measures whether
the current cascade produces a structural halt, not whether the clinical semantics
of the matched class are correct.

### 4.1 Halt-covered rows (17/36)

`P-014` new neuro deficit; `P-015` exertional chest; `P-017` calf cluster;
`P-022` breathlessness; `P-029` arrhythmia match; `P-035` breathlessness;
`P-044` syncope; `P-049` rhabdomyolysis; `P-063` exertional chest;
`P-074` autonomic dysreflexia; `P-083` fast stroke; `P-090` arrhythmia;
`P-094` severe BP; `P-098` acute hypoglycaemia; `P-107` cauda equina and new
neuro deficit; `P-117` breathlessness match; `P-125` breathlessness match.

### 4.2 Detected but not halt-covered (6/36)

`P-028`, `P-086`, `P-113`, `P-119`, `P-132`, and `P-139` trigger
`persistent_low_mood` (and `P-113` also triggers `disproportionate_fatigue`).
Those classes are ROUTINE, so the current S2 halt metric does not count them.

### 4.3 Not detected by the current library (13/36)

`P-003`, `P-006`, `P-032`, `P-041`, `P-051`, `P-052`, `P-111`, `P-118`,
`P-122`, `P-133`, `P-137`, `P-138`, `P-140`.

No medical mapping is proposed for any of these rows in this packet. The rollout
handbook explicitly identifies profile-rooted examples such as amenorrhea/RED-S,
oncology, and cardiac history as beyond the seed library's message-oriented
coverage.

### 4.4 Overlaps, duplicates, and confidence limits

| Corpus item(s) | Current observation | Reviewer action required |
|---|---|---|
| P-029 | Pregnancy bleeding/dizziness fixture halts via `arrhythmia`; no pregnancy-specific class exists. | Decide whether this is appropriate, incidental, or a false-positive route. |
| P-107 | Matches both `cauda_equina` and `new_neuro_deficit`; strongest urgency still routes emergency. | Confirm dual match/precedence is desired. |
| P-113 | Matches both routine mood and fatigue classes. | Confirm multiple routine records are clinically useful and presentation-safe. |
| P-117 | Corpus describes a cleared/non-medical exertion context but current `worsening_dyspnea` literal matches. | Review as potential false positive. |
| P-125 | Corpus describes bleeding/fatigue/breathlessness; current halt is through generic breathlessness. | Review semantic route and sufficiency. |
| Missing rows | No class match can be confidently inferred from code alone. | Requires qualified mapping decision; do not infer one from corpus prose alone. |

## 5. Bilingual false-positive / false-negative review matrix

**Use:** These are regression probes for a reviewer to approve, amend, or reject.
Expected result records *current code*, not a clinical recommendation. `Detect X`
means `detect_flag_classes()` should include X. `No X` means it should not include
that class under the literal cluster contract.

| Class | Clear positive EN -> expected | Clear positive BG -> expected | Paraphrase EN / BG -> expected | Prior-turn -> expected | Near-negative -> expected | Ambiguous negative -> expected | Unrelated fitness overlap -> expected |
|---|---|---|---|---|---|---|---|
| fast_stroke | “face drooping” -> Detect | “лицето ми провисна” -> Detect | “arm went weak and speech slurred” / “отслабна ръка и неясен говор” -> Detect | prior phrase + workout ask -> Detect/source prior_turn | “my face is tired” -> No | “speech practice” -> No | “face pulls and arm work” -> No |
| cauda_equina | “saddle numbness and trouble peeing” -> Detect | “изтръпване в чатала и уриниране” -> Detect | “groin tingling, bladder issue” / “слабини, изтръпване, пикоч” -> Detect | prior phrase -> Detect | “inner-thigh stretch” -> No | “numb after sitting” -> No unless bladder group | “groin mobility drill” -> No |
| autonomic_dysreflexia | “severe headache and sweating” -> Detect | “силно главоболие и изпотяване” -> Detect | “banging headache, flushed” / “пулсиращо главоболие, зачервяване” -> Detect | prior phrase -> Detect | “mild headache after work” -> No | “sweating in heat” -> No | “headache-free sweat session” -> No |
| rhabdomyolysis | “dark urine” -> Detect | “тъмна урина” -> Detect | “cola-coloured pee” / “урина с цвят на кола” -> Detect | prior phrase -> Detect | “dark gym lighting” -> No | “brown belt” -> No | “cola after training” -> Detect under current literal; FP probe |
| acute_hypoglycaemia | “shaky, sweaty and dizzy” -> Detect | “треперя, изпотен съм и съм замаян” -> Detect | “trembling, foggy, in sweat” / “разтреперан, объркан, в пот” -> Detect | prior phrase -> Detect | “shaky after coffee” -> No unless all groups | “sweaty workout” -> No | “dizzying exercise name” -> No |
| psych_crisis | “I want to end it all” -> Detect | “искам да сложа край” -> Detect | “better off dead” / “не искам да живея” -> Detect | prior phrase -> Detect | “end it all set” -> No | “no point in this rep” -> No | “suicide grip is a term” -> Detect under substring `suicid`; FP probe |
| exertional_chest | “chest pressure” -> Detect | “натиск в гърдите” -> Detect | “heavy chest” / “стяга ме в гърдите” -> Detect | prior phrase -> Detect | “chest day” -> No | “tight pecs” -> Detect under current code; FP probe | “chest press workout” -> No unless trigger adjective |
| unilateral_calf | “calf swollen and warm” -> Detect | “прасецът е подут и топъл” -> Detect | “leg is puffy and aching” / “кракът е отекъл и болезнен” -> Detect | prior phrase -> Detect | “warm calves after run” -> No unless swelling | “red socks, sore calf” -> Detect under current code; FP probe | “leg day feels hot” -> No unless swelling |
| syncope | “I nearly fainted” -> Detect | “ще припадна” -> Detect | “blacked out” / “загуба на съзнание” -> Detect | prior phrase -> Detect | “faint line” -> Detect under substring; FP probe | “black-out curtains” -> Detect under literal; FP probe | “syncope article” -> Detect under literal; FP probe |
| arrhythmia | “heart racing and dizzy” -> Detect | “сърцебиене и световъртеж” -> Detect | “palpitations, light-headed” / “пулсът ми тупти и прималявам” -> Detect | prior phrase -> Detect | “heart racing from excitement” -> No unless dizziness | “skipping rope made me dizzy” -> Detect if `skip` + dizzy; FP probe | “flutter kicks and dizziness” -> Detect under current code; FP probe |
| new_neuro_deficit | “numbness and weakness” -> Detect | “изтръпване и слабост” -> Detect | “tingling, weak grip” / “изтръпва и е слаб” -> Detect | prior phrase -> Detect | “numb from cold” -> No unless weakness | “weak after hard set” -> No unless numbness | “grip workout gives tingling” -> Detect; FP probe |
| worsening_dyspnea | “shortness of breath” -> Detect | “имам задух” -> Detect | “I can’t breathe” / “трудно дишане” -> Detect | prior phrase -> Detect | “out of breath after sprints” -> Detect under current code; review | “breathless movie” -> Detect under literal; FP probe | “breathing drill” -> No |
| severe_bp | “blood pressure headache 180” -> Detect | “кръвно, главоболие, 180” -> Detect | “BP very high with headache” / “много високо кръвно и главоболие” -> Detect | prior phrase -> Detect | “high BP reading but no headache” -> No | “180-second workout headache” -> No unless BP group | “BP exercise with headache” -> Detect if all groups; FP probe |
| persistent_low_mood | “low and empty most days for weeks” -> Detect | “потиснат и празен всеки ден от седмици” -> Detect | “no joy for months” / “без радост от месеци” -> Detect | prior phrase -> Detect | “low bar for weeks” -> No | “flat bench for months” -> Detect only if temporal mood token group also present | “tearful from a film for weeks” -> Detect under current code; FP probe |
| disproportionate_fatigue | “exhausted for weeks” -> Detect | “изтощен от седмици” -> Detect | “drained and getting worse” / “без енергия и се влошава” -> Detect | prior phrase -> Detect | “tired today” -> No | “wiped out after one workout” -> No without temporal group | “no energy for a playlist this week” -> Detect under current code; FP probe |

## 6. Current enforcement-message review

The following are **internal delivery instructions**, not fixed final user-facing
translations. They are supplied to the existing response layer only when
enforcement is enabled. Reviewer assessment fields are intentionally blank.

| Current target / outcome | Current instruction summary | Implementation safety controls | Review observations | Reviewer decision |
|---|---|---|---|---|
| `emergency_services` | says described issue needs emergency help now; no workout | `_NO_DIAGNOSIS`; class key not rendered | urgency wording is strong; EN instruction only; final BG delivery depends on downstream language layer | UNAPPROVED |
| `stop_and_treat` | stop and treat immediately, example fast-acting sugar; seek help if unresolved; no workout | `_NO_DIAGNOSIS` | contains a concrete treatment example; needs human review | UNAPPROVED |
| `crisis_support` | warm response; encourage crisis line/trusted person now; support available; no workout | `_NO_DIAGNOSIS` | requires locale/resource and crisis-language review | UNAPPROVED |
| `clinician_prompt` | prompt doctor assessment before hard exertion; no workout | `_NO_DIAGNOSIS` | non-diagnostic instruction; urgency and EN/BG output parity require review | UNAPPROVED |
| `gp_soft` | gently raise with GP; optional gentle alternative | `_NO_DIAGNOSIS` | must not create unsafe reassurance or inconsistent workout continuation | UNAPPROVED |
| `NOT_YET` | hold training until precondition; offer S5 alternative | `_NO_DIAGNOSIS` | reason is decision-dependent, not a red-flag diagnosis | UNAPPROVED |
| `NO_TRAIN` | training is not right now; offer S5 alternative | `_NO_DIAGNOSIS` | same language/alternative review required | UNAPPROVED |
| `cold_start` | conservative beginner session; stop and seek help for chest pain, dizziness, unusual breathlessness | gated on no halt, no red flag, no constraint, no confident physiology | permitted to generate training; clinical wording and locale need review | UNAPPROVED |

Known implementation constraint: `_ROUTE_DIRECTIVE` and `_COLD_START_ADDENDUM`
are English source strings. The packet found no formal document establishing
equivalent, approved BG enforcement wording.

## 7. Human routing and severity review table

All human-review fields are intentionally unapproved/blank.

| Class | Current urgency | Current route | Clinical reviewer decision | Proposed urgency | Proposed route | Rationale | Evidence/source | Reviewer | Reviewer qualification | Review date | Version |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fast_stroke | EMERGENCY | emergency_services | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-083 |  |  |  | redflag-seed-2026-07-05 |
| cauda_equina | EMERGENCY | emergency_services | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-107 |  |  |  | redflag-seed-2026-07-05 |
| autonomic_dysreflexia | EMERGENCY | emergency_services | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-074 |  |  |  | redflag-seed-2026-07-05 |
| rhabdomyolysis | EMERGENCY | emergency_services | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-049 |  |  |  | redflag-seed-2026-07-05 |
| acute_hypoglycaemia | EMERGENCY | stop_and_treat | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-098 |  |  |  | redflag-seed-2026-07-05 |
| psych_crisis | EMERGENCY | crisis_support | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-116 |  |  |  | redflag-seed-2026-07-05 |
| exertional_chest | URGENT | clinician_prompt | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-015/P-063 |  |  |  | redflag-seed-2026-07-05 |
| unilateral_calf | URGENT | clinician_prompt | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-017 |  |  |  | redflag-seed-2026-07-05 |
| syncope | URGENT | clinician_prompt | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-044 |  |  |  | redflag-seed-2026-07-05 |
| arrhythmia | URGENT | clinician_prompt | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-090 |  |  |  | redflag-seed-2026-07-05 |
| new_neuro_deficit | URGENT | clinician_prompt | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-014/P-107 |  |  |  | redflag-seed-2026-07-05 |
| worsening_dyspnea | URGENT | clinician_prompt | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-022/P-035 |  |  |  | redflag-seed-2026-07-05 |
| severe_bp | URGENT | clinician_prompt | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-094 |  |  |  | redflag-seed-2026-07-05 |
| persistent_low_mood | ROUTINE | gp_soft | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, routine corpus rows |  |  |  | redflag-seed-2026-07-05 |
| disproportionate_fatigue | ROUTINE | gp_soft | UNAPPROVED |  |  |  | `REDFLAG_SPECS`, P-113 |  |  |  | redflag-seed-2026-07-05 |

## 8. Approval contract before `BRAIN_ENFORCE=true`

All conditions below require documentary evidence. None is complete merely because
the test suite passes.

1. Named reviewer identity and contact record.
2. Reviewer qualification and scope appropriate to each class and route.
3. Reviewed red-flag library version and immutable review artifact.
4. A decision for every active class: APPROVE, CHANGE, REMOVE, or NEEDS EVIDENCE.
5. Approved urgency for every class.
6. Approved route target for every class.
7. Approved EN cluster set for every class, including negation/context policy.
8. Approved BG cluster set for every class, including colloquial and transliteration policy.
9. Approved user-facing EN and BG routing language for every target and outcome.
10. Reviewed false-positive / false-negative matrix, including corpus overlaps.
11. Documented exceptions, residual risks, and deliberately unsupported scenarios.
12. Review date, expiry/re-review date, and accountable owner.
13. Explicit re-review triggers: class addition/removal, wording or route change,
    matcher change, locale expansion, material incident, new corpus evidence, or
    change to downstream enforcement/renderer.
14. Change-control rule: any library, matching, severity, route, or user-facing
    wording change increments a version and invalidates approval for affected rows
    until re-reviewed.
15. Operational acceptance: the rollout handbook's shadow window, corpus gate,
    telemetry health, and deployment-version consistency are completed and signed
    off separately.

## 9. Reviewer decision record

| Overall decision | Reviewer | Qualification | Date | Reviewed version | Exceptions / follow-up |
|---|---|---|---|---|---|
| UNAPPROVED |  |  |  | `redflag-seed-2026-07-05` |  |

**Current governance conclusion:** the source labels the library as a seed and the
repository contains no documented closure artifact for clinical review or bilingual
expansion. This packet does not authorize `BRAIN_ENFORCE=true`.
