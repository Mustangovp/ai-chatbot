# APEX Health-Safety Production Gate

## Product authority

APEX is a health-aware fitness and wellness system. It may recognise that it
must stop or limit fitness delivery. It does not diagnose, medically triage,
treat, prescribe medication, or provide medical rehabilitation.

The only user-authoritative health result is `MEDICAL_BOUNDARY`: a generic,
non-diagnostic referral to qualified medical help. Internal matcher metadata
such as `class_key`, `urgency`, `route_target`, and `message_key` is never shown
to users and cannot produce disease-specific advice.

## Production acceptance contract

Before `BRAIN_ENFORCE=true` is tested in production, release engineering must
record that all of the following are true:

1. Health knowledge is used only for abstention or scope limitation.
2. User output contains no diagnosis, disease inference, treatment, medication,
   or therapeutic rehabilitation advice.
3. Active concerning context suppresses workout delivery structurally.
4. Unknown or unavailable safety decisions fail closed for workout requests.
5. Explicit clinician and user restrictions remain immutable boundaries.
6. EN and BG generic `MEDICAL_BOUNDARY` messages are available.
7. Internal safety metadata cannot leak through SSE, Composer, Persona/Expert,
   renderer, persistence, or error paths.
8. Deterministic training, shoulder validation, and explicit exclusions remain
   authoritative below the medical boundary.
9. False-positive matches can only abstain; they cannot make medical claims.
10. False negatives cannot bypass explicit medical holds or restrictions.
11. Focused health-safety, enforcement, SSE, and full regression tests pass.
12. Deployment health, rollback ownership, and a tested rollback procedure are
    recorded for the activation session.

This is product-safety governance. It does not claim clinical validation of the
health corpus or grant APEX medical authority.

## Corpus role

The 140-persona corpus, its 36 health-marked fixtures, 15 internal matcher
records, and expert safety rules are regression inputs for boundary matching and
abstention. They may not authorize a diagnosis, disease probability, treatment,
medication, clinical severity statement, or disease-specific user guidance.

## Rollback

If any boundary, output, latency, SSE, or service-health regression appears,
set `BRAIN_ENFORCE=false`, wait for a healthy deployment, and preserve only
non-sensitive operational evidence needed for investigation.
