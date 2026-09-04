"""Closed redaction boundary for Individual Model coaching context."""
from __future__ import annotations

from dataclasses import dataclass
import math

from individual_model_snapshot import IndividualModelSnapshotV1

_GOALS = frozenset({"strength", "hypertrophy", "fat_loss", "endurance", "general"})
_LEVELS = frozenset({"beginner", "intermediate", "advanced"})
_EQUIPMENT = frozenset({"home", "gym", "bodyweight", "dumbbell", "barbell", "cable", "mixed"})
_CONSTRAINTS = frozenset({"vertical_push", "horizontal_push", "vertical_pull", "squat", "lunge", "hinge"})
_NUTRITION_TARGETS = frozenset({"calories", "protein_g", "carbs_g", "fat_g"})

@dataclass(frozen=True)
class IndividualModelCoachingProjectionV1:
    goal_context: str | None; experience_context: str | None; equipment_context: str | None
    active_training_constraint_context: tuple[str, ...]; completed_recent_authoritative_session: bool
    trajectory_context: str | None; nutrition_target_context: tuple[tuple[str, int | float], ...]


def validate_projection(
        projection: IndividualModelCoachingProjectionV1,
) -> IndividualModelCoachingProjectionV1:
    """Reject any projection that escapes the approved closed schema."""
    if not isinstance(projection, IndividualModelCoachingProjectionV1):
        raise ValueError("invalid individual model projection")
    if projection.goal_context is not None and projection.goal_context not in _GOALS:
        raise ValueError("invalid goal context")
    if projection.experience_context is not None and projection.experience_context not in _LEVELS:
        raise ValueError("invalid experience context")
    if projection.equipment_context is not None and projection.equipment_context not in _EQUIPMENT:
        raise ValueError("invalid equipment context")
    if (not isinstance(projection.active_training_constraint_context, tuple)
            or any(value not in _CONSTRAINTS
                   for value in projection.active_training_constraint_context)):
        raise ValueError("invalid training constraint context")
    if type(projection.completed_recent_authoritative_session) is not bool:
        raise ValueError("invalid recent completion context")
    if projection.trajectory_context not in (None, "progressing", "stable"):
        raise ValueError("invalid trajectory context")
    if not isinstance(projection.nutrition_target_context, tuple):
        raise ValueError("invalid nutrition target context")
    for item in projection.nutrition_target_context:
        if (not isinstance(item, tuple) or len(item) != 2
                or item[0] not in _NUTRITION_TARGETS
                or not isinstance(item[1], (int, float))
                or isinstance(item[1], bool)
                or not math.isfinite(item[1])):
            raise ValueError("invalid nutrition target context")
    return projection

def build_projection(snapshot: IndividualModelSnapshotV1) -> IndividualModelCoachingProjectionV1:
    if not isinstance(snapshot, IndividualModelSnapshotV1): raise ValueError("invalid individual model snapshot")
    profile = snapshot.profile; level = profile.get("level") or profile.get("experience_level")
    states = {item.get("trajectory_state") for item in snapshot.trajectory}
    targets = (snapshot.nutrition or {}).get("targets")
    nutrition = tuple(sorted((key, value) for key, value in targets.items() if key in _NUTRITION_TARGETS
                             and isinstance(value, (int, float)) and not isinstance(value, bool))) if isinstance(targets, dict) else ()
    return validate_projection(IndividualModelCoachingProjectionV1(
        profile.get("goal") if profile.get("goal") in _GOALS else None,
        level if level in _LEVELS else None, profile.get("equipment") if profile.get("equipment") in _EQUIPMENT else None,
        tuple(item["pattern"] for item in snapshot.constraints if item.get("pattern") in _CONSTRAINTS),
        bool(snapshot.training and snapshot.training.get("latest_completion_id")),
        "progressing" if "progressing" in states else "stable" if "stable" in states else None, nutrition))

def render_prompt(projection: IndividualModelCoachingProjectionV1) -> str:
    projection = validate_projection(projection)
    fields = [f"{key}={value}" for key, value in (("goal", projection.goal_context), ("experience", projection.experience_context),
              ("equipment", projection.equipment_context), ("trajectory", projection.trajectory_context)) if value]
    if projection.active_training_constraint_context: fields.append("active movement exclusions=" + ",".join(projection.active_training_constraint_context))
    if projection.completed_recent_authoritative_session: fields.append("recent authoritative session completed=true")
    if projection.nutrition_target_context: fields.append("authoritative nutrition targets=" + ",".join(f"{key}:{value}" for key, value in projection.nutrition_target_context))
    return "" if not fields else "[REDACTED INDIVIDUAL MODEL CONTEXT] " + "; ".join(fields) + ". Context only: do not alter deterministic plans, progression, restrictions, safety, or nutrition authority."
