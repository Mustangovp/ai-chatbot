"""Deterministic Progression Engine V1 foundation tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from dataclasses import replace

import pytest

from training_engine import (
    ExercisePerformance,
    ProgressionDecisionType,
    ProgressionEngine,
    RecoverySnapshot,
    RecoveryState,
    WorkoutResult,
    build_training_plan,
)


_FACTS = {
    "goal": "strength", "level": "intermediate", "equipment": "gym", "recoveryFeel": "fresh",
}


def _plan():
    return build_training_plan(recommendation_blueprint_id="rec-progression", facts=_FACTS)


def _result(plan, *, days=0, reps=12, rpe="7", rir=3, load="20", completed=True, pain=False):
    performances = tuple(ExercisePerformance(
        exercise_id=item.exercise_id,
        exercise_version=item.exercise_version,
        completed_sets=item.sets if completed else 0,
        completed_repetitions=reps if completed else 0,
        achieved_rpe=Decimal(rpe), achieved_rir=rir,
        load_kg=Decimal(load) if load is not None else None,
        completed=completed, pain_reported=pain,
    ) for item in plan.sessions[0].prescriptions)
    return WorkoutResult(
        workout_id=f"workout-{days}", plan_id=plan.plan_id, plan_version=plan.version,
        completed_at=datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(days=days),
        completed=completed, performances=performances,
    )


def _recovery(state=RecoveryState.NORMALLY_RECOVERED, fatigue="30"):
    return RecoverySnapshot(state, Decimal(fatigue), "recovery-policy-v1")


def test_progression_is_deterministic_and_traceable_for_identical_evidence():
    plan = _plan()
    first = ProgressionEngine.evaluate(plan, (_result(plan),), _recovery())
    second = ProgressionEngine.evaluate(plan, (_result(plan),), _recovery())

    assert first == second
    assert {item.decision_type for item in first.decisions} == {ProgressionDecisionType.INCREASE_LOAD}
    assert all(item.exercise_id and item.exercise_version and item.policy_version == "progression-policy-v2"
               and item.training_plan_version == plan.version for item in first.decisions)


def test_progression_uses_repetitions_before_load_when_the_range_is_not_complete():
    plan = _plan()
    blueprint = ProgressionEngine.evaluate(plan, (_result(plan, reps=8),), _recovery())

    assert {item.decision_type for item in blueprint.decisions} == {ProgressionDecisionType.INCREASE_REPETITIONS}
    assert {item.repetition_delta for item in blueprint.decisions} == {1}


def test_progression_maintains_when_the_parent_workout_is_incomplete_even_if_a_performance_exists():
    plan = _plan()
    incomplete = replace(_result(plan), completed=False)
    blueprint = ProgressionEngine.evaluate(plan, (incomplete,), _recovery())

    assert {item.decision_type for item in blueprint.decisions} == {ProgressionDecisionType.MAINTAIN}
    assert {item.reason for item in blueprint.decisions} == {"workout_incomplete"}


def test_progression_increases_sets_only_after_the_recorded_load_step_or_for_bodyweight_work():
    plan = _plan()
    load_step = ProgressionEngine.evaluate(plan, (_result(plan),), _recovery())
    progressed = ProgressionEngine.evaluate(
        plan, (_result(plan, days=1),), _recovery(), progression_history=load_step.decisions)
    bodyweight = ProgressionEngine.evaluate(plan, (_result(plan, load=None),), _recovery())

    assert {item.decision_type for item in progressed.decisions} == {ProgressionDecisionType.INCREASE_SETS}
    assert {item.set_delta for item in progressed.decisions} == {1}
    assert {item.decision_type for item in bodyweight.decisions} == {ProgressionDecisionType.INCREASE_SETS}


@pytest.mark.parametrize(("state", "fatigue", "expected"), (
    (RecoveryState.FULLY_RECOVERED, "10", ProgressionDecisionType.INCREASE_LOAD),
    (RecoveryState.NORMALLY_RECOVERED, "30", ProgressionDecisionType.INCREASE_LOAD),
    (RecoveryState.FATIGUED, "50", ProgressionDecisionType.MAINTAIN),
    (RecoveryState.OVERREACHED, "80", ProgressionDecisionType.DELOAD),
))
def test_recovery_state_deterministically_gates_progression(state, fatigue, expected):
    plan = _plan()
    blueprint = ProgressionEngine.evaluate(plan, (_result(plan),), _recovery(state, fatigue))

    assert {item.decision_type for item in blueprint.decisions} == {expected}


def test_progression_replaces_an_exercise_only_when_history_reports_pain_and_a_regression_exists():
    plan = _plan()
    blueprint = ProgressionEngine.evaluate(plan, (_result(plan, pain=True),), _recovery())
    push_up = next(item for item in blueprint.decisions if item.exercise_id == "bodyweight.push_up")

    assert push_up.decision_type is ProgressionDecisionType.REPLACE_EXERCISE
    assert (push_up.replacement_exercise_id, push_up.replacement_exercise_version) == (
        "bodyweight.incline_push_up", "1.0.0")


def test_progression_rejects_missing_or_inconsistent_history_before_deciding():
    plan = _plan()
    with pytest.raises(ValueError, match="requires workout history"):
        ProgressionEngine.evaluate(plan, (), _recovery())
    invalid = WorkoutResult(
        workout_id="invalid", plan_id="other-plan", plan_version=plan.version,
        completed_at=datetime(2026, 7, 1, tzinfo=timezone.utc), completed=True,
        performances=_result(plan).performances,
    )
    with pytest.raises(ValueError, match="does not belong"):
        ProgressionEngine.evaluate(plan, (invalid,), _recovery())
    invalid_exercise = ExercisePerformance(
        "missing.exercise", "1.0.0", 1, 8, Decimal("7"), 3, Decimal("20"), True)
    invalid_reference = WorkoutResult(
        "invalid-reference", plan.plan_id, plan.version,
        datetime(2026, 7, 1, tzinfo=timezone.utc), True, (invalid_exercise,))
    with pytest.raises(ValueError, match="invalid exercise"):
        ProgressionEngine.evaluate(plan, (invalid_reference,), _recovery())


def test_progression_rejects_impossible_load_jumps_and_duplicate_decisions():
    plan = _plan()
    with pytest.raises(ValueError, match="impossible progression jump"):
        ProgressionEngine.evaluate(plan, (_result(plan, days=0, load="10"), _result(plan, days=1, load="40")), _recovery())
    blueprint = ProgressionEngine.evaluate(plan, (_result(plan),), _recovery())
    duplicate = blueprint.decisions + (blueprint.decisions[0],)
    with pytest.raises(ValueError, match="duplicate exercise decisions"):
        type(blueprint)(blueprint.blueprint_id, blueprint.version, blueprint.training_plan_id,
                        blueprint.training_plan_version, blueprint.progression_policy_version,
                        blueprint.recovery, duplicate)
