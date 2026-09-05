"""Factual execution evidence at the transport/persistence boundary.

Legacy clients prefill completed_repetitions from the prescription. Those values
are not observations. Only the explicit actual_repetitions field is accepted as
a reported count; absence stays unknown. No prescription or progression policy
is modified here.
"""
from copy import deepcopy
from enum import Enum
from fractions import Fraction


class ExecutionState(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


def _count(value):
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 100000:
        raise ValueError("invalid observed work count")
    return value


def normalize_execution(session, completion=None, *, plan=None):
    """Return a new session; percentages use observed work / server prescription.

    With no matching server prescription the denominator is unknown. A partial
    or abandoned report remains useful history but never advances progression.
    """
    if not isinstance(session, dict):
        raise ValueError("execution session must be an object")
    result = deepcopy(session)
    payload = completion if isinstance(completion, dict) else {}
    raw = payload.get("exercises", session.get("exercises", []))
    if not isinstance(raw, list):
        raise ValueError("execution exercises must be a list")
    reported = ExecutionState(session.get("execution_state", payload.get("execution_state", "unknown")))
    expected = {}
    if plan is not None and payload:
        from training_engine.completion import prescription_id
        if (payload.get("plan_id"), payload.get("plan_version")) != (plan.plan_id, plan.version):
            raise ValueError("execution does not match delivered plan")
        matching = next((item for item in plan.sessions if item.session_id == payload.get("session_id")), None)
        if matching is None:
            raise ValueError("execution does not match delivered session")
        expected = {prescription_id(plan, matching, item): item for item in matching.prescriptions}
    observations = []
    seen = set()
    observed_work = Fraction(0)
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("execution exercise must be an object")
        identity = item.get("prescription_id")
        prescription = expected.get(identity)
        if expected:
            if prescription is None or identity in seen:
                raise ValueError("unknown or duplicate execution prescription")
            if (item.get("exercise_id"), item.get("exercise_version")) != (
                    prescription.exercise_id, prescription.exercise_version):
                raise ValueError("execution exercise identity mismatch")
            seen.add(identity)
        sets = _count(item.get("completed_sets"))
        reps = _count(item.get("actual_repetitions"))
        state = ExecutionState(item.get("execution_state", "unknown"))
        if prescription and sets is not None and sets > prescription.sets:
            raise ValueError("observed sets exceed prescription")
        if state is ExecutionState.SKIPPED:
            if sets not in (None, 0) or reps not in (None, 0):
                raise ValueError("skipped work cannot contain completed work")
            sets = 0
        elif sets == 0:
            if reps not in (None, 0):
                raise ValueError("repetitions without an observed set")
            state = ExecutionState.SKIPPED
        elif sets is not None and sets > 0:
            if state is not ExecutionState.ABANDONED:
                if prescription and sets < prescription.sets:
                    state = ExecutionState.PARTIAL
                elif reps is None or prescription is None:
                    state = ExecutionState.UNKNOWN
                else:
                    state = (ExecutionState.COMPLETED if reps >= prescription.rep_min
                             else ExecutionState.PARTIAL)
        elif state not in (ExecutionState.ABANDONED, ExecutionState.PARTIAL):
            state = ExecutionState.UNKNOWN
        if prescription and sets is not None and reps is not None:
            observed_work += sets * min(Fraction(reps, prescription.rep_min), 1)
        observations.append({
            **{key: item[key] for key in ("prescription_id", "exercise_id", "exercise_version", "name") if key in item},
            "completed_sets": sets, "completed_repetitions": reps,
            "actual_repetitions": reps, "execution_state": state.value,
            **{key: item.get(key) for key in ("completed_load", "completed_rpe", "completed_rir", "completed_effort")},
        })
    # Missing prescribed exercises are unknown, not implicitly completed.
    missing = bool(expected and seen != set(expected))
    states = {item["execution_state"] for item in observations}
    if reported is ExecutionState.ABANDONED:
        state = reported
    elif missing or not observations:
        state = ExecutionState.PARTIAL if observed_work else ExecutionState.UNKNOWN
    elif states == {"completed"}:
        state = ExecutionState.COMPLETED
    elif states == {"skipped"}:
        state = ExecutionState.SKIPPED
    elif "partial" in states or observed_work or (
            "skipped" in states and any((item["completed_sets"] or 0) > 0 for item in observations)):
        state = ExecutionState.PARTIAL
    else:
        state = ExecutionState.UNKNOWN
    denominator = sum(item.sets for item in expected.values())
    percentage = int(observed_work * 100 / denominator) if denominator else None
    if reported is ExecutionState.PARTIAL and state is ExecutionState.COMPLETED:
        raise ValueError("partial execution contradicts fully completed observations")
    if reported is ExecutionState.PARTIAL and state is ExecutionState.UNKNOWN:
        state = ExecutionState.PARTIAL
    if state is ExecutionState.UNKNOWN and not observed_work:
        percentage = None
    result.update(execution_schema="workout-execution-v1", execution_state=state.value,
                  completion=percentage, exercises=observations)
    if payload:
        result["workout_completion"] = {**payload, "execution_state": state.value,
                                         "exercises": observations}
    return result


def lifecycle_evidence(payload, plan):
    normalized = normalize_execution({}, payload, plan=plan)
    if normalized["execution_state"] != ExecutionState.COMPLETED.value:
        return None
    return normalized["workout_completion"]
