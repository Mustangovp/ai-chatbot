"""Runtime sequencing and policy reconciliation for the deterministic lifecycle."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from training_engine import (
    ExercisePerformance,
    ProgressionDecisionType,
    ProgressionEngine,
    ProgressionHistory,
    ProgressionPolicy,
    ProgressionStateEngine,
    RecoverySnapshot,
    RecoveryState,
    RotationPolicy,
    WorkoutResult,
    advance_training_lifecycle,
    build_training_plan,
    load_exercise_library,
)


def _plan():
    return build_training_plan(recommendation_blueprint_id="rec-lifecycle-runtime", facts={
        "goal": "strength", "level": "intermediate", "equipment": "gym", "recoveryFeel": "fresh",
    })


def _workout(plan, index, *, pain=False):
    return WorkoutResult(
        workout_id=f"runtime-workout-{index}", plan_id=plan.plan_id, plan_version=plan.version,
        completed_at=datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(days=index * 7),
        completed=True,
        performances=tuple(ExercisePerformance(
            item.exercise_id, item.exercise_version, item.sets, item.rep_max,
            Decimal("7"), 3, Decimal("20"), True,
            pain_reported=pain and item.exercise_id == "bodyweight.push_up",
        ) for item in plan.sessions[0].prescriptions),
    )


def _recovery():
    return RecoverySnapshot(RecoveryState.NORMALLY_RECOVERED, Decimal("30"), "recovery-policy-v1")


def test_shared_policy_prevents_state_rejection_of_engine_decisions():
    plan = _plan()
    first, second = _workout(plan, 0), _workout(plan, 1)
    policy = ProgressionPolicy()

    first_decisions = ProgressionEngine.evaluate(plan, (first,), _recovery(), policy=policy)
    first_history = ProgressionHistory((first,), tuple(
        __import__("training_engine").ProgressionEvent(first.workout_id, item)
        for item in first_decisions.decisions
    ))
    first_states = ProgressionStateEngine.derive(first_history, policy=policy)

    second_decisions = ProgressionEngine.evaluate(
        plan, (first, second), _recovery(),
        progression_history=first_decisions.decisions, progress_states=first_states, policy=policy,
    )
    history = ProgressionHistory((first, second), tuple(
        __import__("training_engine").ProgressionEvent(first.workout_id, item)
        for item in first_decisions.decisions
    ) + tuple(
        __import__("training_engine").ProgressionEvent(second.workout_id, item)
        for item in second_decisions.decisions
    ))
    states = ProgressionStateEngine.derive(history, policy=policy)
    assert {item.decision_type for item in second_decisions.decisions} == {ProgressionDecisionType.INCREASE_SETS}
    assert all(state.progression_policy_version == policy.version for state in states)


def test_runtime_replays_multiple_weeks_and_preserves_revision_traceability():
    plan = _plan()
    result = advance_training_lifecycle(
        plan=plan, workouts=(_workout(plan, 0), _workout(plan, 1)), recovery=_recovery(),
    )

    revised = result.revision.revised_plan
    assert (revised.parent_plan_id, revised.parent_plan_version) == (plan.plan_id, plan.version)
    assert revised.progression_decision_ids == tuple(sorted(item.decision_id for item in result.progression.decisions))
    assert result == advance_training_lifecycle(
        plan=plan, workouts=(_workout(plan, 0), _workout(plan, 1)), recovery=_recovery(),
    )


def test_every_selectable_exercise_has_a_governed_rotation_outcome():
    library = load_exercise_library()
    for exercise in library.exercises:
        if exercise.progression.rotation_policy is RotationPolicy.SUCCESSOR:
            assert exercise.progression.next_exercise_ids
            assert all(library.require(successor).movement_pattern is exercise.movement_pattern
                       for successor in exercise.progression.next_exercise_ids)
        else:
            assert exercise.progression.rotation_policy is RotationPolicy.TERMINAL
            assert exercise.progression.next_exercise_ids == ()
