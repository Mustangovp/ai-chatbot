"""
APEX Brain — Station S5: the Intervention Selector.

Even when training is permitted, chooses whether it is *optimal* — selecting the
single highest-value intervention from the full library (training is one of ~ten
and frequently not the winner). This is the organ that turns a workout generator
into a coach. Pure, deterministic. No Flask, no DB, no OpenAI.

On a halt (Addendum 02 A2-0) it selects the route intervention from the
strongest red flag. Otherwise: a refusal/deferral (NO_TRAIN/NOT_YET) selects the
best non-training alternative; GO/MODIFY selects training only when training is
the top need, else the more valuable non-training need. `generate_training` is
True only when the verdict permits AND the chosen kind is training.
"""
from brain.types import Verdict, Intervention

# S3 need name → intervention kind.
_NEED_TO_INTERVENTION = {
    "training": "training",
    "recovery": "recovery",
    "sleep": "sleep",
    "stress_reduction": "stress_reduction",
    "gentle_movement": "walk",
    "nutrition": "nutrition",
    "conversation": "conversation",
    "medical_followup": "medical_followup",
}

_URGENCY_ORDER = {"EMERGENCY_now": 3, "URGENT_soon": 2, "ROUTINE_mention": 1}


def _route_intervention(s2) -> Intervention:
    """The route dictated by the strongest red flag (crisis vs medical)."""
    flags = getattr(s2, "red_flags", None) or []
    if not flags:
        return Intervention("medical_followup", "route_to_care")
    flag = max(flags, key=lambda f: _URGENCY_ORDER.get(getattr(f.urgency, "value", ""), 0))
    if flag.route_target == "crisis_support":
        return Intervention("crisis_support", flag.message_key)
    return Intervention("medical_followup", flag.message_key)


def _top_non_training(need_vector) -> str:
    for need, _w in (need_vector or []):
        if need != "training":
            return need
    return "conversation"


def select(*, verdict, s2, need_vector, athlete_state=None, profile=None) -> Intervention:
    """Return the single chosen Intervention."""
    # Halt → route to care/crisis (the training question is moot).
    if getattr(s2, "halt", False):
        return _route_intervention(s2)

    # Refuse / defer → the best NON-training alternative (a route if a flag exists).
    if verdict in (Verdict.NO_TRAIN, Verdict.NOT_YET):
        if getattr(s2, "red_flags", None):
            return _route_intervention(s2)
        need = _top_non_training(need_vector)
        return Intervention(_NEED_TO_INTERVENTION.get(need, "conversation"), "defer_" + need)

    # GO / MODIFY → training if it's the top need, else the more valuable alternative.
    top = need_vector[0][0] if need_vector else "training"
    return Intervention(_NEED_TO_INTERVENTION.get(top, "training"), "selected_" + top)


def is_training(intervention) -> bool:
    return getattr(intervention, "kind", None) == "training"


def generate_training(verdict, intervention) -> bool:
    """The gate on S6: generation is reachable only here."""
    return verdict in (Verdict.GO, Verdict.MODIFY) and is_training(intervention)
