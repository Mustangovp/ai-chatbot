"""Read-only, bounded projections of persisted training facts."""
from datetime import datetime, timezone

from training_engine.completion import workout_completion_from_payload
from training_engine.lineage import plan_from_delivered_lineage
from training_engine.registry import load_exercise_library
from training_engine.renderer import render_completion_projection
from workout_execution import lifecycle_evidence


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
            })
        return {"completed_at": payload["completion_timestamp"],
                "completion_percent": row["completion_percent"], "exercises": exercises}
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError):
        return None
