"""Deterministic exercise selection tests; no workout prescription is created."""
from __future__ import annotations

from pathlib import Path

from training_engine import (
    Difficulty,
    Equipment,
    MovementPattern,
    SelectionOutcome,
    TrainingGoal,
    TrainingGoalPolicy,
    TrainingSafetyConstraints,
    TrainingSelectionEngine,
    TrainingSelectionRequest,
    load_exercise_library,
)


def _request(*, goal=TrainingGoal.MUSCLE_GAIN, experience=Difficulty.INTERMEDIATE,
             equipment=None, priorities=("quadriceps", "chest"), safety=None, policy=None):
    return TrainingSelectionRequest(
        recommendation_blueprint_id="rec-training-selection-test",
        goal=goal,
        experience_level=experience,
        available_equipment=equipment or frozenset({
            Equipment.BODYWEIGHT, Equipment.DUMBBELL, Equipment.RESISTANCE_BAND, Equipment.BENCH,
        }),
        muscle_priorities=priorities,
        safety=safety or TrainingSafetyConstraints(),
        policy=policy,
    )


def test_selection_is_deterministic_and_preserves_versioned_traceability():
    library = load_exercise_library()
    request = _request()

    first = TrainingSelectionEngine.select(library, request)
    second = TrainingSelectionEngine.select(library, request)

    assert first == second
    assert first.outcome is SelectionOutcome.SELECTED
    assert first.blueprint is not None
    assert first.blueprint.exercise_library_version == library.version
    assert all(item.exercise_id and item.exercise_version and item.selection_reason
               for item in first.blueprint.selections)
    assert all(library.require(item.exercise_id, item.exercise_version) for item in first.blueprint.selections)


def test_selection_filters_unavailable_equipment_and_incompatible_difficulty():
    library = load_exercise_library()
    result = TrainingSelectionEngine.select(
        library,
        _request(
            experience=Difficulty.BEGINNER,
            equipment=frozenset({Equipment.BODYWEIGHT, Equipment.RESISTANCE_BAND, Equipment.BENCH}),
        ),
    )

    assert result.outcome is SelectionOutcome.SELECTED
    assert result.blueprint is not None
    selected = [library.require(item.exercise_id, item.exercise_version) for item in result.blueprint.selections]
    assert all(exercise.equipment <= {Equipment.BODYWEIGHT, Equipment.RESISTANCE_BAND, Equipment.BENCH}
               for exercise in selected)
    assert all(exercise.difficulty is Difficulty.BEGINNER for exercise in selected)
    assert "barbell.back_squat" not in {exercise.exercise_id for exercise in selected}


def test_selection_enforces_push_pull_and_lower_body_movement_balance_without_duplicates():
    result = TrainingSelectionEngine.select(load_exercise_library(), _request())

    assert result.outcome is SelectionOutcome.SELECTED
    assert result.blueprint is not None
    selections = result.blueprint.selections
    assert len({item.exercise_id for item in selections}) == len(selections)
    assert {item.movement_pattern for item in selections} == {
        MovementPattern.SQUAT, MovementPattern.HINGE,
        MovementPattern.HORIZONTAL_PUSH, MovementPattern.HORIZONTAL_PULL,
        MovementPattern.CORE_ANTI_EXTENSION,
    }


def test_selection_rejects_invalid_movement_combinations_with_explicit_reason():
    result = TrainingSelectionEngine.select(
        load_exercise_library(),
        _request(safety=TrainingSafetyConstraints(
            excluded_movement_patterns=frozenset({MovementPattern.HINGE}),
        )),
    )

    assert result.outcome is SelectionOutcome.REJECTED
    assert result.blueprint is None
    assert result.rejection_reasons == ("required_pattern_unavailable:hinge",)


def test_selection_rejects_exercise_when_its_prerequisite_is_unavailable():
    policy = TrainingGoalPolicy(
        "training-goal-policy-test", TrainingGoal.MAINTENANCE,
        (MovementPattern.VERTICAL_PULL,), False,
    )
    result = TrainingSelectionEngine.select(
        load_exercise_library(),
        _request(
            goal=TrainingGoal.MAINTENANCE,
            experience=Difficulty.ADVANCED,
            equipment=frozenset({Equipment.BODYWEIGHT, Equipment.PULLUP_BAR}),
            policy=policy,
        ),
    )

    assert result.outcome is SelectionOutcome.REJECTED
    assert result.rejection_reasons == ("required_pattern_unavailable:vertical_pull",)


def test_selection_engine_has_no_runtime_prompt_or_workout_plan_dependencies():
    source = (Path(__file__).parents[1] / "training_engine" / "selection.py").read_text(encoding="utf-8")
    for token in ("import app", "from app", "openai", "requests.", "flask", "chat.completions"):
        assert token not in source
