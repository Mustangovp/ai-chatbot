"""
APEX Brain — M4 Safety-Front renderer (pure).

Turns a shadow `Decision` into an ENFORCEMENT DIRECTIVE for the /chat generation
call, covering only the SAFETY FRONT (roadmap M4):

  • halt (EMERGENCY/URGENT red flag) → mode "route": do NOT emit a workout; the
    generation call is steered to route the user to the right professional, in
    APEX's voice, WITHOUT naming a condition or diagnosing.
  • NOT_YET / NO_TRAIN (no halt)      → mode "defer" / "refuse": no workout; state
    the reason kindly and offer the S5 alternative.
  • GO / MODIFY                        → mode "constrain": a workout IS generated,
    with the S1 movement constraints + envelope injected into the prompt.
  • cold-start (ADR-001)               → mode "cold_start": an IGNORANCE NOT_YET —
    no halt, no red flags, no constraints, and no confident read on the person's
    state — yields a CONSERVATIVE BEGINNER workout instead of a refusal. POLICY,
    gated so it can never override a safety decision (any halt / red flag /
    constraint / physiological data disqualifies it). The Brain Decision is
    unchanged and still logged truthfully as NOT_YET; only the enforcement response
    differs, flagged `cold_start` on the decision event.

This is a PURE function: it takes a Decision and returns a dict. It performs no
I/O, reads no flags, and touches no organ (S1–S5, the cascade, replay, and the
Event Ledger are untouched) — the caller (behind BRAIN_ENFORCE) decides whether to
apply it. Non-diagnosis is structural: the directive carries routing INSTRUCTIONS
and internal keys, never a clinical label or a message that names an unstated
condition (Brain Architecture §6 / audit R7).
"""
from brain.types import Verdict

# route_target (from the red-flag library) → a non-diagnostic routing instruction.
_ROUTE_DIRECTIVE = {
    "emergency_services": "Tell them, warmly and plainly, that what they describe needs "
                          "emergency medical help NOW (emergency services / A&E). Do not give a workout.",
    "stop_and_treat":     "Tell them to STOP and treat this immediately (e.g. fast-acting sugar "
                          "for a low), then get medical help if it does not resolve. Do not give a workout.",
    "crisis_support":     "Respond with warmth and without alarm; encourage them to reach a crisis "
                          "line or a trusted person right now, and that support is available. Do not give a workout.",
    "clinician_prompt":   "Tell them this needs a doctor's assessment promptly, before hard exertion. "
                          "Do not give a workout.",
    "gp_soft":            "Gently suggest raising this with their GP when they can. A gentle, optional "
                          "alternative may be offered.",
}

_INTERVENTION_ALT = {
    "recovery": "recovery today", "sleep": "protecting sleep first", "walk": "an easy walk",
    "breathing": "a short breathing/down-regulation practice", "mobility": "gentle mobility",
    "stress_reduction": "a brief stress-reduction practice", "nutrition": "a fuelling nudge",
    "conversation": "talking it through before any plan", "medical_followup": "getting this checked first",
    "crisis_support": "reaching support right now",
}

_NO_DIAGNOSIS = (" Do NOT name or imply a medical condition, do NOT diagnose, and do NOT give "
                 "medication or treatment advice. Speak in APEX's voice.")

# ADR-001 cold-start: a brand-new person with no data and no risk signals gets a
# deliberately minimal, universally-safe beginner session — not a refusal.
_COLD_START_ADDENDUM = (
    "COLD START — this is a brand-new person with no history and no risk signals yet. "
    "Generate ONE conservative BEGINNER session only: low intensity, mostly bodyweight or "
    "light load, technique-first, controlled range of motion, a proper warm-up, and short "
    "total volume. No maximal, heavy, or high-impact work. Add a plain line telling them to "
    "stop and seek help if they feel chest pain, dizziness, or unusual shortness of breath. "
    "Invite them to share their goals and any health conditions so the next session can be "
    "tailored." + _NO_DIAGNOSIS)


