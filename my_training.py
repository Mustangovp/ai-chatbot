"""Read-only, bounded projections of persisted training facts."""
from datetime import datetime, timezone
from decimal import Decimal

from training_engine.completion import workout_completion_from_payload
from training_engine.lineage import plan_from_delivered_lineage
from training_engine.registry import load_exercise_library
from training_engine.renderer import render_completion_projection
from training_engine.progression import ProgressionDecision, ProgressionDecisionType
from workout_execution import lifecycle_evidence


# Public explanation codes only; historical/free-form policy text stays private.
_ADJUSTMENT_REASON_CODES = frozenset({
    "recovery_overreached", "progression_cycle_complete", "insufficient_exercise_history",
    "pain_reported", "pain_reported_without_regression", "recovery_fatigued",
    "workout_incomplete", "effort_not_ready_for_progression", "effort_productive",
    "effort_not_recorded", "performance_dose_type_mismatch", "duration_range_not_reached",
    "repetition_range_not_reached", "load_progression_not_eligible", "repetition_ceiling_reached",
    "set_progression_stage_exhausted", "load_progression_already_applied", "progression_ceiling_reached",
})


def _timestamp(value):
    if not isinstance(value, datetime):
        raise ValueError("missing persisted timestamp")
    # SQLite returns the UTC database timestamp without timezone information.
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


def _plan(row):
    plan = plan_from_delivered_lineage(row["lineage"])
    if (plan.plan_id, plan.version) != (row["plan_id"], row["plan_version"]):
        raise ValueError("lineage identity mismatch")
    return plan


def latest_workout(row, session, prescriptions):
    """Only session zero is supported by the existing delivery renderer.

    Matching normalized persistence is required; lineage membership alone does
    not make any later session a delivered or executable workout.
    """
    if not row or not session:
        return None
    try:
        plan = _plan(row)
        first = plan.sessions[0]
        if (session["session_id"], session["session_index"], session["estimated_duration_minutes"]) != (
                first.session_id, first.session_index, first.estimated_duration_minutes):
            return None
        recorded = {item["prescription_id"]: item for item in prescriptions}
        lineage = row["lineage"]["sessions"][0]["prescriptions"]
        if len(recorded) != len(lineage) or any(
                item["prescription_id"] not in recorded or
                recorded[item["prescription_id"]]["prescription"] != item or
                (recorded[item["prescription_id"]]["exercise_id"],
                 recorded[item["prescription_id"]]["exercise_version"]) !=
                (item["exercise_id"], item["exercise_version"]) for item in lineage):
            return None
        library = load_exercise_library(plan.exercise_library_version)
        delivered = render_completion_projection(plan, library)["sessions"][0]
        if delivered["session_id"] != first.session_id:
            return None
        exercises = []
        for metadata, prescription in zip(delivered["exercises"], first.prescriptions, strict=True):
            exercises.append({
                **{key: metadata[key] for key in (
                    "exercise_id", "exercise_version", "display_name", "difficulty",
                    "prescription_type", "rep_min", "rep_max", "duration_min_seconds",
                    "duration_max_seconds", "rest_seconds")},
                "sets": prescription.sets,
                "rpe": float(prescription.target_rpe), "rir": prescription.target_rir,
                "tempo": prescription.tempo,
            })
        return {"delivered_at": _timestamp(row["delivered_at"]),
                "estimated_duration_minutes": first.estimated_duration_minutes,
                "exercises": exercises}
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError):
        return None


