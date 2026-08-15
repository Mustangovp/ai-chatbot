"""Bounded, deterministic rationale for an already validated training plan."""
from __future__ import annotations

from typing import Mapping

from .construction import TrainingPlanBlueprintV2
from .models import MovementPattern


RATIONALE_VERSION = "training-rationale-v1"

_GOALS = frozenset({"strength", "muscle_gain", "fat_loss", "maintenance", "general_fitness"})
_LEVELS = frozenset({"beginner", "intermediate", "advanced"})
_DIRECTIONS = frozenset({"increased", "decreased"})
_REASONS = frozenset({
    "goal_and_capacity",
    "progressed_from_previous_workout",
    "progressed_within_constraints",
    "protective_recovery",
    "cross_session_progressed",
    "cross_session_progressed_with_constraints",
    "longitudinal_split_sequence",
    "longitudinal_exercise_rotation",
})
_USED_KINDS = frozenset({
    "active_constraint", "recent_workout", "protective_recovery",
    "training_goal", "experience_capacity",
    "comparable_session",
    "recent_training_exposure",
})
_CHANGED_KINDS = frozenset({
    "excluded_movement", "difficulty_adjustment", "protective_volume",
    "goal_structure", "capacity_prescription",
    "cross_session_progression",
    "split_sequence", "exercise_rotation",
})
_CROSS_SESSION_CHANGES = frozenset({
    "load", "repetitions", "sets", "eligible_alternative", "conservative", "mixed",
})


def _value(value: object) -> str:
    return str(value or "").strip().lower()


def _item(kind: str, value: str) -> dict[str, str]:
    return {"kind": kind, "value": value}


def _valid_item(item: object, *, used: bool) -> bool:
    if not isinstance(item, dict) or set(item) != {"kind", "value"}:
        return False
    kind, value = item.get("kind"), item.get("value")
    if not isinstance(kind, str) or not isinstance(value, str):
        return False
    if kind not in (_USED_KINDS if used else _CHANGED_KINDS):
        return False
    if kind in {"active_constraint", "excluded_movement"}:
        return value in {pattern.value for pattern in MovementPattern}
    if kind == "training_goal" or kind == "goal_structure":
        return value in _GOALS
    if kind == "experience_capacity" or kind == "capacity_prescription":
        return value in _LEVELS
    if kind == "difficulty_adjustment":
        return value in _DIRECTIONS
    if kind == "recent_workout":
        return value == "previous_session"
    if kind == "protective_recovery":
        return value == "protective"
    if kind == "protective_volume":
        return value == "conservative"
    if kind == "comparable_session":
        return value == "comfortable_completed"
    if kind == "recent_training_exposure":
        return value == "completed_session"
    if kind == "cross_session_progression":
        return value in _CROSS_SESSION_CHANGES
    if kind == "split_sequence":
        return value in {"full_body", "upper_lower", "push_pull_legs"}
    if kind == "exercise_rotation":
        return value == "safe_alternative"
    return False


def validate_recommendation_rationale(value: object) -> dict[str, object] | None:
    """Return only the closed public contract; malformed input is omitted."""
    if not isinstance(value, dict) or set(value) != {"version", "used", "changed", "reason_code"}:
        return None
    used, changed, reason = value.get("used"), value.get("changed"), value.get("reason_code")
    if (value.get("version") != RATIONALE_VERSION or not isinstance(used, list)
            or not isinstance(changed, list) or not isinstance(reason, str)
            or not (1 <= len(used) <= 2 and 1 <= len(changed) <= 2)
            or reason not in _REASONS
            or not all(_valid_item(item, used=True) for item in used)
            or not all(_valid_item(item, used=False) for item in changed)):
        return None
    return {
        "version": RATIONALE_VERSION,
        "used": [{"kind": item["kind"], "value": item["value"]} for item in used],
        "changed": [{"kind": item["kind"], "value": item["value"]} for item in changed],
        "reason_code": reason,
    }


def build_recommendation_rationale(
        plan: TrainingPlanBlueprintV2, *, facts: Mapping[str, object],
        active_constraint_patterns: frozenset[MovementPattern] = frozenset(),
        followup_direction: str | None = None, has_previous_workout: bool = False,
        protective_recovery: bool = False,
        cross_session_change: str | None = None,
        longitudinal_context: object | None = None) -> dict[str, object]:
    """Describe inputs that already affected ``plan`` without changing it."""
    if not isinstance(plan, TrainingPlanBlueprintV2):
        raise ValueError("rationale requires a validated deterministic training plan")
    used: list[dict[str, str]] = []
    changed: list[dict[str, str]] = []
    selected_patterns = {
        prescription.movement_pattern
        for session in plan.sessions for prescription in session.prescriptions
    }
    constraints = tuple(sorted(
        (pattern for pattern in active_constraint_patterns
         if isinstance(pattern, MovementPattern) and pattern not in selected_patterns),
        key=lambda pattern: pattern.value,
    ))
    if constraints:
        pattern = constraints[0].value
        used.append(_item("active_constraint", pattern))
        changed.append(_item("excluded_movement", pattern))

    direction = _value(followup_direction)
    cross_change = _value(cross_session_change)
    if cross_change in _CROSS_SESSION_CHANGES:
        used.append(_item("comparable_session", "comfortable_completed"))
        changed.append(_item("cross_session_progression", cross_change))
        reason = ("cross_session_progressed_with_constraints" if constraints
                  else "cross_session_progressed")
    elif (getattr(longitudinal_context, "has_recent_exposure", False)
          and not has_previous_workout
          and (getattr(longitudinal_context, "next_session_index", 0)
               or any(prescription.exercise_id not in getattr(longitudinal_context, "recent_exercise_ids", frozenset())
                      for session in plan.sessions for prescription in session.prescriptions))):
        used.append(_item("recent_training_exposure", "completed_session"))
        if getattr(longitudinal_context, "next_session_index", 0):
            used_split = getattr(plan.training_split, "value", "")
            changed.append(_item("split_sequence", used_split))
            reason = "longitudinal_split_sequence"
        else:
            changed.append(_item("exercise_rotation", "safe_alternative"))
            reason = "longitudinal_exercise_rotation"
    elif has_previous_workout and direction in _DIRECTIONS:
        used.append(_item("recent_workout", "previous_session"))
        changed.append(_item("difficulty_adjustment", direction))
        reason = "progressed_within_constraints" if constraints else "progressed_from_previous_workout"
    elif protective_recovery:
        used.append(_item("protective_recovery", "protective"))
        changed.append(_item("protective_volume", "conservative"))
        reason = "protective_recovery"
    else:
        goal = _value(facts.get("goal"))
        level = _value(facts.get("level") or facts.get("experience_level"))
        if goal not in _GOALS or level not in _LEVELS:
            raise ValueError("rationale requires verified planning facts")
        used.append(_item("training_goal", goal))
        changed.append(_item("goal_structure", goal))
        if len(used) < 2:
            used.append(_item("experience_capacity", level))
        if len(changed) < 2:
            changed.append(_item("capacity_prescription", level))
        reason = "goal_and_capacity"

    rationale = {
        "version": RATIONALE_VERSION,
        "used": used[:2],
        "changed": changed[:2],
        "reason_code": reason,
    }
    validated = validate_recommendation_rationale(rationale)
    if validated is None:
        raise ValueError("rationale construction produced an invalid contract")
    return validated
