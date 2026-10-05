"""Read-only Progress projection; persisted direction is never reclassified."""
from collections import defaultdict
from uuid import UUID

from my_training import _plan, _timestamp, completed_adjustments, last_completed
from training_engine.registry import load_exercise_library
from training_engine.training_trajectory import CLASSIFIER_VERSION, MINIMUM_COMPARABLE_OBSERVATIONS


def progress_projection(owner, plans, sessions, completions, facts, events, trajectories):
    plans_by_id = {row["id"]: row for row in plans if row["user_id"] == owner}
    sessions_by_id = {row["id"]: row for row in sessions}
    facts_by_completion = defaultdict(list)
    for row in facts:
        facts_by_completion[row["completion_id"]].append(row["fact"])
    verified = {}
    for row in completions:
        plan = plans_by_id.get(row["delivered_plan_id"])
        session = sessions_by_id.get(row["delivered_session_id"])
        if row["user_id"] != owner or not plan or not session or session["delivered_plan_id"] != plan["id"]:
            continue
        observed = facts_by_completion[row["id"]]
        result = last_completed(row, plan, session, observed)
        if result is not None:
            verified[row["id"]] = (row, plan, session, observed, result)
    recent_sessions = []
    for _, _, _, _, result in list(verified.values())[:5]:
        recent_sessions.append({"completed_at": result["completed_at"], "exercises": [
            {key: item[key] for key in ("exercise_id", "exercise_version", "display_name", "completed_sets",
                                      "prescription_type", "completed_repetitions", "completed_duration_seconds",
                                      "completed_load")} for item in result["exercises"]]})

    def project_event(event):
        source = verified.get(event["completion_id"])
        if not source:
            return None
        row, plan, session, observed, _ = source
        projected = completed_adjustments(row, plan, session, observed, [event])
        if not projected:
            return None
        try:
            return {**projected[0], "occurred_at": _timestamp(event["event_at"])}
        except ValueError:
            return None

    events_by_id = {row["id"]: row for row in events if row["user_id"] == owner}
    event_projections = {identifier: project_event(row) for identifier, row in events_by_id.items()}
    recent_adjustments = [value for value in event_projections.values() if value is not None][:5]
    directions = []
    # Choose by delivered plan order BEFORE validating individual trajectories.
    # Invalid/new insufficient rows must never promote an older progressing plan.
    chosen = next((plan for plan in plans if plan["user_id"] == owner and any(
        row["user_id"] == owner and row["delivered_plan_id"] == plan["id"] for row in trajectories)), None)
    if chosen:
        for row in trajectories:
            if row["user_id"] != owner or row["delivered_plan_id"] != chosen["id"]:
                continue
            try:
                state = row["trajectory_state"]
                if row["classifier_version"] != CLASSIFIER_VERSION or state not in (
                        "progressing", "stable", "insufficient_evidence"):
                    continue
                completion_ids, event_ids = row["completion_ids"], row["progression_event_ids"]
                if not isinstance(completion_ids, list) or not isinstance(event_ids, list):
                    continue
                completion_ids = [UUID(str(value)) for value in completion_ids]
                event_ids = [UUID(str(value)) for value in event_ids]
                if (not completion_ids or len(completion_ids) != len(event_ids) or
                        len(set(completion_ids)) != len(completion_ids) or len(set(event_ids)) != len(event_ids)):
                    continue
                # This checks the existing evidence floor, not a new direction decision.
                if state != "insufficient_evidence" and len(completion_ids) < MINIMUM_COMPARABLE_OBSERVATIONS:
                    continue
                identity = (row["exercise_id"], row["exercise_version"])
                for completion_id, event_id in zip(completion_ids, event_ids, strict=True):
                    source, event = verified.get(completion_id), events_by_id.get(event_id)
                    if (source is None or event is None or not event_projections.get(event_id) or
                            source[1]["id"] != chosen["id"] or event["completion_id"] != completion_id or
                            (event["exercise_id"], event["exercise_version"]) != identity):
                        raise ValueError("inconsistent persisted trajectory source")
                exercise = load_exercise_library(_plan(chosen).exercise_library_version).require(*identity)
                directions.append({"exercise_id": exercise.exercise_id, "exercise_version": exercise.version,
                                   "display_name": exercise.display_name, "state": state})
            except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
                continue
    return {"record": {"completed_sessions": len(verified), "recent_sessions": recent_sessions},
            "exercise_trajectories": directions, "recent_adjustments": recent_adjustments}
