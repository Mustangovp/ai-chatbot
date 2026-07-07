"""
BUILD-003 — Adaptive Coach.

The first runtime consumer of Human State. It shapes HOW a response is delivered —
tone, volume, intensity, recovery emphasis, nutrition emphasis, motivational strategy,
communication style, educational content — layered ON TOP of the frozen Brain + the
enforcement directive. It NEVER overrides the Brain verdict, safety, or medical
routing; it never generates a withheld workout, raises load, or drops a constraint.
It only ever SOFTENS. Every adaptation cites the state variable, reason, coaching
rule, and Constitution principle (full explainability).

Reads Human State (persistent view + the current message's signals). Never reads or
touches the Brain.
"""
import human_state
from human_state import extractor, trajectory
from human_state.schema import now_utc

# The clamp is stated to the model AND enforced structurally (only softening rules fire,
# and workout-shaping rules require the enforcement directive to already permit a workout).
_CLAMP = ("COACHING ADAPTATION — delivery only. Do NOT override the safety directive above, "
          "do NOT add a workout if one was withheld, do NOT increase intensity or volume beyond "
          "the stated envelope, do NOT remove any constraint. Adapt as follows:")


def _live_state(subject, message, now):
    """Fresh persistent state + the current message's signals (current message wins)."""
    state = {}
    for k, info in human_state.view(subject, now=now).items():
        if info.get("fresh"):
            state[k] = {"value": info.get("value"), "note": info.get("note")}
    for r in extractor.extract(message or "", now=now):
        skey = f"preference:{r.note}" if r.key == "preference" else r.key
        state[skey] = {"value": r.value, "note": r.note}
    return state


def _val(state, key):
    v = state.get(key)
    return v.get("value") if v else None


def _num(state, key):
    try:
        return float(_val(state, key))
    except (TypeError, ValueError):
        return None


def adapt(subject, message, decision, directive, profile=None, now=None):
    """Return {applied, addendum, adaptations, style}. `decision` is the frozen Brain
    Decision (read-only); `directive` is the enforcement directive (read-only)."""
    at = now or now_utc()
    state = _live_state(subject, message, at)
    generates = bool((directive or {}).get("should_generate_workout"))
    adaptations, frags = [], []
    style = None

    def A(variable, reason, rule, principle, fragment, tone=None):
        nonlocal style
        adaptations.append({"variable": variable, "reason": reason,
                            "rule": rule, "principle": principle})
        if fragment:
            frags.append(fragment)
        if tone and style is None:
            style = tone

    # ── state-driven softening rules ─────────────────────────────────────────
    sleep = _val(state, "sleep")
    if sleep == "low" or (_num(state, "sleep") is not None and _num(state, "sleep") < 6) or _val(state, "sleep_debt"):
        if generates:
            A("sleep", "poor/short sleep reduces recoverable load", "recovery-gate",
              "APX-REC-010 recovery is the limiter",
              "Reduce today's volume and intensity; keep it easy and technique-first.", "reassuring")
        else:
            A("sleep", "poor/short sleep", "recovery-coaching", "APX-REC-011 sleep primacy",
              "Acknowledge the short sleep warmly and emphasise recovery.", "reassuring")

    if _val(state, "fatigue") == "high" or _val(state, "recovery") == "low":
        if generates:
            A("fatigue", "high fatigue / low recovery", "recovery-gate", "APX-REC-010",
              "Trim volume; prioritise quality over quantity today.")

    if _val(state, "stress") == "high":
        A("stress", "high stress shares the adaptive budget", "stress-coaching",
          "APX-REC-012 stress budget",
          "Lower the load; offer movement as stress relief. Warm, calm tone.", "supportive")

    if _val(state, "pain") == "present":
        A("pain", "pain reported", "injury-adaptation", "APX-MOV-020 train pain-free ranges",
          "Keep everything strictly pain-free; work around it, never through it.", "reassuring")

    if _val(state, "illness") == "present":
        A("illness", "illness reported", "illness-recovery", "APX-SAF-020 illness defer",
          "Given illness, favour rest and gentle movement; do not push a hard session; "
          "suggest seeing a doctor if symptoms are severe.", "reassuring")

    if _val(state, "motivation") == "low":
        A("motivation", "low motivation", "motivation-support", "APX-PSY-020 behaviour design",
          "Shrink the ask to something winnable; connect it to their goal; warm, no pressure.", "supportive")

    if _val(state, "confidence") == "low":
        A("confidence", "low confidence", "confidence-building", "APX-PSY self-efficacy",
          "Use mastery framing and reassurance; celebrate showing up.", "reassuring")

    if _val(state, "adherence") in ("missed", "gap"):
        A("adherence", "recent missed sessions (trend)", "relapse-prevention",
          "APX-PSY-002 a lapse is not a relapse",
          "Welcome them back warmly; a lapse isn't a relapse; one small win today.", "supportive")

    # workout-shaping rules ONLY when the enforcement directive already permits a workout
    if generates:
        mins = _num(state, "time_availability")
        if mins is not None:
            A("time_availability", f"only ~{int(mins)} min available", "time-constrained",
              "APX-STR-019 minimum effective dose",
              f"Fit a real session into ~{int(mins)} minutes: minimum effective dose, supersets.")
        if _val(state, "travel") == "present":
            A("travel", "travelling", "travel-adaptation", "APX-PHI-023 constraint realism",
              "Assume no gym: bodyweight / hotel-room-friendly options.")
        if _val(state, "environment"):
            A("environment", "stated environment", "lifestyle-coaching", "APX-PHI-023",
              "Fit the session to their stated environment.")
        if _val(state, "equipment"):
            A("equipment", "stated equipment", "lifestyle-coaching", "APX-PHI-023",
              "Use only the equipment they have available.")

    # ── BUILD-004 · trajectory (trend-aware) adaptations — caution/support only ──
    if trajectory.enabled():
        traj = trajectory.compute(subject, now=at)
        if traj.get("ok") and traj.get("sufficient"):
            if traj["recovery_direction"] == "declining":
                A("recovery_trend", "recovery trending down over recent history", "recovery-gate",
                  "APX-REC-010 recovery is the limiter",
                  "Recovery has been sliding lately — bias conservative today.", "reassuring")
            if traj["adherence_direction"] == "declining" or traj["risk"]["level"] == "elevated":
                A("adherence_trend", f"adherence/dropout risk trend ({traj['risk']['level']})",
                  "relapse-prevention", "APX-PSY-002 a lapse is not a relapse",
                  "Consistency has wobbled — make today small and winnable; warm, no pressure.", "supportive")
            if traj["confidence_direction"] == "improving" or traj["trajectory"] == "improving":
                A("momentum", "positive trajectory / rising confidence", "identity-coaching",
                  "APX-PSY identity", "Momentum is building — reinforce their identity as someone who trains.")
            if any(pk.get("volatility", 0) > 0.4 for pk in traj["per_key"].values()):
                A("volatility", "state has been erratic recently", "consistency-coaching",
                  "APX-PSY-002", "Their state has been up and down — keep it simple and stable today.")

    goal = (profile or {}).get("goal")
    if goal:
        A("goal", f"current goal is {goal}", "goal-alignment", "APX-PHI-021 goal stability",
          f"Keep the emphasis aligned to their goal ({goal}).")

    if not adaptations:
        return {"applied": False, "addendum": "", "adaptations": [], "style": None}

    addendum = _CLAMP + " " + " ".join(frags)
    if style:
        addendum += f" Overall tone: {style}."
    return {"applied": True, "addendum": addendum, "adaptations": adaptations, "style": style}
