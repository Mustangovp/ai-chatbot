"""Training plan construction is deterministic execution prescription only."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from training_engine import (
    Difficulty,
    Equipment,
    ExercisePrescription,
    MovementPattern,
    PrescriptionRule,
    RecoveryAssumption,
    TrainingConstructionError,
    TrainingGoal,
    TrainingPlanConstructionEngine,
    TrainingSafetyConstraints,
    TrainingSelectionEngine,
    TrainingSelectionRequest,
    TrainingStructurePolicy,
    load_exercise_library,
)


def _policy(**changes):
    rules = (
        PrescriptionRule(MovementPattern.SQUAT, 3, 8, 10, Decimal("7"), 3, 90, "3-1-1-0", 4, Decimal("2")),
        PrescriptionRule(MovementPattern.HINGE, 3, 8, 10, Decimal("7"), 3, 90, "3-1-1-0", 4, Decimal("2")),
        PrescriptionRule(MovementPattern.HORIZONTAL_PUSH, 3, 8, 10, Decimal("7"), 3, 90, "3-1-1-0", 4, Decimal("2")),
        PrescriptionRule(MovementPattern.HORIZONTAL_PULL, 3, 8, 10, Decimal("7"), 3, 90, "3-1-1-0", 4, Decimal("2")),
        PrescriptionRule(MovementPattern.CORE_ANTI_EXTENSION, 2, 8, 12, Decimal("6"), 4, 60, "2-1-2-0", 3, Decimal("1")),
    )
    policy = TrainingStructurePolicy(
        version="training-structure-policy-v1",
        goal=TrainingGoal.MUSCLE_GAIN,
        experience_level=Difficulty.INTERMEDIATE,
        recovery=RecoveryAssumption.MODERATE,
        sessions_per_week=2,
        movement_order=(
            MovementPattern.SQUAT, MovementPattern.HORIZONTAL_PUSH,
            MovementPattern.HORIZONTAL_PULL, MovementPattern.HINGE,
            MovementPattern.CORE_ANTI_EXTENSION,
        ),
        prescription_rules=rules,
        max_session_duration_minutes=60,
        max_session_fatigue_units=Decimal("30"),
        max_weekly_sets_per_primary_muscle=12,
        max_push_pull_set_difference=0,
        max_lower_body_set_difference=0,
        transition_seconds=30,
    )
    return replace(policy, **changes)


def _selection():
    request = TrainingSelectionRequest(
        recommendation_blueprint_id="rec-construction-test",
        goal=TrainingGoal.MUSCLE_GAIN,
        experience_level=Difficulty.INTERMEDIATE,
        available_equipment=frozenset({
            Equipment.BODYWEIGHT, Equipment.DUMBBELL, Equipment.RESISTANCE_BAND, Equipment.BENCH,
        }),
        muscle_priorities=("quadriceps", "chest"),
        safety=TrainingSafetyConstraints(),
    )
    result = TrainingSelectionEngine.select(load_exercise_library(), request)
    assert result.blueprint is not None
    return result.blueprint


def test_construction_is_deterministic_and_does_not_change_selection():
    selection = _selection()
    library = load_exercise_library()
    policy = _policy()

    first = TrainingPlanConstructionEngine.construct(selection, library, policy)
    second = TrainingPlanConstructionEngine.construct(selection, library, policy)

    assert first == second
    assert selection == _selection()
    assert len(first.sessions) == 2
    assert tuple(item.movement_pattern for item in first.sessions[0].prescriptions) == policy.movement_order


def test_construction_preserves_exercise_and_policy_traceability():
    selection = _selection()
    plan = TrainingPlanConstructionEngine.construct(selection, load_exercise_library(), _policy())

    assert plan.selection_blueprint_id == selection.blueprint_id
    for prescription in plan.sessions[0].prescriptions:
        selected = next(item for item in selection.selections if item.exercise_id == prescription.exercise_id)
        assert (prescription.exercise_version, prescription.movement_pattern) == (
            selected.exercise_version, selected.movement_pattern)
        assert prescription.selection_policy_version == selection.policy_version
        assert prescription.prescription_policy_version == "training-structure-policy-v1"
        assert prescription.construction_policy_version == "training-structure-policy-v1"
    assert all(item.weekly_sets <= 12 for item in plan.weekly_volume)


def test_construction_enforces_weekly_volume_duration_and_fatigue_limits():
    selection = _selection()
    library = load_exercise_library()
    with pytest.raises(TrainingConstructionError, match="weekly volume limit"):
        TrainingPlanConstructionEngine.construct(selection, library, _policy(max_weekly_sets_per_primary_muscle=5))
    with pytest.raises(TrainingConstructionError, match="session duration limit"):
        TrainingPlanConstructionEngine.construct(selection, library, _policy(max_session_duration_minutes=10))
    with pytest.raises(TrainingConstructionError, match="session fatigue limit"):
        TrainingPlanConstructionEngine.construct(selection, library, _policy(max_session_fatigue_units=Decimal("10")))


def test_prescription_model_and_construction_reject_invalid_policy_or_balance():
    with pytest.raises(ValueError, match="tempo"):
        ExercisePrescription("bodyweight.squat", "1.0.0", MovementPattern.SQUAT,
                             3, 8, 10, Decimal("7"), 3, 90, "fast", "s1", "p1", "p1")
    selection = _selection()
    library = load_exercise_library()
    unbalanced_rules = tuple(
        replace(rule, sets=2) if rule.movement_pattern is MovementPattern.HORIZONTAL_PULL else rule
        for rule in _policy().prescription_rules
    )
    with pytest.raises(TrainingConstructionError, match="push pull balance"):
        TrainingPlanConstructionEngine.construct(selection, library, _policy(prescription_rules=unbalanced_rules))
    with pytest.raises(TrainingConstructionError, match="does not match"):
        TrainingPlanConstructionEngine.construct(
            selection, library, _policy(experience_level=Difficulty.BEGINNER))


def test_construction_has_no_runtime_prompt_renderer_or_selection_side_effects():
    source = (Path(__file__).parents[1] / "training_engine" / "construction.py").read_text(encoding="utf-8")
    for token in ("import app", "from app", "openai", "requests.", "flask", "chat.completions"):
        assert token not in source
