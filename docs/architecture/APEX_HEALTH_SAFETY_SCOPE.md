# APEX Health-Safety Scope

## Product boundary

APEX Pulse PRO is an AI fitness and wellness coach. It provides deterministic
training, general nutrition, recovery, and coaching support. It remembers
user-declared limitations, recognises when health context makes fitness advice
unsafe, and can narrow or stop its own fitness and wellness scope.

APEX is not a doctor, diagnostic system, medical triage service, treatment
system, rehabilitation prescription system, medication advisor, or
disease-management system.

**Health knowledge is used to limit APEX, not to expand APEX into medicine.**

## Scope decisions

| State | APEX behaviour |
| --- | --- |
| `NORMAL_FITNESS` | Normal deterministic fitness, general nutrition, recovery, coaching, Persona/Expert, and Composer paths may run. |
| `FITNESS_LIMITATION` | Treat an explicit movement limitation as authoritative. Adapt or exclude that movement without diagnosing the cause; preserve it across follow-ups. |
| `DECLARED_HEALTH_CONTEXT` | Stay in general fitness and wellness. Respect user- or clinician-supplied restrictions exactly, without changing, interpreting, treating, or managing a condition. |
| `MEDICAL_BOUNDARY` | Stop the relevant training or therapeutic-nutrition delivery. Return the fixed non-diagnostic boundary; do not generate, replay, substitute, complete, or reconstruct a workout. |

`MEDICAL_BOUNDARY` has precedence over explicit restrictions, Brain fitness
safety, shoulder safety, deterministic training, Persona/Expert advice, and
Composer presentation.

## Medical-boundary delivery

Internal red-flag records, route targets, urgency tiers, and condition-like
keys are deterministic safety-matching data only. They never appear in user
output. A boundary response does not diagnose, rank urgency, prescribe a
treatment, recommend medication, or identify an inferred condition. The user
decides whether a situation may be urgent.

At a boundary, the runtime emits no new workout, prior-workout replay, harder or
easier follow-up, exercise substitution, workout completion event, Persona/Expert
override, Composer reconstruction, or LLM workaround. Terminal SSE ordering is
preserved.

## Nutrition boundary

APEX may provide ordinary fitness nutrition around declared preferences,
allergies, and clinician-provided restrictions. It must not use nutrition to
diagnose, treat, cure, control, or manage a disease; requests for that scope use
the same medical boundary. `NUTRITION_ENGINE_V2_ACTIVE` remains independently
gated and does not change this contract.

## Existing safety assets

The repository keeps the health corpus, S1-S5 Brain cascade, red-flag library,
Athlete Model, Human State fields, training safety mappings, and expert/practice
systems. Their permitted roles are conservative matching, scope limitation,
fitness constraints, and non-medical coaching. They do not confer medical
authority.

## Governance status

`BRAIN_ENFORCE` remains off until a separate controlled product-safety review.
The historical clinical governance packet is retained as development evidence;
it is not an approval to make APEX a medical triage product.
