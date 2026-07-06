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

This is a PURE function: it takes a Decision and returns a dict. It performs no
I/O, reads no flags, and touches no organ — the caller (behind BRAIN_ENFORCE)
decides whether to apply it. Non-diagnosis is structural: the directive carries
routing INSTRUCTIONS and internal keys, never a clinical label or a message that
names an unstated condition (Brain Architecture §6 / audit R7).
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
            "verdict": verdict.value,
            "urgency": urgency,
            "route": route,
            "intervention": decision.intervention.kind,
            "generate": should_generate,
        },
        "system_prompt_addendum": addendum,
    }