def last_completed(row, plan_row, session, facts):
    """Observed normalized completion, never prescribed work or an ID-only claim."""
    if not row or not plan_row or not session or row["completion_percent"] != 100:
        return None
    try:
        plan = _plan(plan_row)
        payload = {
            "workout_id": row["workout_id"], "plan_id": plan.plan_id,
            "plan_version": plan.version, "session_id": session["session_id"],
            "completion_timestamp": _timestamp(row["completed_at"]),
            "exercises": [{**item, "actual_repetitions": item["completed_repetitions"],
                           **({"actual_duration_seconds": item["completed_duration_seconds"]}
                              if item.get("prescription_type") == "duration" else {})}
                          for item in facts],
        }
        # Reuse the existing identity and observed-execution truth contracts.
        workout_completion_from_payload(payload, plan=plan)
        if lifecycle_evidence(payload, plan) is None:
            return None
        library = load_exercise_library(plan.exercise_library_version)
        exercises = []
        for item in facts:
            exercise = library.require(item["exercise_id"], item["exercise_version"])
            kind = item.get("prescription_type", "repetitions")
            exercises.append({
                "exercise_id": exercise.exercise_id, "exercise_version": exercise.version,
                "display_name": exercise.display_name, "completed_sets": item["completed_sets"],
                "prescription_type": kind,
                "completed_repetitions": item["completed_repetitions"],
                "completed_duration_seconds": item.get("completed_duration_seconds"),
                "completed_load": item.get("completed_load"),
                "completed_effort": item.get("completed_effort"),
                "completed_rpe": item.get("completed_rpe"),
                "completed_rir": item.get("completed_rir"),
            })
        return {"completed_at": payload["completion_timestamp"],
                "completion_percent": row["completion_percent"], "exercises": exercises}
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError):
        return None


def completed_adjustments(row, plan_row, session, facts, events):
    """Project persisted events only. No progression/recovery inference on reads."""
    try:
        plan = _plan(plan_row)
        if (row["delivered_plan_id"], row["delivered_session_id"], row["user_id"]) != (
                plan_row["id"], session["id"], plan_row["user_id"]):
            return []
        expected = {item["prescription_id"]: item for item in facts}
        library = load_exercise_library(plan.exercise_library_version)
        replacement_library = load_exercise_library("1.4.0")
        result, seen = [], set()
        for event in events:
            if (event["user_id"], event["completion_id"], event["delivered_plan_id"],
                    event["delivered_session_id"]) != (
                    row["user_id"], row["id"], plan_row["id"], session["id"]):
                return []
            fact = expected.get(event["prescription_id"])
            if not fact or event["prescription_id"] in seen or (
                    event["exercise_id"], event["exercise_version"]) != (
                    fact["exercise_id"], fact["exercise_version"]):
                return []
            raw = event["decision"]
            kind = ProgressionDecisionType(raw["decision_type"])
            decision = ProgressionDecision(
                decision_id=raw["decision_id"], decision_type=kind, reason=raw["reason"],
                policy_version=raw["policy_version"], exercise_id=event["exercise_id"],
                exercise_version=event["exercise_version"], training_plan_version=plan.version,
                load_delta_kg=None if raw.get("load_delta_kg") is None else Decimal(str(raw["load_delta_kg"])),
                repetition_delta=raw.get("repetition_delta"), set_delta=raw.get("set_delta"),
                replacement_exercise_id=raw.get("replacement_exercise_id"),
                replacement_exercise_version=raw.get("replacement_exercise_version"),
            )
            exercise = library.require(decision.exercise_id, decision.exercise_version)
            item = {"exercise_id": exercise.exercise_id, "exercise_version": exercise.version,
                    "display_name": exercise.display_name, "decision_type": kind.value}
            if decision.reason in _ADJUSTMENT_REASON_CODES:
                item["reason_code"] = decision.reason
            if kind is ProgressionDecisionType.INCREASE_LOAD:
                if not decision.load_delta_kg.is_finite():
                    return []
                item["load_delta_kg"] = str(decision.load_delta_kg)
            elif kind in (ProgressionDecisionType.INCREASE_REPETITIONS, ProgressionDecisionType.INCREASE_SETS):
                key = "repetition_delta" if kind is ProgressionDecisionType.INCREASE_REPETITIONS else "set_delta"
                if type(raw[key]) is not int:
                    return []
                item[key] = raw[key]
            elif kind is ProgressionDecisionType.REPLACE_EXERCISE:
                replacement = replacement_library.require(decision.replacement_exercise_id,
                                                           decision.replacement_exercise_version)
                item["replacement"] = {"exercise_id": replacement.exercise_id,
                                       "exercise_version": replacement.version,
                                       "display_name": replacement.display_name}
            seen.add(event["prescription_id"])
            result.append(item)
        return result
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError):
        return []