def _is_cold_start(decision) -> bool:
    """ADR-001 gate: an IGNORANCE NOT_YET with ZERO risk signals and no confident
    read on the person's current state.

    SAFETY rests on the first three clauses ONLY — a halt, ANY red flag, or ANY
    constraint disqualifies cold-start. None of those depends on a confidence value,
    so the safety guarantee cannot be weakened by how confidence is computed.

    The last clause is NOT a proxy for "an Athlete Model row exists". It reads
    `S2State.readiness_conf` directly — the *confidence in the readiness estimate*,
    which `s2_sentinel._readiness` sets to exactly 0.0 whenever the Brain has no
    confident physiological read (no physiology, OR physiology carrying no
    confidence). That "0 ⇔ no confident state read" is the field's GUARANTEED
    semantic (its docstring), invariant across revisions unless readiness_conf is
    redefined — at which point this call site is the intended single point to
    revisit. Its role is only to avoid overriding a *confident* state-based deferral
    (e.g. a genuinely-depleted, known user). Even if it ever admitted a known user,
    the result is still safe by construction: someone with no halt, no red flag and
    no constraint receives only a conservative beginner session.

    Reads only the Decision; changes nothing."""
    s2 = decision.s2
    return (decision.verdict is Verdict.NOT_YET
            and not decision.halt
            and not (getattr(s2, "red_flags", None) or [])
            and decision.constraints.is_empty()
            and float(getattr(s2, "readiness_conf", 0.0)) <= 1e-9)


def _strongest_flag(decision):
    order = {"EMERGENCY_now": 3, "URGENT_soon": 2, "ROUTINE_mention": 1}
    flags = getattr(decision.s2, "red_flags", None) or []
    return max(flags, key=lambda f: order.get(f.urgency.value, 0)) if flags else None


def _constraint_directive(decision) -> str:
    cons = decision.constraints
    if cons.is_empty():
        return ""
    movements = ", ".join(sorted({c.movement for c in cons.items}))
    env = decision.envelope
    return (f" Build the session but strictly AVOID/adapt these movements: {movements}. "
            f"Keep intensity at or below {env.intensity_ceiling:.2f} of max, "
            f"{'balance-supported, ' if env.supported else ''}"
            f"technique-first. Do not exceed this envelope.")


def render(decision) -> dict:
    """Decision → enforcement directive for the /chat generation call."""
    verdict = decision.verdict
    flag = _strongest_flag(decision)
    urgency = flag.urgency.value if flag else None
    route = flag.route_target if flag else None
    alt = _INTERVENTION_ALT.get(decision.intervention.kind)

    if decision.halt:
        directive = _ROUTE_DIRECTIVE.get(route, "Steer them to appropriate professional support "
                                                "and do not give a workout.")
        mode, should_generate = "route", False
        addendum = "SAFETY OVERRIDE — do not generate a workout. " + directive + _NO_DIAGNOSIS

    elif _is_cold_start(decision):
        # ADR-001: ignorance NOT_YET with no risk signals + no Athlete Model.
        # Conservative beginner starter instead of a refusal. Checked AFTER the halt
        # branch and gated on no flags / no constraints, so it never masks safety.
        mode, should_generate = "cold_start", True
        addendum = _COLD_START_ADDENDUM

    elif verdict in (Verdict.NOT_YET, Verdict.NO_TRAIN):
        mode, should_generate = ("refuse" if verdict is Verdict.NO_TRAIN else "defer"), False
        stem = ("Training is not the right answer for this request right now"
                if verdict is Verdict.NO_TRAIN else
                "Hold off on training for now — a precondition isn't met yet")
        alt_txt = f" Offer instead: {alt}." if alt else ""
        addendum = (f"SAFETY OVERRIDE — do not generate a workout. {stem}. Say so kindly, with the "
                    f"reason, without shame.{alt_txt}" + _NO_DIAGNOSIS)

    else:  # GO / MODIFY
        mode, should_generate = ("constrain" if verdict is Verdict.MODIFY else "proceed"), True
        addendum = _constraint_directive(decision).strip() or ""

    return {
        "mode": mode,
        "should_generate_workout": should_generate,
        "decision_event": {
            "verdict": verdict.value,                 # the TRUE Brain verdict (unchanged, e.g. NOT_YET)
            "urgency": urgency,
            "route": route,
            "intervention": decision.intervention.kind,
            "generate": should_generate,
            "cold_start": mode == "cold_start",        # policy exception marker (audit-honest)
        },
        "system_prompt_addendum": addendum,
    }
