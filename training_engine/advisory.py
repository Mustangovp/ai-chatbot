"""Bounded advisory inputs for deterministic training selection.

Persona and expert systems may express a preference only through this fixed
mapping. They never supply exercise identities directly, and the registry
filters every mapped identity before it reaches selection.
"""
from __future__ import annotations

from dataclasses import dataclass

from .registry import ExerciseLibrary, load_exercise_library


_PERSONA_PREFERENCES = {
    "strength": ("dumbbell.row",),
    "mentions_motivation": (
        "bodyweight.wall_push_up", "bodyweight.table_row", "bodyweight.squat",
        "bodyweight.hip_hinge", "bodyweight.plank",
    ),
    "mentions_sleep": (
        "bodyweight.wall_push_up", "bodyweight.table_row", "bodyweight.squat",
        "bodyweight.hip_hinge", "bodyweight.plank",
    ),
    "mentions_stress": (
        "bodyweight.wall_push_up", "bodyweight.table_row", "bodyweight.squat",
        "bodyweight.hip_hinge", "bodyweight.plank",
    ),
}
_EXPERT_PREFERENCES = {
    "CLR-002": ("bodyweight.wall_push_up",),
    "GRV-001": ("bodyweight.table_row",),
    "GRV-003": ("bodyweight.wall_push_up",),
    "WNK-003": ("bodyweight.wall_push_up",),
}


@dataclass(frozen=True)
class TrainingAdvisorySignals:
    """Registry-validated preferences that only break deterministic rank ties."""

    preferred_exercise_ids: tuple[str, ...] = ()


def persona_expert_training_signals(*, persona_match=None, expert_consensus=None,
                                    library: ExerciseLibrary | None = None) -> TrainingAdvisorySignals:
    """Return fixed, registry-known preferences without exposing source IDs downstream."""
    candidates = []
    if persona_match is not None and not getattr(persona_match, "abstained", True):
        tags = tuple(getattr(persona_match, "matched_goal_tags", ()) or ()) + tuple(
            getattr(persona_match, "matched_problem_tags", ()) or ())
        for tag in tags:
            candidates.extend(_PERSONA_PREFERENCES.get(str(tag), ()))
    if expert_consensus is not None and not getattr(expert_consensus, "abstained", True):
        for rule_id in getattr(expert_consensus, "applicable_rule_ids", ()) or ():
            candidates.extend(_EXPERT_PREFERENCES.get(str(rule_id), ()))
    registry = library or load_exercise_library()
    return TrainingAdvisorySignals(tuple(dict.fromkeys(
        exercise_id for exercise_id in candidates if registry.get(exercise_id) is not None
    )))
