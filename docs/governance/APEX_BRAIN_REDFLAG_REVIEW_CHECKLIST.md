# APEX Brain Red-Flag Clinical Review Checklist (Historical)

> **Superseded for production activation.** This checklist records the former
> clinical-triage review proposal. APEX now uses these records only for internal
> health-safety boundary matching. The current activation authority is
> [APEX Health-Safety Production Gate](APEX_HEALTH_SAFETY_PRODUCTION_GATE.md).
> Nothing in this historical checklist grants diagnostic, treatment, triage, or
> disease-specific user-facing authority.

**Historical library label:** `redflag-seed-2026-07-05`
**Baseline:** `7a3ba465394616ad69464ff0795b1dfa4467b70b`
**Status:** Historical clinical sign-off is unapproved and is not the current
production gate for non-medical boundary enforcement.

Use with [the full review packet](APEX_BRAIN_REDFLAG_CLINICAL_REVIEW_PACKET.md).
Checking an item requires evidence and reviewer attribution; automated tests alone
do not satisfy any clinical sign-off item.

## Reviewer identity and scope

- [ ] Reviewer identity recorded.
- [ ] Reviewer qualification recorded.
- [ ] Review scope covers every active class, urgency, route, and user-facing language.
- [ ] Reviewed library version recorded: `redflag-seed-2026-07-05`.
- [ ] Review date and re-review date recorded.

## Per-class approval

- [ ] `fast_stroke`
- [ ] `cauda_equina`
- [ ] `autonomic_dysreflexia`
- [ ] `rhabdomyolysis`
- [ ] `acute_hypoglycaemia`
- [ ] `psych_crisis`
- [ ] `exertional_chest`
- [ ] `unilateral_calf`
- [ ] `syncope`
- [ ] `arrhythmia`
- [ ] `new_neuro_deficit`
- [ ] `worsening_dyspnea`
- [ ] `severe_bp`
- [ ] `persistent_low_mood`
- [ ] `disproportionate_fatigue`

For every checked class, the signed record must state: approve/change/remove/needs
evidence; urgency; route; EN patterns; BG patterns; false-positive and
false-negative handling; and any exception.

## Required review evidence

- [ ] EN trigger clusters approved.
- [ ] BG trigger clusters approved.
- [ ] Negation, context, colloquial, and transliteration limitations documented.
- [ ] Prior-turn behaviour approved.
- [ ] Route precedence for multi-match cases approved.
- [ ] Emergency, urgent, and routine semantics approved.
- [ ] `emergency_services`, `stop_and_treat`, `crisis_support`,
  `clinician_prompt`, and `gp_soft` language approved in EN and BG.
- [ ] `NOT_YET`, `NO_TRAIN`, and cold-start language approved in EN and BG.
- [ ] No-diagnosis and no-unsupported-treatment wording verified.
- [ ] False-positive / false-negative matrix reviewed.
- [ ] All 36 corpus rows classified as covered, partial, unsupported, or requiring change.
- [ ] P-029, P-107, P-113, P-117, and P-125 overlap observations resolved.
- [ ] Seed-library gaps and unsupported scenarios documented.

## Operational gate

- [ ] Shadow acceptance criteria from `docs/milestones/APEX_BRAIN_PRODUCTION_ROLLOUT.md` completed.
- [ ] Corpus acceptance run recorded; current 17/36 halt coverage is explicitly understood.
- [ ] No unresolved emergency miss on the approved canary/probe set.
- [ ] Production telemetry and deployment-version consistency reviewed.
- [ ] Rollback owner and procedure confirmed.
- [ ] Change-control/versioning owner confirmed.

## Sign-off

| Decision | Reviewer | Qualification | Date | Library version | Exceptions |
|---|---|---|---|---|---|
| UNAPPROVED |  |  |  | `redflag-seed-2026-07-05` |  |

**Do not treat this historical checklist as authority to enable or block the
current non-medical boundary. Use the current product-safety gate instead.**
